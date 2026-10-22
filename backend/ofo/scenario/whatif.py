"""What-if at a target level, date and IV change; the Estimated curve, expected-move bands, OI and Greeks (W-127).

Requirements: REQ-083 (both curves from ONE engine reply; SD bands by the REQ-027 formula; today's OI only, ADR-066),
REQ-084 (target level / date / IV offset; the engine returns P&L, breakevens and Greeks at the target; Greeks per
unit and per position with rupee examples computed here, never in the browser), ADR-008 (one engine, Decimal).

Everything here is an ESTIMATE from the pricing model (ADR-063) except ``target_expiry_pnl`` (the At Expiry P&L at the
target level, exact, REQ-084 AC-7). The inputs are used for ONE computation and are never stored (REQ-084 AC-6).

Answer states (run-discipline B4 (d)):

- IV present on every option leg: Estimated curve, P&L, breakevens and Greeks at the target.
- an option leg has no IV: no Estimated curve, no Greeks, ``whatif_curve_no_iv``; the exact At Expiry figure stays.
- IV offset makes a leg's IV zero or below: :class:`~ofo.engine.model.WhatIfRefused` (the route answers 422).
- target date before now / after the first expiry close: clamped, with the reason in ``clamp_notes``.
- target date at the expiry close: the leg is worth its expiry value; Greeks are not defined (``whatif_greeks_at_expiry_close``).
- ATM IV absent, or no whole calendar day to the nearest expiry: no bands, ``whatif_bands_unavailable``.
- OI: no chain read for the expiry or no strike carries OI: ``whatif_oi_unavailable``; a strike whose OI is absent has
  ``None`` (never zero); a quote that is not AVAILABLE marks the whole read ``stale``.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Final

from ofo.charges import ChargeRates
from ofo.charges.round_trip import exercise_stt_at, round_trip_charges
from ofo.engine import scenario_grid
from ofo.engine.black_scholes import Greeks
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import ModelInputs, WhatIfRefused, estimate, expiry_model, implied_vol, leg_greeks_at
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.marketdata.forward import mid_price
from ofo.money import PAISE
from ofo.rules.inputs import DataHealth
from ofo.scenario.levels import ExpectedMove, LevelSet
from ofo.scenario.spot import spot_reading
from ofo.table.model import FUTURES_PER_UNIT_GREEKS
from ofo.timeutil import EXPIRY_CLOSE

if TYPE_CHECKING:  # the snapshot module imports nothing from here; a runtime import would cycle through ofo.outcome
    from ofo.outcome.snapshot import MarketSnapshot

__all__ = ["WhatIfInput", "WhatIfRefused", "WhatIfResult", "build_whatif", "expiry_total_at"]

#: the rupee examples use this index move (REQ-084 AC-9: "if NIFTY rises 10 points")
EXAMPLE_POINTS: Final = 10
_GREEK_STEP: Final = Decimal("0.0001")
_IV_STEP: Final = Decimal("0.1")
_BISECT_ROUNDS: Final = 60
_HALF: Final = Decimal("0.5")


@dataclass(frozen=True)
class WhatIfInput:
    """The browser's what-if inputs (REQ-084 AC-4: it sends only these). None = not set: the live spot / now."""

    target_level: Decimal | None = None
    target_time: datetime.datetime | None = None
    iv_offset: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if self.target_time is not None and self.target_time.tzinfo is None:
            raise ValueError("target_time must be timezone-aware")
        if type(self.iv_offset) is not Decimal or not self.iv_offset.is_finite() or \
                self.iv_offset != self.iv_offset.quantize(_IV_STEP):
            raise ValueError("iv_offset must be a Decimal in steps of 0.1 volatility points")


@dataclass(frozen=True)
class GreekExample:
    greek: str
    sentence: ExplanationText


@dataclass(frozen=True)
class GreekRow:
    instrument_id: str
    per_unit: Greeks
    per_position: Greeks


@dataclass(frozen=True)
class GreeksPanel:
    rows: tuple[GreekRow, ...]
    total_per_position: Greeks
    total_per_unit: Greeks | None  # per position / lot size; None when the legs' lot sizes differ
    examples: tuple[GreekExample, ...]


@dataclass(frozen=True)
class Band:
    label: str  # "-2SD" "-1SD" "1SD" "2SD"
    level: Decimal


