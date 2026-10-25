"""Issue #209 / ADR-076: TOTAL Current Value is the NET current premium (sells minus buys at LTP x quantity)
with a Cr/Dr side, exactly the shape of TOTAL Entry Value. Expected values are hand-computed in each docstring."""
from decimal import Decimal as D

import pytest

from ofo.engine.inputs import LegInput
from ofo.engine.legs import Action, Instrument
from ofo.table.columns import ColumnId
from ofo.table.model import TOTAL_ROW_ID, build_table

from table_fixtures import NIFTY_EXPIRY, nifty_input, nifty_leg

REAL_2026_10_15 = [
    (Action.SELL, Instrument.CE, "23200", "42.70", "42.00"),
    (Action.BUY, Instrument.CE, "23400", "14.10", "13.80"),
    (Action.SELL, Instrument.PE, "22800", "75.05", "76.00"),
    (Action.BUY, Instrument.PE, "22600", "38.85", "39.10"),
]
ALL_BUY = [
    (Action.BUY, Instrument.CE, "23200", "40.00", "45.00"),
    (Action.BUY, Instrument.PE, "22800", "30.00", "28.00"),
]
ALL_SELL = [
    (Action.SELL, Instrument.CE, "23200", "40.00", "45.00"),
    (Action.SELL, Instrument.PE, "22800", "30.00", "28.00"),
]


def _total(rows, qty=65, extra=()):
    legs = [nifty_leg(a, i, k, e, l, quantity=qty) for a, i, k, e, l in rows] + list(extra)
    return build_table(nifty_input(legs)).rows[-1]


def _signed(cell) -> D:
    return cell.value if cell.side == "Cr" else -cell.value if cell.side == "Dr" else D(0)


def test_core_real_case_total_current_value_is_net_credit():
    """Core: sells (42.00 + 76.00) x 65 = 7670.00; buys (13.80 + 39.10) x 65 = 3438.50; net 4231.50 Cr.
    Entry (42.70 + 75.05 - 14.10 - 38.85) x 65 = 4212.00 Cr; 4212.00 - 4231.50 = -19.50 = TOTAL Unrealized P&L."""
    total = _total(REAL_2026_10_15)
    cv = total.cell(ColumnId.CURRENT_VALUE)
    assert (cv.value, cv.side) == (D("4231.50"), "Cr")
    assert cv.display.endswith(" Cr") and "4,231.50" in cv.display
    ev = total.cell(ColumnId.ENTRY_VALUE)
    assert (ev.value, ev.side) == (D("4212.00"), "Cr")
    assert total.cell(ColumnId.UNREALIZED_PNL).value == D("-19.50")


def test_all_buy_total_current_value_is_debit():
    """Buys (45 + 28) x 65 = 4745 -> 4745.00 Dr; entry (40 + 30) x 65 = 4550 Dr; pnl = 5x65 - 2x65 = 195."""
    total = _total(ALL_BUY)
    cv = total.cell(ColumnId.CURRENT_VALUE)
    assert (cv.value, cv.side) == (D("4745.00"), "Dr")
    assert total.cell(ColumnId.UNREALIZED_PNL).value == D("195.00")


def test_all_sell_total_current_value_is_credit():
    """Sells (45 + 28) x 65 = 4745 Cr; entry 4550 Cr; pnl = -195."""
    total = _total(ALL_SELL)
    cv = total.cell(ColumnId.CURRENT_VALUE)
    assert (cv.value, cv.side) == (D("4745.00"), "Cr")
    assert total.cell(ColumnId.UNREALIZED_PNL).value == D("-195.00")


def test_zero_net_has_no_side():
    """SELL 40 and BUY 40 at LTP, same quantity: net 0 -> no side (same as Entry Value)."""
    total = _total([(Action.SELL, Instrument.CE, "23200", "40", "40"),
                    (Action.BUY, Instrument.PE, "22800", "40", "40")])
    cv = total.cell(ColumnId.CURRENT_VALUE)
    assert (cv.value, cv.side) == (D("0"), None)


def test_futures_leg_total_current_value_is_dash():
    """Red case: a FUT leg makes TOTAL Current Value '—' (as TOTAL Entry Value)."""
    fut = LegInput(underlying="NIFTY", contract="NIFTY26OCTFUT", action=Action.BUY, instrument=Instrument.FUT,
                   strike=None, expiry=NIFTY_EXPIRY, quantity=75, premium=D("23050.00"), ltp=D("23060.00"))
    total = _total(REAL_2026_10_15[:1], extra=[fut])
    cv = total.cell(ColumnId.CURRENT_VALUE)
    assert cv.value is None and cv.display == "—" and cv.reason
    assert total.cell(ColumnId.ENTRY_VALUE).display == "—"


def test_missing_ltp_total_current_value_is_dash():
    """Red case: a leg without an LTP makes TOTAL Current Value '—'."""
    legs = [nifty_leg(Action.SELL, Instrument.CE, "23200", "42.70", "42.00", quantity=65),
            nifty_leg(Action.BUY, Instrument.PE, "22600", "38.85", None, quantity=65)]
    cv = build_table(nifty_input(legs)).rows[-1].cell(ColumnId.CURRENT_VALUE)
    assert cv.value is None and cv.display == "—" and cv.reason == "not every leg has an LTP"


@pytest.mark.parametrize("rows", [REAL_2026_10_15, ALL_BUY, ALL_SELL], ids=["mixed", "all-buy", "all-sell"])
def test_entry_minus_current_equals_total_unrealized_pnl(rows):
    """Consistency (detection): signed Entry - signed Current = TOTAL Unrealized P&L for every options-only case."""
    total = _total(rows)
    diff = _signed(total.cell(ColumnId.ENTRY_VALUE)) - _signed(total.cell(ColumnId.CURRENT_VALUE))
    assert diff == total.cell(ColumnId.UNREALIZED_PNL).value
    assert total.row_id == TOTAL_ROW_ID
