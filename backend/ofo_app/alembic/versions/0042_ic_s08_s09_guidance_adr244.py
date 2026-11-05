"""Iron condor system playbook: a NEW version that lists S-08 and S-09 as Guidance situations (ADR-244; contract
"Your adjustment settings" step 5).

Spec basis: ADR-244 (the iron condor system playbook lists S-08 "the day before a known event" and S-09 "a weekend or
market holiday ahead" with the other situations, each labelled "Guidance"; possible approaches shown as possible, never
one best (ADR-003); the change ships as a new version, users' own copies and saved strategy plans are not changed);
REQ-159 AC-5; ADR-222 (9), (10) and REQ-169 AC-2 (a system playbook change is a new version, the old one kept).

The "Guidance" label is NOT stored in a body: it is derived from ``playbook_eval.GUIDANCE_SITUATIONS`` (ADR-240 (1)),
which now names S-03, S-04, S-05, S-08, S-09. The body only lists the two situations (id, name, rule words).
Wording source: ADR-244's names; the approaches in the rule words are the possible ones of the adjustments catalogue
(docs/research/adjustments-catalogue-2026-10-30.md part 4, rows S-08 and S-09), none called best.

Changes (one transaction; ADDITIVE: one appended row, no existing row changed, no user row touched):
- public.system_playbook_versions: ONE new row for strategy_type 'ic', version = the newest + 1, its body = the newest
  version's body with the two situations added in id order (every other key kept, so ADR-247's stops, an admin's saved
  edits and the 0040 values survive), status kept, reason REASON, saved_by "release". When the newest body already
  lists both, nothing is written (re-runnable; never an empty version).
- public.adjustment_playbooks: untouched (REQ-169).

downgrade: finds its row by REASON, never by version number; refuses (OF042) when a newer iron condor version was
saved on top of it; otherwise removes exactly that row (append-only guard disabled for that one DELETE inside the
migration's transaction, re-enabled before it ends), then re-runs the allow-list check.

Revision ID: 0042_ic_s08_s09_guidance_adr244
Revises: 0041_plan_switch_is_acceptance
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from alembic import op

revision = "0042_ic_s08_s09_guidance_adr244"
down_revision = "0041_plan_switch_is_acceptance"
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


_M34 = _load("0034_system_playbook_versions.py", "ofo_migration_0034_for_0042")
_BASE = _M34._BASE

SQLSTATE = "OF042"  # a downgrade under a newer saved iron condor version
TABLE = _M34.TABLE
GUARD_TRIGGER = _M34.TRIGGER
TYPE = "ic"
REASON = "ADR-244: situations S-08 (day before a known event) and S-09 (weekend or holiday ahead) listed as Guidance"
SAVED_BY = _M34.SEED_BY

S08 = {
    "id": "S-08",
    "name": "Day before a known event",
    "rule": "Check the event calendar yourself; possible approaches are adding wings, taking profit, reducing, "
            "or exiting",
}
S09 = {
    "id": "S-09",
    "name": "Weekend or market holiday ahead",
    "rule": "The carry check on the day before a weekend or holiday shows the overnight margin and the loss at a "
            "2% gap; possible approaches are holding with wings, or reducing",
}


def _lit(row: dict) -> str:
    return "'" + json.dumps(row).replace("'", "''") + "'::jsonb"


_LISTED = (
    "jsonb_array_elements(CASE WHEN jsonb_typeof(b.body -> 'situations') = 'array' "
    "THEN b.body -> 'situations' ELSE '[]'::jsonb END)"
)
#: the newest body with both situations listed, sorted by id (a missing ``situations`` list is built, never skipped)
_NEW_BODY = (
    "jsonb_set(b.body, '{situations}', COALESCE((SELECT jsonb_agg(s ORDER BY s ->> 'id') FROM ("
    f"SELECT e AS s FROM {_LISTED} e WHERE e ->> 'id' NOT IN ('S-08', 'S-09') "
    f"UNION ALL SELECT {_lit(S08)} UNION ALL SELECT {_lit(S09)}) u), '[]'::jsonb), true)"
)
_HAS_BOTH = f"(SELECT count(*) FROM {_LISTED} e WHERE e ->> 'id' IN ('S-08', 'S-09')) = 2"


def upgrade_sql() -> str:
    return f"""
        INSERT INTO {TABLE} (strategy_type, version, status, body, reason, saved_by)
        SELECT b.strategy_type, b.version + 1, b.status, {_NEW_BODY}, '{REASON}', '{SAVED_BY}'
        FROM (SELECT strategy_type, version, status, body FROM {TABLE}
              WHERE strategy_type = '{TYPE}' ORDER BY version DESC LIMIT 1) b
        WHERE NOT {_HAS_BOTH}
        """  # noqa: S608 - constant names only


def upgrade() -> None:
    op.execute(upgrade_sql())


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
                RAISE EXCEPTION 'refusing to downgrade {revision}: iron condor version % was saved after it', newest
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