@dataclass(frozen=True)
class OiStrike:
    strike: Decimal
    call_oi: int | None
    put_oi: int | None
    call_oi_change: int | None
    put_oi_change: int | None


@dataclass(frozen=True)
class OiOverlay:
    expiry: datetime.date
    read_at: datetime.datetime
    stale: bool
    strikes: tuple[OiStrike, ...]


@dataclass(frozen=True)
class WhatIfResult:
    estimate_label: ExplanationText
    level_min: Decimal
    level_max: Decimal
    level_step: Decimal
    time_min: datetime.datetime
    time_max: datetime.datetime
    target_level: Decimal
    target_time: datetime.datetime
    iv_offset: Decimal
    clamp_notes: tuple[ExplanationText, ...]
    target_expiry_pnl: Decimal  # exact At Expiry P&L at the target level (REQ-084 AC-7)
    estimated_available: bool
    estimated_reason: ExplanationText | None
    estimated_points: tuple[tuple[Decimal, Decimal], ...]
    target_estimated_pnl: Decimal | None
    estimated_breakevens: tuple[Decimal, ...]
    greeks: GreeksPanel | None
    greeks_reason: ExplanationText | None
    bands: tuple[Band, ...]
    bands_reason: ExplanationText | None
    oi: OiOverlay | None
    oi_reason: ExplanationText | None


def expiry_total_at(model: ModelInputs, level: Decimal, rates: ChargeRates | None = None) -> Decimal:
    """The exact At Expiry total at ONE level: the engine's expiry grid and the same charge rule as the At Expiry view
    (ADR-082 (2)). REQ-084 AC-7: this is what the target-level control gives with no live IV."""
    total = scenario_grid(model.strategy, (level,)).totals[0]
    if rates is None:
        return total
    return (total - round_trip_charges(model.strategy.legs, model.underlying, rates)
            - exercise_stt_at(model.strategy.legs, level, rates))


def _first_close(model: ModelInputs) -> datetime.datetime:
    return datetime.datetime.combine(min(leg.expiry for leg in model.legs), EXPIRY_CLOSE)


def _clamp_time(model: ModelInputs, now: datetime.datetime, want: datetime.datetime | None):
    last = _first_close(model)
    if want is None:
        return now, ()
    if want < now:
        return now, (render_explanation("whatif_target_clamped_early"),)
    if want > last:
        return last, (render_explanation("whatif_target_clamped_late"),)
    return want, ()


def _clamp_level(level_set: LevelSet, want: Decimal | None, spot: Decimal):
    pick = spot if want is None else want
    lo, hi = level_set.start, level_set.end
    if pick < lo or pick > hi:
        return min(max(pick, lo), hi), (render_explanation("whatif_level_clamped"),)
    return pick, ()


def _quote_level(level: Decimal) -> Decimal:
    return level.quantize(PAISE, rounding=ROUND_HALF_EVEN)


def _breakevens(total_at: Callable[[Decimal], Decimal], points) -> tuple[Decimal, ...]:
    """Levels where the engine's Estimated total crosses zero: the engine is bisected between each pair of neighbouring
    computed points whose totals have opposite signs; a point that is exactly zero is a breakeven. Every value probed
    is the engine's own estimate (ADR-008); nothing is interpolated."""
    found: list[Decimal] = []
    for (l0, p0), (l1, p1) in zip(points, points[1:], strict=False):
        if p0 == 0:
            found.append(l0)
        elif p0 * p1 < 0:
            lo, hi, lo_positive = _quote_level(l0), _quote_level(l1), p0 > 0
            for _ in range(_BISECT_ROUNDS):
                mid = _quote_level((lo + hi) / 2)
                if mid in (lo, hi):
                    break
                if (total_at(mid) > 0) == lo_positive:
                    lo = mid
                else:
                    hi = mid
            found.append(hi if abs(total_at(hi)) <= abs(total_at(lo)) else lo)
    if points and points[-1][1] == 0:
        found.append(points[-1][0])
    return tuple(found)


def _round(value: Decimal) -> Decimal:
    return value.quantize(_GREEK_STEP, rounding=ROUND_HALF_EVEN)


def _signed(g: Greeks, action: Action, quantity: int) -> list[Decimal]:
    sign = Decimal(1) if action is Action.BUY else Decimal(-1)
    return [x * sign * quantity for x in (g.delta, g.gamma, g.theta, g.vega)]


