"""W-144 (REQ-038 AC-2..AC-4, ADR-019): versions after the first execution on the REAL route, store and return path.

Spec basis: REQ-038 AC-2 ("From the first execution on, every meaningful modification creates a new version");
REQ-038 AC-3 ("A proposed version is separate from the active version"); REQ-038 AC-4 ("the broker's actual state
wins"). Real PostgreSQL (migration 0022); every test rolls back. The fill comes through the existing execution return
(POST /strategies/{id}/execution/return) reading the REAL recorded Kite replies of 2026-10-16 12:21:04 (BUY 65
NIFTY26O1923650CE filled); a second plan's rows are those same rows re-tagged. Nothing is ever sent to Zerodha: the
fake transport answers GET reads only and fails the test on anything else.
"""

# ruff: noqa: PLR2004 - unit counts (65 lot, 130 = two lots) read as the recorded replies state them
from __future__ import annotations

import copy
import os
import subprocess
import sys
from http import HTTPStatus
from pathlib import Path

import pytest
from ofo.errors import render
from ofo.execution.basket import make_tag
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo_app import strategy_store as store
from test_execution_return import _app_for, _data, _post, _Reads, _store_plan
from test_strategy_store import _client, _user

pytestmark = pytest.mark.usefixtures("order_path_on")

ENTRY_ORDER = "261016170576173"  # the real 12:21:04 order (orders-122104 / trades-122104)
GUARD = "OF022"  # migration 0022 SQLSTATE
INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
ROOT = Path(__file__).resolve().parents[1]


async def _versions(conn, sid: int) -> list[tuple]:
    rows = await conn.execute(text("SELECT number, state, definition::text, outcome, actual::text, confirmed_at "
                                   "IS NOT NULL, reconciled_at IS NOT NULL FROM public.strategy_versions "
                                   "WHERE strategy_id = :s ORDER BY number"), {"s": sid})
    return [tuple(r) for r in rows.all()]


async def _history_count(conn, sid: int) -> int:
    return int((await conn.execute(text("SELECT count(*) FROM public.strategy_history WHERE strategy_id = :s"),
                                   {"s": sid})).scalar_one())


def _body(saved, units: int, revision: int) -> dict:
    legs = [{"contract_id": cid, "action": leg.action.value, "quantity": units}
            for cid, leg in zip(saved.contract_ids, saved.definition.legs, strict=True)]
    return {"underlying": saved.definition.underlying, "legs": legs, "rules_ref": None, "risk_limits": {},
            "preferences": {}, "expected_revision": revision}


async def _put(app, sid: int, body: dict):
    async with _client(app) as ac:
        return await ac.put(f"/strategies/{sid}", json=body)


async def _call(app, method: str, path: str):
    async with _client(app) as ac:
        return await ac.request(method, path)


class _Plan2Reads(_Reads):
    """The 12:21:04 replies plus a second plan's order and trade (the same real rows re-tagged to plan 2, new ids);
    Zerodha's position is the recorded one times ``scale`` (1: unchanged, 2: plan 2 filled too)."""

    def __init__(self, sid: int, scale: int) -> None:
        orders, trades = _data("orders-122104"), _data("trades-122104")
        (order,) = [copy.deepcopy(r) for r in orders if r["order_id"] == ENTRY_ORDER]
        (trade,) = [copy.deepcopy(r) for r in trades if r["order_id"] == ENTRY_ORDER]
        order.update(order_id=ENTRY_ORDER + "2", tag=make_tag(sid, 2, 0))
        trade.update(order_id=ENTRY_ORDER + "2", trade_id=str(trade["trade_id"]) + "2")
        super().__init__("122104", orders=[*orders, order], trades=[*trades, trade])
        self.scale = scale

    def __call__(self, method, url, headers, body):
        status, reply = super().__call__(method, url, headers, body)
        if not url.endswith("/portfolio/positions") or self.scale == 1:
            return status, reply
        import json  # noqa: PLC0415
        doc = json.loads(reply)
        for rows in doc["data"].values():
            for row in rows:
                for key, value in list(row.items()):
                    if (key == "quantity" or key.endswith("_quantity")) and isinstance(value, int):
                        row[key] = value * self.scale
        return status, json.dumps(doc)


