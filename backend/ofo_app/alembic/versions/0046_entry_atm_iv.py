"""Each strategy's entry ATM IV beside its entry facts (GC-ICTRACK task 8; ADR-270 (1)).

Spec basis: ADR-270 (1) ("the entry ATM IV is stored when a strategy becomes a paper (or real) position, so T-11 is
checked on live strategies"); ADR-243 / migration 0039 (entry facts written once, never rewritten); ADR-008 (exact
decimals); ADR-048 (the limited application role).
Copy from: 0039_strategy_entry_facts.py (the table, its guard, block 31) and 0045_rule_state_adjustment_no.py (a
later migration changing an earlier block's pinned text, failing closed when the old text is not found exactly once).

Changes (owner-run, one transaction; ADDITIVE: no row rewritten, no back-fill):
- public.strategy_entry_facts.entry_atm_iv NUMERIC NULL CHECK (> 0). NULL = not known at entry; every existing row
  stays NULL. The 0039 insert-only guard is unchanged (UPDATE / DELETE / TRUNCATE still refused).
- Grants: the application role also gets column INSERT on entry_atm_iv.
- public.ofo_assert_app_role_allowlist: 0045's chain text with block 31's INSERT column set widened to the five
  columns (fails closed when 0039's four-column check is not in the chain exactly once).
- downgrade: refuses (SQLSTATE OF039, counted) while any row has entry_atm_iv IS NOT NULL; else drops the column and
  restores 0045's chain text.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable the guard, then edit rows.

Revision ID: 0046_entry_atm_iv
Revises: 0045_rule_state_adjustment_no
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0046_entry_atm_iv"
down_revision = "0045_rule_state_adjustment_no"
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


_M39 = _load("0039_strategy_entry_facts.py", "ofo_migration_0039_for_0046")
_M45 = _load("0045_rule_state_adjustment_no.py", "ofo_migration_0045_for_0046")
_BASE = _M45._BASE
_M3 = _M39._M16._M3
TABLE = _M39.TABLE
SQLSTATE = _M39.SQLSTATE
COLUMN = "entry_atm_iv"
OLD_INSERT_COLUMNS = _M39.INSERT_COLUMNS
INSERT_COLUMNS = (*OLD_INSERT_COLUMNS, COLUMN)


def _replacements() -> tuple[tuple[str, str], ...]:
    """(old, new) texts of block 31: its comment line and its INSERT column check."""
    return (
        (f"column INSERT on {', '.join(OLD_INSERT_COLUMNS)} only",
         f"column INSERT on {', '.join(INSERT_COLUMNS)} only"),
        (_M3._columns_exactly(TABLE, _M39.LABEL, "INSERT", OLD_INSERT_COLUMNS),
         _M3._columns_exactly(TABLE, _M39.LABEL, "INSERT", INSERT_COLUMNS)),
    )


def previous_allowlist_sql() -> str:
    return _M45.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0045's chain text with block 31 asserting the five INSERT columns. Fails closed on a changed shape."""
    sql = previous_allowlist_sql()
    for old, new in _replacements():
        if sql.count(old) != 1:
            raise RuntimeError("previous allowlist SQL does not hold 0039's block 31 text exactly once")
        sql = sql.replace(old, new, 1)
    return sql


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} NUMERIC NULL CHECK ({COLUMN} > 0)")
    op.execute(f'GRANT INSERT ({COLUMN}) ON TABLE {TABLE} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT count(*) FROM {TABLE} WHERE {COLUMN} IS NOT NULL' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored entry ATM IVs', n
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    role = _BASE._app_role()
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}")
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
