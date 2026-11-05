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


async def test_a_fresh_database_ships_the_adr247_iron_condor_as_its_seed(db):
    """Orchestrator decision (5), step 3 r3: the seed (system_playbooks.json, built by scripts/build_system_playbooks.py)
    matches migration 0040, so a fresh install ships the ADR-247 iron condor as version 1 and 0040 writes nothing
    (its re-runnable no-op); an existing database gets 0040's version 2 (tests below)."""
    history = await sys_store.history(db, "ic")
    assert [(v.version, v.reason) for v in history] == [(1, "seed")]
    seed = history[0].body
    assert _stop_shape(seed) == (None, False, T16_VALUES, T16_VALUES)  # margin stop and T-16 off, values kept
    assert seed["guards"]["stop_line_pct_of_max_loss"] == "50"
    others = (await db.execute(text(
        "SELECT count(*) FROM public.system_playbook_versions WHERE strategy_type <> 'ic' AND version > 1")
    )).scalar_one()
    assert others == 0


async def test_adr247_saved_at_is_the_first_ic_version_with_the_adr247_stop_shape(db):
    """ADR-250: the cutoff a saved plan is compared with (``playbook_store.adr247_saved_at``); a plan accepted before
    it keeps its own stops, one accepted at or after it gets the ADR-247 default."""
    import dataclasses  # noqa: PLC0415
    import datetime  # noqa: PLC0415

    cutoff = await pbs.adr247_saved_at(db)
    seed_at = (await db.execute(text(
        "SELECT saved_at FROM public.system_playbook_versions WHERE strategy_type = 'ic' AND version = 1"))).scalar_one()
    assert cutoff == seed_at

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
