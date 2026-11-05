"""Migration 0042 (ADR-244): the iron condor system playbook gets a NEW version that lists S-08 and S-09 as Guidance;
ADR-247/252 stops kept; users' copies and saved plans byte-identical (REQ-169 AC-2/AC-4, REQ-159 AC-5).

Spec basis: ADR-244; ADR-240 (1); ADR-247; REQ-169. Every test runs in one outer transaction that is rolled back.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo_app import playbook_store as pbs
from ofo_app import system_playbook_store as sys_store
from ofo_app.routes.playbooks import situation_kinds
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
ADMIN = "admin-test"


def _load(name: str, filename: str):
    found = importlib.util.spec_from_file_location(name, VERSIONS / filename)
    assert found is not None and found.loader is not None
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


M42 = _load("ofo_migration_0042_test", "0042_ic_s08_s09_guidance_adr244.py")
M40 = _load("ofo_migration_0040_for_0042_test", "0040_ic_default_stop_adr247.py")


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _canon(body: dict) -> str:
    return json.dumps(body, sort_keys=True)


def _ids(body: dict) -> list[str]:
    return [s["id"] for s in body["situations"]]


def test_guidance_constant_names_s08_and_s09_too() -> None:
    assert pe.GUIDANCE_SITUATIONS == ("S-03", "S-04", "S-05", "S-08", "S-09")


async def test_new_version_is_appended_with_reason_and_lists_s08_s09_as_guidance(db):
    history = await sys_store.history(db, "ic")
    assert history[0].reason == M42.REASON and history[0].version == history[1].version + 1
    assert history[1].reason == M40.REASON  # the version it was built from is kept
    new, before = history[0].body, history[1].body
    assert _ids(new) == sorted(_ids(new)) and {"S-08", "S-09"} <= set(_ids(new))
    assert {"S-08", "S-09"}.isdisjoint(_ids(before))
    kinds = {k["id"]: k for k in situation_kinds(new)}
    for sid in ("S-08", "S-09"):
        assert (kinds[sid]["kind"], kinds[sid]["label"]) == ("guidance", "Guidance")
    # nothing else moved
    strip = lambda b: {k: v for k, v in b.items() if k != "situations"}  # noqa: E731
    assert strip(new) == strip(before)
    assert [s for s in new["situations"] if s["id"] not in ("S-08", "S-09")] == before["situations"]


async def test_adr247_and_adr252_stops_are_intact_in_the_new_version(db):
    body = (await sys_store.current(db, "ic")).body
    assert "stop_line_pct_of_margin" not in body["guards"]  # ADR-247: % of margin stop off
    assert body["guards"]["stop_line_pct_of_max_loss"] == "50"
    t16 = body["triggers"]["T-16"]
    assert t16["on"] is False and t16["weekly"] == ["4", "4", "3"] and t16["monthly"] == ["4", "4", "3"]
    assert body["triggers"]["T-06"]  # stop trigger stays


async def test_user_copy_and_saved_plan_are_byte_identical_across_the_upgrade(db):
    user = _user()
    cur = await sys_store.current(db, "ic")
    older = await sys_store.restore(db, ADMIN, "ic", cur.version - 1, "pre-ADR-244 body", cur.version)
    assert "S-08" not in _ids(older.body)
    system = await pbs.active_for(db, user, "ic")
    copy = await pbs.duplicate(db, user, system.id, "My IC")
    _, planned = await _with_draft(db, user)
    await pbs.accept_plan(db, user, planned.id, system.id)
    copy_before = _canon((await pbs.get(db, user, copy.id)).body)
    plan_before = _canon((await pbs.plan_for(db, user, planned.id)).body)
    older_before = _canon(older.body)

    await db.execute(text(M42.upgrade_sql()))

    after = await sys_store.current(db, "ic")
    assert after.version == older.version + 1 and after.reason == M42.REASON
    assert {"S-08", "S-09"} <= set(_ids(after.body))
    assert _canon((await pbs.get(db, user, copy.id)).body) == copy_before
    assert _canon((await pbs.plan_for(db, user, planned.id)).body) == plan_before
    assert _canon((await sys_store.history(db, "ic"))[1].body) == older_before  # the old version is never rewritten
    assert "S-08" not in _canon(json.loads(copy_before))


async def test_upgrade_is_re_runnable_and_never_writes_an_empty_version(db):
    before = (await sys_store.current(db, "ic")).version
    await db.execute(text(M42.upgrade_sql()))
    assert (await sys_store.current(db, "ic")).version == before


async def test_downgrade_removes_only_its_own_row_found_by_reason(db, admin_engine):
    # the downgrade statement is run on the owner role in the same rolled-back transaction style
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            rows = (await conn.execute(text(
                f"SELECT version, reason FROM {M42.TABLE} WHERE strategy_type = 'ic' ORDER BY version"  # noqa: S608
            ))).all()
            mine = [v for v, r in rows if r == M42.REASON]
            assert len(mine) == 1 and mine[0] == rows[-1][0]
            statements: list[str] = []

            class _Op:
                def execute(self, sql):
                    statements.append(str(sql))

            M42.op = _Op()
            M42.downgrade()
            for sql in statements:
                await conn.execute(text(sql))
            after = (await conn.execute(text(
                f"SELECT version, reason FROM {M42.TABLE} WHERE strategy_type = 'ic' ORDER BY version"  # noqa: S608
            ))).all()
            assert after == [r for r in rows if r[1] != M42.REASON]
        finally:
            await outer.rollback()
