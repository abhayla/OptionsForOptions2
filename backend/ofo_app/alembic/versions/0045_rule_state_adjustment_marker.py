"""Rule memory starts again after every adjustment basket: a starting-point marker on the F-71 rule state (ADR-258,
issues 65/89/36, finding rule-entry-baseline-taken-at-first-check).
Spec basis: ADR-258 ("applies again after every adjustment basket (an adjustment as counted by ADR-255) ... Rule
memory from before the adjustment is dropped"); REQ-159 / F-71; migration 0031 (``held_at_entry`` never changes, a
rule state is never deleted); ADR-048 (the limited application role).
Copy from: 0043_scenario_frames_and_marker.py (a marker column whose only writer is a DEFAULT read from a
transaction-local setting; the application role gets no grant on the column).
Changes (owner-run, one transaction):
- public.adjustment_rule_state.adjustment_no INTEGER NOT NULL CHECK (>= 0), DEFAULT the transaction-local setting
  ``ofo.rule_adjustment_no`` (unset -> 0). Every existing row gets 0 (= memory started at the entry): no row is
  rewritten, deleted or re-baselined, ``held_at_entry`` is untouched.
- the primary key becomes (strategy_id, rule_id, adjustment_no): a new starting point is a NEW row, the old one stays.
- the 0031 guard also keeps ``adjustment_no`` fixed after insert (still no DELETE, held_at_entry fixed, seen_clear only
  false -> true).
- no grant change: 0031's block 23 still asserts the role's INSERT columns are exactly the four of 0031.
- downgrade: refuses (SQLSTATE OF031, counted) while a row with adjustment_no > 0 exists (the old key could not hold
  it); else restores 0031's key, guard and column set.
Revision ID: 0045_rule_state_adjustment_marker
Revises: 0044_ic_s06_carry_gap_wording
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0045_rule_state_adjustment_marker"
down_revision = "0044_ic_s06_carry_gap_wording"
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


_M31 = _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0045")
_BASE = _M31._BASE
TABLE = _M31.RULE_STATE
COLUMN = "adjustment_no"
SETTING = "ofo.rule_adjustment_no"
PKEY = "adjustment_rule_state_pkey"


def guard_sql() -> str:
    """0031's rule-state guard with ``adjustment_no`` in the fixed tuple."""
    return _M31._fn("adjustment_rule_state_guard", f"""
            IF TG_OP = 'DELETE' THEN
                {_M31._raise('a rule state is never deleted')}
            END IF;
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            IF (NEW.strategy_id, NEW.rule_id, NEW.held_at_entry, NEW.{COLUMN}) IS DISTINCT FROM
               (OLD.strategy_id, OLD.rule_id, OLD.held_at_entry, OLD.{COLUMN})
               OR (OLD.seen_clear AND NOT NEW.seen_clear) THEN
                {_M31._raise('a rule state only records seen clear, once')}
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;""")


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} INTEGER NOT NULL "
               f"DEFAULT COALESCE(NULLIF(current_setting('{SETTING}', true), '')::integer, 0) "
               f"CHECK ({COLUMN} >= 0)")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {PKEY}")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT {PKEY} PRIMARY KEY (strategy_id, rule_id, {COLUMN})")
    op.execute(guard_sql())
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(f"""
        DO $do$
        DECLARE n BIGINT;
        BEGIN
            SELECT count(*) INTO n FROM {TABLE} WHERE {COLUMN} > 0;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing downgrade: % rule state rows started after an adjustment', n
                    USING ERRCODE = '{_M31.SQLSTATE}';
            END IF;
        END
        $do$
        """)  # noqa: S608 - constant names only
    op.execute(_M31._state_guard_sql())
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {PKEY}")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT {PKEY} PRIMARY KEY (strategy_id, rule_id)")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{_BASE._app_role()}', 'post')")
