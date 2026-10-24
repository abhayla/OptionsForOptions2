"""W-151 (REQ-119 AC-5): Execute refuses a plan built from a version that is not the current saved version.

Spec basis: REQ-119 AC-5 "the server refuses an Execute whose version is not the current saved version". The body
names the saved strategy revision its review was built from (``revision``, required); the route compares it with the
stored revision as the FIRST thing after the strategy is loaded, before any Zerodha read, plan number or plan row.

Every case runs the real route on the database inside a rolled-back transaction, with Zerodha answered by the recorded
replies (``RecordedKite``: it lists every Kite URL asked, so "zero broker calls" is a count, not a claim).

Answer states of the stored strategy (B4 (d)): same revision -> the plan as today; a newer stored revision -> 409
``execute_plan_changed``; not found -> today's 404; unreadable -> today's 410 (``strategy_stored_unreadable``);
store failed -> today's error. The last three are unchanged paths covered by ``test_execute_route.py``.
"""
from __future__ import annotations

import pytest
from ofo.errors import render
from sqlalchemy import text
from test_execute_route import (
    AT,
    KITE_READS_PER_EXECUTE,
    RATES,
    REAL_ORDER,
    _kite_reads,
    _Quotes,
    _Replay,
    _session_for,
    _strategy_one,
)

pytestmark = pytest.mark.usefixtures("order_path_on")  # W-121

PLAN_CHANGED = "Your plan changed - review it again."
INPUT_REFUSED = "USER_INPUT_002"  # the catalogue answer for a body the model refuses


async def _plan_rows(conn, sid: int) -> int:
    return (await conn.execute(text("SELECT count(*) FROM public.execution_plans WHERE strategy_id = :i"),
                               {"i": sid})).scalar_one()


async def _stored_revision(conn, sid: int) -> int:
    return (await conn.execute(text("SELECT revision FROM public.strategies WHERE id = :i"), {"i": sid})).scalar_one()


async def _bump_revision(conn, sid: int) -> int:
    """Another change saved after the review (as a leg edit or a second tab would): the stored revision moves on."""
    await conn.execute(text("UPDATE public.strategies SET revision = revision + 1 WHERE id = :i"), {"i": sid})
    return await _stored_revision(conn, sid)


async def _run(app_engine, admin_engine, monkeypatch, body_of, *, bump: bool = False):
    """Store strategy 1, optionally move its revision on, POST Execute with ``body_of(revision_read)``; returns the
    reply, the recorded Kite transport and the plan rows after."""
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app, _client, _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            reviewed = await _stored_revision(conn, sid)  # the version the user reviewed
            if bump:
                assert await _bump_revision(conn, sid) == reviewed + 1
            app = _app(_ConnMaker(conn), user)
            app.dependency_overrides[route.get_quote_reader] = _Quotes
            app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
            app.dependency_overrides[route.load_charge_rates] = lambda: RATES
            kite = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(kite)
            async with _client(app) as ac:
                resp = await ac.post(f"/strategies/{sid}/execute", json=body_of(reviewed))
            rows = await _plan_rows(conn, sid)
        finally:
            await trans.rollback()
    return resp, kite, rows


@pytest.mark.usefixtures("app_engine")
async def test_core_a_stale_revision_is_refused_before_any_broker_call_or_plan_row(app_engine, admin_engine,
                                                                                    monkeypatch):
    """Attack 2: the review was built from revision N, the stored strategy is now N+1 -> 409 with the exact text,
    zero Zerodha calls, zero plan rows."""
    resp, kite, rows = await _run(app_engine, admin_engine, monkeypatch,
                                  lambda rev: {"action": "ENTRY", "revision": rev}, bump=True)
    assert resp.status_code == 409, resp.text  # noqa: PLR2004
    body = resp.json()
    assert body["what_happened"] == PLAN_CHANGED
    expected = render("execute_plan_changed")
    assert (body["what_happened"], body["impact"], body["what_is_blocked"], body["next_action"]) == (
        expected.what_happened, expected.impact, expected.what_is_blocked, expected.next_action)
    assert "basket" not in body and "orders" not in body  # no plan in the refusal
    assert kite.calls == []  # not one Zerodha read: the check runs before the order book
    assert rows == 0


@pytest.mark.usefixtures("app_engine")
async def test_a_revision_ahead_of_the_stored_one_is_refused_the_same_way(app_engine, admin_engine, monkeypatch):
    """A version the server never saved is not the current saved version either."""
    resp, kite, rows = await _run(app_engine, admin_engine, monkeypatch,
                                  lambda rev: {"action": "ENTRY", "revision": rev + 1})
    assert resp.status_code == 409 and resp.json()["what_happened"] == PLAN_CHANGED, resp.text  # noqa: PLR2004
    assert (kite.calls, rows) == ([], 0)


