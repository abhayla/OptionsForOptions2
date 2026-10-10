"""The two views of the same scenario columns (REQ-034 AC-6; ADR-008 Q33A = C; scenario-calculations.md §4).

- **At Expiry** (default, exact): the engine's §1 expiry P&L per leg and total (:func:`ofo.engine.scenario_grid`).
- **Estimated Now** (model-based): the engine's estimate (:func:`ofo.engine.model.estimate`), labelled
  as an estimate and carrying its assumptions. A strategy with an option leg that has no IV gets no estimate: the
  view is unavailable with a reason, never a zero.

An inserted breakeven can be an exact level with more than two decimals (engine metrics); the estimate is taken at
that level rounded half-even to 0.01 points (the exchange's quote precision), and the estimated level is recorded.

Every view takes a gated :class:`~ofo.engine.model.ModelInputs` (REQ-072 AC-2; W-060 round 3), never a bare level.
"""
from __future__ import annotations
from ofo.errors.explanations import SCENARIO_VIEW_LABEL_TEXT, render_explanation

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Final, Literal

from ofo.engine import scenario_grid
from ofo.engine.estimate import EstimateAssumptions
from ofo.engine.model import ModelInputs, estimate, join_labels
from ofo.marketdata.forward import FALLBACK_LABEL
from ofo.scenario.levels import LevelSet

_QUOTE: Final = Decimal("0.01")


class View(Enum):
    AT_EXPIRY = "at_expiry"
    ESTIMATED_NOW = "estimated_now"


DEFAULT_VIEW: Final = View.AT_EXPIRY

LABELS: Final = {view: render_explanation("scenario_view_label", view=view) for view in View}


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
    # REQ-072 AC-2/AC-3: the spot the calculation used, its time, and "stale since HH:MM IST" when not live
    spot_level: Decimal | None = None
    spot_at: datetime.datetime | None = None
    data_label: str | None = None
    # data label and model label joined, e.g. "stale since 09:20 IST; estimated from spot" (W-060 round 3)
    output_label: str | None = None


def _missing_iv(inputs: ModelInputs) -> list[str]:
    return [leg.contract for leg in inputs.legs if leg.leg.is_option and leg.iv is None]


def scenario_values(level_set: LevelSet, inputs: ModelInputs, view: View = DEFAULT_VIEW) -> ScenarioValues:
    """Values of ``view`` over ``level_set``, each carrying the spot level, its time and its labels.

    ``inputs`` is a gated :class:`~ofo.engine.model.ModelInputs` (spot and each expiry's forward checked once):
    Estimated Now values every leg at S with its expiry's yield q (ADR-061, ADR-063; the engine owns q) and carries
    "estimated from spot" when an expiry fell back. At Expiry and the level columns stay on spot.
    """
    if not isinstance(level_set, LevelSet):
        raise ValueError(f"level_set must be a LevelSet, got {level_set!r}")
    if not isinstance(inputs, ModelInputs):
        raise ValueError(f"inputs must be a ModelInputs (ofo.engine.model.model_inputs), got {inputs!r}")
    if not isinstance(view, View):
        raise ValueError(f"view must be a View, got {view!r}")
    if level_set.index != inputs.underlying or level_set.current != inputs.spot_level:
        raise ValueError("level_set was built for a different strategy input (index or current level differs)")
    if level_set.spot_at != inputs.spot_at or level_set.data_label != inputs.data_label:
        raise ValueError("level_set was built on a different spot reading (time or health differs)")
    spot = dict(spot_level=inputs.spot_level, spot_at=inputs.spot_at, data_label=inputs.data_label)
    levels = level_set.levels
    if view is View.AT_EXPIRY:
        grid = scenario_grid(inputs.strategy, levels)
        return ScenarioValues(view, LABELS[view], "exact", levels, True, None, grid.totals, grid.leg_rows,
                              output_label=inputs.data_label, **spot)
    missing = _missing_iv(inputs)
    if missing:
        reason = render_explanation("scenario_estimated_unavailable", legs=tuple(missing))
        return ScenarioValues(view, LABELS[view], "estimate", levels, False, reason, None, None,
                              output_label=inputs.data_label, **spot)
    quoted = tuple(level.quantize(_QUOTE, rounding=ROUND_HALF_EVEN) for level in levels)
    estimates = tuple(estimate(inputs, level) for level in quoted)
    leg_rows = tuple(tuple(e.leg_pnls[i] for e in estimates) for i in range(len(inputs.legs)))
    model_label = FALLBACK_LABEL if any(em.forward.label for em in inputs.expiries.values()) else None
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
        model_label=model_label,
        output_label=join_labels(inputs.data_label, model_label),
        **spot,
    )
