"""IC e2e paper contract, Stage C1 item 3: ``adjustments_used`` counts only stored paper adjustment batches
(``adjustment_readers.history_count``): not the entry batch, not a settle or stop, never another strategy's orders.
Non-DB: the real function over plain order objects."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.timeutil import IST
from ofo_app.adjustment_readers import history_count

T0 = datetime.datetime(2026, 11, 6, 11, 28, tzinfo=IST)


def _o(cid: int, side: str, kind: str, minute: int, price: str = "50.00"):
    return SimpleNamespace(order=SimpleNamespace(
        contract_id=cid, side=side, quantity=150, price=D(price), kind=kind,
        placed_at=T0 + datetime.timedelta(minutes=minute)))


def _entry(offset: int = 0):
    return [_o(1 + offset, "BUY", "open", 0), _o(2 + offset, "SELL", "open", 0),
            _o(3 + offset, "SELL", "open", 0), _o(4 + offset, "BUY", "open", 0)]


def _adjustment(minute: int, closes: int, opens: int):
    return [_o(closes, "BUY", "exit", minute), _o(opens, "SELL", "open", minute)]


def _count(orders):
    return history_count(orders, lambda _cid: True)


def test_entry_only_counts_zero():
    assert _count(_entry()) == 0  # attack 1: entry orders are not adjustments


def test_each_adjustment_batch_counts_one_and_entry_never():
    orders = _entry() + _adjustment(5, 3, 5)
    assert _count(orders) == 1
    assert _count(orders + _adjustment(9, 5, 6)) == 2


def test_settle_and_stop_orders_are_not_adjustments():
    orders = _entry() + _adjustment(5, 3, 5) + [_o(5, "BUY", "settle", 20, "0"), _o(2, "SELL", "stop", 21)]
    assert _count(orders) == 1


def test_another_strategys_orders_are_not_counted():
    mine = _entry() + _adjustment(5, 3, 5)
    other = _entry(10) + _adjustment(6, 13, 15) + _adjustment(7, 15, 16)
    assert _count(mine) == 1  # the reader is given one strategy's orders only: the other's two do not leak in
    assert _count(other) == 2


def test_unreadable_history_is_none_never_zero():
    assert _count([]) is None  # no orders: the engine refuses, the count is "not available"
