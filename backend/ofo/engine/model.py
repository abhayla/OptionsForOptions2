"""The one gate between an index value and every model number (REQ-072 AC-2/AC-3; ADR-061, ADR-063; W-060 round 3).

Product code never turns an index level into an IV, Greek, estimate, table value or payoff value directly. It calls
:func:`model_inputs` once, with the strategy input (whose ``spot`` is a required :class:`SpotReading`) and each
expiry's :class:`~ofo.marketdata.forward.ExpiryForward`, and gets a :class:`ModelInputs`. Every product entry point
(scenario level set and values, scenario table, payoff graph, strategy table) takes a ``ModelInputs`` and nothing else,
and the pricing calls on it below are the only product path to the engine's Black-Scholes functions.

Answer states (run-discipline B4 (d)):

- spot UNHEALTHY or UNAVAILABLE: :class:`SpotRefused` (a missing reading cannot be built: ``spot`` is required).
- spot STALE / DELAYED: computed; every output carries "stale since HH:MM IST" / "delayed, as of HH:MM IST".
- a leg's expiry has no forward: :class:`~ofo.marketdata.forward.ForwardUnavailable` (refused).
- a forward read on another spot level, spot time, valuation time, rate or day count: ``ForwardUnavailable``.
- a forward from the spot fallback (fewer than 3 strikes, ADR-061): computed with q = 0 and "estimated from spot".
- both: "stale since HH:MM IST; estimated from spot".

The engine owns q (ADR-063): S and q go to the engine; nothing here rescales an engine output.
"""
from __future__ import annotations

import dataclasses
import datetime
import types
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Mapping

from ofo.engine import black_scholes as _bs
from ofo.errors.explanations import ExplanationText, join_explanations, render_explanation
from ofo.engine import estimate as _estimate
from ofo.engine import legs as _legs
from ofo.engine.black_scholes import Greeks
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Instrument
from ofo.marketdata.forward import FALLBACK_LABEL, ExpiryForward, ForwardUnavailable, mid_price
from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST as IST  # re-exported: ofo.scenario.spot imports IST from here

_REFUSED: Final = (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE)
_TOKEN: Final = object()  # only model_inputs() can build a ModelInputs

Forwards = Mapping[datetime.date, ExpiryForward]


class SpotRefused(ValueError):
    """The index value is missing or unusable; the calculation cannot be done, never computed silently."""


def data_label(reading: SpotReading) -> ExplanationText | None:
    """"stale since HH:MM IST" / "delayed, as of HH:MM IST" for a non-live reading; None for an AVAILABLE one. A
    catalogue render (W-066): the time is a typed slot."""
    if reading.health is DataHealth.STALE:
        return render_explanation("data_label_stale", time=reading.at)
    if reading.health is DataHealth.DELAYED:
        return render_explanation("data_label_delayed", time=reading.at)
    return None


def join_labels(*labels: str | None) -> str | None:
    """The non-empty labels joined with "; ". Catalogue renders stay catalogue text (W-066): joined by
    `join_explanations`; a plain string in the mix gives a plain string (refused by a typed API field)."""
    parts = [x for x in labels if x]
    if not parts:
        return None
    if all(type(x) is ExplanationText for x in parts):
        return join_explanations(parts, "; ")
    return "; ".join(parts)


class _Gated:
    """Immutable, and not a dataclass: it cannot be constructed, copied (``dataclasses.replace``) or mutated outside
    this module's gate functions, so a hand-built or edited model with a bare level cannot exist (B8: a structural
    guarantee, not a detector)."""

    __slots__: tuple[str, ...] = ()

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(f"a {type(self).__name__} is built only by ofo.engine.model (REQ-072 AC-2)")

    @classmethod
    def _make(cls, token: object, **fields: object):  # noqa: ANN206
        if token is not _TOKEN:
            raise TypeError(f"a {cls.__name__} is built only by ofo.engine.model (REQ-072 AC-2)")
        obj = object.__new__(cls)
        for name in cls.__slots__:
            object.__setattr__(obj, name, fields[name])
        return obj

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(f'{n}={getattr(self, n)!r}' for n in self.__slots__)})"

    def key_fields(self) -> tuple[tuple[str, object], ...]:
        """Every field by name: what a shared cache key is built from (REQ-050, #519), never a hand-picked part."""
        return tuple((n, getattr(self, n)) for n in self.__slots__)


