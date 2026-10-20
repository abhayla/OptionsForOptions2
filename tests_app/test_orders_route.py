"""GC-6 ORDERS-SCREEN (ADR-135, ADR-138 (1), ADR-079): ``GET /orders`` against the database, on the owner's REAL GC-3L
rows (``orders-gc3l-2026-10-19.json``: BUY 65 filled 65, tag OFS9V1L0), the tag rewritten to the stored strategy's own
(the strategy id of the shared test DB is not 9). The plan stores the test catalogue's real contract symbol; the route
matches by tag only, so the fixture's symbol does not matter. Runs in CI (DB).
"""
from __future__ import annotations

import pytest
from ofo.execution.basket import make_tag

SNAPSHOT = "gc3l-2026-10-19"  # the _Reads snapshot name; every test passes its own orders, so no file is read


def _gc3l_row(tag: str, **changes) -> dict:
    from test_execution_return import _data  # noqa: PLC0415

    entry = next(r for r in _data("orders-gc3l-2026-10-19") if r["tag"] == "OFS9V1L0")
    return {**entry, "tag": tag, **changes}


async def _get(app):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.get("/orders")


async def _events(conn, tag: str) -> int:
    from sqlalchemy import text  # noqa: PLC0415

    sql = text("SELECT count(*) FROM public.audit_events WHERE event_type = 'broker_response_recorded' "
               "AND payload->>'tag' = :t")
    return int((await conn.execute(sql, {"t": tag})).scalar_one())


async def _setup(conn, app_engine, plan_price="7.00"):
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_execution_return import _store_plan  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    user = _user()
    sid = await _strategy_one(conn, user, app_engine.url.username)
    await _store_plan(conn, user, sid, ("ENTRY", "BUY", plan_price))
    return user, sid


@pytest.mark.usefixtures("app_engine")
async def test_core_open_plan_with_no_prior_check_is_decided_by_the_load_read(app_engine, admin_engine, monkeypatch):
    """The page load alone (no Check) turns an open plan into ``Executed 65 of 65`` from Zerodha's row; one GET
    /orders per load; the row is audited once; the plan stays open (only the Check route closes plans)."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from test_execution_return import _app_for, _Reads  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, sid = await _setup(conn, app_engine)
            tag = make_tag(sid, 1, 0)
            reads = _Reads(SNAPSHOT, orders=[_gc3l_row(tag)])
            app = _app_for(conn, user, reads)
            body = (await _get(app)).json()
            assert body["kite_read"] == "read"
            (line,) = body["orders"]
            assert (line["strategy_id"], line["plan_number"], line["action"], line["transaction_type"]) == (
                sid, 1, "ENTRY", "BUY")
            assert (line["state"], line["filled_quantity"], line["ordered_quantity"]) == ("executed", 65, 65)
            assert (line["could_not_confirm"], line["needs_reconciliation"], line["message"]) == (False, False, None)
            assert reads.calls == [("GET", reads.calls[0][1])] and reads.calls[0][1].endswith("/orders")
            assert await _events(conn, tag) == 1
            await _get(app)
            assert await _events(conn, tag) == 1  # a reload records nothing new
            assert [p.status for p in await plans.plans_for(conn, user, sid)] == ["open"]
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
@pytest.mark.parametrize(("book", "state"), [
    ("absent", "not_sent"), ("OPEN", "placed"), ("TRIGGER PENDING", "placed"),
    ("REJECTED", "not_executed"), ("CANCELLED", "not_executed")])
async def test_open_plan_states_from_the_load_read(app_engine, admin_engine, monkeypatch, book, state):
    from test_execution_return import _app_for, _Reads  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, sid = await _setup(conn, app_engine)
            rows = [] if book == "absent" else [_gc3l_row(make_tag(sid, 1, 0), status=book, filled_quantity=0)]
            body = (await _get(_app_for(conn, user, _Reads(SNAPSHOT, orders=rows)))).json()
            (line,) = body["orders"]
            assert (line["state"], line["filled_quantity"], line["could_not_confirm"]) == (state, None, False)
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_failed_read_never_guesses_a_state_for_an_open_plan(app_engine, admin_engine, monkeypatch):
    """No Zerodha session: the open plan has no audit row -> no state, the catalogue message, a Check button; after a
    recorded row (an earlier good load) the same failed read answers from that row."""
    from ofo_app.routes import execute as execute_route  # noqa: PLC0415
    from test_execution_return import _app_for, _Reads  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, sid = await _setup(conn, app_engine)
            down = _app_for(conn, user, _Reads(SNAPSHOT, orders=[]))
            down.dependency_overrides[execute_route.get_kite_session] = lambda: None
            body = (await _get(down)).json()
            (line,) = body["orders"]
            assert body["kite_read"] == "failed"
            assert (line["state"], line["could_not_confirm"]) == (None, True)
            assert line["message"]["what_happened"]  # the catalogue's four parts
            good = _app_for(conn, user, _Reads(SNAPSHOT, orders=[_gc3l_row(make_tag(sid, 1, 0), status="OPEN",
                                                                           filled_quantity=0)]))
            assert (await _get(good)).json()["orders"][0]["state"] == "placed"
            (again,) = (await _get(down)).json()["orders"]
            assert (again["state"], again["could_not_confirm"]) == ("placed", False)
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_another_users_orders_never_appear_and_no_strategy_is_an_empty_list(app_engine, admin_engine,
                                                                                    monkeypatch):
    from test_execution_return import _app_for, _Reads, _store_plan, _strategy_b  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, sid = await _setup(conn, app_engine)
            other = _user()
            other_sid = await _strategy_b(conn, other)
            await _store_plan(conn, other, other_sid, ("ENTRY", "BUY", "7.00"))
            reads = _Reads(SNAPSHOT, orders=[_gc3l_row(make_tag(other_sid, 1, 0))])
            mine = (await _get(_app_for(conn, user, reads))).json()
            assert [line["strategy_id"] for line in mine["orders"]] == [sid]
            assert mine["orders"][0]["state"] == "not_sent"  # the other user's row is not this user's order
            assert await _events(conn, make_tag(other_sid, 1, 0)) == 0  # and it was not recorded for this load
            nobody = (await _get(_app_for(conn, _user(), reads))).json()
            assert (nobody["orders"], nobody["kite_read"]) == ([], "not_needed")
        finally:
            await trans.rollback()
