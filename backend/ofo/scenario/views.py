"""The two views of the same scenario columns (REQ-034 AC-6; ADR-008 Q33A = C; scenario-calculations.md §4).

- **At Expiry** (default, exact): the engine's §1 expiry P&L per leg and total (:func:`ofo.engine.scenario_grid`).
- **Estimated Now** (model-based): the engine's estimate (:func:`ofo.engine.estimate.estimate_now_grid`), labelled
  as an estimate and carrying its assumptions. A strategy with an option leg that has no IV gets no estimate: the
  view is unavailable with a reason, never a zero.

An inserted breakeven can be an exact level with more than two decimals (engine metrics); the estimate is taken at
that level rounded half-even to 0.01 points (the exchange's quote precision), and the estimated level is recorded.
"""
from __future__ import annotations
from ofo.errors.explanations import SCENARIO_VIEW_LABEL_TEXT, render_explanation

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Final, Literal

from ofo.engine import scenario_grid
from ofo.engine.estimate import EstimateAssumptions, estimate_now_grid
from ofo.engine.inputs import StrategyInput
from ofo.scenario.levels import LevelSet

_QUOTE: Final = Decimal("0.01")


class View(Enum):
    AT_EXPIRY = "at_expiry"
    ESTIMATED_NOW = "estimated_now"


DEFAULT_VIEW: Final = View.AT_EXPIRY

LABELS: Final = {
    View.AT_EXPIRY: SCENARIO_VIEW_LABEL_TEXT["AT_EXPIRY"],
    View.ESTIMATED_NOW: SCENARIO_VIEW_LABEL_TEXT["ESTIMATED_NOW"],
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


def _missing_iv(inputs: StrategyInput) -> list[str]:
    return [leg.contract for leg in inputs.legs if leg.leg.is_option and leg.iv is None]


def scenario_values(level_set: LevelSet, inputs: StrategyInput, view: View = DEFAULT_VIEW) -> ScenarioValues:
    """Values of ``view`` at every column of ``level_set``, all from the engine."""
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
        reason = render_explanation("scenario_estimated_unavailable", legs=", ".join(missing))
        return ScenarioValues(view, LABELS[view], "estimate", levels, False, reason, None, None)
    quoted = tuple(level.quantize(_QUOTE, rounding=ROUND_HALF_EVEN) for level in levels)
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
    )
