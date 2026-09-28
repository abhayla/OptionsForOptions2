"""REQ-035: the single strategy table. Core proof: the golden Iron Condor table matches AC-2's locked column
order and every leg/total cell exactly (scenario-calculations.md §6).
"""
from decimal import Decimal as D

import pytest

from ofo.engine.inputs import LegInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.black_scholes import Greeks
from ofo.table.columns import ColumnId
from ofo.table.model import CellKind, TOTAL_ROW_ID, build_table

from conftest import NIFTY_EXPIRY, nifty_input, nifty_leg

FIXED_ORDER = [
    ColumnId.LEG, ColumnId.ACTION, ColumnId.INSTRUMENT, ColumnId.EXPIRY, ColumnId.STRIKE, ColumnId.QUANTITY,
    ColumnId.ENTRY_PRICE, ColumnId.LTP, ColumnId.ENTRY_VALUE, ColumnId.CURRENT_VALUE, ColumnId.UNREALIZED_PNL,
    ColumnId.PNL_PERCENT, ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA,
]
TRAILING_ORDER = [ColumnId.LOWER_BE, ColumnId.UPPER_BE, ColumnId.STATUS]

LEG_ENTRY_VALUES = [D("3187.50"), D("6450"), D("6862.50"), D("3300")]
LEG_LIVE_PNL = [D("-322.50"), D("1012.50"), D("1012.50"), D("-337.50")]
LEG_PNL_PERCENT = [D("-10.12"), D("15.70"), D("14.75"), D("-10.23")]
LEG_CURRENT_VALUES = [D("2865"), D("5437.50"), D("5850"), D("2962.50")]

LEG_GREEKS = [
    Greeks(D("-0.2560"), D("0.0007"), D("-6.1454"), D("12.2756")),
    Greeks(D("-0.4125"), D("0.0009"), D("-6.3666"), D("14.8510")),
    Greeks(D("0.1947"), D("0.0008"), D("-5.6963"), D("10.5071")),
    Greeks(D("0.0992"), D("0.0004"), D("-3.8114"), D("6.6575")),
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
    assert total.cell(ColumnId.PNL_PERCENT).value == D("6.89")
    assert total.cell(ColumnId.LOWER_BE).value == D("22909")
    assert total.cell(ColumnId.UPPER_BE).value == D("23491")


def test_ac2_scenario_level_columns_match_engine_exactly(golden, golden_scenario):
    """AC-2: the scenario level cells are exactly ofo.scenario's totals/leg_rows, never recomputed."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    for i, level in enumerate(level_set.levels):
        assert table.rows[-1].cell(level).value == values.totals[i]
        for leg_idx in range(4):
            assert table.rows[leg_idx].cell(level).value == values.leg_rows[leg_idx][i]


def test_ac6_iv_and_greeks_from_platform_black_scholes(golden, golden_scenario):
    """AC-6: IV and Greeks are the platform's Black-Scholes, computed from each leg's own IV."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    ivs = [D("0.117446"), D("0.108838"), D("0.093349"), D("0.102360")]
    for i, row in enumerate(table.rows[:4]):
        assert row.cell(ColumnId.IV).value == ivs[i]
        assert row.cell(ColumnId.DELTA).value == LEG_GREEKS[i].delta
        assert row.cell(ColumnId.GAMMA).value == LEG_GREEKS[i].gamma
        assert row.cell(ColumnId.THETA).value == LEG_GREEKS[i].theta
        assert row.cell(ColumnId.VEGA).value == LEG_GREEKS[i].vega
    total = table.rows[-1]
    for name, expected in TOTAL_GREEKS.items():
        cid = {"delta": ColumnId.DELTA, "gamma": ColumnId.GAMMA, "theta": ColumnId.THETA,
               "vega": ColumnId.VEGA}[name]
        assert total.cell(cid).value == expected


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
    assert delta_cell.value == LEG_GREEKS[0].delta  # the platform value, not the vendor's -0.9999
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
    for cid in (ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        cell = row.cell(cid)
        assert cell.value is None
        assert cell.reason
    assert row.cell(ColumnId.UNREALIZED_PNL).value == D("-322.50")
    assert row.cell(ColumnId.ENTRY_VALUE).value == D("3187.50")
    # a leg missing IV means the TOTAL row's Greeks are None too, never a partial sum.
    total = table.rows[-1]
    for cid in (ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        cell = total.cell(cid)
        assert cell.value is None
        assert cell.reason


def test_futures_leg_has_no_strike_no_iv_dash_where_not_applicable():
    """Red case: a futures leg row shows '—' (None + reason) for Strike, IV and every Greek."""
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
    assert row.cell(ColumnId.DELTA).value is None
    assert row.cell(ColumnId.STATUS).value is None
    # its live P&L is still exact: (23060 - 23050) * 75
    assert row.cell(ColumnId.UNREALIZED_PNL).value == D("750.00")


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