async def _executed(conn, user: str, app_role: str, monkeypatch) -> int:
    """Strategy 1 (BUY 65), edited twice before execution, then plan 1 filled through the real return path."""
    from test_execute_route import _strategy_one  # noqa: PLC0415
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    sid = await _strategy_one(conn, user, app_role)
    app = _app_for(conn, user, _Reads("122104"))
    saved = (await store.load(conn, user, sid)).saved
    for revision, units in ((1, 130), (2, 65)):  # AC-2 before execution: two history entries, no version
        resp = await _put(app, sid, _body(saved, units, revision))
        assert resp.status_code == HTTPStatus.OK, resp.text
        assert resp.json()["versions"] == []
    assert await _history_count(conn, sid) == 2 and await _versions(conn, sid) == []
    assert await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45")) == 1
    resp = await _post(app, sid)
    assert resp.status_code == HTTPStatus.OK and resp.json()["plans"][0]["state"] == "filled", resp.text
    return sid


async def _propose_130(conn, user: str, sid: int) -> dict:
    app = _app_for(conn, user, _Reads("122104"))
    saved = (await store.load(conn, user, sid)).saved
    resp = await _put(app, sid, _body(saved, 130, 3))
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()


async def _linked_plan(conn, user: str, sid: int, version: int | None) -> int:
    """The next ENTRY plan (65 BUY of the real contract) stored with the version it was built from."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from test_execute_route import CORE_ID  # noqa: PLC0415
    from test_execution_return import SYMBOL, D, PlanOrder  # noqa: PLC0415

    number = await plans.next_plan_number(conn, user, sid)
    order = PlanOrder(0, make_tag(sid, number, 0), f"{CORE_ID.exchange_segment}:{CORE_ID.exchange_token}", SYMBOL,
                      "BUY", 65, D("5.45"))
    await plans.record_plan(conn, user, sid, number, "ENTRY", (order,), strategy_version=version)
    return number


async def _flags(conn, sid: int) -> list[bool]:
    rows = await conn.execute(text("SELECT reconciliation_required FROM public.strategy_versions "
                                   "WHERE strategy_id = :s "
                                   "ORDER BY number"), {"s": sid})
    return [bool(r[0]) for r in rows.all()]


async def _judge(conn, user: str, sid: int, reason: str, units: int | None, *,  # noqa: PLR0913
                 link: int | None = 2) -> str | None:
    """settle_versions on the REAL store: the stored plans plus one ENTRY plan linked to ``link``, closed with
    ``reason``, created a second after version 2's confirmation (none: a minute after version 1); ``units`` is
    Zerodha's share on the real contract (None = undecidable)."""
    import datetime  # noqa: PLC0415

    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    stored = await store.load(conn, user, sid)
    stamps = [v.confirmed_at for v in stored.versions if v.confirmed_at is not None]
    at = max(stamps) + datetime.timedelta(seconds=1)
    history = await plans.plans_for(conn, user, sid)
    plan = plans.StoredPlan(sid, len(history) + 1, "ENTRY", "closed", (), at, at, reason, link)
    (key,) = stored.saved.definition.intended_position()
    return await store.settle_versions(conn, user, sid, (*history, plan), None if units is None else {key: units})


async def _refused_in_a_new_request(conn, user: str, sid: int) -> None:
    """A NEW request (fresh app, fresh store read) is refused for PUT and confirm with the reconciliation template."""
    saved = (await store.load(conn, user, sid)).saved
    put = await _put(_app_for(conn, user, _Reads("122104")), sid, _body(saved, 195, 3))
    assert put.status_code == HTTPStatus.CONFLICT, put.text
    assert render("strategy_reconciliation_required").what_happened in put.text
    number = max(v.number for v in (await store.load(conn, user, sid)).versions)
    app = _app_for(conn, user, _Reads("122104"))
    confirm = await _call(app, "POST", f"/strategies/{sid}/versions/{number}/confirm")
    assert confirm.status_code == HTTPStatus.CONFLICT, confirm.text


