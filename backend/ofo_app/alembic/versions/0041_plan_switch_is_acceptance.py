"""A plan switched to another playbook is a new acceptance (ADR-252 addendum, step 3 round 5).

Spec basis: ADR-252 addendum ("Switching a plan to a newer system playbook version is a new acceptance
(accepted_at = the switch time)"); ADR-250 (a plan accepted before the ADR-247 cutoff keeps its own stops).

Mechanism: the 0031 guard on public.strategy_adjustment_plans stamped ``accepted_at`` only when the BODY changed and
copied the old value otherwise, so a switch to a playbook whose body equals the plan's kept the old time and ADR-250's
cutoff treated it as an old acceptance. This replaces ONLY that function: ``accepted_at`` is also stamped when
``playbook_id`` changes to another playbook (a playbook deleted -> playbook_id NULL is not an acceptance). Existing
rows are not touched. Downgrade restores the 0031 function.

Re-pin: the app-role allow-list (block 23, 0031) pins md5 of this function's body, so replacing the body without
re-pinning makes every later ``'post'`` check refuse. Upgrade installs the chain head (0039's text) with the plan
guard's pin moved to the new body; downgrade re-installs 0039's text (the 0031 pin). Both end with the ``'post'``
check, like 0040. Fails closed (RuntimeError) when the old pin is not in the chain exactly once.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0041_plan_switch_is_acceptance"
down_revision = "0040_ic_default_stop_adr247"
branch_labels = None
depends_on = None

OLD_TEST = "IF NEW.body IS DISTINCT FROM OLD.body THEN"
NEW_TEST = ("IF NEW.body IS DISTINCT FROM OLD.body OR (NEW.playbook_id IS NOT NULL "
            "AND NEW.playbook_id IS DISTINCT FROM OLD.playbook_id) THEN")


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    found = importlib.util.spec_from_file_location(name, path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


def _m31():
    return _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0041")


def _m39():
    return _load("0039_strategy_entry_facts.py", "ofo_migration_0039_for_0041")


PLAN_GUARD = "public.strategy_adjustment_plans_guard"


def upgrade_sql() -> str:
    old = _m31()._plans_guard_sql()
    if old.count(OLD_TEST) != 1:
        raise RuntimeError("the 0031 plan guard no longer has the body test this migration replaces")
    return old.replace(OLD_TEST, NEW_TEST)


def downgrade_sql() -> str:
    return _m31()._plans_guard_sql()


def old_pin() -> str:
    return _m31().PINS[PLAN_GUARD]


def new_pin() -> str:
    return _m31()._M4._md5_body(upgrade_sql())


def previous_allowlist_sql() -> str:
    return _m39().extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0039's chain text with the plan guard's pin moved to the new body. Fails closed on a changed shape."""
    previous = previous_allowlist_sql()
    old, new = f"'{old_pin()}'", f"'{new_pin()}'"
    if old == new or previous.count(old) != 1 or new in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot re-pin the plan guard safely")
    return previous.replace(old, new, 1)


def _install(function_sql: str, allowlist_sql: str) -> None:
    base = _m31()._BASE
    op.execute(function_sql)
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {base.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {base.ALLOWLIST_FUNCTION}('{base._app_role()}', 'post')")


def upgrade() -> None:
    _install(upgrade_sql(), extended_allowlist_sql())


def downgrade() -> None:
    _install(downgrade_sql(), previous_allowlist_sql())
