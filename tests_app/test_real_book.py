"""GC-ICTRACK task 4 (ADR-275/276): real Zerodha trades and adopted holdings become the paper book's order rows, so the
ONE netter answers for a real strategy (``tracked_book.real_orders``, read-only: REQ-073 AC-6). Pure: no DB, no Kite."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.tracking.orderbook import net_positions
from ofo_app.tracked_book import FillRow, HeldRow, RealBookUnreadable, instrument_key, real_orders

T0 = datetime.datetime(2026, 11, 3, 5, 22, tzinfo=datetime.UTC)
CE, PE = "NSE_FO:51392", "NSE_FO:51400"
IDS = {CE: 101, PE: 102}
DAY = datetime.timedelta(days=1)


def _fill(plan, action, iid, side, qty, price, at=T0):  # noqa: PLR0913 - one stored trade row
    return FillRow(plan, action, at, iid, side, qty, Decimal(price))


def test_two_fills_net_to_the_fill_weighted_average():
    fills = [_fill(1, "ENTRY", CE, "SELL", 65, "180.95"), _fill(1, "ENTRY", CE, "SELL", 65, "181.05")]
    orders = real_orders(fills, (), IDS)
    assert [(o.contract_id, o.side, o.quantity, o.kind) for o in orders] == [(101, "SELL", 65, "open")] * 2
    (pos,) = net_positions([o.as_paper() for o in orders], {}).positions
    assert (pos.net_quantity, pos.average) == (-130, Decimal("181.00"))


def test_later_entry_adds_exit_exits_and_adopted_opens_at_its_time():
    fills = [_fill(3, "EXIT", CE, "BUY", 130, "90.00", T0 + 2 * DAY), _fill(1, "ENTRY", CE, "SELL", 65, "90.00"),
             _fill(2, "ENTRY", CE, "SELL", 65, "90.00", T0 + DAY)]
    held = [HeldRow(PE, "BUY", 65, Decimal("72.10"), "kite-1", T0 - datetime.timedelta(hours=1))]
    orders = real_orders(fills, held, IDS)
    assert [(o.contract_id, o.kind) for o in orders] == [(102, "open"), (101, "open"), (101, "add"), (101, "exit")]
    nets = {p.instrument_id: p.net_quantity for p in net_positions([o.as_paper() for o in orders], {}).positions}
    assert nets == {"102": 65, "101": 0}


def test_nothing_traded_is_empty():
    assert real_orders([], [], IDS) == ()


@pytest.mark.parametrize("held", [
    HeldRow(PE, "BUY", 65, Decimal("72.105"), "r", T0),  # finer than a paisa (ADR-126, #673)
    HeldRow(PE, "BUY", 65, Decimal("72.10"), "r", None),  # no adoption time
])
def test_adopted_that_cannot_be_netted_exactly_fails_closed(held):
    with pytest.raises(RealBookUnreadable, match="not usable"):
        real_orders([], [held], IDS)


@pytest.mark.parametrize("bad", [
    _fill(1, "ENTRY", CE, "HOLD", 65, "1.00"),             # not a side
    FillRow(1, "ENTRY", T0, CE, "SELL", 0, Decimal(1)),    # no units
    FillRow(1, "ENTRY", T0, CE, "SELL", 65, 1.0),          # a float price, never
    FillRow(1, "ENTRY", T0, CE, "SELL", 65, Decimal("NaN")),
])
def test_a_stored_row_that_is_not_exact_fails_closed(bad):
    with pytest.raises(RealBookUnreadable, match="not exact"):
        real_orders([bad], [], IDS)


def test_contract_without_live_id_fails_closed():
    with pytest.raises(RealBookUnreadable, match="no live contract"):
        real_orders([_fill(1, "ENTRY", CE, "SELL", 65, "1.00")], [], {})


def test_instrument_key():
    assert (instrument_key(CE).exchange_segment, instrument_key(CE).exchange_token) == ("NSE_FO", 51392)
