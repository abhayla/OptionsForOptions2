"""Lane FD2 item 2 (issues #869, #871; ADR-017): the order request key ``client_request_id`` on
POST /paper/strategies/{id}/orders and POST /strategies/{id}/execute. Core: the same key twice places the order once
(real PostgreSQL; the key store is the app's short-lived store, Redis; fakeredis here). No migration: a durable key
store needs one (listed for Lane FD)."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

import asyncio
import uuid
from http import HTTPStatus

import pytest
from ofo_app import request_key
from ofo_app import strategy_store as store
from ofo_app.routes.paper import PaperOrdersIn
from sqlalchemy import text
from test_paper_armed_exits import _order
from test_paper_routes import _new
from test_paper_triggers_routes import _setup, db, notified  # noqa: F401 - fixtures
from test_strategy_store import _client, _ids, _saved_in

TWO_ORDERS, FOUR_ORDERS, LOTS_130 = 2, 4, 130


@pytest.fixture
async def keys(redis_url):
    client = request_key.new_client(redis_url)
    await client.flushdb()
    yield request_key.RedisKeyStore(lambda: client)
    await client.aclose()


def _prices(stored):
    ids = stored.saved.contract_ids
    return ids, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")]


def _body(orders, key=None) -> dict:
    body = {"orders": [_order(o) for o in orders]}
    if key is not None:
        body["client_request_id"] = str(key)
    return body


async def _count(db, stored) -> int:
    return (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": stored.id})).scalar_one()


async def _post(app, stored, body):
    async with _client(app) as c:
        return await c.post(f"/paper/strategies/{stored.id}/orders", json=body)


def _use(app, store_):
    app.dependency_overrides[request_key.get_key_store] = lambda: store_


async def test_core_the_same_key_twice_places_the_order_once(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    key = uuid.uuid4()
    first = await _post(app, stored, _body(orders, key))
    assert first.status_code == HTTPStatus.CREATED, first.text
    assert await _count(db, stored) == TWO_ORDERS
    second = await _post(app, stored, _body(orders, key))  # the page resends after an unknown outcome
    assert second.status_code == HTTPStatus.CREATED, second.text
    assert await _count(db, stored) == TWO_ORDERS, "a repeat of the same key must place nothing"
    assert [o["id"] for o in second.json()["orders"]] == [o["id"] for o in first.json()["orders"]]


async def test_two_of_four_lots_twice_is_not_four_lots(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    ids = stored.saved.contract_ids
    key = uuid.uuid4()
    body = _body([_new(ids[2], "SELL", 130, "82.75")], key)
    for _ in range(2):
        assert (await _post(app, stored, body)).status_code == HTTPStatus.CREATED
    qty = (await db.execute(text("SELECT coalesce(sum(quantity), 0) FROM public.paper_orders WHERE strategy_id = :i"),
                            {"i": stored.id})).scalar_one()
    assert qty == LOTS_130


async def test_the_same_key_on_another_strategy_is_refused_and_places_nothing(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    second = await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref, await _ids(db)))
    _, orders = _prices(stored)
    key = uuid.uuid4()
    assert (await _post(app, stored, _body(orders, key))).status_code == HTTPStatus.CREATED
    reply = await _post(app, second, _body(orders, key))
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "request key" in reply.text.lower() and "another strategy" in reply.text.lower(), reply.text
    assert await _count(db, second) == 0


async def test_the_same_key_with_a_different_body_is_refused_and_places_nothing_more(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    ids, orders = _prices(stored)
    key = uuid.uuid4()
    assert (await _post(app, stored, _body(orders, key))).status_code == HTTPStatus.CREATED
    other = [_new(ids[2], "SELL", 130, "82.75")]
    reply = await _post(app, stored, _body(other, key))
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "different order" in reply.text.lower(), reply.text
    assert await _count(db, stored) == TWO_ORDERS


async def test_a_pending_hint_with_no_durable_row_lets_the_repeat_place_once(db, notified, keys):
    """B2 item 2 (I-138): Redis `pending` is a hint, the durable claim decides (was: refused 582 for 10 minutes)."""
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    key = uuid.uuid4()
    body = _body(orders, key)
    sent = PaperOrdersIn.model_validate(body).model_dump(mode="json", exclude={"client_request_id"})
    claimed = await keys.claim(request_key.scoped(stored.user_ref, key), request_key.pending(stored.id, sent))
    assert claimed is None
    reply = await _post(app, stored, body)  # the first is "in flight" in Redis only: the table has no row
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert await _count(db, stored) == TWO_ORDERS


async def test_two_claims_at_once_let_exactly_one_through(keys):
    scoped = request_key.scoped("u", uuid.uuid4())
    rec = request_key.pending(1, {"orders": []})
    won = await asyncio.gather(*[keys.claim(scoped, rec) for _ in range(8)])
    assert [w is None for w in won].count(True) == 1


async def test_a_refused_first_request_frees_the_key_for_a_corrected_retry(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    ids = stored.saved.contract_ids
    key = uuid.uuid4()
    too_big = _body([_new(ids[0], "BUY", 650, "30", "exit")], key)
    assert (await _post(app, stored, too_big)).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    ok = _body([_new(ids[2], "SELL", 65, "82.75")], key)
    assert (await _post(app, stored, ok)).status_code == HTTPStatus.CREATED
    assert await _count(db, stored) == 1


class _Down:
    async def claim(self, *_a):
        raise request_key.KeyStoreDown("no store")

    async def put(self, *_a):
        raise request_key.KeyStoreDown("no store")

    async def release(self, *_a):
        raise request_key.KeyStoreDown("no store")


async def test_a_redis_that_cannot_be_read_no_longer_refuses_the_order(db, notified):
    """B2 item 2: the durable table decides, so a Redis outage places the order once (was: 503 583)."""
    app, stored, *_ = await _setup(db)
    _use(app, _Down())
    _, orders = _prices(stored)
    reply = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert await _count(db, stored) == TWO_ORDERS


async def test_a_request_without_a_key_behaves_as_today_and_never_touches_the_store(db, notified):
    app, stored, *_ = await _setup(db)
    _use(app, _Down())  # would refuse any keyed request
    _, orders = _prices(stored)
    assert (await _post(app, stored, _body(orders))).status_code == HTTPStatus.CREATED
    assert (await _post(app, stored, _body(orders))).status_code == HTTPStatus.CREATED  # today: a second basket
    assert await _count(db, stored) == FOUR_ORDERS


async def test_a_key_that_is_not_a_uuid_is_refused_before_anything_is_stored(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    body = _body(orders) | {"client_request_id": "not-a-uuid"}
    assert (await _post(app, stored, body)).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _count(db, stored) == 0


# --- the real order door: POST /strategies/{id}/execute (the same key rules; nothing is ordered here) -----------

async def _real_app(conn, app_engine, monkeypatch, keys_):
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_execute_route import AT, RATES, _Quotes, _Replay, _session_for, _strategy_one  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app, _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    user = _user()
    sid = await _strategy_one(conn, user, app_engine.url.username)
    app = _app(_ConnMaker(conn), user)
    app.dependency_overrides[route.get_quote_reader] = _Quotes
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
    app.dependency_overrides[route.load_charge_rates] = lambda: RATES
    entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
    app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
    _use(app, keys_)
    return app, sid, user


async def _execute(app, sid, key, action="ENTRY", seq=None):
    body = {"action": action, "revision": 1, "client_request_id": str(key)}
    if seq is not None:
        body["seq"] = seq
    async with _client(app) as c:
        return await c.post(f"/strategies/{sid}/execute", json=body)


@pytest.mark.usefixtures("order_path_on")
async def test_real_door_the_same_key_twice_prepares_one_plan(app_engine, admin_engine, monkeypatch, keys):
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            app, sid, user = await _real_app(conn, app_engine, monkeypatch, keys)
            key = uuid.uuid4()
            first = await _execute(app, sid, key, seq=7)
            assert first.status_code == HTTPStatus.OK, first.text
            again = await _execute(app, sid, key, seq=8)  # an unknown outcome: the page sends the same press again
            assert again.status_code == HTTPStatus.CONFLICT, again.text  # never the same sealed Kite form twice
            assert "basket was already prepared" in again.text
            assert len(await plans.plans_for(conn, user, sid)) == 1  # the repeat prepared nothing
            other = await _execute(app, sid, key, action="EXIT")
            assert other.status_code == HTTPStatus.CONFLICT and "different order set" in other.text
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("order_path_on")
async def test_real_door_a_redis_that_cannot_be_read_still_prepares_one_plan(app_engine, admin_engine, monkeypatch):
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            app, sid, user = await _real_app(conn, app_engine, monkeypatch, _Down())
            reply = await _execute(app, sid, uuid.uuid4())  # B2 item 2: the table decides, Redis is a hint
            assert reply.status_code == HTTPStatus.OK, reply.text
            assert len(await plans.plans_for(conn, user, sid)) == 1
        finally:
            await trans.rollback()
