"""Migration 0058 (#753): the plan guard stamps accepted_at only on a playbook switch; the pin moves with the body.

Spec basis: ADR-250, ADR-252 addendum, ADR-048 (the allow-list pins the guard's body). Behaviour of the guard itself:
test_plan_accepted_at_only_on_switch.py.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import text

PATH = pathlib.Path(__file__).resolve().parents[1] / "backend/ofo_app/alembic/versions/0058_plan_stamp_only_on_switch.py"


def _m58():
    found = importlib.util.spec_from_file_location("ofo_migration_0058_test", PATH)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


async def test_the_installed_function_is_0058s_and_the_allowlist_post_check_passes(admin_engine):
    m = _m58()
    async with admin_engine.connect() as c:
        body = (await c.execute(text(
            "SELECT pg_get_functiondef('public.strategy_adjustment_plans_guard()'::regprocedure)"))).scalar_one()
        problems = (await c.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))).all()
    assert m.NEW_TEST in body and "NEW.body IS DISTINCT FROM OLD.body" not in body
    assert problems is not None  # the function raises on any problem; reaching here is the pass


def test_the_pin_moves_once_and_the_downgrade_text_is_0041s_function_and_0057s_chain():
    m = _m58()
    assert m.old_pin() != m.new_pin()
    assert m.extended_allowlist_sql().count(f"'{m.new_pin()}'") == 1
    assert f"'{m.old_pin()}'" not in m.extended_allowlist_sql()
    assert m.old_sql() == m._M41.upgrade_sql()  # the downgrade installs exactly 0041's function ...
    assert m.previous_allowlist_sql() == m._M57.extended_allowlist_sql()  # ... and exactly 0057's chain text
    assert m.NEW_TEST not in m.old_sql() and m.OLD_TEST in m.old_sql()


def test_the_migration_fails_closed_when_the_old_text_or_pin_is_not_found_once(monkeypatch):
    m = _m58()
    monkeypatch.setattr(m, "OLD_TEST", "text that is not in the function")
    with pytest.raises(RuntimeError, match="no longer has the stamping test"):
        m.upgrade_sql()
    m = _m58()
    monkeypatch.setattr(m, "old_pin", lambda: "0" * 32)
    with pytest.raises(RuntimeError, match="changed shape"):
        m.extended_allowlist_sql()


def test_upgrade_and_downgrade_run_only_function_and_allowlist_statements_and_change_no_row():
    m = _m58()
    seen: dict[str, list[str]] = {"up": [], "down": []}

    class _Op:
        def __init__(self, into):
            self.into = into

        def execute(self, sql):
            self.into.append(str(sql))

    m.op = _Op(seen["up"])
    m.upgrade()
    m.op = _Op(seen["down"])
    m.downgrade()
    for statements in seen.values():
        joined = " ".join(statements).upper()
        assert not any(w in joined for w in ("INSERT INTO", "UPDATE PUBLIC", "DELETE FROM", "DROP ", "ALTER TABLE"))
    assert [s.lstrip().split(None, 1)[0].upper() for s in seen["up"]] == ["SELECT", "CREATE", "CREATE", "REVOKE",
                                                                         "SELECT"]
    assert [s.lstrip().split(None, 1)[0].upper() for s in seen["down"]] == ["CREATE", "CREATE", "REVOKE", "SELECT"]
