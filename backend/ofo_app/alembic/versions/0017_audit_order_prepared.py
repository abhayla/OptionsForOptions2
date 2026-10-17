"""Audit store: declare ``order_prepared`` (W-103; REQ-063 AC-5, REQ-073 AC-3).

Basis: REQ-063 AC-5 (a per-event-type field ALLOWLIST, anything undeclared dropped before storage). W-103 declares
``order_prepared`` {strategy_id, plan_number, action, tags} in ``ofo_app.audit_allowlist.ALLOWLIST`` with
``DECLARED_IN_REVISION = 17``. 0002 renders ``allowlist_spec(through_revision=16)`` (the state every database at 0016
holds), so this revision is the ONLY one that renders the new type, and each revision's state is fixed:

upgrade (the 0015 pattern, from 0016's state to the full allowlist):
1. ``public.audit_events``' event-type CHECK is dropped and re-added with every declared type.
2. ``public.ofo_audit_payload_allowlist()`` is re-created from ``allowlist_spec(through_revision=17)``.
3. ``public.ofo_assert_app_role_allowlist`` is re-created from 0016's chain text with the payload allowlist
   function's md5 pin swapped from the 0016 body to the 0017 body (fails closed unless the old pin occurs exactly
   once).

downgrade (REAL: restores 0016's state, the one 0015 left for the audit store): refuses while any ``order_prepared``
row exists (append-only store, the pattern 0015 uses); otherwise re-creates the CHECK and the payload allowlist
function from ``allowlist_spec(through_revision=16)`` and re-runs 0016's chain text (its pins match that body).

Revision ID: 0017_audit_order_prepared
Revises: 0016_execution_plans
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from alembic import op
from ofo_app.audit_allowlist import BASE_REVISION, allowlist_spec

revision = "0017_audit_order_prepared"
down_revision = "0016_execution_plans"
branch_labels = None
depends_on = None

REVISION_NUMBER = 17
NEW_EVENT_TYPES = ("order_prepared",)


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    loader_spec = importlib.util.spec_from_file_location(name, path)
    if loader_spec is None or loader_spec.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0017")
_AUDIT = _PREVIOUS._AUDIT  # 0002
_BASE = _PREVIOUS._BASE  # 0001
_M4 = _PREVIOUS._M4  # 0004: _md5_body

CONSTRAINT = "audit_events_event_type_check"  # PostgreSQL's name for 0002's unnamed column CHECK (as 0015)

#: The allowlist each side of this revision holds.
BEFORE = allowlist_spec(through_revision=BASE_REVISION)
AFTER = allowlist_spec(through_revision=REVISION_NUMBER)


def allowed_function_sql(allowed: dict) -> str:
    """The payload allowlist function exactly as 0002 writes it (same body text, so the same md5 pin)."""
    allowed_json = json.dumps(allowed, sort_keys=True, separators=(",", ":"))
    return f"""
        CREATE OR REPLACE FUNCTION {_AUDIT.ALLOWED_FUNCTION}() RETURNS jsonb
        LANGUAGE sql IMMUTABLE
        SET search_path = {_AUDIT.SEARCH_PATH}
        AS $fn$ SELECT {_AUDIT._sql_literal(allowed_json)}::jsonb $fn$
        """


def check_sql(allowed: dict) -> list[str]:
    types = ", ".join(_AUDIT._sql_literal(t) for t in sorted(allowed))
    return [
        f"ALTER TABLE {_AUDIT.EVENTS} DROP CONSTRAINT {CONSTRAINT}",
        f"ALTER TABLE {_AUDIT.EVENTS} ADD CONSTRAINT {CONSTRAINT} CHECK (event_type IN ({types}))",
    ]


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0016's chain text with the payload allowlist function's pin moved to this revision's body. Fails closed."""
    previous = previous_allowlist_sql()
    old_pin = _M4._md5_body(allowed_function_sql(BEFORE))
    new_pin = _M4._md5_body(allowed_function_sql(AFTER))
    if old_pin == new_pin or previous.count(f"'{old_pin}'") != 1:
        raise RuntimeError("0016's allowlist text does not pin the 0016 payload allowlist body exactly once")
    return previous.replace(f"'{old_pin}'", f"'{new_pin}'", 1)


def _apply(allowed: dict, chain_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    for statement in check_sql(allowed):
        op.execute(statement)
    op.execute(allowed_function_sql(allowed))
    op.execute(chain_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    _apply(AFTER, extended_allowlist_sql())


def downgrade() -> None:
    types = ", ".join(_AUDIT._sql_literal(t) for t in NEW_EVENT_TYPES)
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {_AUDIT.EVENTS} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {_AUDIT.EVENTS} WHERE event_type IN ({types.replace("'", "''")}))'
                INTO has_rows;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: the audit store holds order_prepared events';
            END IF;
        END
        $down$;
        """  # noqa: S608 constant table name
    )
    _apply(BEFORE, previous_allowlist_sql())
