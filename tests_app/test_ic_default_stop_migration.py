"""Migration 0040 (ADR-247): the iron condor system playbook's default stop is 50 % of max loss or 2x the credit; the
"% of margin" stop and T-16 are off by default, T-16's values kept; users' copies and saved plans keep what they had
(REQ-169 AC-4, ADR-222 (9)).

Spec basis: ADR-247; ADR-244 (a change to the iron condor system playbook ships as a new version); REQ-169.
Every test runs inside one outer transaction that is rolled back (the version table is insert-only).
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from ofo_app import adjustment_check as check
from ofo_app import playbook_store as pbs
from ofo_app import system_playbook_store as sys_store
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

MIGRATION = (pathlib.Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
             / "0040_ic_default_stop_adr247.py")
ADMIN = "admin-test"
MARGIN = "stop_line_pct_of_margin"
T16_VALUES = ["4", "4", "3"]


def _m40():
    found = importlib.util.spec_from_file_location("ofo_migration_0040_test", MIGRATION)
    assert found is not None and found.loader is not None
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


M40 = _m40()


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _stop_shape(body: dict) -> tuple:
    t16 = body["triggers"]["T-16"]
    return body["guards"].get(MARGIN), t16["on"], t16["weekly"], t16["monthly"]


async def test_a_fresh_database_ships_the_adr247_iron_condor_as_a_new_version_seed_kept(db):
    history = await sys_store.history(db, "ic")
    assert [(v.version, v.reason) for v in history] == [(2, M40.REASON), (1, "seed")]
    new, seed = history[0].body, history[1].body
    assert _stop_shape(seed) == ("4", True, T16_VALUES, T16_VALUES)  # version 1 kept, never overwritten
    assert _stop_shape(new) == (None, False, T16_VALUES, T16_VALUES)  # margin stop and T-16 off, values kept
    assert new["guards"]["stop_line_pct_of_max_loss"] == "50"
    # nothing else in the body moved
    strip = lambda b: {**b, "guards": {k: v for k, v in b["guards"].items() if k != MARGIN},  # noqa: E731
                       "triggers": {**b["triggers"], "T-16": {**b["triggers"]["T-16"], "on": None}}}
    assert strip(new) == strip(seed)
    # every other strategy type is untouched: version 1 only
    others = (await db.execute(text(
        "SELECT count(*) FROM public.system_playbook_versions WHERE strategy_type <> 'ic' AND version > 1")
    )).scalar_one()
    assert others == 0


async def test_adr247_saved_at_is_the_save_time_of_the_row_0040_wrote(db):
    """ADR-250: the cutoff a saved plan is compared with is the save time of the ic system row whose reason is
    0040's (never a version number); a plan accepted before it keeps its own stops. No such row -> every plan counts
    as pre-ADR-247."""
    import dataclasses  # noqa: PLC0415
    import datetime  # noqa: PLC0415

    cutoff = await pbs.adr247_saved_at(db)
    v2_at = (await db.execute(text(
        "SELECT saved_at FROM public.system_playbook_versions "
        "WHERE strategy_type = 'ic' AND reason = :reason"), {"reason": M40.REASON})).scalar_one()
    assert cutoff == v2_at

    @dataclasses.dataclass
    class _Plan:
        accepted_at: datetime.datetime

    second = datetime.timedelta(seconds=1)
    assert await check.plan_saved_before_adr247(db, _Plan(cutoff - second)) is True
    assert await check.plan_saved_before_adr247(db, _Plan(cutoff)) is False
    assert await check.plan_saved_before_adr247(db, _Plan(cutoff + second)) is False


async def test_existing_user_copies_and_plans_keep_the_margin_stop_when_the_version_lands(db):
    """A copy and a plan made from a version WITH the margin stop keep it after the upgrade's statement runs; a
    strategy on the system playbook itself reads the new version at its next check."""
    user = _user()
    cur = await sys_store.current(db, "ic")
    old = await sys_store.restore(db, ADMIN, "ic", 1, "pre-ADR-247 numbers", cur.version)  # the margin stop is back
    assert _stop_shape(old.body)[:2] == ("4", True)
    system = await pbs.active_for(db, user, "ic")
    copy_before = await pbs.duplicate(db, user, system.id, "My IC")
    _, planned = await _with_draft(db, user)
    await pbs.accept_plan(db, user, planned.id, system.id)
    tracked_user = _user()
    _, tracked = await _with_draft(db, tracked_user)

    await db.execute(text(M40.upgrade_sql()))

    after = await sys_store.current(db, "ic")
    assert (after.version, after.reason, _stop_shape(after.body)) == (
        old.version + 1, M40.REASON, (None, False, T16_VALUES, T16_VALUES))
    assert _stop_shape((await pbs.get(db, user, copy_before.id)).body) == ("4", True, T16_VALUES, T16_VALUES)
    plan = await check.resolve(db, user, planned.id, "ic")
    assert (plan.source, _stop_shape(plan.body)) == ("plan", ("4", True, T16_VALUES, T16_VALUES))
    tracked_now = await check.resolve(db, tracked_user, tracked.id, "ic")
    assert (tracked_now.source, _stop_shape(tracked_now.body)[:2]) == ("system", (None, False))


async def test_the_upgrade_statement_is_re_runnable_and_never_writes_an_empty_version(db):
    before = (await sys_store.current(db, "ic")).version
    await db.execute(text(M40.upgrade_sql()))
    assert (await sys_store.current(db, "ic")).version == before


class _Op:
    """Stands in for alembic's ``op``: records every statement ``upgrade()`` runs, so the test runs exactly those."""

    def __init__(self):
        self.sql: list[str] = []

    def execute(self, sql):
        self.sql.append(str(sql))


