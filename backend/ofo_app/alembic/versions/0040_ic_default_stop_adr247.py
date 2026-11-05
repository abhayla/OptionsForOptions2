"""Iron condor system playbook: a NEW version whose default stop follows ADR-247 (contract "Your adjustment settings"
step 3 part 1).

Spec basis: ADR-247 ("the iron condor system playbook's default stop line is a loss of 50 % of max loss or 2x the
credit received, whichever comes first. The '% of margin' stop and trigger T-16 ... stay available but are OFF by
default"; SPEC CHANGE to ADR-216's "50% of max loss or 4% of margin"); ADR-222 (9), (10) and REQ-169 AC-2 (a system
playbook change is a new version, the old one kept; users' own copies and saved strategy plans are not changed);
ADR-244 (the same treatment: a change to the iron condor system playbook ships as a new version).

TECHNICAL DECISION (builder 2026-11-05): the body's "% of margin" stop is ON exactly when ``guards`` holds
``stop_line_pct_of_margin`` (``settings_in_force.stops_of``, the plan words, the editor's plan line); there is no
separate on/off flag for it. So the new version DROPS that guard key and turns trigger T-16 off with its per-stage
values kept (4 / 4 / 3 % weekly and monthly): a user who turns the margin check on gets those values. The 2x credit
multiple is NOT written into the body: the body schema (docs/design/playbook-body-v1.md "guards") does not list
``stop_line_x_credit`` and ``stops_of`` already defaults it to 2 (ADR-247), as it defaults 50 % of max loss.

Changes (owner-run, one transaction; ADDITIVE: one appended row, no existing row changed, no user row touched):
- public.system_playbook_versions: ONE new row for strategy_type 'ic', version = the newest + 1, its body = the newest
  version's body with guards.stop_line_pct_of_margin removed and triggers.T-16.on = false (every other key kept, so an
  admin's saved edits survive), status kept, reason REASON, saved_by "release". When the newest body already has no
  margin stop and T-16 off (or no T-16), nothing is written (re-runnable; never an empty version).
- public.adjustment_playbooks: untouched. Users' copies (their own rows) and saved strategy plans (their own bodies)
  keep what they had (REQ-169).

downgrade: refuses (OF040) when a newer iron condor version was saved on top of this one; otherwise removes exactly the
row this upgrade appended (version and reason both match), with the append-only guard disabled for that one DELETE
inside the migration's transaction and re-enabled before it ends, then re-runs the allow-list check.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable the guard, then edit rows.

Revision ID: 0040_ic_default_stop_adr247
Revises: 0039_strategy_entry_facts
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0040_ic_default_stop_adr247"
down_revision = "0039_strategy_entry_facts"
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


_M34 = _load("0034_system_playbook_versions.py", "ofo_migration_0034_for_0040")
_BASE = _M34._BASE

SQLSTATE = "OF040"  # a downgrade under a newer saved iron condor version
TABLE = _M34.TABLE
GUARD_TRIGGER = _M34.TRIGGER
TYPE = "ic"
REASON = "ADR-247: default stop 50 % of max loss or 2x credit; % of margin stop and T-16 off by default"
SAVED_BY = _M34.SEED_BY
MARGIN_KEY = "stop_line_pct_of_margin"
TRIGGER_ID = "T-16"

#: the newest body with the ADR-247 change applied (jsonb; a missing T-16 is left missing, never invented)
_NEW_BODY = (
    "CASE WHEN (b.body -> 'triggers' -> '" + TRIGGER_ID + "') IS NULL "
    "THEN b.body #- '{guards," + MARGIN_KEY + "}' "
    "ELSE jsonb_set(b.body #- '{guards," + MARGIN_KEY + "}', "
    "'{triggers," + TRIGGER_ID + ",on}', 'false'::jsonb, false) "
    "END"
)


def upgrade_sql() -> str:
    return f"""
        INSERT INTO {TABLE} (strategy_type, version, status, body, reason, saved_by)
        SELECT b.strategy_type, b.version + 1, b.status, {_NEW_BODY}, '{REASON}', '{SAVED_BY}'
        FROM (SELECT strategy_type, version, status, body FROM {TABLE}
              WHERE strategy_type = '{TYPE}' ORDER BY version DESC LIMIT 1) b
        WHERE {_NEW_BODY} IS DISTINCT FROM b.body
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