class ExpiryModel(_Gated):
    """What the engine is given for one expiry: the level S (live spot), the yield q and their provenance.
    Fields: expiry, level, dividend_yield, source ("parity" / "spot fallback"), label (data label and/or "estimated
    from spot", joined with "; "), forward, spot_at."""

    __slots__ = ("expiry", "level", "dividend_yield", "source", "label", "forward", "spot_at")


class ModelInputs(_Gated):
    """A gated strategy input: built only by :func:`model_inputs`; every product model number starts here.
    Fields: inputs, spot_level, spot_at, data_label, expiries, label (the data label, plus "estimated from spot" if
    any expiry fell back)."""

    __slots__ = ("inputs", "spot_level", "spot_at", "data_label", "expiries", "label")

    # read-only views of the strategy input, so a consumer never needs the raw input to arrange its output
    @property
    def underlying(self) -> str:
        return self.inputs.underlying

    @property
    def legs(self) -> tuple[LegInput, ...]:
        return self.inputs.legs

    @property
    def strategy(self):  # noqa: ANN201 - ofo.engine.strategy.Strategy
        return self.inputs.strategy

    @property
    def spot(self) -> SpotReading:
        return self.inputs.spot

    def expiry_model(self, expiry: datetime.date) -> ExpiryModel:
        em = self.expiries.get(expiry)
        if em is None:
            raise ForwardUnavailable(f"no forward for expiry {expiry}; refused")
        return em


def _gate_spot(reading: object, underlying: str) -> SpotReading:
    if not isinstance(reading, SpotReading):
        raise SpotRefused("no spot reading: a calculation is never built on a bare level (REQ-072 AC-2)")
    if reading.health in _REFUSED:
        raise SpotRefused(f"the {underlying} spot is {reading.health.value}; the calculation cannot be done")
    return reading


def _refuse_mismatch(expiry: datetime.date, pairs: tuple[tuple[str, object, object], ...]) -> None:
    mismatched = [name for name, mine, theirs in pairs if mine != theirs]
    if mismatched:
        raise ForwardUnavailable(f"the {expiry} forward was read with a different {', '.join(mismatched)} than the "
                                 f"spot reading or strategy input; refused")


def expiry_model(reading: SpotReading, fwd: ExpiryForward, *, underlying: str = "index") -> ExpiryModel:
    """Gate one expiry: a usable spot reading and the forward read on that same reading (level, time, health)."""
    reading = _gate_spot(reading, underlying)
    if not isinstance(fwd, ExpiryForward):
        raise ForwardUnavailable(f"an ExpiryForward is required (ADR-061), got {fwd!r}")
    _refuse_mismatch(fwd.expiry, (("spot level", fwd.spot, reading.level), ("spot time", fwd.spot_timestamp, reading.at),
                                  ("spot health", fwd.spot_health, reading.health)))
    return ExpiryModel._make(_TOKEN, expiry=fwd.expiry, level=reading.level, dividend_yield=fwd.implied_yield,
                             source=fwd.source, label=join_labels(data_label(reading), fwd.label), forward=fwd,
                             spot_at=reading.at)


def model_inputs(inputs: StrategyInput, forwards: Forwards) -> ModelInputs:
    """Gate ``inputs`` and ``forwards`` once; refuse a missing/unusable spot or a missing/mismatched forward."""
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    reading = _gate_spot(inputs.spot, inputs.underlying)
    if not isinstance(forwards, Mapping):
        raise ForwardUnavailable(f"each expiry's forward is required (ADR-061), got {forwards!r}")
    expiries: dict[datetime.date, ExpiryModel] = {}
    for leg in inputs.legs:
        if leg.expiry in expiries:
            continue
        fwd = forwards.get(leg.expiry)
        if fwd is None:
            raise ForwardUnavailable(f"no forward for expiry {leg.expiry} (leg {leg.contract}); refused")
        em = expiry_model(reading, fwd, underlying=inputs.underlying)
        _refuse_mismatch(leg.expiry, (("expiry", fwd.expiry, leg.expiry),
                                      ("valuation time", fwd.valuation_time, inputs.valuation_time),
                                      ("rate", fwd.rate, inputs.rate), ("days in year", fwd.days_in_year,
                                                                        inputs.days_in_year)))
        expiries[leg.expiry] = em
    dlabel = data_label(reading)
    fell_back = any(em.forward.label for em in expiries.values())
    built = ModelInputs._make(_TOKEN, inputs=inputs, spot_level=reading.level, spot_at=reading.at, data_label=dlabel,
                              expiries=types.MappingProxyType(dict(expiries)),
                              label=join_labels(dlabel, FALLBACK_LABEL if fell_back else None))
    return _with_basis(built)