async def _confirmed_v2(conn, user: str, app_role: str, monkeypatch) -> int:
    sid = await _executed(conn, user, app_role, monkeypatch)
    await _propose_130(conn, user, sid)
    resp = await _call(_app_for(conn, user, _Reads("122104")), "POST", f"/strategies/{sid}/versions/2/confirm")
    assert resp.status_code == HTTPStatus.OK, resp.text
    return sid


# ---- fix 1 core (attack 1): a reconciled plan built from version 1, or with no link, never activates version 2 ----

async def test_core_a_plan_built_from_another_version_never_activates_the_confirmed_proposal(app_engine, admin_engine,
                                                                                            monkeypatch):
    """AC-3: Zerodha holds exactly version 2's 130, the plan closed filled after the confirmation, but it was built
    from version 1 (link 1) or names no version: version 2 stays proposed, not judged (verifier: time-only match)."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _confirmed_v2(conn, user, app_engine.url.username, monkeypatch)
            for link in (1, None):
                assert await _judge(conn, user, sid, "filled", 130, link=link) is None
                assert [(r[1], r[3]) for r in await _versions(conn, sid)] == [("active", None), ("proposed", None)]
            assert await _flags(conn, sid) == [False, False]
        finally:
            await trans.rollback()


# ---- fix 1 attack 2 + mutants: every answer state's effect on the version and the flag ----

@pytest.mark.parametrize(("reason", "units", "state", "outcome", "flags"), [
    ("partial", 65, "proposed", "partial", [True, False]),  # mutant: PARTIAL treated as superseded
    ("nothing_placed", 65, "superseded", "rejected", [False, False]),  # mutant: nothing_placed treated as complete
    ("nothing_placed", 130, "superseded", "rejected", [True, False]),  # REJECTED with units changed
    ("unresolved_from_positions", 65, "superseded", "failed", [False, False]),
    ("filled", 65, "superseded", "mismatch", [True, False]),  # complete, Zerodha different
    ("filled", None, "proposed", None, [True, False]),  # units unknown: not judged, flagged
])
async def test_each_broker_answer_has_its_stated_effect_and_the_flag_survives_a_new_request(  # noqa: PLR0913
        app_engine, admin_engine, monkeypatch, reason, units, state, outcome, flags):
    """AC-4: the broker wins; a result that leaves Zerodha away from the active version flags it, the flag is stored
    and a NEW request's PUT and confirm are refused (verifier: _replay dropped the domain's flag)."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _confirmed_v2(conn, user, app_engine.url.username, monkeypatch)
            assert await _judge(conn, user, sid, reason, units) == outcome
            rows = await _versions(conn, sid)
            assert [(r[0], r[1]) for r in rows] == [(1, "active"), (2, state)] and rows[1][3] == outcome
            assert await _flags(conn, sid) == flags
            if flags[0]:
                await _refused_in_a_new_request(conn, user, sid)
                # Q222: a later clean, reconciled answer never clears it, and nothing activates while flagged
                await _judge(conn, user, sid, "filled", 130)
                assert await _flags(conn, sid) == flags and (await _versions(conn, sid))[0][1] == "active"
        finally:
            await trans.rollback()


# ---- fix 1 attack 3: manual units on the broker are outside lots, never the strategy's (ADR-109) ----

