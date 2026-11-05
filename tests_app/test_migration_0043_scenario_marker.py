"""Migration 0043 (IC e2e paper contract decisions 2, 3, 16) and the isolation it carries, on real PostgreSQL.

- round trip as the owner through the SQL the migration and every later one run (``_migration_replay``): the frame
  table, its grants, the marker column with its server-side default, and NO app-role write on the marker;
- the back-fill finds its rows by REASON (the seed's exact name), counted: exactly the exact-name rows get a marker;
- the marker is written by the server from the process mode, never carried to a later insert, NULL in live mode;
- the screen check and the paper order routes refuse each cross case with 409 (attack list 1, 2).
Every test rolls back (or uses its own user).
"""
from __future__ import annotations

import pytest
from _migration_replay import round_trip_sql
from httpx import ASGITransport, AsyncClient
from ofo_app import scenario_mode
from ofo_app import strategy_store as store
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

MIGRATION = "0043_scenario_frames_and_marker.py"
CONFLICT = 409
_STATE = text(
    "SELECT to_regclass('public.scenario_frames') IS NOT NULL AS frames, "
    "(SELECT column_default FROM information_schema.columns WHERE table_schema = 'public' "
    " AND table_name = 'strategies' AND column_name = 'scenario_id') AS marker_default, "
    "(SELECT array_agg(privilege_type || ':' || column_name ORDER BY privilege_type, column_name) "
    " FROM information_schema.column_privileges WHERE table_schema = 'public' AND table_name = 'scenario_frames' "
    " AND grantee = 'ofo_app' AND privilege_type IN ('INSERT', 'UPDATE')) AS frame_writes, "
    "(SELECT count(*) FROM information_schema.column_privileges WHERE table_schema = 'public' "
    " AND table_name = 'strategies' AND column_name = 'scenario_id' AND grantee = 'ofo_app' "
    " AND privilege_type IN ('INSERT', 'UPDATE')) AS marker_writes")


async def _state(conn) -> tuple:
    return tuple((await conn.execute(_STATE)).one())


async def test_round_trip_creates_frames_marker_and_grants_and_downgrade_removes_them(admin_engine):
    _own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1]  # ends with the allow-list post check
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await _state(conn)
            assert head[0] is True and "current_setting('ofo.scenario_id'" in head[1]
            assert head[2] == ["INSERT:frame", "INSERT:moved_at", "INSERT:scenario_id", "UPDATE:frame",
                               "UPDATE:moved_at"]
            assert head[3] == 0  # the app role can never write the marker itself
            for sql in down:
                await conn.execute(text(sql))
            assert await _state(conn) == (False, None, None, 0)
            for sql in up:
                await conn.execute(text(sql))
            assert await _state(conn) == head
        finally:
            await trans.rollback()


BACKFILL_NAMES = {  # name -> marker after the back-fill (by reason: the seed's exact name only)
    "Scenario ADJ-02": "ADJ-02", "Scenario PATH-01": "PATH-01", "Scenario ADJ-20a": "ADJ-20a",
    "Scenario ADJ-02 copy": None, "scenario ADJ-02": None, "Scenario ADJ-2": None, "My iron condor": None,
}


async def test_backfill_marks_exactly_the_seed_named_strategies(admin_engine):
    _own_down, _own_up, down, up = round_trip_sql(MIGRATION)
    user = _user()
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _ids, first = await _with_draft(conn, user)
            for name in BACKFILL_NAMES:
                await store.save_draft(conn, user, first.saved, name)
            for sql in down:
                await conn.execute(text(sql))
            for sql in up:
                await conn.execute(text(sql))
            rows = dict((await conn.execute(text("SELECT name, scenario_id FROM public.strategies "
                                                 "WHERE user_ref = :u AND name <> :d"),
                                            {"u": user, "d": first.name})).all())
            assert rows == BACKFILL_NAMES
            print(f"BACKFILL marked={sum(v is not None for v in rows.values())} of {len(rows)}")
        finally:
            await trans.rollback()