def _with_basis(model: ModelInputs) -> ModelInputs:
    """D-08: the ONE place the answer's label (Outcome.output_label, Table.output_label read ``model.label``) gains the
    at-intrinsic basis line, when :func:`no_time_value` values any leg; else the model unchanged."""
    basis = intrinsic_basis(model)
    if basis is None:
        return model
    return ModelInputs._make(_TOKEN, **{n: getattr(model, n) for n in ModelInputs.__slots__ if n != "label"},
                             label=join_labels(model.label, basis))


def market_closed_model(model: ModelInputs) -> ModelInputs:
    """ADR-200 (2): the same gated inputs with the "stale since" data label dropped everywhere it is read (every curve,
    the payoff table, the target): the held last close sits under the one market-closed banner. The model's own
    "estimated from spot" (ADR-061) stays. Numbers are untouched; only the labels change."""
    expiries = {d: ExpiryModel._make(_TOKEN, expiry=em.expiry, level=em.level, dividend_yield=em.dividend_yield,
                                     source=em.source, label=em.forward.label, forward=em.forward, spot_at=em.spot_at)
                for d, em in model.expiries.items()}
    fell_back = any(em.forward.label for em in expiries.values())
    return _with_basis(ModelInputs._make(_TOKEN, inputs=model.inputs, spot_level=model.spot_level,
                                         spot_at=model.spot_at, data_label=None,
                                         expiries=types.MappingProxyType(expiries),
                                         label=FALLBACK_LABEL if fell_back else None))


def _require(model: object) -> ModelInputs:
    if not isinstance(model, ModelInputs):
        raise ValueError(f"a ModelInputs (ofo.engine.model.model_inputs) is required, got {model!r}")
    return model


def _require_expiry(em: object) -> ExpiryModel:
    if not isinstance(em, ExpiryModel):
        raise ValueError(f"an ExpiryModel (ofo.engine.model.expiry_model) is required, got {em!r}")
    return em


# ---- the product's only pricing calls ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelIV:
    iv: Decimal
    dividend_yield: Decimal
    spot_level: Decimal
    spot_at: datetime.datetime
    label: str | None


@dataclass(frozen=True)
class ModelGreeks:
    greeks: Greeks  # from the engine, relative to the index level
    level: Decimal  # the S the engine was given (the live spot, or a what-if level)
    dividend_yield: Decimal
    spot_level: Decimal
    spot_at: datetime.datetime
    label: str | None


def leg_greeks_unrounded(model: ModelInputs, leg: LegInput) -> Greeks:
    """Per-unit UNROUNDED engine Greeks of an option leg at the live spot with its expiry's q (ADR-063)."""
    m = _require(model)
    if leg.iv is None:
        raise ValueError(f"leg {leg.contract} has no IV")
    return greeks_unrounded(m.expiry_model(leg.expiry), leg.instrument, leg.strike, leg.iv)


