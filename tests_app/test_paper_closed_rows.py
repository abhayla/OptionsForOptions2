"""D-10 (ADR-207 (2), REQ-109 AC-4): the paper reply serves each CLOSED lifecycle as its own row (contract, side, lots,
average entry, average exit, booked) and an open row's booked is from its own lifecycle only. Real case C1 155: SELL 25400 PE
bought back for +643.50, then a NEW long 25400 PE. Hand arithmetic: (120.00 - 115.71) x 150 = 4.29 x 150 = 643.50."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from ofo.tracking import paper
from ofo.tracking.orderbook import PaperOrder
from ofo_app import tracked_contracts
from ofo_app.routes import paper as P

D = Decimal
AT = datetime.datetime(2026, 11, 23, 4, 0, tzinfo=datetime.UTC)
LOT = 75


def _found(cid: int):
    contract = SimpleNamespace(name="NIFTY", instrument_type="PE", strike=D("25400"), expiry=datetime.date(2026, 11, 24),
                               lot_size=LOT)
    return SimpleNamespace(contract_id=cid, state=tracked_contracts.LIVE, feed_key=f"NSE_FO:{cid}", identity=f"c{cid}",
                           stored=SimpleNamespace(listed=SimpleNamespace(contract=contract)))


def _order(n: int, side: str, qty: int, price: str, kind: str):
    paper_order = PaperOrder("7", side, qty, D(price), kind, AT + datetime.timedelta(minutes=n))
    return SimpleNamespace(order=SimpleNamespace(contract_id=7, as_paper=lambda: paper_order))


def _figures(orders):
    live = paper.Price("NSE_FO:7", "live", D("95.00"), AT)
    return P._figures(orders, {7: _found(7)}, {7: live}, True, datetime.date(2026, 11, 23))


C1 = [_order(0, "SELL", 150, "120.00", "open"), _order(1, "BUY", 150, "115.71", "exit"), _order(2, "BUY", 150, "90.00", "open")]


def test_c1_155_one_closed_short_row_and_one_open_long_row_booked_zero():
    got = _figures(C1)
    assert len(got["closed"]) == 1
    row = got["closed"][0]
    assert (row["contract_text"], row["side"], row["lots"], row["quantity"]) == (
        "NIFTY 24 Nov 25400 PE", "SELL", 2, 150)
    assert (row["average_entry"], row["average_exit"], row["booked"]) == (D("120.00"), D("115.71"), D("643.50"))
    assert row["booked_text"] and row["average_exit_text"]
    [position] = got["positions"]
    assert (position["net_quantity"], position["booked"]) == (150, D("0"))
    open_booked = sum((p["booked"] for p in got["positions"] if p["net_quantity"]), D(0))
    assert sum((c["booked"] for c in got["closed"]), D(0)) + open_booked == got["booked"] == D("643.50")


def test_no_closed_row_for_a_book_that_never_closed():
    assert _figures([_order(0, "SELL", 150, "120.00", "open")])["closed"] == []


def test_a_settled_leg_is_a_closed_row_with_exit_zero():
    got = _figures([_order(0, "SELL", 75, "12.00", "open"), _order(1, "BUY", 75, "0.00", "settle")])
    assert (got["closed"][0]["average_exit"], got["closed"][0]["booked"]) == (D("0.00"), D("900.00"))
