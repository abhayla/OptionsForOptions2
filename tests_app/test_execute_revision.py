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
# ruff: noqa: F811 - the imported fixture is used as a test argument
from __future__ import annotations

from decimal import Decimal as D

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
from test_order_request_key_r2_fd2 import keys  # noqa: F401 - fixture

pytestmark = pytest.mark.usefixtures("order_path_on")  # W-121

PLAN_CHANGED = "Your plan changed after you reviewed it."
INPUT_REFUSED = "USER_INPUT_002"  # the catalogue answer for a body the model refuses


async def _plan_rows(conn, sid: int) -> int:
    return (await conn.execute(text("SELECT count(*) FROM public.execution_plans WHERE strategy_id = :i"),
                               {"i": sid})).scalar_one()


async def _stored_revision(conn, sid: int) -> int:
    return (await conn.execute(text("SELECT revision FROM public.strategies WHERE id = :i"), {"i": sid})).scalar_one()


async def _bump_revision(conn, user: str, sid: int, reviewed: int) -> int:
    """Another change saved after the review (as a leg edit or a second tab would), through the store's own update
    (the database trigger moves the revision on a definition change; ``revision`` is never written directly): the
    same contract, 130 units instead of 65."""
    from ofo.engine import Action  # noqa: PLC0415
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from ofo_app import strategy_store as store  # noqa: PLC0415

    stored = await store.load(conn, user, sid)
    (cid,) = stored.saved.contract_ids
    saved = await store.build_definition(conn, "NIFTY", [sf.LegChoice(int(cid), Action.BUY, 130, None)],
                                         rules_ref=None, risk_limits={}, preferences={})
    await store.update(conn, user, sid, saved, expected_revision=reviewed)
    return await _stored_revision(conn, sid)


async def _run(app_engine, admin_engine, monkeypatch, body_of, *, bump: bool = False, during=None, keys=None,  # noqa: PLR0913
               tweak=None):
    """Store strategy 1, optionally move its revision on, POST Execute with ``body_of(revision_read)``; returns the
    reply, the recorded Kite transport and the plan rows after. ``during(conn, user, sid)`` (R3) runs once, after the
    margin wait (the LAST wait of the door), as another tab would between the reads and the plan write.
    ``tweak(app)`` (B2 item 3) may replace a dependency override before the request."""
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
                assert await _bump_revision(conn, user, sid, reviewed) == reviewed + 1
            if during is not None:
                real_off_loop, fired = route._off_loop, []

                async def off_loop(req, fn, *a, **k):
                    out = await real_off_loop(req, fn, *a, **k)
                    if getattr(fn, "__name__", "") == "checked_basket" and not fired:
                        fired.append(1)
                        await during(conn, user, sid)
                    return out
                monkeypatch.setattr(route, "_off_loop", off_loop)
            maker = _ConnMaker(conn)
            if keys is not None:  # a real session over savepoints: its rollback really undoes the request's writes
                from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: PLC0415
                maker = async_sessionmaker(bind=conn, class_=AsyncSession, expire_on_commit=False,
                                           join_transaction_mode="create_savepoint")
            app = _app(maker, user)
            if keys is not None:
                from ofo_app import request_key  # noqa: PLC0415
                app.dependency_overrides[request_key.get_key_store] = lambda: keys
            app.dependency_overrides[route.get_quote_reader] = _Quotes
            app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
            app.dependency_overrides[route.load_charge_rates] = lambda: RATES
            kite = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(kite)
            if tweak is not None:
                tweak(app)
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
    # one commit: the pooled connection is given back BEFORE the Zerodha read (FD3 item 4); nothing is written
    assert (plan_calls, db.commits) == ([], 1)


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


@pytest.mark.usefixtures("app_engine")
async def test_r3_a_holding_adopted_during_the_waits_refuses_the_plan_and_stores_nothing(app_engine, admin_engine,
                                                                                         monkeypatch):
    """R3 (W-151): the adopted holdings were read before the Zerodha and margin waits; another tab adopts a holding
    during them -> 409 ``execute_plan_changed`` under the lock, no plan row (the plan was priced without it)."""
    from ofo_app import order_book_store as books  # noqa: PLC0415
    from test_execute_route import CORE_ID  # noqa: PLC0415

    async def adopt(conn, user, sid):
        await books.record_adopted(conn, user, sid, books.AdoptedHolding(
            f"{CORE_ID.exchange_segment}:{CORE_ID.exchange_token}", "BUY", 65, "NRML", D("7.00"), "adopt:r3:1"))
    resp, _kite, rows = await _run(app_engine, admin_engine, monkeypatch,
                                   lambda rev: {"action": "ENTRY", "revision": rev}, during=adopt)
    assert resp.status_code == 409, resp.text  # noqa: PLR2004
    assert resp.json()["what_happened"] == PLAN_CHANGED
    assert rows == 0


