"""REQ-034 AC-2, AC-3, AC-5: the scenario level set (scenario-calculations.md §4, §6)."""
from decimal import Decimal as D

import pytest

from ofo.engine import MultiExpiryError, scenario_grid
from ofo.engine.legs import Action, Instrument
from ofo.scenario.config import ScenarioConfig
from ofo.scenario.levels import ColumnKind, ExpectedMove, RangeOverride, build_level_set
from scenario_fixtures import GOLDEN_SPOT, nifty_input, nifty_leg

GRID, CURRENT, ZERO = ColumnKind.GRID, ColumnKind.CURRENT, ColumnKind.ZERO_PNL

# §6 strategy expiry P&L at every 100-point level 22,000..24,000.
GOLDEN_GRID_PNL = {
    **{D(lvl): D("-8175") for lvl in range(22000, 22801, 100)},
    D("22900"): D("-675"),
    **{D(lvl): D("6825") for lvl in range(23000, 23401, 100)},
    D("23500"): D("-675"),
    **{D(lvl): D("-8175") for lvl in range(23600, 24001, 100)},
}


def _labels(level_set):
    return [(c.level, c.kinds) for c in level_set.columns]


def test_core_golden_iron_condor_level_set(golden, settings):
    """AC-5 (core proof): ... 22,900 | 22,909 (0 P&L) | 23,000 | 23,047 CURRENT | 23,100 ..., values from the engine."""
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    assert (ls.start, ls.end, ls.step) == (D("22000"), D("24000"), D("100"))
    expected = sorted(
        [(lvl, frozenset({GRID})) for lvl in GOLDEN_GRID_PNL]
        + [(D("22909"), frozenset({ZERO})), (D("23047"), frozenset({CURRENT})), (D("23491"), frozenset({ZERO}))]
    )
    assert _labels(ls) == expected
    assert len(ls.columns) == 24
    window = [c.level for c in ls.columns if D("22900") <= c.level <= D("23100")]
    assert window == [D("22900"), D("22909"), D("23000"), D("23047"), D("23100")]
    grid = scenario_grid(golden.strategy, ls.levels)
    by_level = dict(zip(grid.levels, grid.totals))
    for lvl, pnl in GOLDEN_GRID_PNL.items():
        assert by_level[lvl] == pnl, lvl
    assert by_level[D("22909")] == D("0")
    assert by_level[D("23491")] == D("0")
    assert by_level[D("23047")] == D("6825")
    # Q213: Lower / Upper BE summary values alongside the grid.
    assert (ls.lower_be, ls.upper_be) == (D("22909"), D("23491"))
    assert ls.risk_boundaries == (D("22800"), D("23600"))


def test_ac2_current_level_always_present_and_marked(golden, settings):
    """AC-2: the current level is always a column and flagged CURRENT — also under a user range that excludes it."""
    config = settings.for_index("NIFTY")
    ls = build_level_set(golden, config)
    assert [c.level for c in ls.columns if c.is_current] == [GOLDEN_SPOT]
    far = build_level_set(golden, config, override=RangeOverride(D("24000"), D("25000")))
    assert [c.level for c in far.columns if c.is_current] == [GOLDEN_SPOT]
    assert far.columns[0].level == GOLDEN_SPOT  # at its price position: below the user's range
    # A current level that is itself a grid level is flagged, not duplicated.
    on_grid = build_level_set(nifty_input([nifty_leg(*row) for row in _golden_rows()], spot=D("23100")), config)
    matches = [c for c in on_grid.columns if c.level == D("23100")]
    assert len(matches) == 1 and matches[0].kinds == frozenset({GRID, CURRENT})


def test_ac2_range_not_centred_on_spot(settings):
    """AC-2: the default range follows the strategy, not spot: far-away strikes stretch one side only."""
    far_calls = nifty_input([
        nifty_leg(Action.BUY, Instrument.CE, "25000", "20.00"),
        nifty_leg(Action.SELL, Instrument.CE, "25500", "8.00"),
    ])
    ls = build_level_set(far_calls, settings.for_index("NIFTY"))
    # Spot 23,047 -> anchor 23,000 -> at least 22,000 below; strikes to 25,500 + 2 steps = 25,700 above.
    assert (ls.start, ls.end) == (D("22000"), D("25700"))
    assert ls.end - GOLDEN_SPOT != GOLDEN_SPOT - ls.start
    # One breakeven (25,012), profit above it -> it is the Lower BE; the Upper BE is missing ("—").
    assert ls.breakevens == (D("25012"),)
    assert (ls.lower_be, ls.upper_be) == (D("25012"), None)


def test_ac3_nifty_default_step_100_and_width_from_ac4(golden, settings):
    """AC-3: NIFTY step 100; width follows AC-4 — the golden Iron Condor reads 22,000 ... 24,000 (T1 #83 example)."""
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    grid = [c.level for c in ls.columns if GRID in c.kinds]
    assert grid == [D(x) for x in range(22000, 24001, 100)]
    assert {b - a for a, b in zip(grid, grid[1:])} == {D("100")}
    # Width is not fixed: an expected move of 20 % IV over 30 days (23,047 x 0.2 x sqrt(30/365) = 1,321.5 -> 1,322)
    # widens it to 23,047 +/- 1,322 plus 2 steps: 21,525 -> 21,500 and 24,569 -> 24,600.
    wide = build_level_set(golden, settings.for_index("NIFTY"), expected_move=ExpectedMove(D("0.20"), 30))
    assert wide.expected_move_points == D("1322")
    assert (wide.start, wide.end) == (D("21500"), D("24600"))