def _greeks_panel(model: ModelInputs, level: Decimal, when: datetime.datetime, offset: Decimal,
                  legs_meta: Sequence[tuple[str, int | None]]) -> GreeksPanel:
    """Per-leg and total Greeks at the target, each rounded ONCE after scaling and summing (no round-then-scale)."""
    rows: list[GreekRow] = []
    totals = [Decimal(0)] * 4
    lot_sizes: set[int | None] = set()
    for leg, (iid, lot_size) in zip(model.legs, legs_meta, strict=True):
        lot_sizes.add(lot_size)
        unit = (FUTURES_PER_UNIT_GREEKS if leg.instrument is Instrument.FUT
                else leg_greeks_at(model, leg, level, when, offset))
        pos = _signed(unit, leg.action, leg.quantity)
        totals = [t + p for t, p in zip(totals, pos, strict=True)]
        rows.append(GreekRow(iid, Greeks(*(_round(x) for x in (unit.delta, unit.gamma, unit.theta, unit.vega))),
                             Greeks(*(_round(x) for x in pos))))
    total = Greeks(*(_round(x) for x in totals))
    size = next(iter(lot_sizes)) if len(lot_sizes) == 1 else None
    per_unit = None if not size else Greeks(*(_round(x / size) for x in totals))
    return GreeksPanel(tuple(rows), total, per_unit, _examples(model.underlying, totals, total))


def _rupees(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_EVEN)


def _examples(index: str, raw: list[Decimal], total: Greeks) -> tuple[GreekExample, ...]:
    """The engine's rupee examples (REQ-084 AC-9), computed from the UNROUNDED position Greeks, 2 dp."""
    pts = Decimal(EXAMPLE_POINTS)
    delta, gamma, theta, vega = raw
    return (
        GreekExample("delta", render_explanation("greeks_example_delta", total=total.delta, index=index,
                                                 points=EXAMPLE_POINTS, rupees=_rupees(delta * pts))),
        GreekExample("gamma", render_explanation("greeks_example_gamma", total=total.gamma, index=index,
                                                 points=EXAMPLE_POINTS, rupees=_rupees(_HALF * gamma * pts * pts))),
        GreekExample("theta", render_explanation("greeks_example_theta", total=total.theta, rupees=_rupees(theta))),
        GreekExample("vega", render_explanation("greeks_example_vega", total=total.vega, rupees=_rupees(vega))),
    )


def _atm_iv(model: ModelInputs, snapshot: MarketSnapshot, expiry: datetime.date) -> Decimal | None:
    """IV at the strike nearest the spot: the mean of its CE and PE implied vols (each from the mid price); None when
    either side cannot be read."""
    chain = snapshot.chains.get(expiry, ())
    strikes = {q.strike for q in chain if q.strike is not None}
    if not strikes or snapshot.spot is None:
        return None
    atm = min(strikes, key=lambda k: (abs(k - model.spot_level), k))
    em = expiry_model(spot_reading(snapshot.spot), snapshot.forwards[expiry], underlying=model.underlying)
    ivs: list[Decimal] = []
    for kind in (Instrument.CE, Instrument.PE):
        q = next((x for x in chain if x.strike == atm and x.instrument_type is kind), None)
        if q is None or q.ltp is None or q.health in (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE):
            return None
        price = mid_price(q.bid, q.ask) if q.bid and q.ask and q.ask >= q.bid else q.ltp
        try:
            ivs.append(implied_vol(em, kind, price, atm).iv)
        except (ValueError, ArithmeticError):
            return None
    return sum(ivs, Decimal(0)) / len(ivs)


def _bands(model: ModelInputs, snapshot: MarketSnapshot, until: datetime.date, now: datetime.datetime):
    """REQ-083 AC-4: spot x ATM IV x sqrt(calendar days / 365), 1 SD and 2 SD each side of the live spot. Days run from
    today to ``until``: the first expiry, or the target date when the user set one (already clamped to the expiry)."""
    expiry = min(leg.expiry for leg in model.legs)
    days = (until - now.date()).days
    reason = render_explanation("whatif_bands_unavailable")
    if days < 1 or expiry not in snapshot.forwards:
        return (), reason
    atm = _atm_iv(model, snapshot, expiry)
    if atm is None:
        return (), reason
    one = ExpectedMove(atm, days).points(model.spot_level)
    s = model.spot_level
    return (Band("-2SD", s - 2 * one), Band("-1SD", s - one), Band("1SD", s + one), Band("2SD", s + 2 * one)), None


