"""The two consumers of the scenario level set: the scenario table and the payoff graph (REQ-034 AC-8).

Both call :func:`ofo.scenario.levels.build_level_set` and :func:`ofo.scenario.views.scenario_values` — one level
set, one engine; both take a gated ModelInputs (ofo.engine.model.model_inputs) — so the graph can never show a level or a number the table does not.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import datetime

from ofo.engine.model import ModelInputs
from ofo.scenario import levels as _levels
from ofo.scenario import views as _views
from ofo.scenario.config import ScenarioConfig


@dataclass(frozen=True)
class ScenarioTable:
    level_set: _levels.LevelSet
    values: _views.ScenarioValues


@dataclass(frozen=True)
class PayoffGraph:
    """Graph points (level, total P&L); empty with a reason when the chosen view is unavailable."""

    view: _views.View
    label: str
    points: tuple[tuple[Decimal, Decimal], ...]
    current: Decimal
    breakevens: tuple[Decimal, ...]
    unavailable_reason: str | None
    # REQ-072 AC-2/AC-3: the spot the values used, its time, and the joined data/model label
    spot_level: Decimal | None = None
    spot_at: datetime.datetime | None = None
    output_label: str | None = None


def _compute(
    inputs: ModelInputs,
    config: ScenarioConfig,
    view: _views.View,
    expected_move: _levels.ExpectedMove | None,
    override: _levels.RangeOverride | None,
) -> tuple[_levels.LevelSet, _views.ScenarioValues]:
    level_set = _levels.build_level_set(inputs, config, expected_move=expected_move, override=override)
    return level_set, _views.scenario_values(level_set, inputs, view)


def scenario_table(
    inputs: ModelInputs,
    config: ScenarioConfig,
    view: _views.View = _views.DEFAULT_VIEW,
    *,
    expected_move: _levels.ExpectedMove | None = None,
    override: _levels.RangeOverride | None = None,
) -> ScenarioTable:
    level_set, values = _compute(inputs, config, view, expected_move, override)
    return ScenarioTable(level_set, values)


def payoff_graph(
    inputs: ModelInputs,
    config: ScenarioConfig,
    view: _views.View = _views.DEFAULT_VIEW,
    *,
    expected_move: _levels.ExpectedMove | None = None,
    override: _levels.RangeOverride | None = None,
) -> PayoffGraph:
    level_set, values = _compute(inputs, config, view, expected_move, override)
    points = tuple(zip(values.levels, values.totals)) if values.available and values.totals is not None else ()
    return PayoffGraph(values.view, values.label, points, level_set.current, level_set.breakevens,
                       values.unavailable_reason, values.spot_level, values.spot_at, values.output_label)