async def test_manual_units_at_zerodha_are_not_counted_as_the_strategys(app_engine, admin_engine, monkeypatch):
    """AC-4 + ADR-109: plan 2 (built from version 2) filled; Zerodha holds 195 (65 bought by hand): the strategy's
    share is its own 130, so version 2 activates and the extra lots block nothing."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _confirmed_v2(conn, user, app_engine.url.username, monkeypatch)
            assert await _linked_plan(conn, user, sid, 2) == 2
            resp = await _post(_app_for(conn, user, _Plan2Reads(sid, 3)), sid)
            assert resp.status_code == HTTPStatus.OK, resp.text
            rows = await _versions(conn, sid)
            assert [(r[0], r[1], r[3]) for r in rows] == [(1, "superseded", None), (2, "active", "activated")]
            import json  # noqa: PLC0415
            assert [line["units"] for line in json.loads(rows[1][4])] == [130]  # not 195
            assert await _flags(conn, sid) == [False, False]
        finally:
            await trans.rollback()


def test_the_broker_share_is_none_when_the_book_drifted_or_a_contract_is_undecidable(monkeypatch):
    """AC-4 (mutant: the drift/undecidable check removed): no share, so nothing is judged and the strategy is
    flagged."""
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app.routes import execution_return as route  # noqa: PLC0415
    check = SimpleNamespace(key=("k",), platform_units=65, zerodha_units=65, other_units=0, kind=None,
                            undecidable=None)
    monkeypatch.setattr(route, "_checks", lambda history, world: [check])
    monkeypatch.setattr(route.er, "drifted", lambda history, book: {1})
    assert route._broker_share((), None, None) is None
    monkeypatch.setattr(route.er, "drifted", lambda history, book: set())
    assert route._broker_share((), None, None) == {("k",): 65}
    monkeypatch.setattr(route, "_checks", lambda history, world: [SimpleNamespace(**{**vars(check),
                                                                                     "undecidable": "x"})])
    assert route._broker_share((), None, None) is None


# ---- fix 1 attack 4: an open plan is in flight even after versions exist ----

async def test_an_open_plan_is_in_flight_after_versions_exist(app_engine, admin_engine, monkeypatch):
    """AC-3: the open-plan check runs before the versions' early EXECUTED answer; the edit is refused."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            await _propose_130(conn, user, sid)
            assert await store.execution_state(conn, user, sid) == store.EXECUTED
            await _linked_plan(conn, user, sid, 1)
            assert await store.execution_state(conn, user, sid) == store.IN_FLIGHT
        finally:
            await trans.rollback()


# ---- fix 1 attack 5: the database refuses an inserted active row that skipped proposal and reconciliation ----

