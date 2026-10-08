"""The two views of the same scenario columns (REQ-034 AC-6; ADR-008 Q33A = C; scenario-calculations.md §4).

- **At Expiry** (default, exact): the engine's §1 expiry P&L per leg and total (:func:`ofo.engine.scenario_grid`).
- **Estimated Now** (model-based): the engine's estimate (:func:`ofo.engine.estimate.estimate_now_grid`), labelled
  as an estimate and carrying its assumptions. A strategy with an option leg that has no IV gets no estimate: the
  view is unavailable with a reason, never a zero.

An inserted breakeven can be an exact level with more than two decimals (engine metrics); the estimate is taken at
that level rounded half-even to 0.01 points (the exchange's quote precision), and the estimated level is recorded.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Final, Literal

from ofo.engine import scenario_grid
from ofo.engine.estimate import EstimateAssumptions, estimate_now_grid
from ofo.engine.inputs import StrategyInput
from ofo.marketdata.forward import FALLBACK_LABEL
from ofo.scenario.forward_model import Forwards, estimate_now_grid_on_forward
from ofo.scenario.levels import LevelSet

_QUOTE: Final = Decimal("0.01")


class View(Enum):
    AT_EXPIRY = "at_expiry"
    ESTIMATED_NOW = "estimated_now"


DEFAULT_VIEW: Final = View.AT_EXPIRY

LABELS: Final = {
    View.AT_EXPIRY: "At Expiry",
    View.ESTIMATED_NOW: "Estimated Now (estimate)",
}


@dataclass(frozen=True)
class ScenarioValues:
    """One view's values over a level set. ``totals``/``leg_rows`` are None only when ``available`` is False."""

    view: View
    label: str
    kind: Literal["exact", "estimate"]
    levels: tuple[Decimal, ...]
    available: bool
    unavailable_reason: str | None
    totals: tuple[Decimal, ...] | None
    leg_rows: tuple[tuple[Decimal, ...], ...] | None
    assumptions: EstimateAssumptions | None = None
    estimated_levels: tuple[Decimal, ...] | None = None
    model_label: str | None = None  # "estimated from spot" unless every leg's expiry used its parity forward


def _missing_iv(inputs: StrategyInput) -> list[str]:
    return [leg.contract for leg in inputs.legs if leg.leg.is_option and leg.iv is None]


def scenario_values(level_set: LevelSet, inputs: StrategyInput, view: View = DEFAULT_VIEW,
                    forwards: Forwards | None = None) -> ScenarioValues:
    """Values of ``view`` at every column of ``level_set``, all from the engine.

    ``forwards`` (ADR-061): each expiry's parity forward; Estimated Now marks every leg at S e^(-qT) of its expiry.
    Without it the estimate is on spot and is labelled "estimated from spot" - never silently. At Expiry and the
    level columns (CURRENT, the range) always stay on spot.
    """
    if not isinstance(level_set, LevelSet):
        raise ValueError(f"level_set must be a LevelSet, got {level_set!r}")
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    if not isinstance(view, View):
        raise ValueError(f"view must be a View, got {view!r}")
    if level_set.index != inputs.underlying or level_set.current != inputs.underlying_level:
        raise ValueError("level_set was built for a different strategy input (index or current level differs)")
    levels = level_set.levels
    if view is View.AT_EXPIRY:
        grid = scenario_grid(inputs.strategy, levels)
        return ScenarioValues(view, LABELS[view], "exact", levels, True, None, grid.totals, grid.leg_rows)
    missing = _missing_iv(inputs)
    if missing:
        reason = f"Estimated Now is unavailable: no implied volatility for {', '.join(missing)}"
        return ScenarioValues(view, LABELS[view], "estimate", levels, False, reason, None, None)
    quoted = tuple(level.quantize(_QUOTE, rounding=ROUND_HALF_EVEN) for level in levels)
    if forwards is not None:
        on_fwd = estimate_now_grid_on_forward(inputs, quoted, forwards)
        rows = tuple(tuple(e.leg_pnls[i] for e in on_fwd) for i in range(len(inputs.legs)))
        assumptions = estimate_now_grid(inputs, quoted[:1])[0].assumptions
        return ScenarioValues(view, LABELS[view], "estimate", levels, True, None, tuple(e.total for e in on_fwd),
                              rows, assumptions, quoted, on_fwd[0].label)
    estimates = estimate_now_grid(inputs, quoted)
    leg_rows = tuple(tuple(e.leg_pnls[i] for e in estimates) for i in range(len(inputs.legs)))
    return ScenarioValues(
        view=view,
        label=LABELS[view],
        kind="estimate",
        levels=levels,
        available=True,
        unavailable_reason=None,
        totals=tuple(e.total for e in estimates),
        leg_rows=leg_rows,
        assumptions=estimates[0].assumptions,
        estimated_levels=quoted,
        model_label=FALLBACK_LABEL,
    )
