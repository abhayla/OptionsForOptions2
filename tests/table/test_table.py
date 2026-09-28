"""REQ-035: the single strategy table. Core proof: the golden Iron Condor table matches AC-2's locked column
order and every leg/total cell exactly (scenario-calculations.md §6).
"""
from decimal import Decimal as D

import pytest

from ofo.engine.inputs import LegInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.black_scholes import Greeks
from ofo.table.columns import ColumnId
from ofo.table.model import CellKind, StrategyHealth, TOTAL_ROW_ID, build_table

from conftest import NIFTY_EXPIRY, nifty_input, nifty_leg

FIXED_ORDER = [
    ColumnId.LEG, ColumnId.ACTION, ColumnId.INSTRUMENT, ColumnId.EXPIRY, ColumnId.STRIKE, ColumnId.QUANTITY,
    ColumnId.ENTRY_PRICE, ColumnId.LTP, ColumnId.ENTRY_VALUE, ColumnId.CURRENT_VALUE, ColumnId.UNREALIZED_PNL,
    ColumnId.PNL_PERCENT, ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA,
]
TRAILING_ORDER = [ColumnId.LOWER_BE, ColumnId.UPPER_BE, ColumnId.STATUS]
GREEK_COLUMNS = [ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA]

LEG_ENTRY_VALUES = [D("3187.50"), D("6450"), D("6862.50"), D("3300")]
LEG_LIVE_PNL = [D("-322.50"), D("1012.50"), D("1012.50"), D("-337.50")]
LEG_PNL_PERCENT = [D("-10.12"), D("15.70"), D("14.75"), D("-10.23")]
LEG_CURRENT_VALUES = [D("2865"), D("5437.50"), D("5850"), D("2962.50")]

# Platform Black-Scholes PER-UNIT Greeks (Cell.per_unit — the secondary, Advanced-only field).
PER_UNIT_GREEKS = [
    Greeks(D("-0.2560"), D("0.0007"), D("-6.1454"), D("12.2756")),
    Greeks(D("-0.4125"), D("0.0009"), D("-6.3666"), D("14.8510")),
    Greeks(D("0.1947"), D("0.0008"), D("-5.6963"), D("10.5071")),
    Greeks(D("0.0992"), D("0.0004"), D("-3.8114"), D("6.6575")),
]
# POSITION Greeks (per_unit x quantity x sign: BUY +1, SELL -1) — Cell.value, the table's ONE Greek unit
# (fix round: leg cells used to be per-unit while the TOTAL row was position-level; now both are position-level
# and TOTAL = sum of the leg cells exactly, proven below).
POSITION_GREEKS = [
    Greeks(D("-19.2000"), D("0.0525"), D("-460.9050"), D("920.6700")),   # leg 1: BUY x 75
    Greeks(D("30.9375"), D("-0.0675"), D("477.4950"), D("-1113.8250")),  # leg 2: SELL x 75
    Greeks(D("-14.6025"), D("-0.0600"), D("427.2225"), D("-788.0325")),  # leg 3: SELL x 75
    Greeks(D("7.4400"), D("0.0300"), D("-285.8550"), D("499.3125")),     # leg 4: BUY x 75
]
TOTAL_GREEKS = {"delta": D("4.5750"), "gamma": D("-0.0450"), "theta": D("157.9575"), "vega": D("-481.8750")}


def test_core_golden_iron_condor_column_order_matches_ac2(golden, golden_scenario):
    """Core/AC-2: the table's column order is exactly Leg..Vega, the scenario levels, Lower BE, Upper BE, Status."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    ids = table.column_ids
    assert ids[: len(FIXED_ORDER)] == tuple(FIXED_ORDER)
    n_levels = len(level_set.levels)
    assert ids[len(FIXED_ORDER): len(FIXED_ORDER) + n_levels] == level_set.levels
    assert ids[len(FIXED_ORDER) + n_levels:] == tuple(TRAILING_ORDER)


def test_ac1_exactly_one_table_five_rows(golden, golden_scenario):
    """AC-1: one table, one row per leg (4) plus one TOTAL row, never two tables."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert len(table.rows) == 5
    assert [r.row_id for r in table.rows] == ["1", "2", "3", "4", TOTAL_ROW_ID]


