"""GC-CLEAN review MAJOR (2026-10-30): the outcome route's booked-P&L read (GC-TP R-18, ADR-209) moved off
strategy_store / paper_store onto the order-free leaf ofo_app.paper_book (REQ-073 AC-6). Its owner check is now in
the query (`load_owned`: id + user_ref + deleted_at IS NULL, the filter of strategy_store.load). This file proves it:
the owner's book reads; another user's, a missing and a hidden (deleted) strategy read as no orders.

Real PostgreSQL as the limited application role; every test rolls back (one outer transaction). Strategies come from
the shared test_strategy_store helpers, as in test_paper_store.py.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo_app import paper_book, paper_store
from ofo_app import strategy_store as store
from test_strategy_store import _user, _with_draft

AT = datetime.datetime(2026, 10, 29, 5, 0, tzinfo=datetime.UTC)
MISSING_ID = 2_000_000_000  # a valid INTEGER no test creates


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _booked_strategy(db, user: str) -> int:
    ids, stored = await _with_draft(db, user)
    c = sorted(ids.values())
    await paper_store.place(db, user, stored.id, [paper_store.NewOrder(c[0], "BUY", 65, Decimal("10.00"), "open", AT)])
    return stored.id


async def test_the_owner_reads_the_same_orders_as_paper_store(db):
    user = _user()
    sid = await _booked_strategy(db, user)
    owned = await paper_book.load_owned(db, user, sid)
    assert len(owned) == 1
    assert owned == await paper_store.load(db, sid)


async def test_another_users_strategy_reads_as_no_orders(db):
    sid = await _booked_strategy(db, _user())
    assert len(await paper_store.load(db, sid)) == 1  # the orders exist: the empty answer below is the owner check
    assert await paper_book.load_owned(db, _user(), sid) == ()


async def test_a_missing_strategy_reads_as_no_orders(db):
    assert await paper_book.load_owned(db, _user(), MISSING_ID) == ()


async def test_a_hidden_strategy_reads_as_no_orders(db):
    user = _user()
    ids, stored = await _with_draft(db, user)
    c = sorted(ids.values())
    await paper_store.place(db, user, stored.id, [paper_store.NewOrder(c[0], "BUY", 65, Decimal("10.00"), "open", AT)])
    revision = (await store.load(db, user, stored.id)).revision
    try:
        await store.delete_draft(db, user, stored.id, expected_revision=revision)
    except store.StrategyStoreError as exc:  # a paper order is not a basket; if the store refuses, say so plainly
        pytest.fail(f"delete_draft refused a paper-only strategy: {exc.code}")
    assert len(await paper_store.load(db, stored.id)) == 1
    assert await paper_book.load_owned(db, user, stored.id) == ()