@pytest.mark.usefixtures("app_engine")
async def test_the_current_revision_builds_the_plan_exactly_as_today(app_engine, admin_engine, monkeypatch):
    """Attack 3: the reviewed revision is still the stored one -> plan 1, BUY 65 LIMIT 3.35 tagged as the real order,
    the same Zerodha reads as before W-151, one plan row."""
    resp, kite, rows = await _run(app_engine, admin_engine, monkeypatch,
                                  lambda rev: {"action": "ENTRY", "revision": rev})
    assert resp.status_code == 200, resp.text  # noqa: PLR2004
    body = resp.json()
    (order,) = body["orders"]
    assert body["plan_number"] == 1 and body["tags"] == [REAL_ORDER["tag"]]
    assert (order["transaction_type"], order["quantity"], order["price"]) == ("BUY", 65, "3.35")
    assert "seq" not in body  # no seq sent -> no seq key
    assert _kite_reads(kite) == KITE_READS_PER_EXECUTE
    assert rows == 1


class _CountingBroker:
    """A fake Zerodha session: every read or margin call is counted (and answered with an error, so a route that
    reaches the broker is visible both in the count and in the reply)."""

    api_key = "kitekey"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.reads = self._side("reads")
        self.margin = self._side("margin")

    def _side(self, name: str):
        broker = self

        class _Side:
            def __getattr__(self, attr: str):
                def call(*_a, **_k):
                    broker.calls.append(f"{name}.{attr}")
                    raise RuntimeError("counting fake broker: no reply")
                return call
        return _Side()


class _FakeDb:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


async def _db_free(monkeypatch, sent: int, stored_revision: int = 3):
    """The real route with the store answering a strategy at ``stored_revision`` and a counting broker; the plan
    store's number and write are counted too. No database is opened."""
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_browser_never_decides_eligibility import _post  # noqa: PLC0415

    plan_calls: list[str] = []

    async def load(_db, _user, sid):
        return SimpleNamespace(id=sid, revision=stored_revision, saved=None)

    async def plan_write(*_a, **_k):
        plan_calls.append("plan")
        raise AssertionError("a plan number or row was asked for")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(route.store, "load", load)
    monkeypatch.setattr(route.plans, "next_plan_number", plan_write)
    monkeypatch.setattr(route.plans, "record_plan", plan_write)
    broker, db = _CountingBroker(), _FakeDb()
    app = create_app()
    app.dependency_overrides[route.get_db] = lambda: db
    app.dependency_overrides[route.get_kite_session] = lambda: broker
    app.dependency_overrides[route.get_quote_reader] = lambda: None
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
    app.dependency_overrides[route.load_charge_rates] = lambda: None
    app.dependency_overrides[route.current_user_ref] = lambda: "u"
    resp = await _post(app, "/strategies/7/execute", {"action": "ENTRY", "revision": sent})
    return resp, broker, plan_calls, db


@pytest.mark.parametrize("sent", [2, 4])
async def test_core_db_free_a_stale_revision_never_reaches_the_broker_or_the_plan_store(monkeypatch, sent):
    """Core proof without a database: stored revision 3, the review built from 2 (or a never-saved 4) -> 409 with the
    exact text, zero broker calls, zero plan-store calls, nothing committed."""
    resp, broker, plan_calls, db = await _db_free(monkeypatch, sent)
    assert resp.status_code == 409, resp.text  # noqa: PLR2004
    assert resp.json()["what_happened"] == PLAN_CHANGED
    assert (broker.calls, plan_calls, db.commits) == ([], [], 0)


async def test_db_free_discrimination_the_current_revision_goes_on_to_the_broker(monkeypatch):
    """The zero counts above come from the check, not from a route that never reads the broker: the same request at
    the stored revision asks Zerodha's order book first (the counting fake answers with an error)."""
    resp, broker, plan_calls, db = await _db_free(monkeypatch, 3)
    assert broker.calls == ["reads.fetch_orders"]
    assert resp.json().get("what_happened") != PLAN_CHANGED
    assert (plan_calls, db.commits) == ([], 0)


@pytest.mark.parametrize("body", [
    {"action": "ENTRY"},  # missing
    {"action": "ENTRY", "revision": 0},
    {"action": "ENTRY", "revision": -1},
    {"action": "ENTRY", "revision": "1"},
    {"action": "ENTRY", "revision": True},
    {"action": "ENTRY", "revision": 1.0},
])
async def test_a_missing_or_malformed_revision_is_a_malformed_request(body, monkeypatch):
    """No database: the body model refuses before any dependency result is used (as the closed-body test)."""
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_browser_never_decides_eligibility import _post  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    app = create_app()
    app.dependency_overrides[route.get_db] = lambda: None
    app.dependency_overrides[route.get_kite_session] = lambda: None
    app.dependency_overrides[route.get_quote_reader] = lambda: None
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: None)
    app.dependency_overrides[route.load_charge_rates] = lambda: None
    app.dependency_overrides[route.current_user_ref] = lambda: "u"
    resp = await _post(app, "/strategies/1/execute", body)
    assert resp.status_code == 422, resp.text  # noqa: PLR2004
    assert resp.json()["code"] == INPUT_REFUSED