async def test_the_guard_refuses_an_inserted_active_or_superseded_row(app_engine, admin_engine, monkeypatch):
    """AC-3 (migration 0023): as the table owner, an INSERT of an active version 3 with both stamps, an active one
    without them, a superseded one, or a flagged one is refused by the guard (OF022)."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            await _propose_130(conn, user, sid)
            await conn.execute(text("RESET ROLE"))
            insert = ("INSERT INTO public.strategy_versions (strategy_id, number, state, based_on, definition, "
                      "definition_schema_version, confirmed_at, reconciled_at, reconciliation_required) "
                      "SELECT strategy_id, 3, {state}, 1, definition, definition_schema_version, {at}, {at}, {flag} "
                      "FROM public.strategy_versions WHERE strategy_id = :s AND number = 1")
            for state, at, flag in (("'active'", "now()", "FALSE"), ("'active'", "NULL", "FALSE"),
                                    ("'superseded'", "now()", "FALSE"), ("'proposed'", "NULL", "TRUE"),
                                    ("'proposed'", "now()", "FALSE")):
                sql = insert.format(state=state, at=at, flag=flag)
                assert await _refused_with(conn, sql, sid) == GUARD, sql
        finally:
            await trans.rollback()


# ---- core + attack 2: after a fill an edit is version 2 proposed; version 1 stays active, byte for byte ----

async def test_core_after_a_fill_an_edit_is_a_proposed_version_and_version_1_stays_active(app_engine, admin_engine,
                                                                                          monkeypatch):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            before = (await conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :s"),
                                         {"s": sid})).scalar_one()
            body = await _propose_130(conn, user, sid)
            assert [(v["number"], v["state"], v["based_on"]) for v in body["versions"]] == [
                (1, "active", None), (2, "proposed", 1)]
            assert [leg["quantity"] for leg in body["definition"]["legs"]] == [65]  # the ACTIVE definition
            rows = await _versions(conn, sid)
            assert rows[0][2] == before  # version 1 = the executed definition, unchanged byte for byte
            assert await _history_count(conn, sid) == 2  # no history entry after execution
            got = await _call(_app_for(conn, user, _Reads("122104")), "GET", f"/strategies/{sid}")
            assert got.json()["versions"] == body["versions"] and got.json()["definition"] == body["definition"]
            # a second change while version 2 waits is refused (domain: one pending proposal), nothing written
            saved = (await store.load(conn, user, sid)).saved
            again = await _put(_app_for(conn, user, _Reads("122104")), sid, _body(saved, 195, 3))
            assert again.status_code == HTTPStatus.CONFLICT
            assert render("strategy_version_pending").what_happened in again.text
            assert len(await _versions(conn, sid)) == 2
        finally:
            await trans.rollback()


# ---- attack 1: no fill: edits and restore unchanged, no version row ----

async def test_without_a_fill_edits_and_restore_are_history_and_no_version_is_written(app_engine, admin_engine,
                                                                                    monkeypatch):
    from test_execute_route import _strategy_one  # noqa: PLC0415
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            app = _app_for(conn, user, _Reads("122104"))
            saved = (await store.load(conn, user, sid)).saved
            assert (await _put(app, sid, _body(saved, 130, 1))).status_code == HTTPStatus.OK
            resp = await _call(app, "POST", f"/strategies/{sid}/restore/1?expected_revision=2")
            assert resp.status_code == HTTPStatus.OK, resp.text
            assert [leg["quantity"] for leg in resp.json()["definition"]["legs"]] == [65]
            assert await _history_count(conn, sid) == 2 and await _versions(conn, sid) == []
            # a plan that ended with nothing filled is still no execution
            assert await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45")) == 1
            from ofo_app import execution_plan_store as plans  # noqa: PLC0415
            await plans.close_plan(conn, user, sid, 1, reason="nothing_placed")
            assert await store.execution_state(conn, user, sid) == store.NOT_EXECUTED
        finally:
            await trans.rollback()


# ---- standing item (c): the fill check fails closed ----

async def test_the_fill_check_fails_closed_on_an_open_plan_and_an_unreadable_store(app_engine, admin_engine,
                                                                                 monkeypatch):
    from test_execute_route import _strategy_one  # noqa: PLC0415
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            assert await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45")) == 1
            assert await store.execution_state(conn, user, sid) == store.IN_FLIGHT  # unknown fill: not a draft
            saved = (await store.load(conn, user, sid)).saved
            resp = await _put(_app_for(conn, user, _Reads("122104")), sid, _body(saved, 130, 1))
            assert resp.status_code == HTTPStatus.CONFLICT and await _history_count(conn, sid) == 0

            async def broken(*_a, **_k):
                raise RuntimeError("plan store unreadable")
            monkeypatch.setattr(store, "_plans", broken)
            assert await store.execution_state(conn, user, sid) == store.UNREADABLE
            with pytest.raises(store.StrategyStoreError) as err:
                await store.update(conn, user, sid, saved, expected_revision=1)
            assert err.value.code == store.VERSION_PENDING and await _history_count(conn, sid) == 0
        finally:
            await trans.rollback()


# ---- attack 3 and (d): confirm alone never activates; a complete reconciled return does ----

async def test_a_proposed_version_becomes_active_only_after_confirm_and_a_reconciled_return(app_engine, admin_engine,
                                                                                          monkeypatch):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            await _propose_130(conn, user, sid)
            # a return before confirmation activates nothing, even with a closed plan linked to version 2
            await _judge(conn, user, sid, "filled", 130)
            assert [(r[1], r[3]) for r in await _versions(conn, sid)] == [("active", None), ("proposed", None)]
            resp = await _call(_app_for(conn, user, _Reads("122104")), "POST", f"/strategies/{sid}/versions/2/confirm")
            assert resp.status_code == HTTPStatus.OK, resp.text
            assert [(v["state"], v["confirmed_at"] is not None) for v in resp.json()["versions"]] == [
                ("active", True), ("proposed", True)]
            assert [leg["quantity"] for leg in resp.json()["definition"]["legs"]] == [65]  # still version 1
            again = await _call(_app_for(conn, user, _Reads("122104")), "POST", f"/strategies/{sid}/versions/2/confirm")
            assert again.status_code == HTTPStatus.CONFLICT  # confirmed once
            # plan 2 (built after the confirmation) fills 65 more; Zerodha holds 130 = version 2's position
            assert await _linked_plan(conn, user, sid, 2) == 2
            resp = await _post(_app_for(conn, user, _Plan2Reads(sid, 2)), sid)
            assert resp.status_code == HTTPStatus.OK, resp.text
            rows = await _versions(conn, sid)
            assert [(r[0], r[1], r[3], r[6]) for r in rows] == [(1, "superseded", None, True),
                                                                (2, "active", "activated", True)]
            got = await _call(_app_for(conn, user, _Reads("122104")), "GET", f"/strategies/{sid}")
            assert [leg["quantity"] for leg in got.json()["definition"]["legs"]] == [130]
        finally:
            await trans.rollback()


# ---- attack 4: the broker differs: the recorded actual is Zerodha's and the version is not active ----

async def test_a_broker_position_other_than_the_version_is_recorded_and_never_activates(app_engine, admin_engine,
                                                                                      monkeypatch):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            await _propose_130(conn, user, sid)
            app = _app_for(conn, user, _Reads("122104"))
            assert (await _call(app, "POST", f"/strategies/{sid}/versions/2/confirm")).status_code == HTTPStatus.OK
            assert await _linked_plan(conn, user, sid, 2) == 2
            resp = await _post(_app_for(conn, user, _Plan2Reads(sid, 1)), sid)  # Zerodha still holds 65
            assert resp.status_code == HTTPStatus.OK, resp.text
            rows = await _versions(conn, sid)
            assert [(r[0], r[1]) for r in rows] == [(1, "active"), (2, "superseded")]
            assert rows[1][3] == "mismatch" and not rows[1][6]  # never reconciled, never active
            import json  # noqa: PLC0415
            assert [line["units"] for line in json.loads(rows[1][4])] == [65]  # the broker's position, not 130
            assert await _flags(conn, sid) == [True, False]  # attack 2: MISMATCH flags the active version
            await _refused_in_a_new_request(conn, user, sid)
        finally:
            await trans.rollback()


# ---- attack 5: restore of a pre-execution entry after a fill is refused with the template; nothing written ----

async def test_restore_after_a_fill_is_refused_with_the_template_and_writes_nothing(app_engine, admin_engine,
                                                                                  monkeypatch):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            before = (await _history_count(conn, sid), await _versions(conn, sid))
            resp = await _call(_app_for(conn, user, _Reads("122104")), "POST",
                               f"/strategies/{sid}/restore/1?expected_revision=3")
            assert resp.status_code == HTTPStatus.CONFLICT, resp.text
            assert render("strategy_restore_after_execution").what_happened in resp.text
            assert (await _history_count(conn, sid), await _versions(conn, sid)) == before
        finally:
            await trans.rollback()


# ---- attack 6: the app role reads and writes the table as granted; the guard freezes a version ----

async def test_the_app_role_has_exactly_the_granted_rights_and_a_version_is_frozen(app_engine):
    """SELECT / INSERT / UPDATE are granted (column-limited for INSERT and UPDATE: has_any_column_privilege);
    DELETE and TRUNCATE are table-level rights only (has_table_privilege) and are not granted."""
    role = app_engine.url.username
    column_sql = text("SELECT has_any_column_privilege(:r, 'public.strategy_versions', :p)")
    table_sql = text("SELECT has_table_privilege(:r, 'public.strategy_versions', :p)")
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for right in ("SELECT", "INSERT", "UPDATE"):
                assert (await conn.execute(column_sql, {"r": role, "p": right})).scalar_one() is True, right
            for right in ("DELETE", "TRUNCATE"):
                assert (await conn.execute(table_sql, {"r": role, "p": right})).scalar_one() is False, right
            for sql in ("DELETE FROM public.strategy_versions", "TRUNCATE public.strategy_versions"):
                savepoint = await conn.begin_nested()
                with pytest.raises(DBAPIError) as err:
                    await conn.execute(text(sql))
                await savepoint.rollback()
                assert getattr(err.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, sql
        finally:
            await trans.rollback()


async def _refused_with(conn, sql: str, sid: int) -> str | None:
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as err:
        await conn.execute(text(sql), {"s": sid})
    await savepoint.rollback()
    return getattr(err.value.orig, "sqlstate", None)


CHANGE_DEFINITION = ("UPDATE public.strategy_versions SET definition = definition || '{\"x\": 1}' "
                     "WHERE strategy_id = :s AND number = 1")


async def test_the_guard_refuses_a_changed_definition_and_a_backward_state(app_engine, admin_engine, monkeypatch):
    """First as the application role (the setup leaves the transaction in it): changing a definition is refused by
    the column grant (42501). Then as the table owner (RESET ROLE on the owner connection that ran the migrations,
    TEST_ADMIN_DATABASE_URL): the version guard itself refuses each change (OF022), and the CHECK refuses an active
    version that was never confirmed and reconciled (23514)."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            await _propose_130(conn, user, sid)
            assert await _refused_with(conn, CHANGE_DEFINITION, sid) == INSUFFICIENT_PRIVILEGE
            await conn.execute(text("RESET ROLE"))  # the owner from here on: only the guard and the CHECK stand
            for sql, sqlstate in (
                    (CHANGE_DEFINITION, GUARD),
                    ("UPDATE public.strategy_versions SET state = 'proposed' WHERE strategy_id = :s AND number = 1",
                     GUARD),
                    ("DELETE FROM public.strategy_versions WHERE strategy_id = :s", GUARD),
                    ("UPDATE public.strategy_versions SET state = 'active' WHERE strategy_id = :s AND number = 2",
                     CHECK_VIOLATION)):
                assert await _refused_with(conn, sql, sid) == sqlstate, sql
        finally:
            await trans.rollback()


