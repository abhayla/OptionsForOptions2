"""D-15 review MAJOR: "an exit exists in the order history" is read from the whole history, not the open book.

The reviewer's runs: exit then re-sell the same 65 -> the open book equals the plan again; a partial exit then a re-add
to the planned 130 -> likewise. Both must read as "an exit was seen" (so no plan line). Pure rules first, then the real
owner-checked read on the database (as the limited application role; each test rolls back).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.tracking.orderbook import PaperOrder
from ofo_app import paper_book, paper_store
from ofo_app.routes.outcome import exit_seen
from test_strategy_store import _user, _with_draft

AT = datetime.datetime(2026, 11, 26, 5, 0, tzinfo=datetime.UTC)
PX = Decimal("10.00")


def _o(side, qty, kind, n=0):
    return PaperOrder("1", side, qty, PX, kind, AT + datetime.timedelta(minutes=n))


def test_an_untouched_book_and_a_plain_add_are_no_exit():
    assert exit_seen([_o("SELL", 65, "open")]) is False
    assert exit_seen([_o("SELL", 65, "open"), _o("SELL", 65, "add", 1)]) is False


def test_exit_then_re_entry_is_an_exit_seen():
    assert exit_seen([_o("SELL", 65, "open"), _o("BUY", 65, "exit", 1), _o("SELL", 65, "open", 2)]) is True


def test_partial_exit_then_re_add_to_the_planned_size_is_an_exit_seen():
    orders = [_o("SELL", 130, "open"), _o("BUY", 65, "exit", 1), _o("SELL", 65, "add", 2)]
    assert exit_seen(orders) is True


def test_a_stop_or_a_settle_is_an_exit_seen():
    assert exit_seen([_o("SELL", 65, "open"), _o("BUY", 65, "stop", 1)]) is True
    assert exit_seen([_o("SELL", 65, "open"), _o("BUY", 65, "settle", 1)]) is True


def test_a_closed_lifecycle_without_an_exit_kind_is_an_exit_seen():
    assert exit_seen([_o("SELL", 65, "open"), _o("BUY", 65, "add", 1)]) is True  # flat again: a closed lifecycle


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def test_the_stored_history_of_exit_and_re_entry_reads_as_an_exit_seen(db):
    user = _user()
    ids, stored = await _with_draft(db, user)
    c = sorted(ids.values())[0]
    minute = datetime.timedelta(minutes=1)
    await paper_store.place(db, user, stored.id, [paper_store.NewOrder(c, "SELL", 130, PX, "open", AT)])
    held = await paper_book.load_owned(db, user, stored.id)
    assert exit_seen([o.order.as_paper() for o in held]) is False
    await paper_store.place(db, user, stored.id, [paper_store.NewOrder(c, "BUY", 65, PX, "exit", AT + minute)])
    await paper_store.place(db, user, stored.id, [paper_store.NewOrder(c, "SELL", 65, PX, "add", AT + 2 * minute)])
    held = await paper_book.load_owned(db, user, stored.id)
    assert exit_seen([o.order.as_paper() for o in held]) is True  # the open book is 130 again, as planned
