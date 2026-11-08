# ruff: noqa: E501, PLC0414, PLR2004, RUF007
"""GC-SET batch 1 (REQ-167 AC-4): each moved calculation reads the setting in force when it runs, never a literal.

Spec basis: REQ-167 AC-4 "Each wired calculation reads the value in force when it runs (no restart) ... A test proves it
for each wired setting."; ADR-222 (1). Each test hands the SAME real calculation a settings mapping that differs in ONE
key from the registry defaults and asserts the figure that key feeds changes. The SD-horizon test is the batch's core
proof (the figure goes through ``build_outcome`` on the real replay chain).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.engine.legs import Action
from ofo.engine.target import target_level_limits
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.config import ScenarioSettings
from ofo.settings import calc, defaults
from ofo.strategy.placement import PlacementRefused, QuickPick, place_quick_pick
from outcome._both_curves_cases import S54, as_json, definition, market, outcome
from outcome.test_payoff_table_and_sd import ONE_19OCT, _independent_sd
from outcome.test_payoff_table_and_sd import _body as _default_body
from outcome.test_payoff_table_and_sd import provider as provider
from strategy.test_placement import LIVE, NEAR
from strategy.test_placement import listed as listed


def _with(**changes) -> dict[str, Decimal]:
    values = defaults()
    for key, value in changes.items():
        assert key in values, key
        values[key] = Decimal(value)
    return values


def _json(provider, legs=S54, **kw) -> dict:
    return as_json(outcome_to_dict(outcome(provider, legs, **kw)))


def test_core_sd_horizon_setting_changes_the_sd_band_figures(provider):
    """Core: 7 days (the registry default) vs 10 days gives different SD bands through the outcome service, each equal
    to the independent formula at its own horizon (19-Oct is 11 days out, so neither is capped)."""
    key = calc.SD_HORIZON_DAYS
    seven = _json(provider, ONE_19OCT, sd_bands=True, settings=_with(**{key: 7}))["standard_deviation"]
    ten = _json(provider, ONE_19OCT, sd_bands=True, settings=_with(**{key: 10}))["standard_deviation"]
    assert defaults()[key] == Decimal(7)
    assert (seven["horizon_days"], ten["horizon_days"]) == (7, 10)
    assert seven["rows"] != ten["rows"]
    spot, iv = Decimal(seven["spot"]), Decimal(seven["iv"])
    for sd, days in ((seven, 7), (ten, 10)):
        want = _independent_sd(spot, iv, days)
        assert [{k: r[k] for k in ("sd", "move", "percent", "lower", "upper")} for r in sd["rows"]] == want
    # no settings handed in = the registry default, the figure the code gave before the move
    assert _json(provider, ONE_19OCT, sd_bands=True)["standard_deviation"] == seven


def test_payoff_table_steps_setting_changes_the_allowed_steps_and_the_table(provider):
    """Step 1 set to 20: a 20-point table is now allowed (and has 20-point gaps); the default refuses it."""
    changed = _with(**{calc.PAYOFF_STEP_KEY.format(1): 20})
    table = _json(provider, S54, payoff_step=Decimal(20), settings=changed)["payoff_table"]
    levels = [Decimal(r["level"]) for r in table["rows"]]
    assert table["step"] == "20" and {b - a for a, b in zip(levels, levels[1:], strict=False)} == {Decimal(20)}
    with pytest.raises(ValueError, match="payoff table step"):
        outcome(provider, S54, payoff_step=Decimal(20))  # the defaults 10/25/50/100 do not allow 20
    with pytest.raises(ValueError, match="payoff table step"):
        outcome(provider, S54, payoff_step=Decimal(10), settings=changed)  # 10 was replaced by 20
    assert calc.payoff_steps(defaults()) == (Decimal(10), Decimal(25), Decimal(50), Decimal(100))  # defaults unchanged


def test_payoff_default_step_setting_changes_the_default_table(provider):
    key = calc.PAYOFF_DEFAULT_STEP_KEY.format("nifty")
    default = _json(provider, S54, both_views=True)["payoff_table"]["step"]
    moved = _json(provider, S54, both_views=True, settings=_with(**{key: 25}))["payoff_table"]["step"]
    assert (default, moved) == ("50", "25")


def test_scenario_column_settings_change_the_columns(provider):
    """NIFTY step and anchor 200: the grid columns of the same strategy are 200 points apart, not 100."""
    default = _json(provider, S54)["scenario"]
    changed = _json(provider, S54, settings=_with(**{"scenarios.nifty_step_points": 200,
                                                      "scenarios.nifty_anchor_points": 200}))["scenario"]
    assert default["step"] == "100" and changed["step"] == "200"
    assert changed["levels"] != default["levels"]
    assert default == _default_body(provider)["scenario"]  # registry defaults = today's figures


@pytest.mark.parametrize(("field", "key", "value"), [
    ("half_width_points", "scenarios.nifty_half_width_points", 3000),
    ("margin_steps", "scenarios.nifty_margin_steps", 5),
    ("max_columns", "scenarios.nifty_max_columns", 50),
])
def test_scenario_config_fields_follow_their_setting(field, key, value):
    default = ScenarioSettings.from_values(defaults()).for_index("NIFTY")
    moved = ScenarioSettings.from_values(_with(**{key: value})).for_index("NIFTY")
    assert getattr(moved, "min_half_width_points" if field == "half_width_points" else field) == value
    assert moved != default
    assert ScenarioSettings.from_values(_with(**{key: value})).for_index("SENSEX") == \
        ScenarioSettings.from_values(defaults()).for_index("SENSEX")  # one key per index: the other index is untouched


def test_sensex_scenario_settings_are_their_own_keys():
    moved = ScenarioSettings.from_values(_with(**{"scenarios.sensex_step_points": 600,
                                                  "scenarios.sensex_anchor_points": 300}))
    assert moved.for_index("SENSEX").step_points == 600
    assert moved.for_index("NIFTY") == ScenarioSettings.from_values(defaults()).for_index("NIFTY")


def test_target_span_setting_changes_the_what_if_limits():
    spot, step = Decimal("22976.85"), Decimal(50)
    wide = target_level_limits(spot, step, calc.target_span(defaults()))
    narrow = target_level_limits(spot, step, calc.target_span(_with(**{calc.TARGET_SPAN: "0.05"})))
    assert wide == (Decimal(20700), Decimal(25250))  # the default 0.10 is today's figure
    assert narrow == (Decimal(21850), Decimal(24100)) and narrow != wide


def test_quick_pick_distance_settings_change_the_offered_strangles(listed):
    """250 is not offered by default; setting NIFTY quick pick 1 to 250 offers it, and 50 is then not offered."""
    pick = QuickPick("strangle", "NIFTY", 250, Action.SELL, NEAR)
    with pytest.raises(PlacementRefused):
        place_quick_pick(pick, LIVE, listed[NEAR], calc.quick_pick_distances(defaults()))
    moved = calc.quick_pick_distances(_with(**{calc.QUICK_PICK_KEY.format("nifty", 1): 250}))
    assert moved["NIFTY"] == (250, 100, 150, 200) and moved["SENSEX"] == calc.quick_pick_distances(defaults())["SENSEX"]
    assert len(place_quick_pick(pick, LIVE, listed[NEAR], moved)) == 2
    with pytest.raises(PlacementRefused):
        place_quick_pick(QuickPick("strangle", "NIFTY", 50, Action.SELL, NEAR), LIVE, listed[NEAR], moved)


def test_the_registry_defaults_are_the_values_the_code_had():
    """Defaults never change (REQ-167 AC-5): the numbers the moved constants held."""
    d = defaults()
    assert calc.quick_pick_distances(defaults()) == {"NIFTY": (50, 100, 150, 200), "SENSEX": (100, 200, 300, 400)}
    assert calc.payoff_default_step(defaults(), "NIFTY") == 50 and calc.payoff_default_step(defaults(), "SENSEX") == 100
    assert d[calc.TARGET_SPAN] == Decimal("0.1") and d[calc.SD_HORIZON_DAYS] == 7
    assert calc.scenario_fields(defaults(), "SENSEX") == {"step_points": 300, "anchor_points": 300, "half_width_points": 3000,
                                                    "margin_steps": 2, "max_columns": 200}
    with pytest.raises(KeyError):  # a mapping without the key is an error, never a silent default
        calc.sd_horizon_days({})
    assert definition and market  # the helpers import (module-level names used by the fixtures above)
