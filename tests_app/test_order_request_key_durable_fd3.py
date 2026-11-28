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


async def test_two_presses_with_one_key_one_wins_and_the_other_gets_the_first_result(
        app_engine, admin_engine, strategy):
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


async def test_a_repeat_names_the_stops_the_first_request_cancelled(db, notified, keys):
    """FD3 item 2: the stored ``cancelled_stops`` come back on the repeat exactly as the first reply named them."""
    from test_paper_orders_r2_fd2 import _stop  # noqa: PLC0415
    from test_paper_routes import _new  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)  # short 22800 CE (ids[0]), long 23000 CE (ids[1]); ids[2] is flat
    _use(app, keys)
    await _stop(app, stored, ids[0])
    key = uuid.uuid4()
    body = _body([_new(ids[0], "BUY", 65, "30", "exit"), _new(ids[2], "SELL", 65, "82.75")], key)
    first = await _post(app, stored, body)
    assert first.status_code == HTTPStatus.CREATED, first.text
    named = [{"leg": "NIFTY 13 Oct 22800 CE", "contract": ids[0], "level": "120.00"}]
    assert first.json()["cancelled_stops"] == named
    again = await _post(app, stored, body)
    assert again.status_code == HTTPStatus.CREATED, again.text[:300]
    assert again.json()["cancelled_stops"] == named
    await keys._factory().flushdb()  # and from the table alone
    third = await _post(app, stored, body)
    assert third.status_code == HTTPStatus.CREATED, third.text[:300]
    assert third.json()["cancelled_stops"] == named


async def test_an_unknown_outcome_keeps_the_key_and_a_repeat_is_told_still_being_placed(
        db, notified, keys, monkeypatch):
    """FD2 review F7 route test: a request whose commit outcome is unknown (the exception comes AFTER the commit began)
    never frees the key; the repeat is told 582 and places nothing."""
    from ofo_app.routes import paper as route  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    key = uuid.uuid4()
    real = route._place_orders

    async def crash_after_commit_began(db_, strategy_id, stored_, body, deps, stage):  # noqa: PLR0913
        stage["commit_started"] = True
        raise RuntimeError("the connection dropped during the commit")

    monkeypatch.setattr(route, "_place_orders", crash_after_commit_began)
    first = await _post(app, stored, _body(orders, key))
    assert first.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, first.text[:200]
    monkeypatch.setattr(route, "_place_orders", real)
    again = await _post(app, stored, _body(orders, key))
    assert again.status_code == HTTPStatus.CONFLICT and "still being placed" in again.text, again.text[:300]
    assert await _count(db, stored) == 0  # nothing stored by either


async def test_a_stop_the_monitor_fired_first_is_not_named_as_cancelled(db, notified, keys):
    """FD2 review F7 route test: a leg stop that FIRED before this request closed its leg is not "cancelled by it"."""
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    from test_paper_orders_r2_fd2 import _stop  # noqa: PLC0415
    from test_paper_routes import _new  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)
    _use(app, keys)
    await _stop(app, stored, ids[0])
    (armed,) = [r.trigger.id for r in await triggers.list_for(db, stored.id)]
    assert await triggers.claim_fire(db, armed)  # the monitor fired it first
    reply = await _post(app, stored, _body([_new(ids[0], "BUY", 65, "30", "exit")], uuid.uuid4()))
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert reply.json()["cancelled_stops"] == []


async def test_a_claim_lost_to_a_rollback_refuses_and_stores_no_orders(app_engine, strategy):
    """Opus review F1: something (``stored_kind``'s catalogue failure path) rolls the request's session back between the
    claim and the finish; the finish must not commit orders without their key (no row updated: 583, nothing stored)."""
    key = uuid.uuid4()
    async with app_engine.connect() as conn:
        await conn.begin()
        await request_key.claim_in_transaction(conn, USER, key, strategy, BODY, "paper")
        await conn.rollback()  # the claim is gone
        await conn.begin()
        with pytest.raises(StrategyRefused, match="request_key_store_unavailable"):
            await request_key.finish_in_transaction(conn, USER, key, {"cancelled_stops": []})


