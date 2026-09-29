"""REQ-035 AC-2, W-034: the TOTAL row's risk-based P&L % and options-only Entry Value (owner decision Q233).

Every expected value below is a hand computation (shown in each docstring), not the code's own output.
"""
import datetime
from decimal import Decimal as D

from conftest import NIFTY_EXPIRY, nifty_input, nifty_leg

from ofo.engine.legs import Action, Instrument
from ofo.table.columns import ColumnId
from ofo.table.model import build_table


def _total(inputs):
    return build_table(inputs).rows[-1]


def _long_call(ltp):
    """BUY 75 x 23000 CE @ 100: max loss = 100 x 75 = 7,500 (premium paid)."""
    return nifty_input([nifty_leg(Action.BUY, Instrument.CE, "23000", "100.00", ltp)])


def test_core_golden_condor_total_pnl_percent_and_entry_value(golden, golden_scenario):
    """AC-2 (core): golden condor credit 91, wings 200, max loss (200-91) x 75 = 8,175; unrealized (91-72.80) x 75
    = 1,365; 1,365 / 8,175 = 16.697..% -> +16.7%. Entry Value = 3,187.50 + 6,450 + 6,862.50 + 3,300 = 19,800."""
    level_set, values = golden_scenario
    total = build_table(golden, level_set=level_set, scenario=values).rows[-1]
    pct = total.cell(ColumnId.PNL_PERCENT)
    assert pct.value == D("16.7")
    assert pct.display == "+16.7%"
    assert total.cell(ColumnId.UNREALIZED_PNL).value == D("1365.00")
    assert total.cell(ColumnId.ENTRY_VALUE).value == D("19800.00")


def test_ac2_total_pnl_percent_loss_case_is_negative():
    """AC-2: golden legs, only the short 23400 CE LTP 78 -> 100.50: pnl = (91.50-100.50) x 75 = -675 (other legs
    at entry); max loss stays 8,175; -675 / 8,175 = -8.2568..% -> -8.3%."""
    rows = [("BUY", "PE", "22800", "42.50", "42.50"), ("SELL", "PE", "23000", "86.00", "86.00"),
            ("SELL", "CE", "23400", "91.50", "100.50"), ("BUY", "CE", "23600", "44.00", "44.00")]
    legs = [nifty_leg(Action[a], Instrument[i], k, e, l) for a, i, k, e, l in rows]
    cell = _total(nifty_input(legs)).cell(ColumnId.PNL_PERCENT)
    assert cell.value == D("-8.3")
    assert cell.display == "-8.3%"


def test_ac2_total_pnl_percent_rounds_half_up_at_one_decimal():
    """AC-2: long call max loss 7,500; LTP 116.65 -> pnl 16.65 x 75 = 1,248.75; 1,248.75 / 7,500 = exactly 16.65%,
    a tie at 1 dp: half-up gives 16.7 (half-even would give 16.6). Loss side: LTP 83.35 -> exactly -16.65% ->
    -16.7 (away from zero, symmetric)."""
    assert _total(_long_call("116.65")).cell(ColumnId.PNL_PERCENT).value == D("16.7")
    assert _total(_long_call("83.35")).cell(ColumnId.PNL_PERCENT).value == D("-16.7")


def test_ac2_total_pnl_percent_dash_when_max_loss_unlimited():
    """AC-2: naked short 23400 CE has an unbounded upside loss -> P&L % is '—' (reason names it), while
    Entry Value is still shown (options-only): 91.50 x 75 = 6,862.50."""
    total = _total(nifty_input([nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00")]))
    cell = total.cell(ColumnId.PNL_PERCENT)
    assert (cell.value, cell.display) == (None, "—")
    assert "unlimited" in cell.reason
    assert total.cell(ColumnId.ENTRY_VALUE).value == D("6862.50")


def test_ac2_total_pnl_percent_dash_when_max_loss_zero():
    """AC-2: SELL 22900 CE @150 + BUY 23000 CE @40 = credit 110 >= width 100, payoff never below +10 x 75 ->
    max loss 0 -> '—' (no divide by zero)."""
    legs = [nifty_leg(Action.SELL, Instrument.CE, "22900", "150.00", "150.00"),
            nifty_leg(Action.BUY, Instrument.CE, "23000", "40.00", "40.00")]
    cell = _total(nifty_input(legs)).cell(ColumnId.PNL_PERCENT)
    assert cell.value is None and cell.display == "—"
    assert "zero" in cell.reason


def test_ac2_total_pnl_percent_dash_when_a_leg_has_no_ltp():
    """AC-2: unrealized P&L is unknown without every LTP, so the % is '—' rather than computed from a guess."""
    cell = _total(_long_call(None)).cell(ColumnId.PNL_PERCENT)
    assert cell.value is None and cell.display == "—"


def test_ac2_total_pnl_percent_dash_for_multi_expiry_strategy():
    """AC-2: the engine's exact max loss needs one expiry; a calendar spread shows '—', not a wrong number."""
    later = NIFTY_EXPIRY + datetime.timedelta(days=7)
    legs = [nifty_leg(Action.BUY, Instrument.CE, "23000", "100.00", "100.00", expiry=later),
            nifty_leg(Action.SELL, Instrument.CE, "23000", "80.00", "80.00")]
    cell = _total(nifty_input(legs)).cell(ColumnId.PNL_PERCENT)
    assert cell.value is None and "single-expiry" in cell.reason


def test_ac2_total_entry_value_dash_with_a_futures_leg_but_percent_still_computed():
    """AC-2: BUY FUT 23050 (LTP 23060) + BUY 23000 PE @86 (LTP 80), 75 units: Entry Value '—' (premium and futures
    notional cannot be added). Max loss: at 0 and at 23000 the payoff is -50-86 = -136/unit -> 10,200; unrealized
    = 10 x 75 + (80-86) x 75 = 300; 300 / 10,200 = 2.94..% -> +2.9%."""
    fut = nifty_leg(Action.BUY, Instrument.FUT, None, "23050.00", "23060.00")
    put = nifty_leg(Action.BUY, Instrument.PE, "23000", "86.00", "80.00")
    total = _total(nifty_input([fut, put]))
    entry = total.cell(ColumnId.ENTRY_VALUE)
    assert entry.value is None and entry.display == "—" and entry.reason
    assert total.cell(ColumnId.PNL_PERCENT).value == D("2.9")


def test_ac2_leg_rows_entry_value_is_unaffected_by_a_futures_leg():
    """AC-2: only the TOTAL Entry Value goes to '—'; the futures leg's own cell is 23,050 x 75 = 1,728,750."""
    fut = nifty_leg(Action.BUY, Instrument.FUT, None, "23050.00", "23060.00")
    table = build_table(nifty_input([fut]))
    assert table.rows[0].cell(ColumnId.ENTRY_VALUE).value == D("1728750.00")
    assert table.rows[-1].cell(ColumnId.ENTRY_VALUE).value is None