def test_ac2_leg_row_values_exact(golden, golden_scenario):
    """AC-2: every leg row's core money/points cells are exact engine values, no re-derivation."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    expected_actions = [Action.BUY, Action.SELL, Action.SELL, Action.BUY]
    expected_instruments = [Instrument.PE, Instrument.PE, Instrument.CE, Instrument.CE]
    expected_strikes = [D("22800"), D("23000"), D("23400"), D("23600")]
    for i, row in enumerate(table.rows[:4]):
        assert row.cell(ColumnId.LEG).value == str(i + 1)
        assert row.cell(ColumnId.ACTION).value == expected_actions[i].value
        assert row.cell(ColumnId.INSTRUMENT).value == expected_instruments[i].value
        assert row.cell(ColumnId.EXPIRY).value == NIFTY_EXPIRY.isoformat()
        assert row.cell(ColumnId.STRIKE).value == expected_strikes[i]
        assert row.cell(ColumnId.QUANTITY).value == 75
        assert row.cell(ColumnId.ENTRY_VALUE).value == LEG_ENTRY_VALUES[i]
        assert row.cell(ColumnId.CURRENT_VALUE).value == LEG_CURRENT_VALUES[i]
        assert row.cell(ColumnId.UNREALIZED_PNL).value == LEG_LIVE_PNL[i]
        assert row.cell(ColumnId.PNL_PERCENT).value == LEG_PNL_PERCENT[i]


def test_ac2_total_row_values_exact(golden, golden_scenario):
    """AC-2: the strategy TOTAL row sums the legs exactly (§6: net +1,365.00 live P&L)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    total = table.rows[-1]
    assert total.cell(ColumnId.ENTRY_VALUE).value == D("19800.00")
    assert total.cell(ColumnId.UNREALIZED_PNL).value == D("1365.00")
    assert total.cell(ColumnId.LOWER_BE).value == D("22909")
    assert total.cell(ColumnId.UPPER_BE).value == D("23491")


def test_fix_round_total_pnl_percent_is_always_a_dash(golden, golden_scenario):
    """Fix round item 4: the TOTAL row's P&L % is always '—' (owner-reviewed source leaves it blank;
    gross entry value misleads for a net-credit strategy — open owner question, never computed)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    cell = table.rows[-1].cell(ColumnId.PNL_PERCENT)
    assert cell.value is None
    assert cell.display == "—"
    assert cell.reason
    # a leg's P&L % is unaffected: it still uses unrealized / |entry value| x 100.
    assert table.rows[0].cell(ColumnId.PNL_PERCENT).value == LEG_PNL_PERCENT[0]


def test_ac2_scenario_level_columns_match_engine_exactly(golden, golden_scenario):
    """AC-2: the scenario level cells are exactly ofo.scenario's totals/leg_rows, never recomputed."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    for i, level in enumerate(level_set.levels):
        assert table.rows[-1].cell(level).value == values.totals[i]
        for leg_idx in range(4):
            assert table.rows[leg_idx].cell(level).value == values.leg_rows[leg_idx][i]


def test_ac6_iv_and_greeks_from_platform_black_scholes(golden, golden_scenario):
    """AC-6: IV cells are exact; Greek cells are POSITION-level (per-unit x quantity x sign), the platform's
    per-unit Black-Scholes value kept as the secondary ``per_unit`` field (fix round)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    ivs = [D("0.117446"), D("0.108838"), D("0.093349"), D("0.102360")]
    for i, row in enumerate(table.rows[:4]):
        assert row.cell(ColumnId.IV).value == ivs[i]
        for j, cid in enumerate(GREEK_COLUMNS):
            name = ("delta", "gamma", "theta", "vega")[j]
            cell = row.cell(cid)
            assert cell.value == getattr(POSITION_GREEKS[i], name)
            assert cell.per_unit == getattr(PER_UNIT_GREEKS[i], name)
    total = table.rows[-1]
    for name, expected in TOTAL_GREEKS.items():
        cid = {"delta": ColumnId.DELTA, "gamma": ColumnId.GAMMA, "theta": ColumnId.THETA,
               "vega": ColumnId.VEGA}[name]
        assert total.cell(cid).value == expected


def test_fix_round_leg_greeks_sum_exactly_to_total_greeks(golden, golden_scenario):
    """Fix round Proof (Class: one column mixing per-unit and position-level units): the four leg Delta cells
    (and Gamma, Theta, Vega) must SUM to the TOTAL cell — same unit throughout the column, red before the fix."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    for cid in GREEK_COLUMNS:
        leg_sum = sum((table.rows[i].cell(cid).value for i in range(4)), D(0))
        assert leg_sum == table.rows[-1].cell(cid).value, cid


