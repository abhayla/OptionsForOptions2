"""Lane FD3 item 2 (ADR-017, ADR-048): the durable order request key, public.order_request_keys (migration 0061).
Core: the claim lives in the orders' own transaction (a crash stores neither), two presses with one key place once, and
a repeat after a Redis flush still finds the key. Real PostgreSQL; the committed throwaway strategy is deleted after."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

import asyncio
import json
import uuid
from http import HTTPStatus

import pytest
from ofo_app import request_key
from ofo_app.strategy_refused import StrategyRefused
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_order_request_key_r2_fd2 import _body, _count, _post, _prices, _use, keys  # noqa: F401 - fixtures
from test_paper_triggers_routes import _setup, db, notified  # noqa: F401 - fixtures

BODY = {"orders": [{"contract_id": 1, "side": "BUY", "quantity": 65}]}
USER = "fd3-key-user"
DEFINITION = json.dumps({"schema_version": 1, "underlying": "NIFTY", "rules_ref": None, "risk_limits": {},
                         "preferences": {}, "legs": [{"contract_id": 1001, "action": "SELL", "instrument": "CE",
                                                      "strike": "23000", "expiry": "2026-10-29", "quantity": 75}]})


@pytest.fixture
async def strategy(admin_engine):
    async with admin_engine.begin() as conn:
        sid = (await conn.execute(text(
            "INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
            "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1) RETURNING id"), {"u": USER, "d": DEFINITION})).scalar_one()
    try:
        yield sid
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(text("DELETE FROM public.order_request_keys WHERE user_ref = :u"), {"u": USER})
            # a strategy is never deleted (W-061): this file commits one row, so it runs on a disposable clone only
            # (db_run.py, or OFO_TEST_DB_PER_FILE=1 on a throwaway database)


async def _rows(admin_engine) -> list:
    async with admin_engine.connect() as conn:
        return list((await conn.execute(text(
            "SELECT state, door, result FROM public.order_request_keys WHERE user_ref = :u"), {"u": USER})).all())


async def test_a_crash_between_the_claim_and_the_commit_stores_neither(app_engine, admin_engine, strategy):
    key = uuid.uuid4()
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        await request_key.claim_in_transaction(conn, USER, key, strategy, BODY, "paper")
        await trans.rollback()  # the crash: the orders and the claim go together
    assert await _rows(admin_engine) == []
    async with app_engine.connect() as conn:
        assert await request_key.lookup(conn, USER, key, strategy, BODY) is None  # the key is free again


async def test_two_presses_with_one_key_one_wins_and_the_other_gets_the_first_result(app_engine, admin_engine, strategy):
    key = uuid.uuid4()
    async with app_engine.connect() as one, app_engine.connect() as two:
        t1, t2 = await one.begin(), await two.begin()
        await request_key.claim_in_transaction(one, USER, key, strategy, BODY, "paper")
        second = asyncio.ensure_future(request_key.claim_in_transaction(two, USER, key, strategy, BODY, "paper"))
        await asyncio.sleep(0.5)
        assert not second.done(), "the second press must wait for the first to decide"
        await request_key.finish_in_transaction(one, USER, key, {"cancelled_stops": [{"leg": "x"}]})
        await t1.commit()
        with pytest.raises(request_key.Repeated) as repeat:
            await second
        assert repeat.value.result == {"cancelled_stops": [{"leg": "x"}]}
        await t2.rollback()
    rows = await _rows(admin_engine)
    assert [(r.state, r.door) for r in rows] == [("done", "paper")]


async def test_a_second_press_after_the_first_rolled_back_places(app_engine, admin_engine, strategy):
    key = uuid.uuid4()
    async with app_engine.connect() as one, app_engine.connect() as two:
        t1, t2 = await one.begin(), await two.begin()
        await request_key.claim_in_transaction(one, USER, key, strategy, BODY, "real")
        second = asyncio.ensure_future(request_key.claim_in_transaction(two, USER, key, strategy, BODY, "real"))
        await asyncio.sleep(0.3)
        await t1.rollback()
        await second  # no Repeated: the first stored nothing, this one is now the first
        await request_key.finish_in_transaction(two, USER, key, {"plan_number": 3})
        await t2.commit()
    assert [(r.state, r.door, r.result) for r in await _rows(admin_engine)] == [("done", "real", {"plan_number": 3})]


async def test_a_recorded_key_answers_by_the_rules(app_engine, strategy):
    key = uuid.uuid4()
    async with app_engine.begin() as conn:
        await request_key.claim_in_transaction(conn, USER, key, strategy, BODY, "paper")
        await request_key.finish_in_transaction(conn, USER, key, {"cancelled_stops": []})
    async with app_engine.connect() as conn:
        assert await request_key.lookup(conn, USER, key, strategy, BODY) == {"cancelled_stops": []}
        with pytest.raises(StrategyRefused, match="request_key_other_strategy"):
            await request_key.lookup(conn, USER, key, strategy + 1, BODY)
        with pytest.raises(StrategyRefused, match="request_key_different_body"):
            await request_key.lookup(conn, USER, key, strategy, {"orders": []})


async def test_a_claim_never_finished_reads_as_still_running(app_engine, strategy):
    key = uuid.uuid4()
    async with app_engine.begin() as conn:
        await request_key.claim_in_transaction(conn, USER, key, strategy, BODY, "paper")
    async with app_engine.connect() as conn:
        with pytest.raises(StrategyRefused, match="request_key_in_progress"):
            await request_key.lookup(conn, USER, key, strategy, BODY)


async def test_the_app_role_cannot_delete_or_rewrite_a_key_and_the_door_is_checked(app_engine, strategy):
    key = uuid.uuid4()
    async with app_engine.begin() as conn:
        await request_key.claim_in_transaction(conn, USER, key, strategy, BODY, "paper")
    for sql in ("DELETE FROM public.order_request_keys WHERE user_ref = :u",
                "UPDATE public.order_request_keys SET body_sha256 = repeat('0', 64) WHERE user_ref = :u"):
        async with app_engine.connect() as conn:
            with pytest.raises(ProgrammingError):  # permission denied
                await conn.execute(text(sql), {"u": USER})
    async with app_engine.connect() as conn:
        with pytest.raises(DBAPIError):  # CHECK: door in ('paper','real')
            await conn.execute(text("INSERT INTO public.order_request_keys (user_ref, request_key, strategy_id, "
                                    "body_sha256, door, state) VALUES (:u, :k, :s, repeat('a', 64), 'x', 'pending')"),
                               {"u": USER, "k": uuid.uuid4(), "s": strategy})


async def test_a_table_that_cannot_be_written_refuses_by_name_and_stores_nothing(monkeypatch):
    class Broken:
        async def execute(self, *_a, **_k):
            from sqlalchemy.exc import OperationalError  # noqa: PLC0415
            raise OperationalError("x", {}, Exception("down"))

        async def rollback(self):
            return None

    with pytest.raises(StrategyRefused, match="request_key_store_unavailable"):
        await request_key.lookup(Broken(), USER, uuid.uuid4(), 1, BODY)
    with pytest.raises(StrategyRefused, match="request_key_store_unavailable"):
        await request_key.claim_in_transaction(Broken(), USER, uuid.uuid4(), 1, BODY, "paper")


async def test_a_repeat_after_a_redis_flush_still_finds_the_key(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    key = uuid.uuid4()
    first = await _post(app, stored, _body(orders, key))
    assert first.status_code == HTTPStatus.CREATED, first.text
    await keys._factory().flushdb()  # the fast path is gone; the table is the record of truth
    again = await _post(app, stored, _body(orders, key))
    assert again.status_code == HTTPStatus.CREATED, again.text
    assert await _count(db, stored) == len(orders)
    assert [o["id"] for o in again.json()["orders"]] == [o["id"] for o in first.json()["orders"]]
    row = (await db.execute(text("SELECT state, door FROM public.order_request_keys WHERE request_key = :k"),
                            {"k": key})).one()
    assert (row.state, row.door) == ("done", "paper")
    other = await _post(app, stored, _body(orders[:1], key))
    assert other.status_code == HTTPStatus.CONFLICT and "different order set" in other.text
