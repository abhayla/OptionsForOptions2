"""GC-UI step 2 round 2b: every IV and Greek cell carries the exact text the browser prints (REQ-145 AC-3, AC-8).

Inputs are the REAL recorded reply (scratch gcui-checker run1 a_debit_spread_s54 outcome_estimated_now.json, leg 1):
IV 0.160347; delta position 40.7883, per unit 0.6275126604423561; gamma 0.0523 / 0.0008050247282850743;
theta -1122.3449 / -17.266844940108367; vega 721.0948 / 11.0937662602045.
"""
from decimal import Decimal as D

from conftest import nifty_input, nifty_leg
from ofo.engine.legs import Action, Instrument
from ofo.outcome.serialize import _cell
from ofo.table.columns import ColumnId
from ofo.table.model import TOTAL_ROW_ID, _greek_cell, _iv_cell, build_table


def _greek(position, per_unit, places):
    return _cell(_greek_cell(D(position), None, D(per_unit), None, places=places, unrounded=D(position)))


def test_core_real_reply_iv_and_delta_cells_carry_the_browser_text():
    leg = nifty_leg(Action.BUY, Instrument.CE, "22400", "81.30", ltp="85", iv="0.160347")
    iv = _cell(_iv_cell(leg))
    assert iv["value"] == "0.160347" and iv["display"] == "16.03%"
    delta = _greek("40.7883", "0.6275126604423561", 2)
    assert delta["per_unit"] == "0.6275"
    assert delta["per_unit_display"] == "0.63"
    assert delta["display"] == "40.79"
    assert delta["value"] == "40.7883"


def test_gamma_four_places_theta_vega_two_places_negative_sign_kept():
    gamma = _greek("0.0523", "0.0008050247282850743", 4)
    assert (gamma["display"], gamma["per_unit_display"], gamma["per_unit"]) == ("0.0523", "0.0008", "0.0008")
    theta = _greek("-1122.3449", "-17.266844940108367", 2)
    assert (theta["display"], theta["per_unit_display"], theta["per_unit"]) == ("-1122.34", "-17.27", "-17.2668")
    vega = _greek("721.0948", "11.0937662602045", 2)
    assert (vega["display"], vega["per_unit_display"]) == ("721.09", "11.09")


def test_round_half_up_not_half_even_at_the_display_boundary():
    cell = _greek("0.125", "0.125", 2)
    assert cell["display"] == "0.13" and cell["per_unit_display"] == "0.13"
    iv = _cell(_iv_cell(nifty_leg(Action.BUY, Instrument.CE, "22400", "81.30", iv="0.18365")))
    assert iv["display"] == "18.37%"  # half-up at the second decimal (REQ-145 AC-3 example family)


def _rows(legs):
    return {r.row_id: {str(k): _cell(c) for k, c in r.cells.items()} for r in build_table(nifty_input(legs)).rows}


def test_answer_states_show_dash_or_null_never_zero_or_nan():
    legs = [nifty_leg(Action.BUY, Instrument.CE, "22400", "81.30", ltp="85", iv="0.160347"),
            nifty_leg(Action.SELL, Instrument.PE, "22300", "30.00", ltp="31", iv=None),
            nifty_leg(Action.BUY, Instrument.FUT, None, "22500", ltp="22510")]
    rows = _rows(legs)
    leg_ids = [k for k in rows if k != TOTAL_ROW_ID]
    no_iv, fut = rows[leg_ids[1]], rows[leg_ids[2]]
    for col in (ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        cell = no_iv[str(col)]
        assert cell["display"] == "—" and cell["value"] is None, col
        assert cell.get("per_unit_display") is None, col
    assert fut[str(ColumnId.IV)]["display"] == "—" and fut[str(ColumnId.IV)]["value"] is None
    assert fut[str(ColumnId.DELTA)]["per_unit_display"] == "1.00"
    assert fut[str(ColumnId.GAMMA)]["per_unit_display"] == "0.0000"
    for cells in rows.values():
        for cell in cells.values():
            for text in (cell["display"], cell.get("per_unit_display")):
                assert text is None or text.lower() not in ("nan", "inf")
    total = rows[TOTAL_ROW_ID]
    for col in (ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        cell = total[str(col)]
        assert cell["display"] == "—" and cell["per_unit"] is None and cell.get("per_unit_display") is None


def test_all_options_total_row_has_a_display_and_no_per_unit():
    legs = [nifty_leg(Action.BUY, Instrument.CE, "22400", "81.30", ltp="85", iv="0.160347"),
            nifty_leg(Action.SELL, Instrument.PE, "22300", "30.00", ltp="31", iv="0.154691")]
    total = _rows(legs)[TOTAL_ROW_ID]
    for col in (ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        cell = total[str(col)]
        assert cell["per_unit"] is None and cell.get("per_unit_display") is None
        assert cell["display"] != "—" and "." in cell["display"]
    leg1 = _rows(legs)
    first = leg1[next(k for k in leg1 if k != TOTAL_ROW_ID)]
    assert first[str(ColumnId.IV)]["display"] == "16.03%"
    assert first[str(ColumnId.DELTA)]["per_unit_display"] is not None