def leg_decay_unrounded(model: ModelInputs, leg: LegInput, until: datetime.datetime) -> Decimal:
    """Per-unit UNROUNDED Decay of one leg to ``until`` (the next market open; GC-UI D-B34, REQ-145 AC-2, F-63): the
    model value at ``until`` minus the model value now, at the live spot with the expiry's q, the leg's IV and the
    rate, time in calendar days / ``days_in_year`` like every model figure (scenario-calculations section 4). A futures
    leg has no time value: a true 0. An expiry whose close is at or before ``until`` decays to its intrinsic value."""
    m = _require(model)
    if leg.instrument is Instrument.FUT:
        return Decimal(0)
    if leg.iv is None:
        raise ValueError(f"leg {leg.contract} has no IV")
    if not isinstance(until, datetime.datetime) or until.tzinfo is None or until <= m.inputs.valuation_time:
        raise ValueError(f"until must be a timezone-aware time after the valuation, got {until!r}")
    em = m.expiry_model(leg.expiry)
    f = em.forward
    close = datetime.datetime.combine(leg.expiry, _bs.EXPIRY_CLOSE)
    then = (_bs.year_fraction(until, leg.expiry, days_in_year=f.days_in_year) if until < close else Decimal(0))
    return _bs.bs_decay_unrounded(leg.instrument, em.level, leg.strike, f.years, then, f.rate, leg.iv,
                                  dividend_yield=em.dividend_yield)


def greeks(em: ExpiryModel, kind: Instrument, strike: Decimal, vol: Decimal, level: Decimal | None = None) -> ModelGreeks:
    """Per-unit engine Greeks (4 dp) at ``level`` (default: the live spot) with the expiry's q."""
    e = _require_expiry(em)
    f = e.forward
    s = e.level if level is None else level
    g = _bs.bs_greeks(kind, s, strike, f.years, f.rate, vol, days_in_year=f.days_in_year,
                      dividend_yield=e.dividend_yield)
    return ModelGreeks(g, s, e.dividend_yield, e.level, e.spot_at, e.label)


def greeks_unrounded(em: ExpiryModel, kind: Instrument, strike: Decimal, vol: Decimal) -> Greeks:
    """Per-unit UNROUNDED engine Greeks at the live spot with the expiry's q: for a display that must not read a real
    ~0.00001 gamma as 0.0000 (the 4 dp of :func:`greeks` is a display step), and the one per-unit Greeks of a leg
    (:func:`leg_greeks_unrounded`). Reads only the contract (kind, strike), its IV and the expiry model, never a
    strategy, so the outcome shares one result per contract across every holder (REQ-050 AC-1)."""
    e = _require_expiry(em)
    f = e.forward
    return _bs.bs_greeks_unrounded(kind, e.level, strike, f.years, f.rate, vol, days_in_year=f.days_in_year,
                                   dividend_yield=e.dividend_yield)


def greeks_at_price(kind: Instrument, spot: Decimal, strike: Decimal, expiry: datetime.date,  # noqa: PLR0913
                    clock: datetime.datetime, rate: Decimal, price: Decimal,
                    vol: Decimal | None = None) -> Greeks:
    """Per-unit engine Greeks at an explicit ``spot`` and ``clock`` (a past instant, e.g. a leg's entry), for a caller
    that holds no gated forward: vol = ``vol`` when stated, else the vol the engine solves from ``price``. The engine's
    refusals (no IV for this price, expiry passed) raise ValueError."""
    years = _bs.year_fraction(clock, expiry)
    if vol is None:
        vol = _bs.implied_volatility(kind, price, spot, strike, years, rate)
    return _bs.bs_greeks(kind, spot, strike, years, rate, vol)


def delta_at_intrinsic(kind: Instrument, strike: Decimal, spot: Decimal, ltp: Decimal, tick: Decimal) -> Decimal | None:
    """ADR-268 (1): an option price within one ``tick`` of its intrinsic value has no time value left, so its absolute
    delta is 1 in the money, 0 out of the money; a price with time value left -> None (no delta from this rule)."""
    intrinsic = max(spot - strike if kind is Instrument.CE else strike - spot, Decimal(0))
    if ltp - intrinsic > tick:
        return None
    return Decimal(1) if intrinsic > 0 else Decimal(0)


def iv_price(q: NormalizedQuote) -> Decimal | None:
    """ADR-172: THE price an implied volatility is solved from, for every caller (the outcome leg, the ATM pair, the
    leg picker's chain and the chain push): the bid-ask mid when both sides are live and the ask is at or above the
    bid, else the LTP (None when there is no LTP either: no IV). A side is live only when it is present, above 0 AND
    the quote's health is AVAILABLE (GC-UI F-5): a STALE / DELAYED / UNHEALTHY / UNAVAILABLE book stopped ticking, so
    after hours every leg solves from its closing LTP (ADR-197), never from the stale mid - the same health gate the
    parity forward's mid uses (ofo.marketdata.forward._mid)."""
    return mid_price(q.bid, q.ask) if live_book(q.bid, q.ask, q.health) else q.ltp  # type: ignore[arg-type]