@pytest.mark.usefixtures("app_engine")
async def test_r3_a_strategy_saved_during_the_waits_refuses_the_plan_and_stores_nothing(app_engine, admin_engine,
                                                                                        monkeypatch):
    """R3 (W-151): the revision matched at the start; a save from another tab during the waits moves it -> 409, no
    plan row."""
    async def save(conn, user, sid):
        reviewed = await _stored_revision(conn, sid)
        assert await _bump_revision(conn, user, sid, reviewed) == reviewed + 1
    resp, _kite, rows = await _run(app_engine, admin_engine, monkeypatch,
                                   lambda rev: {"action": "ENTRY", "revision": rev}, during=save)
    assert resp.status_code == 409, resp.text  # noqa: PLR2004
    assert resp.json()["what_happened"] == PLAN_CHANGED
    assert rows == 0


@pytest.mark.usefixtures("app_engine")
async def test_g_a_request_past_the_server_deadline_refuses_too_slow_stores_nothing_and_frees_its_key(
        app_engine, admin_engine, monkeypatch, keys):
    """R9 on the real door (as the paper door): the page gives up at 10 s; a request that reaches its commit after the
    8 s server deadline refuses ``order_request_too_slow`` (409), stores no plan, and frees its key, so the same key on
    time then
    prepares the plan (a fake slow clock; the second run proves the late one released the key)."""
    import uuid  # noqa: PLC0415

    from ofo_app.routes import execute as route  # noqa: PLC0415

    key = str(uuid.uuid4())
    clock = iter([0.0] + [route.COMMIT_DEADLINE_S + 1.0] * 20)
    monkeypatch.setattr(route, "_monotonic", lambda: next(clock))
    late, _kite, rows = await _run(app_engine, admin_engine, monkeypatch, keys=keys,
                                   body_of=lambda rev: {"action": "ENTRY", "revision": rev, "client_request_id": key})
    assert late.status_code == 409 and "took too long" in late.text, late.text[:300]  # noqa: PLR2004
    assert rows == 0
    monkeypatch.setattr(route, "_monotonic", lambda: 0.0)
    again, _kite, rows = await _run(app_engine, admin_engine, monkeypatch, keys=keys,
                                    body_of=lambda rev: {"action": "ENTRY", "revision": rev, "client_request_id": key})
    assert again.status_code == 200 and rows == 1, again.text[:300]  # noqa: PLR2004


@pytest.mark.usefixtures("app_engine")
async def test_b2_item3_the_deadline_counts_from_arrival_not_from_the_handlers_first_line(
        app_engine, admin_engine, monkeypatch, keys):
    """B2 item 3 (RA review F-1 on the real door). Real case: a basket committed 10.5 s after arrival on the paper
    door. Here the dependency stage takes 3 s (settings, charge rates, the pool wait) and the last wait ends at 10.5 s:
    7.5 s after the handler's first line (the old start: committed, 200), 10.5 s after ARRIVAL (past the page's 10 s:
    refused, nothing stored, key freed)."""
    import uuid  # noqa: PLC0415

    from ofo_app.routes import execute as route  # noqa: PLC0415

    now = {"t": 0.0}
    monkeypatch.setattr(route, "_monotonic", lambda: now["t"])
    key = str(uuid.uuid4())

    def slow_dependency(app):
        async def charge_rates():
            now["t"] = 3.0
            return RATES
        app.dependency_overrides[route.load_charge_rates] = charge_rates

    async def late_wait(_conn, _user, _sid):
        now["t"] = 10.5

    late, _kite, rows = await _run(app_engine, admin_engine, monkeypatch, keys=keys, during=late_wait,
                                   tweak=slow_dependency,
                                   body_of=lambda rev: {"action": "ENTRY", "revision": rev, "client_request_id": key})
    assert late.status_code == 409 and "took too long" in late.text, late.text[:300]  # noqa: PLR2004
    assert rows == 0
    now["t"] = 0.0
    again, _kite, rows = await _run(app_engine, admin_engine, monkeypatch, keys=keys,
                                    body_of=lambda rev: {"action": "ENTRY", "revision": rev, "client_request_id": key})
    assert again.status_code == 200 and rows == 1, again.text[:300]  # noqa: PLR2004