async def test_marker_comes_from_the_process_mode_and_is_never_carried(app_engine, monkeypatch):
    user = _user()
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _ids, first = await _with_draft(conn, user)  # live mode
            monkeypatch.setenv("OFO_SCENARIO", "PATH-01")
            in_scenario = await store.save_draft(conn, user, first.saved, "made in scenario mode")
            setting = (await conn.execute(text("SELECT current_setting('ofo.scenario_id', true)"))).scalar_one()
            monkeypatch.delenv("OFO_SCENARIO")
            after = await store.save_draft(conn, user, first.saved, "made live after it")
            rows = dict((await conn.execute(text("SELECT id, scenario_id FROM public.strategies WHERE user_ref = :u"),
                                            {"u": user})).all())
            assert rows == {first.id: None, in_scenario.id: "PATH-01", after.id: None}
            assert setting == ""  # cleared after the insert: never carried to a later one
        finally:
            await trans.rollback()


async def _committed_pair(app_engine, user: str) -> tuple[int, int, int]:
    """One live strategy, one PATH-01 and one ADJ-02 strategy of ``user`` (committed: the app's requests read them)."""
    async with app_engine.connect() as conn:
        _ids, live = await _with_draft(conn, user)
        own = await store.save_draft(conn, user, live.saved, "own scenario", scenario_id="PATH-01")
        other = await store.save_draft(conn, user, live.saved, "other scenario", scenario_id="ADJ-02")
        await conn.commit()
    return live.id, own.id, other.id


def _app(monkeypatch, app_engine, scenario: str | None, user: str):
    from ofo_app import db as app_db  # noqa: PLC0415
    from ofo_app.config import get_settings  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.broker import current_user_ref  # noqa: PLC0415
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    if scenario is None:
        monkeypatch.delenv("OFO_SCENARIO", raising=False)
    else:
        monkeypatch.setenv("OFO_SCENARIO", scenario)
    get_settings.cache_clear()
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    scenario_mode._loaded.clear()
    app = create_app()
    app.dependency_overrides[current_user_ref] = lambda: user
    return app


async def test_cross_cases_are_refused_with_409(app_engine, monkeypatch):
    from ofo_app import db as app_db  # noqa: PLC0415
    user = _user()
    live, own, other = await _committed_pair(app_engine, user)
    await app_engine.dispose()  # one engine at a time (the role's connection limit)
    try:
        app = _app(monkeypatch, app_engine, "PATH-01", user)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            for sid in (live, other):  # attack 1 (a live strategy) and 2 (another scenario's) in scenario mode
                for path in (f"/paper/strategies/{sid}/orders", f"/paper/strategies/{sid}/triggers",
                             f"/strategies/{sid}/tracking/exit"):
                    r = await ac.post(path, json={})
                    assert r.status_code == CONFLICT and r.json()["code"] == "USER_INPUT_026", (sid, path, r.text)
                r = await ac.get(f"/api/strategies/{sid}/adjustment-check")
                assert r.status_code == CONFLICT and r.json()["code"] == "USER_INPUT_193", (sid, r.text)
            r = await ac.post(f"/paper/strategies/{own}/orders", json={})
            assert r.status_code != CONFLICT, r.text  # own scenario: the guard lets it through (body then refused)
        await app_db.close_db()
        app = _app(monkeypatch, app_engine, None, user)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            for sid in (own, other):  # live mode never checks a scenario strategy
                r = await ac.get(f"/api/strategies/{sid}/adjustment-check")
                assert r.status_code == CONFLICT and r.json()["code"] == "USER_INPUT_193", (sid, r.text)
        await app_db.close_db()
    finally:
        monkeypatch.delenv("OFO_SCENARIO", raising=False)
        scenario_mode._loaded.clear()


@pytest.mark.parametrize("mode", [None, "PATH-01"])
async def test_live_and_scenario_listers_list_only_their_own(app_engine, monkeypatch, mode):
    """Decision 17: the live lister on one real and one scenario strategy lists the real one; scenario the reverse."""
    from ofo_app import background  # noqa: PLC0415
    user = _user()
    live, own, other = await _committed_pair(app_engine, user)
    async with app_engine.connect() as conn:
        summaries = await store.list_strategies(conn, user)
    if mode is None:
        monkeypatch.delenv("OFO_SCENARIO", raising=False)
    else:
        monkeypatch.setenv("OFO_SCENARIO", mode)
    listed = [s.id for s in summaries if background.listable(s.scenario_id, scenario_mode.current_id())]
    assert listed == ([live] if mode is None else [own])
    assert {s.id: s.scenario_id for s in summaries} == {live: None, own: "PATH-01", other: "ADJ-02"}
