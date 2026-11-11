"""System playbooks: a NEW version of every playbook whose trigger labels T-09, T-11c, T-14t and T-19 say the new words
(issue #685 item 5a, GC-ICSAFE c16).

Spec basis: ADR-244 (0042 / 0044 pattern: a system playbook change is a new version, the old one kept; users' own
copies and saved plans are not changed), REQ-169 AC-2 ("the old one is kept, never overwritten"). Words only: the
"below" labels of the four "at or below" triggers (and "IV percentile above" for a trigger that fires at or above)
now say what the compare does. No rule, value, compare or stage changes.

Copy from: 0044_ic_s06_carry_gap_wording.py (same shape: one appended row built from the NEWEST body), for every
strategy type instead of one.

Changes (one transaction; ADDITIVE: appended rows, no existing row changed, no user row touched):
- public.system_playbook_versions: for each strategy_type whose NEWEST body still has one of the four old labels, ONE
  new row, version = that type's newest + 1, body = the newest body with those labels replaced (every other key kept,
  so an admin's saved edits survive), status kept, reason REASON, saved_by "release". A type whose newest body has none
  of the old labels (already new, or the trigger absent) gets nothing (re-runnable; never a duplicate or empty
  version). The base is the NEWEST row of each type, never found by number.
- the seed ``system_playbooks.json`` was changed in the same change (as 0048) and is not read here: a fresh database
  is seeded with the new words, so this writes nothing there.

downgrade: finds its rows by REASON, never by version number; refuses (OF051) when a newer version of such a type was
saved on top of its row; otherwise removes exactly those rows (append-only guard disabled for those DELETEs inside the
migration's transaction, re-enabled before it ends). Both directions end with the allow-list post check.

Revision ID: 0051_trigger_label_words
Revises: 0050_strategy_basket_facts
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0051_trigger_label_words"
down_revision = "0050_strategy_basket_facts"
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


_M44 = _load("0044_ic_s06_carry_gap_wording.py", "ofo_migration_0044_for_0051")
_BASE = _M44._BASE

SQLSTATE = "OF051"  # a downgrade under a newer saved version
TABLE = _M44.TABLE
GUARD_TRIGGER = _M44.GUARD_TRIGGER
REASON = "Issue 685: trigger labels T-09, T-11c, T-14t and T-19 say at or below / reaches, as the compare does"
SAVED_BY = _M44.SAVED_BY
#: (trigger id, old label, new label)
LABELS = (
    ("T-09", "A short leg's premium falls below Rs (close for pennies)",
     "A short leg's premium falls to Rs or below (close for pennies)"),
    ("T-11c", "IV percentile above", "IV percentile reaches"),
    ("T-14t", "Theta per day falls below this % of premium left",
     "Theta per day falls to this % of premium left or below"),
    ("T-19", "Premium still left to earn is below this many x the adjustment's cost",
     "Premium still left to earn is this many x the adjustment's cost or below"),
)


def _quoted(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _path(trigger: str) -> str:
    return f"'{{triggers,{trigger},label}}'"


def _new_body() -> str:
    """The newest body with each old label swapped; a missing trigger or any other label is left as it is."""
    body = "b.body"
    for trigger, old, new in LABELS:
        label = f"b.body #>> {_path(trigger)}"
        body = (f"jsonb_set({body}, {_path(trigger)}, "
                f"COALESCE(to_jsonb(CASE WHEN {label} = {_quoted(old)} THEN {_quoted(new)} ELSE {label} END), "
                "'null'::jsonb), false)")
    return body


_HAS_OLD = " OR ".join(f"b.body #>> {_path(trigger)} = {_quoted(old)}" for trigger, old, _new in LABELS)


def upgrade_sql() -> str:
    return f"""
        INSERT INTO {TABLE} (strategy_type, version, status, body, reason, saved_by)
        SELECT b.strategy_type, b.version + 1, b.status, {_new_body()}, '{REASON}', '{SAVED_BY}'
        FROM (SELECT DISTINCT ON (strategy_type) strategy_type, version, status, body FROM {TABLE}
              ORDER BY strategy_type, version DESC) b
        WHERE {_HAS_OLD}
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
            mine RECORD;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            FOR mine IN SELECT strategy_type, max(version) AS version FROM {TABLE}
                        WHERE reason = '{REASON}' GROUP BY strategy_type
            LOOP
                IF mine.version <> (SELECT max(version) FROM {TABLE} WHERE strategy_type = mine.strategy_type) THEN
                    RAISE EXCEPTION 'refusing to downgrade {revision}: % has a version saved after it',
                        mine.strategy_type
                        USING ERRCODE = '{SQLSTATE}';
                END IF;
            END LOOP;
            EXECUTE 'ALTER TABLE {TABLE} DISABLE TRIGGER {GUARD_TRIGGER}';
            DELETE FROM {TABLE} WHERE reason = '{REASON}';
            EXECUTE 'ALTER TABLE {TABLE} ENABLE TRIGGER {GUARD_TRIGGER}';
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
