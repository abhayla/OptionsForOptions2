"""What-if target (REQ-084 AC-1, AC-2, AC-4, AC-6, AC-7; ADR-151, ADR-008): every figure at a target index level and a
target date-time, from the one engine.

The browser sends only the inputs (a level in points, an aware date-time); this module clamps them to the server's
limits and values the strategy there with :func:`ofo.engine.model.estimate` (the Estimated Now function, valued at
``at``), so the target P&L, the curve, the breakevens and the Greeks are the engine's. Nothing here is saved, changes a
leg or reaches the margin check or an order (AC-6): it reads a :class:`ModelInputs` and returns figures.

Answer states:

- level absent: the live spot (rounded to the paisa); outside spot -10% .. +10% (snapped to the strike step): clamped.
- time absent: now; before now: clamped to now; after the FIRST expiry's 15:30 IST close: clamped to that close.
- an option leg without IV, or no live data (from your prices): At Expiry P&L at the level (one expiry only); the time
  is refused with the reason (AC-7); no curve, breakevens or Greeks.
- legs on more than one expiry: P&L, curve and Greeks at the target; breakevens absent with the mixed-expiry reason.
- a leg with no time left at the target (its close at or before ``at``): its Greeks are absent (``no_time_left``,
  RD-081: explained, never an error); the total is then absent too.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

from ofo.engine import scenario_grid
from ofo.engine.black_scholes import Greeks
from ofo.engine.estimate import MODEL
from ofo.engine.legs import Instrument
from ofo.engine.model import ModelInputs, estimate, leg_close, leg_greeks_at_unrounded
from ofo.engine.target import breakevens_at, greeks_total, target_level_limits
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.money import PAISE
from ofo.scenario.levels import LevelSet
from ofo.scenario.views import ScenarioValues, View, scenario_values
from ofo.table.model import FUTURES_PER_UNIT_GREEKS, position_greeks, round_greek

ClampCode = Literal["before_now", "after_first_expiry"]
GreeksGap = Literal["no_time_left"]


@dataclass(frozen=True)
class TargetAsk:
    """The what-if inputs of one request (None: not sent)."""

    level: Decimal | None = None
    at: datetime.datetime | None = None

    @property
    def asked(self) -> bool:
        return self.level is not None or self.at is not None


@dataclass(frozen=True)
class TargetLimits:
    min: Decimal
    max: Decimal
    step: Decimal
    at_min: datetime.datetime | None = None  # the date range: now ..
    at_max: datetime.datetime | None = None  # .. the first expiry's 15:30 IST (None: the time input is refused)


@dataclass(frozen=True)
class TargetOffer:
    """No target asked: only what the sliders need (REQ-084 AC-1, Sensibull 020), nothing computed that was not asked."""

    limits: TargetLimits
    at_refused_reason: ExplanationText | None


@dataclass(frozen=True)
class TargetGreeks:
    """Position Greeks at the target (per-unit x quantity x sign, rounded once to 4 dp), one row per leg in leg order
    (None: that leg has no time left) and the total (None unless every leg has a value)."""

    legs: tuple[Greeks | None, ...]
    total: Greeks | None
    unavailable: GreeksGap | None

    @property
    def unavailable_text(self) -> ExplanationText | None:
        """REQ-084 AC-2 / RD-081: the sentence beside ``unavailable`` (a sentence, never an error)."""
        return None if self.unavailable is None else render_explanation("target_greeks_no_time_left")


@dataclass(frozen=True)
class Target:
    limits: TargetLimits
    level: Decimal
    level_clamped: bool
    at: datetime.datetime | None  # None: the time input is refused (``at_refused_reason``)
    at_clamped: bool
    clamp: ClampCode | None
    at_refused_reason: ExplanationText | None
    kind: Literal["estimate", "exact"]
    model: str | None
    output_label: str | None
    pnl: Decimal | None
    breakevens: tuple[Decimal, ...] | None
    breakevens_reason: ExplanationText | None
    curve: ScenarioValues | None
    greeks: TargetGreeks | None

    @property
    def level_clamp_text(self) -> ExplanationText | None:
        """REQ-084 AC-2: "Target moved to the nearest allowed value: 23,000.00." beside ``level_clamped``."""
        return render_explanation("target_clamped", value=self.level) if self.level_clamped else None

    @property
    def at_clamp_text(self) -> ExplanationText | None:
        """REQ-084 AC-2: "Target moved to the nearest allowed value: 3 Nov, 15:30 IST." beside ``clamp``."""
        if self.clamp is None or self.at is None:
            return None
        return render_explanation("target_clamped", value=self.at)


def target_limits(spot: Decimal, step: Decimal) -> TargetLimits:
    """Spot -10% .. +10%, each end snapped inward to a multiple of ``step`` (REQ-084 AC-1)."""
    low, high = target_level_limits(spot, step)
    return TargetLimits(low, high, step)


def _level(ask: TargetAsk, spot: Decimal, limits: TargetLimits) -> tuple[Decimal, bool]:
    wanted = spot.quantize(PAISE, rounding=ROUND_HALF_EVEN) if ask.level is None else ask.level
    level = min(max(wanted, limits.min), limits.max)
    return level, level != wanted


def first_close(model: ModelInputs) -> datetime.datetime:
    """The strategy's FIRST expiry at 15:30 IST: the latest a target time may be (REQ-084 AC-2)."""
    return min(leg_close(leg) for leg in model.legs)


