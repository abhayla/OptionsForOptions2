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
from ofo.engine import estimate as _estimate
from ofo.engine.black_scholes import Greeks
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Instrument
from ofo.marketdata.forward import FALLBACK_LABEL, ExpiryForward, ForwardUnavailable
from ofo.rules.inputs import DataHealth

IST: Final = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
_REFUSED: Final = (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE)
_TOKEN: Final = object()  # only model_inputs() can build a ModelInputs

Forwards = Mapping[datetime.date, ExpiryForward]


class SpotRefused(ValueError):
    """The index value is missing or unusable; the calculation is refused, never computed silently."""


def data_label(reading: SpotReading) -> str | None:
    """"stale since HH:MM IST" / "delayed, as of HH:MM IST" for a non-live reading; None for an AVAILABLE one."""
    hhmm = reading.at.astimezone(IST).strftime("%H:%M")
    if reading.health is DataHealth.STALE:
        return f"stale since {hhmm} IST"
    if reading.health is DataHealth.DELAYED:
        return f"delayed, as of {hhmm} IST"
    return None


def join_labels(*labels: str | None) -> str | None:
    parts = [x for x in labels if x]
    return "; ".join(parts) if parts else None


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
        raise SpotRefused(f"the {underlying} spot is {reading.health.value}; the calculation is refused")
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
    return ModelInputs._make(_TOKEN, inputs=inputs, spot_level=reading.level, spot_at=reading.at, data_label=dlabel,
                             expiries=types.MappingProxyType(dict(expiries)),
                             label=join_labels(dlabel, FALLBACK_LABEL if fell_back else None))


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
    em = m.expiry_model(leg.expiry)
    f = em.forward
    return _bs.bs_greeks_unrounded(leg.instrument, em.level, leg.strike, f.years, f.rate, leg.iv,
                                   days_in_year=f.days_in_year, dividend_yield=em.dividend_yield)


def greeks(em: ExpiryModel, kind: Instrument, strike: Decimal, vol: Decimal, level: Decimal | None = None) -> ModelGreeks:
    """Per-unit engine Greeks (4 dp) at ``level`` (default: the live spot) with the expiry's q."""
    e = _require_expiry(em)
    f = e.forward
    s = e.level if level is None else level
    g = _bs.bs_greeks(kind, s, strike, f.years, f.rate, vol, days_in_year=f.days_in_year,
                      dividend_yield=e.dividend_yield)
    return ModelGreeks(g, s, e.dividend_yield, e.level, e.spot_at, e.label)


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


def estimate(model: ModelInputs, level: Decimal) -> Estimate:
    """Estimated Now P&L if the index were at ``level`` at the valuation time (ADR-008 Q33A = C; ADR-063)."""
    m = _require(model)
    marks: list[Decimal] = []
    pnls: list[Decimal] = []
    years: list[Decimal] = []
    qs: list[Decimal] = []
    sources: list[str] = []
    for leg in m.legs:
        em = m.expiry_model(leg.expiry)
        one = _estimate.estimate_now(dataclasses.replace(m.inputs, legs=(leg,)), level,
                                     dividend_yield=em.dividend_yield, yield_source=em.source)
        marks.append(one.marks[0])
        pnls.append(one.leg_pnls[0])
        years.append(one.assumptions.years_to_expiry[0])
        qs.append(em.dividend_yield)
        sources.append(em.source)
    i = m.inputs
    assumptions = _estimate.EstimateAssumptions(
        model=_estimate.MODEL, valuation_time=i.valuation_time, rate=i.rate, days_in_year=i.days_in_year,
        ivs=tuple(leg.iv for leg in m.legs), years_to_expiry=tuple(years), dividend_yields=tuple(qs),
        yield_sources=tuple(sources))
    return Estimate(level, tuple(marks), tuple(pnls), sum(pnls, Decimal(0)), assumptions, m.label, m.spot_level,
                    m.spot_at)
