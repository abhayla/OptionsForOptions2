"""A plan switched to another playbook is a new acceptance (ADR-252 addendum, step 3 round 5).

Spec basis: ADR-252 addendum ("Switching a plan to a newer system playbook version is a new acceptance
(accepted_at = the switch time)"); ADR-250 (a plan accepted before the ADR-247 cutoff keeps its own stops).

Mechanism: the 0031 guard on public.strategy_adjustment_plans stamped ``accepted_at`` only when the BODY changed and
copied the old value otherwise, so a switch to a playbook whose body equals the plan's kept the old time and ADR-250's
cutoff treated it as an old acceptance. This replaces ONLY that function: ``accepted_at`` is also stamped when
``playbook_id`` changes to another playbook (a playbook deleted -> playbook_id NULL is not an acceptance). Existing
rows are not touched. Downgrade restores the 0031 function.
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


def _m31():
    path = Path(__file__).with_name("0031_adjustment_playbooks.py")
    found = importlib.util.spec_from_file_location("ofo_migration_0031_for_0041", path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


def upgrade_sql() -> str:
    old = _m31()._plans_guard_sql()
    if old.count(OLD_TEST) != 1:
        raise RuntimeError("the 0031 plan guard no longer has the body test this migration replaces")
    return old.replace(OLD_TEST, NEW_TEST)


def downgrade_sql() -> str:
    return _m31()._plans_guard_sql()


def upgrade() -> None:
    op.execute(upgrade_sql())


def downgrade() -> None:
    op.execute(downgrade_sql())