def live_book(bid: Decimal | None, ask: Decimal | None, health: DataHealth | None) -> bool:
    """ADR-172: THE one live-book rule (the mid is used only on a live book): both sides present and above 0, the ask
    at or above the bid, and the quote's health AVAILABLE (None = not known = not live). ``iv_price`` and the
    adjustment approach builder's planned price (ADR-241, ``ofo.adjustment.approaches.planned_price``) both call it."""
    return (health is DataHealth.AVAILABLE and bid is not None and ask is not None and bid > 0 and ask > 0
            and ask >= bid)


def implied_vol(em: ExpiryModel, kind: Instrument, price: Decimal, strike: Decimal) -> ModelIV:
    """Implied volatility of a market price at the live spot with the expiry's q."""
    e = _require_expiry(em)
    f = e.forward
    iv = _bs.implied_volatility(kind, price, e.level, strike, f.years, f.rate, dividend_yield=e.dividend_yield)
    return ModelIV(iv, e.dividend_yield, e.level, e.spot_at, e.label)


@dataclass(frozen=True)
class Estimate:
    """Estimated Now at one what-if level S; each leg marked with its own expiry's q."""

    level: Decimal
    marks: tuple[Decimal, ...]
    leg_pnls: tuple[Decimal, ...]
    total: Decimal
    assumptions: _estimate.EstimateAssumptions
    label: str | None
    spot_level: Decimal | None = None
    spot_at: datetime.datetime | None = None


def valued_at(model: ModelInputs, at: datetime.datetime | None = None) -> datetime.datetime:
    """The time a what-if is valued at (REQ-084 AC-2): ``at``, or the model's own valuation time when None. A time
    before the valuation, or a naive time, is refused (the route clamps before it gets here)."""
    m = _require(model)
    now = m.inputs.valuation_time
    if at is None:
        return now
    if not isinstance(at, datetime.datetime) or at.tzinfo is None or at < now:
        raise ValueError(f"a what-if time must be timezone-aware and not before the valuation, got {at!r}")
    return at


def leg_close(leg: LegInput) -> datetime.datetime:
    """The leg's expiry close (15:30 IST): at or after it the leg holds no time value."""
    return datetime.datetime.combine(leg.expiry, _bs.EXPIRY_CLOSE)


def estimate(model: ModelInputs, level: Decimal, at: datetime.datetime | None = None) -> Estimate:
    """Estimated P&L if the index were at ``level`` at ``at`` (default: the valuation time, which IS Estimated Now;
    ADR-008 Q33A = C; ADR-063; REQ-084 AC-4). One code path for every time: the model's input with its valuation time
    moved to ``at`` (unchanged when ``at`` is the valuation time). A leg whose expiry close is at or before ``at`` is
    marked at its At Expiry value (the engine's expiry payoff, years 0); every other leg keeps its own remaining time,
    so a multi-expiry strategy values each leg on its own expiry. D-08: a leg with no time value left in its price
    (:func:`no_time_value`) is marked at its At Expiry value at ``level`` too, never dropped from the curve."""
    m = _require(model)
    when = valued_at(m, at)
    shifted = m.inputs if when == m.inputs.valuation_time else dataclasses.replace(m.inputs, valuation_time=when)
    marks: list[Decimal] = []
    pnls: list[Decimal] = []
    years: list[Decimal] = []
    qs: list[Decimal] = []
    sources: list[str] = []
    for leg in m.legs:
        em = m.expiry_model(leg.expiry)
        if when >= leg_close(leg) or no_time_value(m, leg):  # D-08: no time left, or none in the price (ADR-268 (1))
            mark = _legs.expiry_value(leg.leg, level)
            marks.append(mark)
            pnls.append(_legs.expiry_pnl(leg.leg, level))
            years.append(Decimal(0))
        else:
            one = _estimate.estimate_now(dataclasses.replace(shifted, legs=(leg,)), level,
                                         dividend_yield=em.dividend_yield, yield_source=em.source)
            marks.append(one.marks[0])
            pnls.append(one.leg_pnls[0])
            years.append(one.assumptions.years_to_expiry[0])
        qs.append(em.dividend_yield)
        sources.append(em.source)
    assumptions = _estimate.EstimateAssumptions(
        model=_estimate.MODEL, valuation_time=when, rate=shifted.rate, days_in_year=shifted.days_in_year,
        ivs=tuple(leg.iv for leg in m.legs), years_to_expiry=tuple(years), dividend_yields=tuple(qs),
        yield_sources=tuple(sources))
    return Estimate(level, tuple(marks), tuple(pnls), sum(pnls, Decimal(0)), assumptions, m.label, m.spot_level,
                    m.spot_at)


