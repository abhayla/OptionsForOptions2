"""GC-ICFIX issue 24 round 2 (ADR-311): the practice page (GET /paper/strategies) names an unpriced leg the same way the
tracking page does. No database: the route's figure function is called on stub contract rows.

- expired: a retired contract, or its expiry date is before the snapshot's India date; a contract expiring TODAY is not
  expired (expired yesterday = True, expiring today = False), as on the tracking page.
- one meaning of ``leg_index``: the leg's place among ALL the book's legs in order (closed ones count), the same as the
  tracking page; the row with "no price" is the row at that place.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.tracking import paper
from ofo.tracking.orderbook import PaperOrder
from ofo_app import tracked_contracts
from ofo_app.routes import paper as P

D = Decimal
AT = datetime.datetime(2026, 10, 8, 3, 50, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 10, 8)


def _found(cid: int, expiry: datetime.date):
    contract = SimpleNamespace(name="NIFTY", instrument_type="CE", strike=D("23000"), expiry=expiry, lot_size=65)
    return SimpleNamespace(contract_id=cid, state=tracked_contracts.LIVE, feed_key=f"NSE_FO:{cid}", identity=f"c{cid}",
                           stored=SimpleNamespace(listed=SimpleNamespace(contract=contract)))


def _order(cid: int, side: str, price: str, kind: str):
    paper_order = PaperOrder(str(cid), side, 65, D(price), kind, AT)
    return SimpleNamespace(order=SimpleNamespace(contract_id=cid, as_paper=lambda: paper_order))


def _figures(expiry: datetime.date, today: datetime.date | None, closed_first: bool = False):
    orders = [_order(2, "SELL", "100", "open")]
    if closed_first:  # contract 1 was bought and sold before contract 2 was opened: it is leg 0, contract 2 is leg 1
        orders = [_order(1, "BUY", "50", "open"), _order(1, "SELL", "60", "exit"), *orders]
    found = {1: _found(1, expiry), 2: _found(2, expiry)}
    prices = {2: paper.Price("NSE_FO:2", "missing", None, None)}
    return P._figures(orders, found, prices, True, today)


@pytest.mark.parametrize(("expiry", "expired", "text"), [
    (datetime.date(2026, 10, 7), True, "Expired contracts have no price: NIFTY 7 Oct 23000 CE."),
    (datetime.date(2026, 10, 8), False, "No price for: NIFTY 8 Oct 23000 CE."),
    (datetime.date(2026, 10, 13), False, "No price for: NIFTY 13 Oct 23000 CE."),
])
def test_expired_yesterday_is_expired_expiring_today_is_not(expiry, expired, text):
    got = _figures(expiry, TODAY)
    assert [u["expired"] for u in got["unpriced_legs"]] == [expired] and got["unpriced_text"] == text


def test_without_a_date_only_a_retired_contract_is_called_expired():
    assert _figures(datetime.date(2026, 10, 7), None)["unpriced_legs"][0]["expired"] is False


def test_a_closed_leg_before_an_open_one_the_name_and_the_no_price_cell_are_on_the_same_row():
    got = _figures(datetime.date(2026, 10, 13), TODAY, closed_first=True)
    assert [u["leg_index"] for u in got["unpriced_legs"]] == [1]
    rows = got["positions"]
    assert [p["contract_id"] for p in rows] == [1, 2]
    assert [p["no_price_text"] for p in rows] == [None, "no price"]
    assert rows[got["unpriced_legs"][0]["leg_index"]]["no_price_text"] == "no price"
    assert (got["total"], got["unbooked"]) == (None, None) and rows[0]["booked"] == D("650.00")