async def _run_upgrade(conn, monkeypatch) -> None:
    op = _Op()
    monkeypatch.setattr(M40, "op", op)
    M40.upgrade()  # upgrade() itself, not only upgrade_sql()
    assert op.sql
    for sql in op.sql:
        await conn.execute(text(sql))


@pytest.fixture
async def owner_db(admin_engine):
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def test_cutoff_is_0040s_row_found_by_reason_on_the_ofo_dev_history(owner_db, monkeypatch):
    """#656 MAJOR 1 (ofo_dev's real history): v1 seed, v2 an admin save, v3 a restore, THEN 0040 -> v4. The cutoff
    is v4's save time (found by 0040's reason), never v2's; a plan accepted between v2 and v4 keeps its own stops;
    admin edits and users' copies survive upgrade()."""
    db = owner_db
    table, guard = M40.TABLE, M40.GUARD_TRIGGER
    await db.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {guard}"))
    await db.execute(text(f"DELETE FROM {table} WHERE strategy_type = 'ic' AND version > 1"))  # noqa: S608 - constant
    await db.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {guard}"))
    saved = await sys_store.restore(db, ADMIN, "ic", 1, "owner test save", 1)  # v2: an admin's row
    restored = await sys_store.restore(db, ADMIN, "ic", 1, "restore", saved.version)  # v3
    assert (saved.version, restored.version) == (2, 3)
    user = _user()
    system = await pbs.active_for(db, user, "ic")
    copy_before = await pbs.duplicate(db, user, system.id, "My IC")
    _, planned = await _with_draft(db, user)
    await pbs.accept_plan(db, user, planned.id, system.id)  # accepted between v2 and v4

    await _run_upgrade(db, monkeypatch)

    rows = dict((await db.execute(text(
        f"SELECT version, saved_at FROM {table} WHERE strategy_type = 'ic'"))).all())  # noqa: S608 - constant
    assert sorted(rows) == [1, 2, 3, 4]
    cutoff = await pbs.adr247_saved_at(db)
    assert cutoff == rows[4] and cutoff != rows[2]  # expected read by the version the test built, not by reason
    plan_row = await pbs.plan_for(db, user, planned.id)
    assert rows[2] < plan_row.accepted_at < rows[4]
    assert await check.plan_saved_before_adr247(db, plan_row) is True
    history = {v.version: v for v in await sys_store.history(db, "ic")}
    assert history[4].reason == M40.REASON and _stop_shape(history[4].body)[:2] == (None, False)
    assert _stop_shape(history[2].body)[:2] == ("4", True)  # the admin's row is never rewritten
    assert _stop_shape((await pbs.get(db, user, copy_before.id)).body)[:2] == ("4", True)  # the user's copy kept


async def test_upgrade_function_leaves_copies_and_plans_untouched(db, monkeypatch):
    """upgrade() (not only upgrade_sql()) on top of a restored margin stop: the new version drops it, a user's copy and
    plan keep it."""
    user = _user()
    cur = await sys_store.current(db, "ic")
    await sys_store.restore(db, ADMIN, "ic", 1, "pre-ADR-247 numbers", cur.version)
    system = await pbs.active_for(db, user, "ic")
    copy_before = await pbs.duplicate(db, user, system.id, "My IC")
    _, planned = await _with_draft(db, user)
    await pbs.accept_plan(db, user, planned.id, system.id)
    await _run_upgrade(db, monkeypatch)
    assert _stop_shape((await sys_store.current(db, "ic")).body)[:2] == (None, False)
    assert _stop_shape((await pbs.get(db, user, copy_before.id)).body)[:2] == ("4", True)
    plan = await check.resolve(db, user, planned.id, "ic")
    assert _stop_shape(plan.body)[:2] == ("4", True)


def test_the_store_cutoff_reason_is_0040s_reason():
    assert pbs.ADR247_REASON == M40.REASON
