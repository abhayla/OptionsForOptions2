"""GC-ICGUIDE g23 (audit C13; contract task 23): a strategy whose last open leg is exited is stored as 'closed' and the
Completed list carries its final P&L, adjustments made and their cost, all from the server.

Real PostgreSQL, every test rolled back. CORE: exit every leg through POST /paper/strategies/{id}/orders and read the
strategy row's status (before this change it stayed 'draft': CHECK + guard of alembic 0008).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from http import HTTPStatus

import pytest
from _migration_replay import round_trip_sql
from ofo_app import paper_store
from ofo_app.routes.outcome import load_charge_rates
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_migration_0026_strategy_deleted_at import DEFINITION, INSERT
from test_paper_routes import AT, RATES, _new, _order
from test_strategy_store import _client
from test_strategy_tracking import _setup

MIGRATION = "0049_strategy_closed_status.py"
LATER = AT + datetime.timedelta(minutes=30)
GUARD_REFUSAL = "OF008"


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _status(db, strategy_id: int) -> str:
    row = await db.execute(text("SELECT status FROM public.strategies WHERE id = :i"), {"i": strategy_id})
    return row.scalar_one()


async def _two_legs(db):
    app, stored, *_ = await _setup(db)
    c0, c1 = stored.saved.contract_ids[:2]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c1, "SELL", 65, "60.05")])
    return app, stored, c0, c1


async def test_core_exiting_every_leg_through_the_route_stores_closed(db):
    app, stored, c0, c1 = await _two_legs(db)
    assert await _status(db, stored.id) == "draft"
    async with _client(app) as c:
        first = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(c0, "BUY", 65, "80.00", "exit")]})
        assert first.status_code == HTTPStatus.CREATED, first.text
        assert await _status(db, stored.id) == "draft"  # one leg still open: no change
        last = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(c1, "BUY", 65, "50.05", "exit")]})
        assert last.status_code == HTTPStatus.CREATED, last.text
    assert await _status(db, stored.id) == "closed"


async def test_a_partial_exit_leaves_the_strategy_a_draft(db):
    app, stored, c0, _ = await _two_legs(db)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(c0, "BUY", 30, "80.00", "exit")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert await _status(db, stored.id) == "draft"


async def test_expiry_settlement_of_the_last_open_legs_stores_closed(db):
    _, stored, c0, c1 = await _two_legs(db)
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(c0, "BUY", 65, D("0.00"), "settle", LATER),
        paper_store.NewOrder(c1, "BUY", 65, D("10.00"), "settle", LATER)])
    assert await _status(db, stored.id) == "closed"


async def test_a_second_exit_batch_on_a_closed_strategy_is_refused_and_keeps_it_closed(db):
    _, stored, c0, c1 = await _two_legs(db)
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "BUY", 65, "80.00", "exit"),
                                                              _new(c1, "BUY", 65, "50.05", "exit")])
    with pytest.raises(Exception, match=r"exit_exceeds_open|contract"):
        await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "BUY", 65, "80.00", "exit")])
    assert await _status(db, stored.id) == "closed"


async def _close_with_two_batches(db):
    app, stored, c0, c1 = await _two_legs(db)
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(c0, "BUY", 65, D("80.00"), "exit", LATER)])
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(c1, "BUY", 65, D("50.05"), "exit", LATER + datetime.timedelta(minutes=5))])
    return app, stored


async def test_the_list_carries_final_pnl_adjustments_and_their_cost_for_a_closed_strategy(db):
    app, stored = await _close_with_two_batches(db)
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    async with _client(app) as c:
        rows = (await c.get("/strategies")).json()["strategies"]
    row = next(r for r in rows if r["id"] == stored.id)
    assert row["status"] == "closed"
    assert (row["final_pnl"], row["final_pnl_text"]) == ("1950.00", "+1,950.00")  # 65 x 20.00 + 65 x 10.00
    assert row["adjustments_made"] == 1  # the first exit; entry and closing exit do not count
    assert D(row["adjustment_cost"]) > 0 and row["adjustment_cost_text"] and row["completed_reason_text"] is None


async def test_unreadable_charge_rates_say_not_available_with_a_reason_never_zero(db):
    app, stored = await _close_with_two_batches(db)
    app.dependency_overrides[load_charge_rates] = lambda: None
    async with _client(app) as c:
        rows = (await c.get("/strategies")).json()["strategies"]
    row = next(r for r in rows if r["id"] == stored.id)
    assert row["final_pnl"] == "1950.00"
    assert row["adjustment_cost"] is None and row["adjustment_cost_text"] is None
    assert row["completed_reason_text"]


async def test_a_draft_row_carries_no_completed_figures(db):
    app, stored, *_ = await _two_legs(db)
    async with _client(app) as c:
        rows = (await c.get("/strategies")).json()["strategies"]
    row = next(r for r in rows if r["id"] == stored.id)
    assert row["status"] == "draft"
    assert (row["final_pnl"], row["adjustments_made"], row["adjustment_cost"], row["completed_reason_text"]) == (
        None, None, None, None)


@pytest.mark.parametrize("sql", ["UPDATE public.strategies SET status = 'draft' WHERE id = :id",
                                 "UPDATE public.strategies SET status = 'open' WHERE id = :id"])
async def test_closed_never_reopens_and_no_other_status_exists(app_engine, sql):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid = (await conn.execute(text(INSERT), {"u": "test-0049-reopen", "d": DEFINITION})).scalar_one()
            await conn.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :id"), {"id": sid})
            with pytest.raises(DBAPIError) as err:
                async with conn.begin_nested():
                    await conn.execute(text(sql), {"id": sid})
            assert getattr(err.value.orig, "sqlstate", None) in {GUARD_REFUSAL, "23514"}
            assert (await conn.execute(text("SELECT status FROM public.strategies WHERE id = :i"),
                                       {"i": sid})).scalar_one() == "closed"
        finally:
            await trans.rollback()


async def test_migration_downgrade_is_refused_while_a_strategy_is_closed_and_round_trips_when_none(admin_engine):
    own_down, _, down, up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid = (await conn.execute(text(INSERT), {"u": "test-0049-down", "d": DEFINITION})).scalar_one()
            await conn.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :id"), {"id": sid})
            with pytest.raises(DBAPIError, match=r"public\.strategies is closed"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
        finally:
            await trans.rollback()
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            sid = (await conn.execute(text(INSERT), {"u": "test-0049-rt", "d": DEFINITION})).scalar_one()
            with pytest.raises(DBAPIError):
                async with conn.begin_nested():
                    await conn.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :id"),
                                       {"id": sid})
            for sql in up:
                await conn.execute(text(sql))
            await conn.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :id"), {"id": sid})
        finally:
            await trans.rollback()
