"""Audit store: declare the three broker-reply event types (W-017; REQ-063 AC-5).

Basis: REQ-063 AC-5 (a per-event-type field ALLOWLIST, anything undeclared dropped before storage). W-017 adds
``broker_response_recorded``, ``execution_recorded`` and ``reconciliation_recorded`` to
``ofo_app.audit_allowlist.ALLOWLIST``. 0002 and 0003 render that allowlist at import, so a fresh database already
has it; a database created before this revision still holds the nine-type text, so this revision brings it level
(the case 0003's docstring names: a change to allowlist_spec() REQUIRES a new migration that re-creates the function AND
rebuilds the pins):

1. ``public.audit_events``' event-type CHECK is dropped and re-added with the full declared list.
2. ``public.ofo_audit_payload_allowlist()`` is re-created from ``allowlist_spec()`` (the same text 0002 renders).
3. ``public.ofo_assert_app_role_allowlist`` is re-created from the predecessor's chain text, whose pins (md5 of the
   guarded function bodies, including the payload allowlist function) are computed from the same allowlist.

Both re-creations are idempotent on a fresh database. Pre-phase runs against the old text, post-phase against the new.

Downgrade: refuses only WHEN rows of the three new types exist (append-only store; the pattern 0011 uses), and
otherwise round-trips: the predecessors render their state from the current allowlist, so 0014's state is already
what upgrade() leaves.

Revision ID: 0015_audit_broker_allowlist
Revises: 0014_charge_rates_caps
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from alembic import op

revision = "0015_audit_broker_allowlist"
down_revision = "0014_charge_rates_caps"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    loader_spec = importlib.util.spec_from_file_location(name, path)
    if loader_spec is None or loader_spec.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0015")
_AUDIT = _PREVIOUS._M8._PREV  # 0002: the audit store's constants and renderers
_BASE = _AUDIT._BASE  # 0001

NEW_EVENT_TYPES = ("broker_response_recorded", "execution_recorded", "reconciliation_recorded")
CONSTRAINT = "audit_events_event_type_check"  # PostgreSQL's name for 0002's unnamed column CHECK


def extended_allowlist_sql() -> str:
    """The predecessor's allowlist function text (no new block): its pins already follow allowlist_spec()."""
    return _PREVIOUS.extended_allowlist_sql()


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION

    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    types = ", ".join(_AUDIT._sql_literal(t) for t in _AUDIT.DECLARED_EVENT_TYPES)
    op.execute(f"ALTER TABLE {_AUDIT.EVENTS} DROP CONSTRAINT {CONSTRAINT}")
    op.execute(f"ALTER TABLE {_AUDIT.EVENTS} ADD CONSTRAINT {CONSTRAINT} CHECK (event_type IN ({types}))")

    allowed_json = json.dumps(_AUDIT.PAYLOAD_ALLOWLIST, sort_keys=True, separators=(",", ":"))
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_AUDIT.ALLOWED_FUNCTION}() RETURNS jsonb
        LANGUAGE sql IMMUTABLE
        SET search_path = {_AUDIT.SEARCH_PATH}
        AS $fn$ SELECT {_AUDIT._sql_literal(allowed_json)}::jsonb $fn$
        """
    )

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Audit rows are append-only: refuse (like 0011) only when a row of one of the three new types exists.
    # Otherwise the schema is already 0014's: 0002/0003/0014 render the CHECK, the payload allowlist and the pins from
    # the current allowlist_spec() at import, so on a replay chain 0014's state equals the state upgrade() leaves.
    # (A database created before this revision keeps the superset text; the narrower text cannot be rebuilt from the
    # current allowlist, and a superset cannot lose a row.)
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
                RAISE EXCEPTION 'refusing to downgrade {revision}: the audit store holds broker-reply events';
            END IF;
        END
        $down$;
        """
    )