def test_fix_round_futures_leg_delta_is_position_level_and_included_in_total():
    """Fix round Proof: a table with one SELL NIFTY FUT x 75 shows leg Delta -75 and TOTAL Delta -75 (futures
    legs were silently excluded from the TOTAL Greek aggregate — the second half of the Class defect)."""
    fut_leg = LegInput(
        underlying="NIFTY", contract="NIFTY26OCTFUT", action=Action.SELL, instrument=Instrument.FUT,
        strike=None, expiry=NIFTY_EXPIRY, quantity=75, premium=D("23050.00"), ltp=D("23060.00"),
    )
    inputs = nifty_input([fut_leg])
    table = build_table(inputs)
    row = table.rows[0]
    assert row.cell(ColumnId.DELTA).value == D("-75")
    assert row.cell(ColumnId.GAMMA).value == D("0")
    assert row.cell(ColumnId.THETA).value == D("0")
    assert row.cell(ColumnId.VEGA).value == D("0")
    total = table.rows[-1]
    assert total.cell(ColumnId.DELTA).value == D("-75")
    # per-unit for a futures leg (secondary field): +1 magnitude, direction applied like any other leg.
    assert row.cell(ColumnId.DELTA).per_unit == D("1")


def test_ac6_vendor_greek_is_a_reference_field_never_the_value(golden_scenario):
    """AC-6: a vendor Greek is kept only as a reference (``Cell.vendor``); it never replaces the platform value."""
    level_set, values = golden_scenario
    vendor_greeks = Greeks(D("-0.9999"), D("0.9999"), D("0.9999"), D("0.9999"))
    legs = [
        nifty_leg(Action.BUY, Instrument.PE, "22800", "42.50", "38.20", "0.117446", greeks=vendor_greeks),
        nifty_leg(Action.SELL, Instrument.PE, "23000", "86.00", "72.50", "0.108838"),
        nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349"),
        nifty_leg(Action.BUY, Instrument.CE, "23600", "44.00", "39.50", "0.102360"),
    ]
    inputs = nifty_input(legs)
    table = build_table(inputs, level_set=level_set, scenario=values)
    delta_cell = table.rows[0].cell(ColumnId.DELTA)
    assert delta_cell.value == POSITION_GREEKS[0].delta  # the platform position value, not the vendor's -0.9999
    assert delta_cell.value != vendor_greeks.delta
    assert delta_cell.vendor == vendor_greeks.delta


def test_missing_iv_gives_none_greeks_with_reason_but_exact_pnl(golden_scenario):
    """Red case: a leg with no IV gets None IV/Greek cells and a reason; its P&L cells stay exact."""
    level_set, values = golden_scenario
    legs = [
        nifty_leg(Action.BUY, Instrument.PE, "22800", "42.50", "38.20", iv=None),
        nifty_leg(Action.SELL, Instrument.PE, "23000", "86.00", "72.50", "0.108838"),
        nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349"),
        nifty_leg(Action.BUY, Instrument.CE, "23600", "44.00", "39.50", "0.102360"),
    ]
    inputs = nifty_input(legs)
    table = build_table(inputs, level_set=level_set, scenario=values)
    row = table.rows[0]
    assert row.cell(ColumnId.IV).value is None
    assert row.cell(ColumnId.IV).reason
    for cid in GREEK_COLUMNS:
        cell = row.cell(cid)
        assert cell.value is None
        assert cell.reason
    assert row.cell(ColumnId.UNREALIZED_PNL).value == D("-322.50")
    assert row.cell(ColumnId.ENTRY_VALUE).value == D("3187.50")
    # a leg missing IV means the TOTAL row's Greeks are None too, never a partial sum.
    total = table.rows[-1]
    for cid in GREEK_COLUMNS:
        cell = total.cell(cid)
        assert cell.value is None
        assert cell.reason


