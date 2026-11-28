"""A plan's stop amounts are fixed at entry: the stop base is stored on the plan row (P3; ADR-330 (1)).

Spec basis: ADR-330 (1) ("the rupee amounts of a plan's stop line (the % of max loss stop and the 2x the credit
received stop of ADR-247) are worked out ONCE, from the trade as entered, and stay fixed. They change only when the
user edits the plan. Closing a side or a leg does not move them"); ADR-247, ADR-230; ADR-008 (exact decimals, stored
as text inside JSON); ADR-048 (the limited application role).
Copy from: 0046_entry_atm_iv.py (a column added to a table the role writes, the allow-list block's column set widened,
failing closed when the old text is not in the chain exactly once).

Changes (owner-run, one transaction; ADDITIVE: no row rewritten, no back-fill here):
- public.strategy_adjustment_plans.stop_base JSONB NULL: {"max_loss": "<decimal>" | "unlimited", "credit":
  "<decimal>" | null, "taken_at": "<iso time>", "source": "entry" | "backfill"}. NULL = none stored: a plan saved before
  this change gets its base worked out ONCE from the strategy's entry orders at its first check (source "backfill").
- Grants: the application role also gets column INSERT and UPDATE on stop_base (a plan edit rewrites it; the
  back-fill writes it only where it is NULL). The 0031 / 0041 plan guard is unchanged (it never looked at the column).
- public.ofo_assert_app_role_allowlist: 0054's chain text with the plan block's INSERT and UPDATE column sets widened
  (fails closed when 0031's two column checks are not in the chain exactly once).
- downgrade (as 0046's): the allow-list 'pre' check, then locks the table and REFUSES (SQLSTATE OF039, counted)
  while any
  plan row holds a stop_base; else drops the column and restores 0054's chain text.

Revision ID: 0055_plan_stop_base
Revises: 0054_actionable_alert_answers
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0055_plan_stop_base"
down_revision = "0054_actionable_alert_answers"
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


_M31 = _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0055")
_M39 = _load("0039_strategy_entry_facts.py", "ofo_migration_0039_for_0055")
_M54 = _load("0054_actionable_alert_answers.py", "ofo_migration_0054_for_0055")
_BASE = _M31._BASE
_M3 = _M31._M16._M3
TABLE = _M31.PLANS
LABEL = "strategy_adjustment_plans"
COLUMN = "stop_base"
SQLSTATE = _M39.SQLSTATE
OLD_INSERT_COLUMNS = _M31.PLAN_INSERT_COLUMNS
OLD_UPDATE_COLUMNS = _M31.PLAN_UPDATE_COLUMNS
INSERT_COLUMNS = (*OLD_INSERT_COLUMNS, COLUMN)
UPDATE_COLUMNS = (*OLD_UPDATE_COLUMNS, COLUMN)


def _replacements() -> tuple[tuple[str, str], ...]:
    return (
        (_M3._columns_exactly(TABLE, LABEL, "INSERT", OLD_INSERT_COLUMNS),
         _M3._columns_exactly(TABLE, LABEL, "INSERT", INSERT_COLUMNS)),
        (_M3._columns_exactly(TABLE, LABEL, "UPDATE", OLD_UPDATE_COLUMNS),
         _M3._columns_exactly(TABLE, LABEL, "UPDATE", UPDATE_COLUMNS)),
    )


def previous_allowlist_sql() -> str:
    return _M54.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0054's chain text with the plan block asserting the widened column sets. Fails closed on a changed shape."""
    sql = previous_allowlist_sql()
    for old, new in _replacements():
        if sql.count(old) != 1:
            raise RuntimeError("previous allowlist SQL does not hold 0031's plan column checks exactly once")
        sql = sql.replace(old, new, 1)
    return sql


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} JSONB NULL")
    op.execute(f'GRANT INSERT ({COLUMN}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({COLUMN}) ON TABLE {TABLE} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT count(*) FROM {TABLE} WHERE {COLUMN} IS NOT NULL' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored stop bases', n
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}")
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