async def test_r9_a_request_past_the_server_deadline_refuses_and_stores_nothing(db, notified, keys, monkeypatch):
    """Opus review R9: the page gives up at 10 s and may press again; a request that only reaches its commit after the
    server deadline (8 s) refuses ``store_busy`` with nothing stored, and its key is free again."""
    from ofo_app.routes import paper as route  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    clock = iter([0.0] + [route.COMMIT_DEADLINE_S + 1.0] * 20)
    monkeypatch.setattr(route, "_monotonic", lambda: next(clock))
    key = uuid.uuid4()
    late = await _post(app, stored, _body(orders, key))
    assert late.status_code == HTTPStatus.CONFLICT and "busy with another action" in late.text, late.text[:300]
    assert await _count(db, stored) == 0
    monkeypatch.setattr(route, "_monotonic", lambda: 0.0)  # the same key on time: placed (the late one freed it)
    again = await _post(app, stored, _body(orders, key))
    assert again.status_code == HTTPStatus.CREATED, again.text[:300]


async def test_n5_the_deadline_counts_from_the_requests_entry_not_from_after_the_early_work(db, notified, keys,
                                                                                            monkeypatch):
    """FD5 N5: the 8 s deadline started after the key lookup and the Redis claim, so a request that spent 3 s there
    could commit at 11 s, after the page's 10 s timeout. Now the clock starts at the entry: entered at 0, 3 s spent in
    the early work, the commit check at 9 s is past 8 s from the entry (it would be 6 s from the old start)."""
    from ofo_app.routes import paper as route  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    now = {"t": 0.0}
    real_lookup = request_key.lookup

    async def slow_lookup(*a, **k):
        now["t"] = 3.0  # the early work took 3 s
        return await real_lookup(*a, **k)

    from ofo_app import paper_limit  # noqa: PLC0415
    real_place = paper_limit.place_checked

    async def place_at_nine(*a, **k):
        now["t"] = 9.0  # the work before the commit took 6 s more: the commit check reads 9 s after the entry
        return await real_place(*a, **k)
    monkeypatch.setattr(request_key, "lookup", slow_lookup)
    monkeypatch.setattr(paper_limit, "place_checked", place_at_nine)
    monkeypatch.setattr(route, "_monotonic", lambda: now["t"])
    late = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert late.status_code == HTTPStatus.CONFLICT, late.text[:300]
    assert await _count(db, stored) == 0


async def test_f_a_failing_catalogue_read_keeps_the_claim_and_stores_orders_with_their_key(
        db, notified, keys, monkeypatch):
    """Class fix (``stored_kind``): on the production tracked-reader shape (the request's OWN session,
    ``get_tracked_reader`` with no test override) a catalogue read that fails must roll back only its savepoint. It used
    to call ``db.rollback()``, which dropped the caller's order-key claim and strategy lock, and the orders then
    committed with no key row. Now: 201, the orders stored, and the key row done."""
    from ofo_app import adjustment_readers as readers  # noqa: PLC0415
    from ofo_app.routes.adjustment import get_tracked_reader  # noqa: PLC0415
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415

    app, stored, _ids = await _open(db)  # an open paper position: the reader reaches ``stored_kind``
    _use(app, keys)
    app.dependency_overrides.pop(get_tracked_reader)  # production: ``partial(read_tracked, db=<the request>)``
    monkeypatch.setattr(readers, "current_user_ref", lambda: stored.user_ref)

    async def broken(_db):
        raise OperationalError("SELECT", {}, Exception("catalogue read failed"))
    monkeypatch.setattr(readers, "load_catalogue", broken)
    before = await _count(db, stored)
    _, orders = _prices(stored)
    key = uuid.uuid4()
    reply = await _post(app, stored, _body(orders, key))
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert await _count(db, stored) == before + len(orders)
    state = (await db.execute(text("SELECT state FROM public.order_request_keys WHERE request_key = :k"),
                              {"k": key})).scalar_one()
    assert state == "done"