def leg_greeks_at_unrounded(model: ModelInputs, leg: LegInput, level: Decimal,
                            at: datetime.datetime | None = None) -> Greeks | None:
    """Per-unit UNROUNDED engine Greeks of an option leg at ``level`` and ``at`` (REQ-084 AC-4) with its expiry's q.
    None when the leg's expiry close is at or before ``at``: no time is left, so no model Greek exists (RD-081: the
    caller explains it in a sentence, never an error)."""
    m = _require(model)
    if no_time_value(m, leg):  # D-08 / ADR-268 (1): delta 1 in the money at ``level``, 0 out of it; no other Greek
        itm = level > leg.strike if leg.instrument is Instrument.CE else level < leg.strike
        delta = Decimal(0) if not itm else Decimal(1) if leg.instrument is Instrument.CE else Decimal(-1)
        return Greeks(delta, Decimal(0), Decimal(0), Decimal(0))
    if leg.iv is None:
        raise ValueError(f"leg {leg.contract} has no IV")
    when = valued_at(m, at)
    if when >= leg_close(leg):
        return None
    em = m.expiry_model(leg.expiry)
    f = em.forward
    years = _bs.year_fraction(when, leg.expiry, days_in_year=f.days_in_year)
    return _bs.bs_greeks_unrounded(leg.instrument, level, leg.strike, years, f.rate, leg.iv,
                                   days_in_year=f.days_in_year, dividend_yield=em.dividend_yield)


#: ADR-268 (1): an option price within one tick of its intrinsic value has no time value left.
INTRINSIC_TICK: Final = Decimal("0.05")


def no_time_value(model: ModelInputs, leg: LegInput) -> bool:
    """D-08 (ADR-268 (1), the nearest decision): ON THE LEG'S OWN EXPIRY DAY, before its 15:30 IST close, an option leg
    whose IV is not solvable while its price is within one tick of its intrinsic value at the live spot (either side,
    ``|ltp - intrinsic| <= 0.05``) holds no time value: the engine values it at its intrinsic value (its At Expiry
    value at the level) instead of dropping the estimate, and every figure built so says it (:func:`intrinsic_basis`).
    Any other day, a price more than a tick away from intrinsic (ADR-019: never substituted), a leg with an IV, a
    futures leg or a leg with no price: False, so the estimate stays not available (no guess)."""
    m = _require(model)
    if leg.instrument is Instrument.FUT or leg.iv is not None or leg.ltp is None or leg.strike is None:
        return False
    now = m.inputs.valuation_time
    if now.astimezone(IST).date() != leg.expiry or now >= leg_close(leg):
        return False
    spot = m.expiry_model(leg.expiry).level
    intrinsic = max(spot - leg.strike if leg.instrument is Instrument.CE else leg.strike - spot, Decimal(0))
    return abs(leg.ltp - intrinsic) <= INTRINSIC_TICK


def intrinsic_basis(model: ModelInputs) -> ExplanationText | None:
    """D-08: the basis line every estimate that valued a leg by :func:`no_time_value` carries; None when none did."""
    m = _require(model)
    return render_explanation("estimate_intrinsic_basis") if any(no_time_value(m, leg) for leg in m.legs) else None


