"""Iron condor system playbook: a NEW version whose S-06 rule says "the loss at your carry gap" (issue #658).

Spec basis: goal contract ic-e2e-paper design decisions 12 and 13, Stage B5; ADR-244 (0042 pattern: a system playbook
change is a new version, the old one kept; users' own copies and saved plans are not changed); ADR-222 (9), (10),
REQ-169 AC-2. The carry gap is the user's own setting, so the old fixed "+/-2% gap" words were untrue.

Changes (one transaction; ADDITIVE: one appended row, no existing row changed, no user row touched):
- public.system_playbook_versions: ONE new row for strategy_type 'ic', version = the newest + 1, its body = the newest
  version's body with the S-06 rule replaced by NEW_RULE (every other key and situation kept, so an admin's saved
  edits survive), status kept, reason REASON, saved_by "release". When the newest body's S-06 already says NEW_RULE,
  nothing is written (re-runnable; never a duplicate version). The base is the NEWEST ic row, never found by number.
- the seed ``system_playbooks.json`` is unchanged (as 0042 did).

downgrade: finds its row by REASON, never by version number; refuses (OF044) when a newer iron condor version was
saved on top of it; otherwise removes exactly that row (append-only guard disabled for that one DELETE inside the
migration's transaction, re-enabled before it ends). Both directions end with the allow-list post check.

Revision ID: 0044_ic_s06_carry_gap_wording
Revises: 0043_scenario_frames_and_marker
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0044_ic_s06_carry_gap_wording"
down_revision = "0043_scenario_frames_and_marker"
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


_M34 = _load("0034_system_playbook_versions.py", "ofo_migration_0034_for_0044")
_BASE = _M34._BASE

SQLSTATE = "OF044"  # a downgrade under a newer saved iron condor version
TABLE = _M34.TABLE
GUARD_TRIGGER = _M34.TRIGGER
TYPE = "ic"
REASON = "Issue 658: situation S-06 rule says the loss at your carry gap, not a fixed 2% gap"
SAVED_BY = _M34.SEED_BY
NEW_RULE = "At 15:00: show overnight margin and the loss at your carry gap"
S06_NAME = "Afternoon carry check"

_LISTED = (
    "jsonb_array_elements(CASE WHEN jsonb_typeof(b.body -> 'situations') = 'array' "
    "THEN b.body -> 'situations' ELSE '[]'::jsonb END)"
)
_NEW_ROW = (
    "jsonb_build_object('id', 'S-06', 'name', COALESCE((SELECT e ->> 'name' FROM "  # noqa: S608 - constant SQL
    f"{_LISTED} e WHERE e ->> 'id' = 'S-06' LIMIT 1), '{S06_NAME}'), 'rule', '{NEW_RULE}')"
)
#: the newest body with S-06 replaced (or added when missing), situations sorted by id
_NEW_BODY = (
    "jsonb_set(b.body, '{situations}', COALESCE((SELECT jsonb_agg(s ORDER BY s ->> 'id') FROM ("  # noqa: S608
    f"SELECT e AS s FROM {_LISTED} e WHERE e ->> 'id' <> 'S-06' UNION ALL SELECT {_NEW_ROW}) u), '[]'::jsonb), true)"
)
_HAS_NEW = (
    f"(SELECT count(*) FROM {_LISTED} e WHERE e ->> 'id' = 'S-06' "  # noqa: S608 - constants
    f"AND e ->> 'rule' = '{NEW_RULE}') = 1"
)


def upgrade_sql() -> str:
    return f"""
        INSERT INTO {TABLE} (strategy_type, version, status, body, reason, saved_by)
        SELECT b.strategy_type, b.version + 1, b.status, {_NEW_BODY}, '{REASON}', '{SAVED_BY}'
        FROM (SELECT strategy_type, version, status, body FROM {TABLE}
              WHERE strategy_type = '{TYPE}' ORDER BY version DESC LIMIT 1) b
        WHERE NOT {_HAS_NEW}
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