def clamp_at(at: datetime.datetime | None, now: datetime.datetime,
             last: datetime.datetime) -> tuple[datetime.datetime, ClampCode | None]:
    """``at`` inside now .. ``last`` (None: now), with the code of the side it was clamped on."""
    if at is None:
        return now, None
    if at < now:
        return now, "before_now"
    if at > last:
        return last, "after_first_expiry"
    return at, None


def _at_expiry_pnl(model: ModelInputs, level: Decimal) -> Decimal | None:
    """The At Expiry view's own function at one level; None for legs on more than one expiry (no exact figure)."""
    if not model.strategy.is_single_expiry:
        return None
    return scenario_grid(model.strategy, (level,)).totals[0]


def _breakevens(model: ModelInputs, curve: ScenarioValues, at: datetime.datetime) -> tuple[Decimal, ...]:
    """The levels where the target-time estimate crosses zero, from the engine's search on the target curve."""
    return breakevens_at(model, curve.estimated_levels or (), curve.totals or (), at)


def _greeks(model: ModelInputs, level: Decimal, at: datetime.datetime) -> TargetGreeks:
    rows: list[Greeks | None] = []
    raw: list[Greeks] = []
    for leg in model.legs:
        unit = (FUTURES_PER_UNIT_GREEKS if leg.instrument is Instrument.FUT
                else leg_greeks_at_unrounded(model, leg, level, at))
        if unit is None:
            rows.append(None)
            continue
        pos = position_greeks(unit, leg.action, leg.quantity)
        raw.append(pos)
        rows.append(_rounded(pos))
    if len(raw) != len(rows):
        return TargetGreeks(tuple(rows), None, "no_time_left")
    return TargetGreeks(tuple(rows), _rounded(greeks_total(raw)), None)


def _rounded(g: Greeks) -> Greeks:
    """Each Greek rounded once to 4 dp (the table's one rounding rule)."""
    return Greeks(round_greek(g.delta), round_greek(g.gamma), round_greek(g.theta), round_greek(g.vega))


def _missing_iv_reason(model: ModelInputs) -> ExplanationText | None:
    missing = [leg.contract for leg in model.legs if leg.leg.is_option and leg.iv is None]
    return render_explanation("scenario_estimated_unavailable", legs=tuple(missing)) if missing else None


def target_offer(model: ModelInputs, step: Decimal, *, live: bool) -> TargetOffer:
    """The slider limits of an answer where no target was asked: the level range, and the date range now .. first expiry
    close when the estimate can be made (live data and every option leg's IV); else the AC-7 reason for the date."""
    limits = target_limits(model.spot_level, step)
    if not live:
        return TargetOffer(limits, render_explanation("outcome_from_entries_no_estimate"))
    reason = _missing_iv_reason(model)
    if reason is not None:
        return TargetOffer(limits, reason)
    return TargetOffer(dataclasses.replace(limits, at_min=model.inputs.valuation_time, at_max=first_close(model)), None)


def live_target(ask: TargetAsk, model: ModelInputs, graph_levels: LevelSet, step: Decimal) -> Target:
    """The target block of a live computed answer: clamp, then every figure from the engine at the target."""
    limits = target_limits(model.spot_level, step)
    level, level_clamped = _level(ask, model.spot_level, limits)
    reason = _missing_iv_reason(model)
    if reason is not None:  # AC-7: no IV -> the level still gives At Expiry P&L; the time input is refused with the reason
        return _exact_only(limits, level, level_clamped, model, reason)
    limits = dataclasses.replace(limits, at_min=model.inputs.valuation_time, at_max=first_close(model))
    at, clamp = clamp_at(ask.at, model.inputs.valuation_time, first_close(model))
    label = render_explanation("target_estimate_label")  # REQ-084 AC-5: every target figure, the curve included
    curve = dataclasses.replace(scenario_values(graph_levels, model, View.ESTIMATED_NOW, at=at), output_label=label)
    single = model.strategy.is_single_expiry
    return Target(
        limits=limits, level=level, level_clamped=level_clamped, at=at, at_clamped=clamp is not None, clamp=clamp,
        at_refused_reason=None, kind="estimate", model=MODEL, output_label=label,
        pnl=estimate(model, level, at).total,
        breakevens=_breakevens(model, curve, at) if single else None,
        breakevens_reason=None if single else render_explanation("mixed_expiry_worst_case"),
        curve=curve, greeks=_greeks(model, level, at))


def _exact_only(limits: TargetLimits, level: Decimal, level_clamped: bool, model: ModelInputs,
                reason: ExplanationText) -> Target:
    return Target(limits=limits, level=level, level_clamped=level_clamped, at=None, at_clamped=False, clamp=None,
                  at_refused_reason=reason, kind="exact", model=None, output_label=model.data_label,
                  pnl=_at_expiry_pnl(model, level), breakevens=None, breakevens_reason=None, curve=None, greeks=None)


def entries_target(ask: TargetAsk, model: ModelInputs, step: Decimal) -> Target:
    """REQ-077 AC-9 / REQ-084 AC-7: no live data -> At Expiry P&L at the level (limits around the grid's centre, the
    same centre the levels use); the time input is refused with the no-live-prices reason."""
    limits = target_limits(model.spot_level, step)
    level, level_clamped = _level(ask, model.spot_level, limits)
    return _exact_only(limits, level, level_clamped, model, render_explanation("outcome_from_entries_no_estimate"))