def test_ac5_breakeven_on_grid_level_is_flagged_not_duplicated(settings):
    """AC-5: a breakeven equal to a grid level becomes a flag on that column, never a second column."""
    # SELL 23,000 PE @ 100 -> breakeven exactly 22,900 (a grid level).
    short_put = nifty_input([nifty_leg(Action.SELL, Instrument.PE, "23000", "100.00")])
    ls = build_level_set(short_put, settings.for_index("NIFTY"))
    at = [c for c in ls.columns if c.level == D("22900")]
    assert len(at) == 1 and at[0].kinds == frozenset({GRID, ZERO})
    assert len(ls.levels) == len(set(ls.levels))
    # Short put: profit above the breakeven -> Lower BE.
    assert (ls.lower_be, ls.upper_be) == (D("22900"), None)


def test_ac5_grid_anchored_to_rounded_levels_index_points(golden, settings):
    """AC-5: every grid column is a multiple of the 100-point anchor; inserted columns keep their exact level."""
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    for column in ls.columns:
        if GRID in column.kinds:
            assert column.level % D("100") == 0
        else:
            assert column.level % D("100") != 0
    assert [c.level for c in ls.columns] == sorted(c.level for c in ls.columns)


def test_ac5_sensex_real_strikes_step_300(sensex, settings, catalogue):
    """AC-5: SENSEX (real fixture strikes, gap 100) lays its grid on 300-point multiples with inserted columns."""
    config = settings.for_index("SENSEX")
    assert config.check_against_catalogue(catalogue, sensex.legs[0].expiry) == D("100")
    ls = build_level_set(sensex, config)
    # spot 75,530.45 -> anchor 75,600; min width 3,000 -> 72,600 .. 78,600 covers strikes 74,700..76,500 +/- 600.
    assert (ls.start, ls.end, ls.step) == (D("72600"), D("78600"), D("300"))
    grid = [c.level for c in ls.columns if GRID in c.kinds]
    assert grid == [D(x) for x in range(72600, 78601, 300)]
    assert all(level % D("100") == 0 for level in grid)  # every column on a real strike level
    # Net credit 180 + 170 - 60 - 55 = 235/unit -> breakevens 75,300 - 235 and 75,900 + 235.
    assert ls.breakevens == (D("75065"), D("76135"))
    inserted = [(c.level, c.kinds) for c in ls.columns if GRID not in c.kinds]
    assert inserted == [(D("75065"), frozenset({ZERO})), (D("75530.45"), frozenset({CURRENT})),
                        (D("76135"), frozenset({ZERO}))]
    grid_pnl = dict(zip(ls.levels, scenario_grid(sensex.strategy, ls.levels).totals))
    assert grid_pnl[D("75065")] == D("0") and grid_pnl[D("76135")] == D("0")
    assert grid_pnl[D("75600")] == D("4700")  # 235 x 20 (lot size from the real fixture)


def test_override_accepted_within_bounds_and_refused_outside(golden, settings):
    """AC-2/AC-4: a user range on the grid is accepted as given; off-grid, reversed or oversized ranges are refused."""
    config = settings.for_index("NIFTY")
    ls = build_level_set(golden, config, override=RangeOverride(D("22500"), D("23500")))
    assert ls.customised and (ls.start, ls.end) == (D("22500"), D("23500"))
    assert [c.level for c in ls.columns if c.is_zero_pnl] == [D("22909"), D("23491")]
    # A breakeven outside the user's range is not inserted (the Lower/Upper BE summary still shows it).
    narrow = build_level_set(golden, config, override=RangeOverride(D("23000"), D("23400")))
    assert [c.level for c in narrow.columns if c.is_zero_pnl] == []
    assert (narrow.lower_be, narrow.upper_be) == (D("22909"), D("23491"))
    for bad in [(D("22550"), D("23500")), (D("23500"), D("22500")), (D("22500"), D("22500")),
                (D("0"), D("23000")), (D("-100"), D("23000")), (D("2000"), D("40000"))]:
        with pytest.raises(ValueError):
            build_level_set(golden, config, override=RangeOverride(*bad))
    with pytest.raises(ValueError):
        build_level_set(golden, config, override=(D("22500"), D("23500")))


def test_inputs_fail_closed(golden, settings):
    """Negative cases: wrong index config, multi-expiry strategy, bad expected-move inputs are refused."""
    with pytest.raises(ValueError, match="config is for SENSEX"):
        build_level_set(golden, settings.for_index("SENSEX"))
    import datetime
    two_expiries = nifty_input([
        nifty_leg(Action.BUY, Instrument.CE, "23000", "100.00"),
        nifty_leg(Action.SELL, Instrument.CE, "23000", "60.00", expiry=datetime.date(2026, 11, 24)),
    ])
    with pytest.raises(MultiExpiryError):
        build_level_set(two_expiries, settings.for_index("NIFTY"))
    for iv, days in [(D("0"), 30), (D("-0.1"), 30), (D("6"), 30), (D("0.2"), 0), (D("0.2"), 100000),
                     (D("0.2"), True), (0.2, 30), (D("NaN"), 30)]:
        with pytest.raises(ValueError):
            ExpectedMove(iv, days)
    tight = ScenarioConfig("NIFTY", D("100"), D("100"), D("1000"), 2, 5)
    with pytest.raises(ValueError, match="maximum is 5"):
        build_level_set(golden, tight)


def _golden_rows():
    from scenario_fixtures import GOLDEN_LEGS
    return GOLDEN_LEGS
