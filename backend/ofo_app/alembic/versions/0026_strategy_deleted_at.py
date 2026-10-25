"""Strategy store: a never-executed draft can be hidden (deleted) and brought back, its rows kept (REQ-070 AC-6, W-156).

Spec basis: REQ-070 AC-6 ("the draft is hidden from every list and kept on the server with its history for audit");
ADR-118 ("Deleting never erases history or audit rows"); ADR-048 (the limited application role).

Copy from: none - this repo's own pattern: 0025's grant, allow-list replacement (``_replaced_once``) and downgrade refusal.

Changes (owner-run, one transaction):
- public.strategies.deleted_at TIMESTAMPTZ NULL (NULL = visible; a time = hidden since then).
- Grants: the application role gets column UPDATE on ``deleted_at`` only. INSERT is NOT granted: a new row is never born
  hidden.
- Guard public.strategies_guard: UNCHANGED. 0025's guard already refuses every FIXED_COLUMNS change, keeps ``revision``
  unless the definition changed and keeps ``updated_at`` unless the definition changed, so an UPDATE that changes only
  ``deleted_at`` (NULL -> time, or back to NULL) already leaves both as they are. A test pins that (the guard pin in the
  allow-list is therefore the same as 0025's).
- public.ofo_assert_app_role_allowlist: 0025's chain text with block 11's strategies UPDATE column list replaced.
- downgrade: refuses while any row has deleted_at set (a hidden draft and its audit trail must not vanish silently); else
  0025's state comes back.

Revision ID: 0026_strategy_deleted_at
Revises: 0025_strategy_name
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0026_strategy_deleted_at"
down_revision = "0025_strategy_name"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    found = importlib.util.spec_from_file_location(name, path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0026")  # 0025
_M8 = _PREVIOUS._M8
_BASE = _PREVIOUS._BASE  # 0001

DELETED_COLUMN = "deleted_at"
INSERT_COLUMNS = _PREVIOUS.INSERT_COLUMNS
UPDATE_COLUMNS = (*_PREVIOUS.UPDATE_COLUMNS, DELETED_COLUMN)
GUARD_PIN = _PREVIOUS.NEW_GUARD_PIN  # the guard is not changed


def _replaced_once(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"the previous migration's text changed shape: {old[:60]!r} found {sql.count(old)} times")
    return sql.replace(old, new, 1)


def _strategies_block(insert_columns, update_columns) -> str:
    return _M8._table_block(_M8.STRATEGIES, "strategies", insert_columns, update_columns, _M8.STRATEGIES_SEQUENCE,
                            _M8.STRATEGIES_GUARD, _M8.STRATEGIES_TRIGGER, GUARD_PIN)


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0025's chain text with block 11's strategies block carrying the new UPDATE column. Fails closed."""
    return _replaced_once(previous_allowlist_sql(), _strategies_block(INSERT_COLUMNS, _PREVIOUS.UPDATE_COLUMNS),
                          _strategies_block(INSERT_COLUMNS, UPDATE_COLUMNS))


def _install(allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} ADD COLUMN {DELETED_COLUMN} TIMESTAMPTZ NULL")
    op.execute(f'GRANT UPDATE ({DELETED_COLUMN}) ON TABLE {_M8.STRATEGIES} TO "{role}"')
    _install(extended_allowlist_sql())


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_hidden BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {_M8.STRATEGIES} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {_M8.STRATEGIES} WHERE {DELETED_COLUMN} IS NOT NULL)' INTO has_hidden;
            IF has_hidden THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: a strategy in {_M8.STRATEGIES} is hidden (deleted)';
            END IF;
        END
        $down$;
        """  # noqa: E501, S608 constant names, one message line
    )
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} DROP COLUMN {DELETED_COLUMN}")  # its column grants go with it
    _install(previous_allowlist_sql())