def legs_without_estimate(model: ModelInputs) -> list[str]:
    """The option legs an estimate cannot value (no IV and time value left in the price): the one list every
    "Estimate not available" reason reads (the scenario view, the what-if)."""
    m = _require(model)
    return [leg.contract for leg in m.legs if leg.leg.is_option and leg.iv is None and not no_time_value(m, leg)]


def expiry_day_close(model: ModelInputs, at: datetime.datetime | None = None) -> datetime.datetime | None:
    """ADR-320 (1), ADR-310 (4): today's 15:30 IST close when the strategy's NEAREST expiry is today (IST) and ``at``
    (default: the valuation time) is before it; else None (another day, or after the close: no theta is replaced)."""
    m = _require(model)
    when = valued_at(m, at)
    return close_if_expiry_day(min(leg.expiry for leg in m.legs), when) if m.legs else None


def close_if_expiry_day(nearest: datetime.date, at: datetime.datetime) -> datetime.datetime | None:
    """THE expiry-day check of ADR-320 (1) (ADR-310 (4)): ``nearest``'s 15:30 IST close when ``nearest`` is ``at``'s IST
    date and ``at`` is before that close; else None. :func:`expiry_day_close` and the adjustment drawer call it."""
    close = datetime.datetime.combine(nearest, _bs.EXPIRY_CLOSE)
    return close if at.astimezone(IST).date() == nearest and at < close else None


def unit_decay_left_today(em: ExpiryModel, kind: Instrument, strike: Decimal, vol: Decimal,
                          until: datetime.datetime | None = None) -> Decimal | None:
    """D-12 (ADR-320 (1)) for one contract of an expiry (the option chain, the adjustment drawer): per-unit UNSIGNED,
    UNROUNDED Decay left today at the live spot = its value at today's close minus its model value now. The expiry IS
    today (IST) and the valuation is before its 15:30 close: its intrinsic value at the close (minus its whole time
    value). A later expiry with ``until`` (today's close of the position's nearest expiry, from
    :func:`expiry_day_close`): its decay over the hours left today, as :func:`leg_decay_left_today` values a later
    leg. Else None (theta stays)."""
    e = _require_expiry(em)
    f = e.forward
    when = f.valuation_time
    close = datetime.datetime.combine(e.expiry, _bs.EXPIRY_CLOSE)
    if until is not None and when < until < close:
        then = _bs.year_fraction(until, e.expiry, days_in_year=f.days_in_year)
    elif when.astimezone(IST).date() == e.expiry and when < close:
        then = Decimal(0)
    else:
        return None
    return _bs.bs_decay_unrounded(kind, e.level, strike, f.years, then, f.rate, vol,
                                  dividend_yield=e.dividend_yield)


def leg_decay_left_today(model: ModelInputs, leg: LegInput, level: Decimal | None = None,
                         at: datetime.datetime | None = None) -> Decimal | None:
    """D-12 (ADR-320 (1)): per-unit UNSIGNED, UNROUNDED "Decay left today" of one leg: the model value at today's close
    minus the model value at ``at`` (default now), at ``level`` (default the live spot) with the leg's IV, the rate and
    the expiry's q; a leg expiring today is at its intrinsic value at the close, so this is minus its whole time value.
    A later-expiry leg decays over the hours left today. None when it is not expiry day (:func:`expiry_day_close`).
    A futures leg and a leg with no time value left: 0. No IV with time value left: ValueError (the caller's reason)."""
    m = _require(model)
    close = expiry_day_close(m, at)
    if close is None:
        return None
    if leg.instrument is Instrument.FUT or no_time_value(m, leg):
        return Decimal(0)
    if leg.iv is None:
        raise ValueError(f"leg {leg.contract} has no IV")
    when = valued_at(m, at)
    em = m.expiry_model(leg.expiry)
    f = em.forward
    s = em.level if level is None else level
    now = _bs.year_fraction(when, leg.expiry, days_in_year=f.days_in_year)
    then = (_bs.year_fraction(close, leg.expiry, days_in_year=f.days_in_year) if close < leg_close(leg)
            else Decimal(0))
    return _bs.bs_decay_unrounded(leg.instrument, s, leg.strike, now, then, f.rate, leg.iv,
                                  dividend_yield=em.dividend_yield)