@pytest.mark.skipif(not os.environ.get("ALEMBIC_DATABASE_URL"), reason="needs the owner-role migration URL")
def test_migration_0022_runs_down_and_up_again():
    """On the fresh database the run uses: down to 0021 (no version rows are stored) and back to head."""
    cmd = [sys.executable, "-m", "alembic", "-c", "backend/ofo_app/alembic.ini"]
    for step in (["downgrade", "0021_strategy_tracking"], ["upgrade", "head"]):
        done = subprocess.run([*cmd, *step],  # noqa: S603 - fixed argv, no shell
                               cwd=ROOT, capture_output=True, text=True, timeout=300, check=False)
        assert done.returncode == 0, done.stderr[-2000:]


def _migration_0023():
    import importlib.util  # noqa: PLC0415

    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0023_version_evidence.py"
    found = importlib.util.spec_from_file_location("_m0023_downgrade_test", path)
    module = importlib.util.module_from_spec(found)  # type: ignore[arg-type]
    found.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def _downgrade_refusal(conn, module) -> str:
    """Run 0023's real ``downgrade()`` inside a savepoint; return the refusal text (the savepoint undoes the rest)."""
    from alembic.migration import MigrationContext  # noqa: PLC0415
    from alembic.operations import Operations  # noqa: PLC0415

    def run(sync_conn) -> None:
        with Operations.context(MigrationContext.configure(sync_conn)):
            module.downgrade()

    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as err:
        await conn.run_sync(run)
    await savepoint.rollback()
    return str(err.value)


