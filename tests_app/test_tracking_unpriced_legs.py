"""GC-ICFIX issue 24 (ADR-311, REQ-109 AC-5 as narrowed; ADR-008): when an open leg of a practice book has no price,
the reply keeps every TOTAL paused (and the after-charges figures with it), shows each priced leg's own unbooked figure,
marks the unpriced leg "no price" (never 0, never blank), and names it, calling an expired contract expired.

Real case (the user test, 13 Nov): the 8 Oct 2026 condor (65 a leg) with the far BUY 23000 CE without a price. By hand:
SELL 22800 CE (39.15 - 45.15) x 65 = -390.00; SELL 22400 PE (82.75 - 70.75) x 65 = +780.00; BUY 22200 PE (30.80 - 35.80)
x 65 = -325.00. No database: the route's own figure function is called on a hand-built engine view.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.charges import ChargeRates
from ofo.engine.legs import Action, Instrument
from ofo.errors.explanations import render_explanation
from ofo.tracking import book, paper
from ofo.tracking.orderbook import PaperOrder
from ofo_app.routes import tracking as T

D = Decimal
AT = datetime.datetime(2026, 10, 8, 3, 50, tzinfo=datetime.UTC)
EXPIRY = datetime.date(2026, 10, 13)
KEYS = ["NSE_FO:44624", "NSE_FO:44632", "NSE_FO:44604", "NSE_FO:44595"]
SPEC = [("SELL", Action.SELL, Instrument.CE, "22800", "39.15"), ("BUY", Action.BUY, Instrument.CE, "23000", "12.95"),
        ("SELL", Action.SELL, Instrument.PE, "22400", "82.75"), ("BUY", Action.BUY, Instrument.PE, "22200", "35.80")]
NOW = [D("45.15"), None, D("70.75"), D("30.80")]
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")


def _book(closed_first=False):
    orders = tuple(PaperOrder(str(i + 1), side, 65, D(price), "open", AT) for i, (side, *_, price) in enumerate(SPEC))
    if closed_first:  # leg 0 (SELL 22800 CE at 39.15) is bought back at 30.00: booked (39.15 - 30.00) x 65 = +594.75
        orders = (*orders, PaperOrder("1", "BUY", 65, D("30.00"), "exit", AT))
    legs = [paper.TrackedLeg(KEYS[i], act, inst, D(strike), EXPIRY, 65, D(price), AT)
            for i, (_, act, inst, strike, price) in enumerate(SPEC)]
    return T._Book(1, orders, book.contract_legs(orders)), legs


def _paused(unpriced, now=NOW, rates=None):
    bk, legs = _book()
    prices = tuple(paper.Price(KEYS[i], "live", p, AT) if p is not None else paper.Price(KEYS[i], "missing", None, None)
                   for i, p in enumerate(now))
    view = paper.TrackingView(True, "prices_not_live", None, AT, prices, None, None, (), D(0), None, False,
                              (None,) * 4, unpriced)
    return T._figures(bk, legs, view, [None] * 4, "NIFTY", rates)


def test_core_the_notes_case_totals_stay_paused_priced_legs_keep_their_figure_the_unpriced_leg_is_named():
    got = _paused((paper.UnpricedLeg(1, KEYS[1], "missing", False),))
    assert (got["state"], got["total"], got["unbooked"], got["booked"]) == ("PAUSED", None, None, D("0.00"))
    rows = got["legs"]
    assert [r["pnl"] for r in rows] == [D("-390.00"), None, D("780.00"), D("-325.00")]
    assert rows[1]["pnl_text"] is None and rows[0]["pnl_kind"] == "unbooked"
    assert [r["no_price_text"] for r in rows] == [None, "no price", None, None]  # a marker, never "0.00" / blank
    assert got["unpriced_legs"] == [{"leg_index": 1, "contract_text": "NIFTY 13 Oct 23000 CE", "expired": False}]
    assert got["unpriced_text"] == "No price for: NIFTY 13 Oct 23000 CE."
    assert "partial_total" not in got and "priced_total" not in got  # nothing sums the priced legs


def test_after_charges_figures_stay_paused_with_the_total():
    got = _paused((paper.UnpricedLeg(1, KEYS[1], "missing", False),))
    assert (got["total_after"], got["unbooked_after"]) == (None, None)
    assert got["after_charges_reason"] == "prices_not_live"
    # no rates here: the charges paid are unknown, so Booked after is absent with ITS OWN reason, not the price reason
    assert got["booked_after"] is None and got["booked_after_reason"] == "rates_unavailable"


def test_booked_after_is_shown_while_paused_when_the_charges_paid_are_known():
    got = _paused((paper.UnpricedLeg(1, KEYS[1], "missing", False),), rates=RATES)
    assert (got["total_after"], got["unbooked_after"], got["after_charges_reason"]) == (None, None, "prices_not_live")
    assert got["charges_paid"] is not None and got["booked_after_reason"] is None
    assert got["booked_after"] == got["booked"] - got["charges_paid"]  # booked 0.00 here: minus ALL charges paid


def test_a_closed_leg_before_an_open_one_the_figure_and_the_name_land_on_the_same_row():
    bk, legs = _book(closed_first=True)
    prices = (paper.Price(KEYS[0], "exited", None, None), paper.Price(KEYS[1], "live", D("12.00"), AT),
              paper.Price(KEYS[2], "missing", None, None), paper.Price(KEYS[3], "live", D("30.80"), AT))
    view = paper.TrackingView(True, "prices_not_live", None, AT, prices, None, None, (), D("594.75"), None, False,
                              (D("594.75"), D("-61.75"), None, D("-325.00")),
                              (paper.UnpricedLeg(2, KEYS[2], "missing", False),))
    got = T._figures(bk, legs, view, [None] * 4, "NIFTY", None)
    assert [r["pnl"] for r in got["legs"]] == [D("594.75"), D("-61.75"), None, D("-325.00")]
    assert [r["no_price_text"] for r in got["legs"]] == [None, None, "no price", None]
    assert got["unpriced_legs"] == [{"leg_index": 2, "contract_text": "NIFTY 13 Oct 22400 PE", "expired": False}]
    assert got["booked"] == D("594.75") and got["total"] is None


def test_several_unpriced_and_an_expired_one_are_each_named_and_called_expired():
    now = [None, D("12.00"), None, None]
    left = (paper.UnpricedLeg(0, KEYS[0], "stale", False), paper.UnpricedLeg(2, KEYS[2], "contract_retired", True),
            paper.UnpricedLeg(3, KEYS[3], "missing", False))
    got = _paused(left, now)
    assert [r["pnl"] for r in got["legs"]] == [None, D("-61.75"), None, None]  # BUY 23000 CE (12.00 - 12.95) x 65
    assert [u["leg_index"] for u in got["unpriced_legs"]] == [0, 2, 3] and got["unpriced_legs"][1]["expired"] is True
    assert got["unpriced_text"] == ("No price for: NIFTY 13 Oct 22800 CE, NIFTY 13 Oct 22400 PE (expired), "
                                    "NIFTY 13 Oct 22200 PE.")


def test_when_every_unpriced_leg_is_expired_the_reason_is_that_they_expired():
    got = _paused((paper.UnpricedLeg(1, KEYS[1], "contract_retired", True),))
    assert got["unpriced_text"] == "Expired contracts have no price: NIFTY 13 Oct 23000 CE."


def test_wording_the_five_new_texts():
    r = render_explanation
    x = r("leg_no_price")  # any finished explanation text stands in for a contract name
    assert x == "no price"
    assert r("unpriced_leg", contract=x) == "no price" and r("unpriced_leg_expired", contract=x) == "no price (expired)"
    assert r("unpriced_legs", legs=x) == "No price for: no price."
    assert r("unpriced_legs_expired", legs=x) == "Expired contracts have no price: no price."
