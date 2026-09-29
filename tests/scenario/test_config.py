"""REQ-034 AC-4: step and range are configuration, not code constants (ADR-042; scenario-calculations.md §4)."""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action, Instrument
from ofo.scenario.config import DEFAULT_CONFIGS, ScenarioConfig, ScenarioSettings
from ofo.scenario.levels import RangeOverride, build_level_set
from scenario_fixtures import nifty_input, nifty_leg

NIFTY_NEAR = datetime.date(2026, 9, 29)
SENSEX_NEAR = datetime.date(2026, 10, 1)

VALID = {
    "index": "NIFTY",
    "step_points": "200",
    "anchor_points": "100",
    "min_half_width_points": "1000",
    "margin_steps": 2,
    "max_columns": 200,
}


def test_ac4_defaults_are_config_objects_nifty_100_sensex_300(settings):
    """AC-4: the Admin defaults are ScenarioConfig values (ADR-042): NIFTY step 100, SENSEX step 300."""
    assert settings.for_index("NIFTY") == ScenarioConfig("NIFTY", D("100"), D("100"), D("1000"), 2, 200)
    assert settings.for_index("SENSEX") == ScenarioConfig("SENSEX", D("300"), D("300"), D("3000"), 2, 200)
    assert [c.index for c in DEFAULT_CONFIGS] == ["NIFTY", "SENSEX"]
    with pytest.raises(ValueError, match="no scenario config"):
        settings.for_index("BANKNIFTY")


def test_ac4_admin_config_change_changes_grid_without_code_change(golden):
    """AC-4: an Admin record with NIFTY step 200 gives 200-point columns; nothing in the level code changes."""
    config = ScenarioConfig.from_mapping(VALID)
    ls = build_level_set(golden, config)
    grid =[c.level for c in ls.columns if c.level % D("100") == 0 and not c.is_current]
    assert grid == [D(x) for x in range(22000, 24001, 200)]
    wider = ScenarioConfig.from_mapping({**VALID, "step_points": "100", "min_half_width_points": "2000"})
    ls2 = build_level_set(golden, wider)
    assert (ls2.start, ls2.end) == (D("21000"), D("25000"))


def test_ac4_step_must_be_multiple_of_listed_strike_gap(catalogue):
    """AC-4 / ADR-042: step and anchor must be positive multiples of the catalogue's strike gap (real fixture)."""
    assert catalogue.strike_gap("NIFTY", NIFTY_NEAR) == D("50")
    assert catalogue.strike_gap("SENSEX", SENSEX_NEAR) == D("100")
    nifty, sensex = DEFAULT_CONFIGS
    assert nifty.check_against_catalogue(catalogue, NIFTY_NEAR) == D("50")
    assert sensex.check_against_catalogue(catalogue, SENSEX_NEAR) == D("100")
    for bad in (ScenarioConfig("NIFTY", D("75"), D("75"), D("1000"), 2, 200),
                ScenarioConfig("SENSEX", D("250"), D("50"), D("3000"), 2, 200),
                ScenarioConfig("SENSEX", D("150"), D("150"), D("3000"), 2, 200)):
        with pytest.raises(ValueError, match="not a multiple of the listed strike gap"):
            bad.check_against_catalogue(catalogue, NIFTY_NEAR if bad.index == "NIFTY" else SENSEX_NEAR)


def test_ac4_default_range_is_chosen_from_spot_strikes_breakevens(settings):
    """AC-4: with zero minimum width and margin, the range edges are the strategy's own points.

    BUY 23,000 CE @ 150 at spot 23,047: strike 23,000 sets the low edge, the breakeven 23,150 sets the high edge
    (23,200 on the 100-point grid); without the breakeven the high edge would be 23,100. Risk boundaries are always
    strikes (the payoff kinks only there), so they never move an edge on their own; they are reported.
    """
    bare = ScenarioConfig("NIFTY", D("100"), D("100"), D("0"), 0, 200)
    long_call = nifty_input([nifty_leg(Action.BUY, Instrument.CE, "23000", "150.00")])
    ls = build_level_set(long_call, bare)
    assert ls.breakevens == (D("23150"),)
    assert (ls.start, ls.end) == (D("23000"), D("23200"))
    assert ls.risk_boundaries == (D("23000"),)
    # The user can customise it.
    custom = build_level_set(long_call, bare, override=RangeOverride(D("22500"), D("23500")))
    assert (custom.start, custom.end, custom.customised) == (D("22500"), D("23500"), True)


def test_ac4_admin_records_fail_closed():
    """AC-4 negative cases: unknown/missing keys, floats, absurd sizes, bad relations and duplicates are refused."""
    with pytest.raises(ValueError, match="unknown scenario config keys"):
        ScenarioConfig.from_mapping({**VALID, "stepp_points": "100"})
    missing = dict(VALID)
    del missing["margin_steps"]
    with pytest.raises(ValueError, match="missing scenario config keys"):
        ScenarioConfig.from_mapping(missing)
    bad_values = [
        {"step_points": 100.0}, {"step_points": "abc"}, {"step_points": "0"}, {"step_points": "-100"},
        {"step_points": "100.5"}, {"step_points": "20000"}, {"anchor_points": "300"},
        {"min_half_width_points": "-1"}, {"min_half_width_points": "100000"},
        {"margin_steps": -1}, {"margin_steps": 51}, {"margin_steps": True}, {"max_columns": 1},
        {"max_columns": 5000}, {"index": "nifty"}, {"index": ""},
    ]
    for change in bad_values:
        with pytest.raises(ValueError):
            ScenarioConfig.from_mapping({**VALID, **change})
    with pytest.raises(ValueError):
        ScenarioConfig.from_mapping([("index", "NIFTY")])
    with pytest.raises(ValueError, match="duplicate scenario config for NIFTY"):
        ScenarioSettings([DEFAULT_CONFIGS[0], ScenarioConfig.from_mapping(VALID)])
    with pytest.raises(ValueError):
        ScenarioSettings([])
    config = DEFAULT_CONFIGS[0]
    with pytest.raises(Exception):
        config.step_points = D("50")  # frozen: no raw state change bypassing validation
