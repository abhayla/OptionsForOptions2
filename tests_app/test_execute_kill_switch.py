"""ADR-127 core: the owner's kill switch refuses every basket build and the Execute screen's read says so (DB, CI).

On the owner's REAL 2026-10-16 order, replayed as in ``test_execute_route`` (market open at the replay clock): switch on
-> an ENTRY prepare is refused with exactly the ADR-127 sentence, nothing is stored and no ``order_prepared`` is audited;
``GET /execute/market-status`` says ``paused``; switch off -> the same prepare passes the gate (200, plan 1 stored).
Flipping writes exactly ONE audit event (``admin_change_recorded``) and the hash chain still verifies. A request without
the owner key, with a wrong key, or on a server with no (or a short) key is a plain 404 and writes nothing.
"""
from __future__ import annotations

import pytest
from ofo_app.execute_replay import AT
from test_execute_route import (  # noqa: F401 - the route test's own seams and fixtures
    RATES,
    _Quotes,
    _Replay,
    _session_for,
    _strategy_one,
    audit_head,
    audit_since,
)

OWNER_KEY = "k" * 32
ADR_127 = ("Execution is paused by the platform right now. You can review and save your plan; "
           "no orders can be sent.")
HEADERS = {"X-Owner-Key": OWNER_KEY}


async def _setup(admin_engine, app_engine, monkeypatch, conn):
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app, _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    monkeypatch.setenv("OFO_OWNER_KEY", OWNER_KEY)
    user = _user()
    sid = await _strategy_one(conn, user, app_engine.url.username)
    app = _app(_ConnMaker(conn), user)
    app.dependency_overrides[route.get_quote_reader] = _Quotes
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
    app.dependency_overrides[route.load_charge_rates] = lambda: RATES
    entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
    app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
    return app, user, sid


async def _flip(app, paused: bool, headers=HEADERS):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.put("/admin/kill-switch", json={"paused": paused, "reason": "test flip"}, headers=headers)


async def _prepare(app, sid: int):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.post(f"/strategies/{sid}/execute", json={"action": "ENTRY"})


async def _screen_verdict(app) -> dict:
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        resp = await ac.get("/execute/market-status")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.usefixtures("app_engine")
async def test_core_switch_on_refuses_the_prepare_off_passes_and_each_flip_is_one_audit_event(
        app_engine, admin_engine, monkeypatch):
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app import kill_switch  # noqa: PLC0415
    from ofo_app.audit_store import load_log  # noqa: PLC0415

    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            app, user, sid = await _setup(admin_engine, app_engine, monkeypatch, conn)
            assert await kill_switch.is_paused(conn) is False  # no event yet: off
            assert (await _screen_verdict(app))["status"] == "open"

            head = await audit_head(conn)
            on = await _flip(app, True)
            assert on.status_code == 200 and on.json() == {"paused": True}, on.text
            (event,) = await audit_since(conn, head)  # exactly ONE event for the flip
            assert event[0] == "admin_change_recorded" and event[1].startswith("kill-switch:")
            assert event[2] == {"action": "kill_switch_on", "reason": "test flip"}

            head = await audit_head(conn)
            refused = await _prepare(app, sid)
            assert refused.status_code == 409, refused.text
            assert refused.json()["what_happened"] == ADR_127  # exactly the ADR-127 sentence
            assert await audit_since(conn, head) == []  # a refusal writes nothing (no order_prepared)
            assert not await plans.plans_for(conn, user, sid)  # no plan, no plan number consumed

            verdict = await _screen_verdict(app)  # the screen's read, before any click
            assert verdict["status"] == "paused" and verdict["next_open"] is None
            assert verdict["message"]["what_happened"] == ADR_127

            head = await audit_head(conn)
            off = await _flip(app, False)
            assert off.status_code == 200 and off.json() == {"paused": False}, off.text
            (event,) = await audit_since(conn, head)
            assert event[2] == {"action": "kill_switch_off", "reason": "test flip"}

            assert (await _screen_verdict(app))["status"] == "open"
            passed = await _prepare(app, sid)  # the same prepare, switch off: passes the gate
            assert passed.status_code == 200, passed.text
            (stored,) = await plans.plans_for(conn, user, sid)
            assert stored.plan_number == 1

            _, anchor = await load_log(conn)  # the chain verifies with the flips in it
            assert anchor.count == await audit_head(conn)
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_a_switch_flipped_between_requests_is_seen_by_the_next_gate_not_a_cached_value(
        app_engine, admin_engine, monkeypatch):
    """Threat: a cached "off" during a request. Off -> on -> off, each answered by the very next prepare."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            app, _, sid = await _setup(admin_engine, app_engine, monkeypatch, conn)
            assert (await _flip(app, True)).status_code == 200
            assert (await _prepare(app, sid)).status_code == 409
            assert (await _flip(app, False)).status_code == 200
            assert (await _prepare(app, sid)).status_code == 200
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
@pytest.mark.parametrize("headers, key_env", [
    ({}, "k" * 32),                               # no key sent
    ({"X-Owner-Key": "w" * 32}, "k" * 32),        # wrong key
    ({"X-Owner-Key": "short"}, "short"),          # a server key below the minimum is no key at all
    ({"X-Owner-Key": OWNER_KEY}, ""),             # a server with no key set
])
async def test_a_normal_user_cannot_flip_it_and_nothing_is_written(app_engine, admin_engine, monkeypatch,
                                                                    headers, key_env):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            app, user, sid = await _setup(admin_engine, app_engine, monkeypatch, conn)
            monkeypatch.setenv("OFO_OWNER_KEY", key_env)
            head = await audit_head(conn)
            resp = await _flip(app, True, headers=headers)
            assert resp.status_code == 404, resp.text
            assert await audit_since(conn, head) == []
            assert (await _screen_verdict(app))["status"] == "open"  # still off
        finally:
            await trans.rollback()
