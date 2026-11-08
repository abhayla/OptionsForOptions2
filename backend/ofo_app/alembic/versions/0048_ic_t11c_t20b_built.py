"""Iron condor system playbook: a NEW version where T-11c and T-20b are no longer greyed and T-20b has its limit
(GC-ICTRACK task 21m).

Spec basis: ADR-277 (5) ("T-11c and T-20b lose their greyed 'not available' flag in the playbook"), ADR-280 (12) (T-20b
fires at ADX >= 25), ADR-276 (3) (the new triggers keep the OFF default), ADR-244 (0042 / 0044 pattern: a system
playbook change is a new version, the old one kept; users' own copies and saved plans are not changed).

Copy from: 0044_ic_s06_carry_gap_wording.py (same shape: one appended row built from the NEWEST ic body).

Changes (one transaction; ADDITIVE: one appended row, no existing row changed, no user row touched):
- public.system_playbook_versions: ONE new row for strategy_type 'ic', version = the newest + 1, its body = the newest
  body with ``triggers.T-11c`` minus its ``greyed`` key and ``triggers.T-20b`` minus ``greyed`` plus cmp ``ge``, unit
  ``ADX`` and weekly / monthly limits 25 / 25 / 25 (every other key kept, ``on`` untouched, so an admin's saved edits
  survive), status kept, reason REASON, saved_by "release". Nothing is written when the newest body already has both
  un-greyed with T-20b at cmp ge, or lacks either trigger (re-runnable; never a duplicate version).
- the seed ``system_playbooks.json`` was regenerated in the same change (task 21) and is not read here.

downgrade: as 0044: finds its row by REASON, refuses (OF048) when a newer iron condor version was saved on top of it,
otherwise removes exactly that row (append-only guard disabled for that one DELETE inside the transaction). Both
directions end with the allow-list post check.

Revision ID: 0048_ic_t11c_t20b_built
Revises: 0047_daily_atm_iv
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0048_ic_t11c_t20b_built"
down_revision = "0047_daily_atm_iv"
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


_M44 = _load("0044_ic_s06_carry_gap_wording.py", "ofo_migration_0044_for_0048")
_BASE = _M44._BASE

SQLSTATE = "OF048"  # a downgrade under a newer saved iron condor version
TABLE = _M44.TABLE
GUARD_TRIGGER = _M44.GUARD_TRIGGER
TYPE = "ic"
REASON = "GC-ICTRACK: T-11c and T-20b built (India VIX percentile, ADX 25), no longer greyed"
SAVED_BY = _M44.SAVED_BY
T20B_SET = '{"cmp": "ge", "unit": "ADX", "weekly": ["25", "25", "25"], "monthly": ["25", "25", "25"]}'

_NEW_BODY = (
    "jsonb_set(jsonb_set(b.body, '{triggers,T-11c}', (b.body #> '{triggers,T-11c}') - 'greyed'), "
    f"'{{triggers,T-20b}}', ((b.body #> '{{triggers,T-20b}}') - 'greyed') || '{T20B_SET}'::jsonb)"
)
_BOTH_THERE = "b.body #> '{triggers,T-11c}' IS NOT NULL AND b.body #> '{triggers,T-20b}' IS NOT NULL"
_DONE = ("NOT (b.body #> '{triggers,T-11c}') ? 'greyed' AND NOT (b.body #> '{triggers,T-20b}') ? 'greyed' "
         "AND b.body #>> '{triggers,T-20b,cmp}' = 'ge'")


def upgrade_sql() -> str:
    return f"""
        INSERT INTO {TABLE} (strategy_type, version, status, body, reason, saved_by)
        SELECT b.strategy_type, b.version + 1, b.status, {_NEW_BODY}, '{REASON}', '{SAVED_BY}'
        FROM (SELECT strategy_type, version, status, body FROM {TABLE}
              WHERE strategy_type = '{TYPE}' ORDER BY version DESC LIMIT 1) b
        WHERE {_BOTH_THERE} AND NOT ({_DONE})
        """  # noqa: S608 - constant names only


def upgrade() -> None:
    op.execute(upgrade_sql())
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{_BASE._app_role()}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    op.execute(
        f"""
        DO $down$
        DECLARE
            mine INTEGER;
            newest INTEGER;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            SELECT max(version) INTO newest FROM {TABLE} WHERE strategy_type = '{TYPE}';
            SELECT max(version) INTO mine FROM {TABLE} WHERE strategy_type = '{TYPE}' AND reason = '{REASON}';
            IF mine IS NULL THEN
                RETURN;
            END IF;
            IF mine <> newest THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: {TYPE} version % was saved after it',
                    newest
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            EXECUTE 'ALTER TABLE {TABLE} DISABLE TRIGGER {GUARD_TRIGGER}';
            DELETE FROM {TABLE} WHERE strategy_type = '{TYPE}' AND version = mine AND reason = '{REASON}';
            EXECUTE 'ALTER TABLE {TABLE} ENABLE TRIGGER {GUARD_TRIGGER}';
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
