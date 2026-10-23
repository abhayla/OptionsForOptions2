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
GUARD = "OF022"
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
            # a return before confirmation activates nothing
            assert (await _post(_app_for(conn, user, _Reads("122104")), sid)).status_code == HTTPStatus.OK
            assert [r[1] for r in await _versions(conn, sid)] == ["active", "proposed"]
            resp = await _call(_app_for(conn, user, _Reads("122104")), "POST", f"/strategies/{sid}/versions/2/confirm")
            assert resp.status_code == HTTPStatus.OK, resp.text
            assert [(v["state"], v["confirmed_at"] is not None) for v in resp.json()["versions"]] == [
                ("active", True), ("proposed", True)]
            assert [leg["quantity"] for leg in resp.json()["definition"]["legs"]] == [65]  # still version 1
            again = await _call(_app_for(conn, user, _Reads("122104")), "POST", f"/strategies/{sid}/versions/2/confirm")
            assert again.status_code == HTTPStatus.CONFLICT  # confirmed once
            # plan 2 (built after the confirmation) fills 65 more; Zerodha holds 130 = version 2's position
            assert await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45")) == 2
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
            assert await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45")) == 2
            resp = await _post(_app_for(conn, user, _Plan2Reads(sid, 1)), sid)  # Zerodha still holds 65
            assert resp.status_code == HTTPStatus.OK, resp.text
            rows = await _versions(conn, sid)
            assert [(r[0], r[1]) for r in rows] == [(1, "active"), (2, "superseded")]
            assert rows[1][3] == "mismatch" and not rows[1][6]  # never reconciled, never active
            import json  # noqa: PLC0415
            assert [line["units"] for line in json.loads(rows[1][4])] == [65]  # the broker's position, not 130
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
    role = app_engine.url.username
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for right, expected in (("SELECT", True), ("INSERT", True), ("UPDATE", True), ("DELETE", False),
                                    ("TRUNCATE", False)):
                has = (await conn.execute(text("SELECT has_table_privilege(:r, 'public.strategy_versions', :p) OR "
                                               "has_any_column_privilege(:r, 'public.strategy_versions', :p)"),
                                          {"r": role, "p": right})).scalar_one() if right != "TRUNCATE" else (
                    await conn.execute(text("SELECT has_table_privilege(:r, 'public.strategy_versions', :p)"),
                                       {"r": role, "p": right})).scalar_one()
                assert has is expected, right
            for sql in ("DELETE FROM public.strategy_versions", "TRUNCATE public.strategy_versions"):
                savepoint = await conn.begin_nested()
                with pytest.raises(DBAPIError):
                    await conn.execute(text(sql))
                await savepoint.rollback()
        finally:
            await trans.rollback()


async def test_the_guard_refuses_a_changed_definition_and_a_backward_state(app_engine, admin_engine, monkeypatch):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _executed(conn, user, app_engine.url.username, monkeypatch)
            await _propose_130(conn, user, sid)
            for sql in ("UPDATE public.strategy_versions SET definition = definition || '{\"x\": 1}' "
                        "WHERE strategy_id = :s AND number = 1",
                        "UPDATE public.strategy_versions SET state = 'proposed' WHERE strategy_id = :s AND number = 1",
                        "DELETE FROM public.strategy_versions WHERE strategy_id = :s",
                        "UPDATE public.strategy_versions SET state = 'active' WHERE strategy_id = :s AND number = 2"):
                savepoint = await conn.begin_nested()
                with pytest.raises(DBAPIError) as err:
                    await conn.execute(text(sql), {"s": sid})
                await savepoint.rollback()
                assert getattr(err.value.orig, "sqlstate", None) in (GUARD, "23514", "23505"), sql
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
