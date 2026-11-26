"""Migration 0055 (P3; ADR-330 (1)): public.strategy_adjustment_plans.stop_base JSONB NULL.

Real PostgreSQL. The column exists and is nullable; the limited application role may INSERT and UPDATE exactly that one
new column (and still not accumulated others); the app-role allow-list's 'post' check passes with the widened column
sets; the plan guard is the one 0041 pinned (a stop_base-only update does not move ``accepted_at``, ADR-250); the
migration chain text fails closed when the old column checks are not found exactly once.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from ofo_app import playbook_store
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

PATH = pathlib.Path(__file__).resolve().parent.parent / "backend/ofo_app/alembic/versions/0055_plan_stop_base.py"
TABLE = "public.strategy_adjustment_plans"


def _m55():
    found = importlib.util.spec_from_file_location("ofo_migration_0055_test", PATH)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


async def test_the_column_is_nullable_jsonb(admin_engine):
    async with admin_engine.connect() as c:
        row = (await c.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'strategy_adjustment_plans' AND column_name = 'stop_base'"
        ))).one()
    assert tuple(row) == ("jsonb", "YES")


async def test_the_app_role_holds_insert_and_update_on_stop_base_only_as_the_allowlist_pins(admin_engine):
    async with admin_engine.connect() as c:
        got = {(priv, col): (await c.execute(text(
            f"SELECT has_column_privilege('ofo_app', '{TABLE}', :col, :priv)"),
            {"col": col, "priv": priv})).scalar_one()
            for priv in ("INSERT", "UPDATE") for col in ("stop_base", "accepted_at", "strategy_type")}
        problems = (await c.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))).all()
    assert got == {("INSERT", "stop_base"): True, ("UPDATE", "stop_base"): True,
                   ("INSERT", "accepted_at"): False, ("UPDATE", "accepted_at"): False,
                   ("INSERT", "strategy_type"): True, ("UPDATE", "strategy_type"): False}
    assert problems is not None  # the function raises on any problem; reaching here is the pass


def test_the_widened_allowlist_text_holds_the_new_column_sets_and_fails_closed():
    m = _m55()
    sql = m.extended_allowlist_sql()
    assert "'strategy_id', 'playbook_id', 'strategy_type', 'body', 'stop_base'" in sql
    assert "'playbook_id', 'body', 'stop_base'" in sql
    assert sql != m.previous_allowlist_sql()
    m._replacements = lambda: (("text that is not in the chain", "x"),)
    with pytest.raises(RuntimeError, match="exactly once"):
        m.extended_allowlist_sql()


async def test_the_plan_guard_still_keeps_accepted_at_when_only_stop_base_changes(app_engine):
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            user = _user()
            _, strategy = await _with_draft(c, user)
            system = await playbook_store.active_for(c, user, "ic")
            first = await playbook_store.accept_plan(c, user, strategy.id, system.id)
            await c.execute(text("SELECT pg_sleep(0.01)"))
            second = await playbook_store.accept_plan(c, user, strategy.id, system.id, None, {"max_loss": "1"})
            assert second.accepted_at == first.accepted_at and second.stop_base == {"max_loss": "1"}
        finally:
            await outer.rollback()