def _oi(snapshot: MarketSnapshot, expiry: datetime.date) -> tuple[OiOverlay | None, ExplanationText | None]:
    """Today's OI per strike for ``expiry`` (ADR-066: no history). A strike with no OI figure keeps None, never 0."""
    chain = snapshot.chains.get(expiry, ())
    sides = {kind: {q.strike: q for q in chain if q.strike is not None and q.instrument_type is kind}
             for kind in (Instrument.CE, Instrument.PE)}
    strikes = sorted(set(sides[Instrument.CE]) | set(sides[Instrument.PE]))
    if not any(q.oi is not None for q in chain):
        return None, render_explanation("whatif_oi_unavailable")

    def one(strike: Decimal) -> OiStrike:
        ce, pe = sides[Instrument.CE].get(strike), sides[Instrument.PE].get(strike)
        return OiStrike(strike, None if ce is None else ce.oi, None if pe is None else pe.oi,
                        None if ce is None else ce.oi_change, None if pe is None else pe.oi_change)

    return OiOverlay(expiry, max(q.timestamp for q in chain),
                     any(q.health is not DataHealth.AVAILABLE for q in chain),
                     tuple(one(k) for k in strikes)), None


def build_whatif(model: ModelInputs, snapshot: MarketSnapshot, level_set: LevelSet, now: datetime.datetime,
                 inputs: WhatIfInput, expiry_total_at: Callable[[Decimal], Decimal],
                 legs_meta: Sequence[tuple[str, int | None]], charges: Decimal | None = None) -> WhatIfResult:
    """The what-if block of one reply. ``expiry_total_at(level)`` is the engine's exact At Expiry total at a level (the
    caller passes the engine function the table uses, charges included). ``legs_meta`` is, per engine leg in order,
    (instrument id, lot size). ``charges`` are the round-trip charges taken off the At Expiry curve (ADR-082); the
    Estimated curve takes the same amount off so both curves are net of the same charges."""
    when, time_notes = _clamp_time(model, now, inputs.target_time)
    level, level_notes = _clamp_level(level_set, inputs.target_level, model.spot_level)
    level = _quote_level(level)
    expiry = min(leg.expiry for leg in model.legs)
    oi, oi_reason = _oi(snapshot, expiry)
    bands, bands_reason = _bands(model, snapshot, expiry if inputs.target_time is None else when.date(), now)
    common = dict(
        estimate_label=render_explanation("whatif_estimate_label"), level_min=level_set.start, level_max=level_set.end,
        level_step=level_set.step, time_min=now, time_max=_first_close(model), target_level=level, target_time=when,
        iv_offset=inputs.iv_offset, clamp_notes=(*time_notes, *level_notes), target_expiry_pnl=expiry_total_at(level),
        bands=bands, bands_reason=bands_reason, oi=oi, oi_reason=oi_reason)
    refusal: ExplanationText | None = None
    if any(leg.instrument is not Instrument.FUT and leg.iv is None for leg in model.legs):
        refusal = render_explanation("whatif_curve_no_iv")
    else:
        try:  # AC-3: an IV at or below 0 after the offset is a stated refusal of the estimate, never an error page
            estimate(model, level, valuation_time=when, iv_offset=inputs.iv_offset)
        except WhatIfRefused as err:
            refusal = err.reason
    if refusal is not None:
        return WhatIfResult(estimated_available=False, estimated_reason=refusal, estimated_points=(),
                            target_estimated_pnl=None, estimated_breakevens=(), greeks=None, greeks_reason=refusal,
                            **common)
    charge = Decimal(0) if charges is None else charges

    def total_at(lvl: Decimal) -> Decimal:
        return estimate(model, _quote_level(lvl), valuation_time=when, iv_offset=inputs.iv_offset).total - charge

    points = tuple((lvl, total_at(lvl)) for lvl in level_set.levels)
    greeks = reason = None
    at_close = when == _first_close(model)
    if at_close:
        reason = render_explanation("whatif_greeks_at_expiry_close")
    else:
        greeks = _greeks_panel(model, level, when, inputs.iv_offset, legs_meta)
    return WhatIfResult(estimated_available=True, estimated_reason=None, estimated_points=points,
                        target_estimated_pnl=total_at(level), estimated_breakevens=_breakevens(total_at, points),
                        greeks=greeks, greeks_reason=reason, **common)
