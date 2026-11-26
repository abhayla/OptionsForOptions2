"""A plan's ``accepted_at`` moves only on an explicit acceptance, never on an edit (#753).

Spec basis: ADR-250 ("a strategy plan saved before ADR-247 keeps its own stop alerts exactly as saved ... and does NOT
gain the 2x-credit stop ... Why: nothing under a live position changes without the user choosing it"); ADR-252
addendum 2026-11-05 ("Switching a plan to a newer system playbook version is a new acceptance (accepted_at = the
switch time)"); ADR-330 (1) (the stop base is fixed at entry and changes only when the user edits the plan: this
migration does not touch it); ADR-048 (the limited application role).

Defect (measured on strategy 82's shape): 0041 made the plan guard stamp ``accepted_at`` on EVERY body change
(``NEW.body IS DISTINCT FROM OLD.body``) as well as on a playbook switch. ADR-250's cutoff reads ``accepted_at``
against the ADR-247 version time, so editing only the target of a plan saved before ADR-247 moved it past the cutoff
and the plan gained the 2x-credit stop under a live position, a change the user never chose.

Mechanism: this replaces ONLY ``public.strategy_adjustment_plans_guard``. On UPDATE, ``accepted_at`` is stamped
(clock) only while the transaction-local setting ``ofo.plan_acceptance`` is ``'on'``; otherwise it keeps its old value,
whatever the body or ``playbook_id`` do. INSERT (the first save) takes the column default, a stamp, as before. The
store sets the signal (``SELECT set_config('ofo.plan_acceptance', 'on', true)``) right before the write of an explicit
acceptance and sets it ``'off'`` right after: (a) the first save, (b) the user accepting a playbook (POST
/adjustment-plan, any playbook id, the same one included: it takes the newest version, ADR-252 addendum), (c) Reset to
playbook. A plan-sheet edit (PUT) never sets it, so it never stamps, also when it re-points a plan whose playbook was
deleted (playbook_id NULL) at the active playbook. A bare ``playbook_id`` change without the signal does not stamp (0041
stamped on it; the NULL toggle of an earlier draft of this migration made a sheet edit of an old plan read as saved
after ADR-247). The stop base (0055) is not looked at by the guard and follows ``accept_plan`` unchanged.

Known bypass: the application role can set the setting itself. It is the app's own code path, as the NULL toggle was;
the role still cannot write the column (no column grant) and the guard still ignores any value it tries to write.

Additive, no row changed: existing rows are NOT repaired. A plan whose ``accepted_at`` was already moved by an
earlier edit keeps that value; undoing it is the owner's choice per row (ADR-250: "nothing ... changes without the
user choosing it").

Re-pin: the app-role allow-list pins md5 of this function's body (block 23), so the plan guard's pin moves to the new
body in 0057's chain text (fails closed, RuntimeError, when the old pin is not in the chain exactly once). Downgrade
re-installs 0041's function and 0057's chain text exactly. Both end with the ``'post'`` check.

Old-code safety: code before this migration (12bc1852) never sets the signal, so on a 0058 database an accept it makes
(POST or Reset) does NOT stamp: the plan keeps its earlier ``accepted_at`` (an old plan stays "saved before ADR-247",
no credit stop gained), and its edits no longer restamp. New code against a 0057 database (0041's function) still
works: it stamps on every body change and the extra setting is ignored. Deploy: migrate, then new code.

Revision ID: 0058_plan_stamp_only_on_switch
Revises: 0057_history_delete_entries
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0058_plan_stamp_only_on_switch"
down_revision = "0057_history_delete_entries"
branch_labels = None
depends_on = None

# 0041's stamping test (body changed OR playbook switched) and the one this migration installs (explicit acceptance)
OLD_TEST = ("IF NEW.body IS DISTINCT FROM OLD.body OR (NEW.playbook_id IS NOT NULL "
            "AND NEW.playbook_id IS DISTINCT FROM OLD.playbook_id) THEN")
SIGNAL = "ofo.plan_acceptance"
NEW_TEST = f"IF coalesce(current_setting('{SIGNAL}', true), '') = 'on' THEN"


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    found = importlib.util.spec_from_file_location(name, path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


_M41 = _load("0041_plan_switch_is_acceptance.py", "ofo_migration_0041_for_0058")
_M57 = _load(f"{down_revision}.py", "ofo_migration_0057_for_0058")
_M31 = _M41._m31()
_BASE = _M31._BASE


def old_sql() -> str:
    """0041's function (what is installed at 0057)."""
    return _M41.upgrade_sql()


def upgrade_sql() -> str:
    old = old_sql()
    if old.count(OLD_TEST) != 1:
        raise RuntimeError("the 0041 plan guard no longer has the stamping test this migration replaces")
    return old.replace(OLD_TEST, NEW_TEST)


def old_pin() -> str:
    return _M41.new_pin()


def new_pin() -> str:
    return _M31._M4._md5_body(upgrade_sql())


def previous_allowlist_sql() -> str:
    return _M57.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0057's chain text with the plan guard's pin moved to the new body. Fails closed on a changed shape."""
    previous = previous_allowlist_sql()
    old, new = f"'{old_pin()}'", f"'{new_pin()}'"
    if old == new or previous.count(old) != 1 or new in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot re-pin the plan guard safely")
    return previous.replace(old, new, 1)


def _install(function_sql: str, allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(function_sql)
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{_BASE._app_role()}', 'pre')")
    _install(upgrade_sql(), extended_allowlist_sql())


def downgrade() -> None:
    _install(old_sql(), previous_allowlist_sql())