def test_futures_leg_strike_and_iv_dash_but_greeks_and_pnl_populated():
    """Red case: a futures leg has no Strike/IV ('—' + reason), but its Greeks (position-level, fix round) and
    P&L are populated, not dashed."""
    fut_leg = LegInput(
        underlying="NIFTY", contract="NIFTY26OCTFUT", action=Action.BUY, instrument=Instrument.FUT,
        strike=None, expiry=NIFTY_EXPIRY, quantity=75, premium=D("23050.00"), ltp=D("23060.00"),
    )
    other_leg = nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349")
    inputs = nifty_input([fut_leg, other_leg])
    table = build_table(inputs)
    row = table.rows[0]
    assert row.cell(ColumnId.STRIKE).value is None
    assert row.cell(ColumnId.STRIKE).reason
    assert row.cell(ColumnId.IV).value is None
    assert "futures" in row.cell(ColumnId.IV).reason
    assert row.cell(ColumnId.DELTA).value == D("75")  # BUY x 75, per-unit 1
    assert row.cell(ColumnId.GAMMA).value == D("0")
    # its live P&L is still exact: (23060 - 23050) * 75
    assert row.cell(ColumnId.UNREALIZED_PNL).value == D("750.00")


def test_status_leg_and_total_are_caller_supplied_not_computed(golden, golden_scenario):
    """Fix round item 3: leg Status is the caller-supplied state; TOTAL Status is the caller-supplied
    StrategyHealth using ADR-010 lines 29-30's exact labels. No status given -> '—'."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    total = table.rows[-1]
    assert table.rows[0].cell(ColumnId.STATUS).value is None
    assert table.rows[0].cell(ColumnId.STATUS).reason
    assert total.cell(ColumnId.STATUS).value is None
    assert total.cell(ColumnId.STATUS).reason

    table2 = build_table(
        golden, level_set=level_set, scenario=values,
        leg_statuses=["Open", "Open", "Open", "Open"],
        strategy_health=StrategyHealth.WATCH,
    )
    for row in table2.rows[:4]:
        assert row.cell(ColumnId.STATUS).value == "Open"
    assert table2.rows[-1].cell(ColumnId.STATUS).value == "Watch"


def test_strategy_health_labels_match_adr_010_exactly():
    """ADR-010 lines 29-30 (Q20 = B, T1 #41): the owner's exact four strategy-health labels."""
    assert {h.value for h in StrategyHealth} == {
        "Healthy", "Watch", "Adjustment opportunity", "Exit condition reached",
    }


def test_leg_statuses_length_must_match_legs(golden):
    """Fail closed: leg_statuses must have one entry per leg."""
    with pytest.raises(ValueError):
        build_table(golden, leg_statuses=["Open"])


def test_strategy_health_rejects_a_plain_string(golden):
    """Fail closed: strategy_health must be a StrategyHealth, not an arbitrary string."""
    with pytest.raises(ValueError):
        build_table(golden, strategy_health="Healthy")


def test_build_table_without_scenario_leaves_no_scenario_columns():
    """No scenario view given: no scenario level columns, and Lower/Upper BE show unavailable, not an error."""
    inputs = nifty_input(nifty_leg(*row) for row in [
        (Action.BUY, Instrument.PE, "22800", "42.50", "38.20", "0.117446"),
    ])
    table = build_table(inputs)
    ids = table.column_ids
    assert ids == tuple(FIXED_ORDER) + tuple(TRAILING_ORDER)
    total = table.rows[-1]
    assert total.cell(ColumnId.LOWER_BE).value is None
    assert total.cell(ColumnId.LOWER_BE).reason


def test_build_table_rejects_mismatched_inputs_type():
    """Fail closed: build_table refuses a non-StrategyInput."""
    with pytest.raises(ValueError):
        build_table("not a strategy input")


def test_build_table_rejects_level_set_without_scenario(golden, golden_scenario):
    """Fail closed: level_set and scenario must be given together."""
    level_set, _values = golden_scenario
    with pytest.raises(ValueError):
        build_table(golden, level_set=level_set)