async def _column_exists(conn, table: str, column: str) -> bool:
    row = await conn.execute(text("SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
                                  "AND table_name = :t AND column_name = :c"), {"t": table, "c": column})
    return row.first() is not None


async def test_f2_attack7_the_0023_downgrade_refuses_while_a_flag_or_a_plan_version_link_is_stored(
        app_engine, admin_engine, monkeypatch):
    """Review F2 item 7 (as 0022 refuses with versions stored): with a raised reconciliation flag the downgrade is
    refused; with the flag down but a plan's version link stored it is refused too; nothing is dropped either way."""
    module = _migration_0023()
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            await _linked_plan(conn, user, sid, 1)
            await conn.execute(text("RESET ROLE"))  # the owner runs migrations
            await conn.execute(text("UPDATE public.strategy_versions SET reconciliation_required = TRUE "
                                    "WHERE strategy_id = :s AND state = 'active'"), {"s": sid})
            assert "reconciliation_required flag" in await _downgrade_refusal(conn, module)
            await conn.execute(text("UPDATE public.strategy_versions SET reconciliation_required = FALSE "
                                    "WHERE reconciliation_required"))
            assert "plan version links" in await _downgrade_refusal(conn, module)
            assert await _column_exists(conn, "execution_plans", "strategy_version")
            assert await _column_exists(conn, "strategy_versions", "reconciliation_required")
        finally:
            await trans.rollback()
