"""Strategy store: a strategy whose every leg is exited is stored as 'closed' (GC-ICGUIDE g23; audit C13).

Spec basis: audit C13 ("a closed status is never stored, and the Completed page filter is empty"; decision: fix in
GC-ICGUIDE, ADR-282); ADR-048 (the limited application role); ADR-118 (history is never erased).
Copy from: 0026_strategy_deleted_at.py (one more UPDATE column, allow-list block replaced once) and 0025's guard text.

Changes (owner-run, one transaction):
- public.strategies.status CHECK widened from ('draft') to ('draft', 'closed').
- Guard public.strategies_guard: 0025's text with ONE change - ``status`` may change from 'draft' to 'closed' and
  nothing else (closed never reopens; inserts are still forced to 'draft'). Every other fixed column is still refused.
- Grants: the application role gets column UPDATE on ``status`` (only the guard's one transition can succeed).
- public.ofo_assert_app_role_allowlist: 0047's chain text with block 11's strategies block (UPDATE column list, guard
  pin) replaced once.
- downgrade: refuses while any strategy is closed (a finished strategy must not silently become a draft again).

Revision ID: 0049_strategy_closed_status
Revises: 0048_ic_t11c_t20b_built
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0049_strategy_closed_status"
down_revision = "0048_ic_t11c_t20b_built"
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


_M25 = _load("0025_strategy_name.py", "ofo_migration_0025_for_0049")
_M26 = _load("0026_strategy_deleted_at.py", "ofo_migration_0026_for_0049")
_M47 = _load("0047_daily_atm_iv.py", "ofo_migration_0047_for_0049")
_M8 = _M25._M8
_M4 = _M25._M4
_BASE = _M25._BASE

STATUS = "status"
CONSTRAINT = "strategies_status_check"
CLOSED = "closed"
UPDATE_COLUMNS = (*_M26.UPDATE_COLUMNS, STATUS)


def _replaced_once(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"the previous migration's text changed shape: {old[:60]!r} found {sql.count(old)} times")
    return sql.replace(old, new, 1)


def _checks(columns) -> str:
    return "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in columns)


def _old_guard_sql() -> str:
    return _M25._new_guard_sql()


def _new_guard_sql() -> str:
    others = [c for c in _M8.FIXED_COLUMNS if c != STATUS]
    new = (f"{_checks(others)}\n               OR (NEW.status IS DISTINCT FROM OLD.status "
           f"AND NOT (OLD.status = 'draft' AND NEW.status = '{CLOSED}'))")
    return _replaced_once(_old_guard_sql(), _checks(_M8.FIXED_COLUMNS), new)


OLD_GUARD_PIN = _M26.GUARD_PIN
NEW_GUARD_PIN = _M4._md5_body(_new_guard_sql())


def _strategies_block(update_columns, pin: str) -> str:
    return _M8._table_block(_M8.STRATEGIES, "strategies", _M26.INSERT_COLUMNS, update_columns,
                            _M8.STRATEGIES_SEQUENCE, _M8.STRATEGIES_GUARD, _M8.STRATEGIES_TRIGGER, pin)


def previous_allowlist_sql() -> str:
    return _M47.extended_allowlist_sql()  # 0048 does not touch the allow-list


def extended_allowlist_sql() -> str:
    """0047's chain text with block 11's strategies block carrying the status UPDATE column and the new guard pin."""
    return _replaced_once(previous_allowlist_sql(), _strategies_block(_M26.UPDATE_COLUMNS, OLD_GUARD_PIN),
                          _strategies_block(UPDATE_COLUMNS, NEW_GUARD_PIN))


def _install(guard_sql: str, allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(guard_sql)
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} DROP CONSTRAINT {CONSTRAINT}")
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} ADD CONSTRAINT {CONSTRAINT} CHECK ({STATUS} IN ('draft', '{CLOSED}'))")
    op.execute(f'GRANT UPDATE ({STATUS}) ON TABLE {_M8.STRATEGIES} TO "{role}"')
    _install(_new_guard_sql(), extended_allowlist_sql())


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_closed BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {_M8.STRATEGIES} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {_M8.STRATEGIES} WHERE {STATUS} = ''{CLOSED}'')' INTO has_closed;
            IF has_closed THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: a strategy in {_M8.STRATEGIES} is closed';
            END IF;
        END
        $down$;
        """  # noqa: S608 constant names, one message line
    )
    role = _BASE._app_role()
    op.execute(f'REVOKE UPDATE ({STATUS}) ON TABLE {_M8.STRATEGIES} FROM "{role}"')
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} DROP CONSTRAINT {CONSTRAINT}")
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} ADD CONSTRAINT {CONSTRAINT} CHECK ({STATUS} IN ('draft'))")
    _install(_old_guard_sql(), previous_allowlist_sql())
