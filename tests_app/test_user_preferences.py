"""REQ-168 AC-2..AC-5: per-user adjustment preferences (migration 0033, ``ofo_app.user_preferences_store``,
``routes.adjustment_preferences``) and their wiring into the near-level alert of the tracking view.

Spec basis: ADR-222 (7) "A user who has not changed a value follows the admin default in force (an admin change moves
them); a user who changed it keeps their own"; (9) "applies at the next check ... a strategy's saved plan ... is not
changed by it; every alert line names the value it used"; REQ-168 AC-3 "A user reads and changes only their own
preferences ... passes one guard".

Real input: the recorded 2026-10-08 replay (test_strategy_tracking), NIFTY 50 at 22,533.25; a three-leg untyped shape
(no playbook) whose short 22400 is 133.25 points = 0.59% away. Every test runs in a rolled-back transaction: the
preference and settings tables are insert-only, a committed row would stay for ever.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from ofo.settings import SettingRefused  # noqa: E402
from ofo_app import settings_store  # noqa: E402
from ofo_app import user_preferences_store as store  # noqa: E402
from ofo_app.main import create_app  # noqa: E402
from ofo_app.routes import adjustment_preferences as prefs_routes  # noqa: E402
from ofo_app.routes import tracking as tracking_routes  # noqa: E402
from ofo_app.settings_store import SettingsError  # noqa: E402
from test_strategy_store import _client  # noqa: E402
from test_strategy_tracking import _paper_body, _setup  # noqa: E402

D = Decimal
pytestmark = pytest.mark.real_preferences

KEY = "adjustments.near_level_percent"
PREFS = "/api/adjustments/preferences"


@pytest.fixture
async def db(app_engine):
    """One connection whose outer transaction is always rolled back (the route's commits become savepoints)."""
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _untyped(db_conn):
    """The app (rolled-back db, the user from ``_setup``) with a tracked three-leg untyped shape; the tracking
    threshold comes from the REAL dependency (the user's preference), not an override."""
    app, stored, *_ = await _setup(db_conn)
    del app.dependency_overrides[tracking_routes.get_near_level_threshold]
    body = _paper_body(stored)
    body["orders"] = body["orders"][:3]
    return app, stored, body


def _near_short(view: dict) -> list[tuple[str, str, str]]:
    return [(d["level"], d["threshold_percent"], d["line"]) for d in view["detections"]
            if d["condition"] == "near_short_strike"]


async def _plan_digest(conn, strategy_id: int) -> str:
    rows = (await conn.execute(text(
        "SELECT s::text FROM public.strategies s WHERE id = :i UNION ALL "
        "SELECT p::text FROM public.strategy_adjustment_plans p WHERE strategy_id = :i ORDER BY 1"),
        {"i": strategy_id})).scalars().all()
    return hashlib.md5("\n".join(rows).encode()).hexdigest()  # noqa: S324 - a change detector, not security


async def test_core_proof_user_value_then_reset_then_admin_default_moves_the_reset_user(db):
    """Core proof (REQ-168 AC-4, AC-5): 22400 is 0.59% from 22533.25.
    no rows -> admin/registry default 0.5 -> no flag; the user sets 1.0 -> the next check flags it and the line names
    1.0%; reset -> follows the default (0.5) -> no flag; the admin sets the default 0.6 -> the reset user follows 0.6
    -> flags naming 0.6%; the saved strategy and its plan rows are unchanged throughout."""
    app, stored, body = await _untyped(db)
    async with _client(app) as c:
        placed = await c.post(f"/paper/strategies/{stored.id}/orders", json=body)
        assert placed.status_code == HTTPStatus.CREATED, placed.text
        before = await _plan_digest(db, stored.id)

        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
        assert _near_short(view) == []  # 0.59% > 0.5% (the default)

        r = await c.post(f"{PREFS}/{KEY}", json={"value": "1.0"})
        assert r.status_code == HTTPStatus.OK, r.text
        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
        assert _near_short(view) == [("22400.00", "1.0", "Index 22533.25 is within 1.0% of the short strike 22400.00 "
                                                       "(0.59% away).")]

        r = await c.post(f"{PREFS}/{KEY}/reset", json={})
        assert r.status_code == HTTPStatus.OK, r.text
        mine = next(p for p in r.json()["preferences"] if p["key"] == KEY)
        assert (mine["value"], mine["source"], mine["admin_default"]) == ("0.5", "default", "0.5")
        assert [h["value"] for h in mine["history"]] == [None, "1"]  # AC-2: the reset is a row, the change kept
        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
        assert _near_short(view) == []

        await settings_store.add_setting(db, KEY, "0.6", set_by="admin-test", correlation_id="prefs-test")
        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
        assert _near_short(view) == [("22400.00", "0.6", "Index 22533.25 is within 0.6% of the short strike "
                                                         "22400.00 (0.59% away).")]
        assert await _plan_digest(db, stored.id) == before


async def test_a_users_own_value_is_kept_when_the_admin_default_changes(db):
    await store.set_preference(db, "user-a", KEY, "1.0")
    await settings_store.add_setting(db, KEY, "0.6", set_by="admin-test", correlation_id="prefs-test")
    got = (await store.answers(db, "user-a"))[KEY]
    assert (got.value, got.source, got.admin_default) == (D("1.0"), "yours", D("0.6"))


async def test_isolation_a_write_by_user_a_never_changes_user_b(db):
    await store.set_preference(db, "user-a", KEY, "1.0")
    b = (await store.answers(db, "user-b"))[KEY]
    assert (b.value, b.source) == (D("0.5"), "default")
    assert (await store.history(db, "user-b"))[KEY] == []
    assert [r.value for r in (await store.history(db, "user-a"))[KEY]] == [D("1.0")]


async def test_isolation_over_http_the_guard_decides_whose_row_is_written(db):
    app, _stored, _body = await _untyped(db)
    app.dependency_overrides[prefs_routes.require_user] = lambda: "user-a"
    async with _client(app) as c:
        assert (await c.post(f"{PREFS}/{KEY}", json={"value": "2"})).status_code == HTTPStatus.OK
        app.dependency_overrides[prefs_routes.require_user] = lambda: "user-b"
        mine = next(p for p in (await c.get(PREFS)).json()["preferences"] if p["key"] == KEY)
    assert (mine["value"], mine["source"], mine["history"]) == ("0.5", "default", [])


def test_every_preference_route_and_the_read_dependency_depend_on_the_one_guard():
    """AC-3: a route under /api/adjustments/preferences without ``require_user`` fails the suite."""
    def deps(dependant) -> set:
        out = set()
        for d in dependant.dependencies:
            out.add(d.call)
            out |= deps(d)
        return out

    app = create_app()
    routes = [r for r in app.routes if getattr(r, "path", "").startswith(PREFS)]
    assert {(next(iter(r.methods)), r.path) for r in routes} == {
        ("GET", PREFS), ("POST", PREFS + "/{key}"), ("POST", PREFS + "/{key}/reset")}
    assert all(prefs_routes.require_user in deps(r.dependant) for r in routes)
    from fastapi.dependencies.utils import get_dependant  # noqa: PLC0415
    assert prefs_routes.require_user in deps(get_dependant(path="", call=prefs_routes.get_user_preferences))


@pytest.mark.parametrize(("raw", "status", "reason"), [
    ("9", 422, "Alert distance with no playbook must be between 0.1 and 5 (percent)."),
    ("abc", 422, "Alert distance with no playbook must be a number written as text, for example 0.5."),
])
async def test_a_refused_value_answers_the_reason_and_writes_nothing(db, raw, status, reason):
    app, _stored, _body = await _untyped(db)
    async with _client(app) as c:
        r = await c.post(f"{PREFS}/{KEY}", json={"value": raw})
    assert (r.status_code, r.json()["reason"]) == (status, reason)
    user = next(iter(_users(app)))
    assert (await store.history(db, user))[KEY] == []


def _users(app) -> list[str]:
    from ofo_app.routes import strategies as strategy_routes  # noqa: PLC0415
    return [app.dependency_overrides[strategy_routes.current_user_ref]()]


async def test_an_unknown_key_is_404(db):
    app, _stored, _body = await _untyped(db)
    async with _client(app) as c:
        r = await c.post(f"{PREFS}/pricing.risk_free_rate", json={"value": "0.07"})  # an admin-only setting
        r2 = await c.post(f"{PREFS}/adjustments.nope/reset", json={})
    assert (r.status_code, r2.status_code) == (404, 404)
    assert r.json()["reason"] == "There is no adjustment preference with that name."


async def test_a_gap_time_with_60_minutes_is_refused(db):
    with pytest.raises(SettingRefused) as info:
        await store.set_preference(db, "user-a", "adjustments.gap_at_open_until", "960")
    assert info.value.code == "setting_not_a_time"


async def test_a_stored_own_value_the_registry_now_refuses_fails_closed(db):
    await db.execute(text("INSERT INTO public.user_adjustment_preferences (user_ref, key, value, effective_from) "
                          "VALUES ('user-a', :k, 9, clock_timestamp())"), {"k": KEY})
    with pytest.raises(store.PreferencesError):
        await store.answers(db, "user-a")


async def test_an_admin_default_the_registry_now_refuses_fails_closed(db):
    await db.execute(text("INSERT INTO public.app_settings (key, value, effective_from, set_by) "
                          "VALUES (:k, 9, clock_timestamp(), 'raw-test')"), {"k": KEY})
    with pytest.raises(SettingsError):
        await store.answers(db, "user-b")  # a user with no own value follows a refused default: no figure


@pytest.mark.parametrize("sql", [
    "UPDATE public.user_adjustment_preferences SET value = 2 WHERE user_ref = 'user-a'",
    "DELETE FROM public.user_adjustment_preferences WHERE user_ref = 'user-a'",
    "TRUNCATE public.user_adjustment_preferences",
])
async def test_the_application_role_cannot_update_delete_or_truncate(db, sql):
    await store.set_preference(db, "user-a", KEY, "1.0")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql))


@pytest.mark.parametrize("sql", [
    "UPDATE public.user_adjustment_preferences SET value = 2",
    "DELETE FROM public.user_adjustment_preferences",
    "TRUNCATE public.user_adjustment_preferences",
])
async def test_the_guard_refuses_update_delete_truncate_even_for_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("INSERT INTO public.user_adjustment_preferences (user_ref, key, value, "
                                    "effective_from) VALUES ('owner-test', :k, 1, clock_timestamp())"), {"k": KEY})
            with pytest.raises(DBAPIError) as info:
                await conn.execute(text(sql))
            assert getattr(info.value.orig, "sqlstate", None) == "OF033"
        finally:
            await trans.rollback()


async def test_a_back_dated_raw_insert_is_refused(db):
    with pytest.raises(DBAPIError) as info:
        async with db.begin_nested():
            await db.execute(text("INSERT INTO public.user_adjustment_preferences (user_ref, key, value, "
                                  "effective_from) VALUES ('user-a', :k, 1, clock_timestamp() - interval '1 minute')"),
                             {"k": KEY})
    assert getattr(info.value.orig, "sqlstate", None) == "OF033"
