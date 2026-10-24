"""Strategy store: a saved leg can carry the mark of a typed entry price (REQ-077 AC-4, ADR-048).

Basis: REQ-077 AC-4 ("A typed price is saved with the definition, marked as typed, with its time"); REQ-038 AC-5 /
ADR-075 (the planned entry and its capture time are part of the saved leg); ADR-048 (the limited application role).

Copy from: none - this repo's own pattern: 0011's validator replacement (CREATE OR REPLACE of the same function, the
allow-list pins swapped) and 0023's downgrade refusal (LOCK TABLE, RAISE EXCEPTION naming the tables).

The mark is one optional ninth key of the stored leg, ``entry_source``: a JSON string that is exactly ``typed`` or
``captured``. It is allowed ONLY together with the 0011 pair ``planned_entry`` + ``captured_at`` (the time of a typed
price is ``captured_at``). The key set of a definition leg is an allow-list of exactly three shapes: the six 0008 keys,
those plus the pair (eight), those plus the pair and ``entry_source`` (nine). The key alone, the pair partly, another
value (any case change, a number, null) and a change-item leg carrying it are refused.

Changes (owner-run, one transaction):
- public.ofo_strategy_leg_valid: 0011's body with the key count and the value check extended (found exactly once each).
- public.ofo_assert_app_role_allowlist: 0023's chain text with block 11's pin of the leg validator replaced. No grant
  changes: the application role keeps exactly what it had.
- downgrade: refuses while any stored definition (current or history; history is append-only) holds a leg with an
  ``entry_source`` mark - the 0011 validator would refuse to load such a row and a typed mark must not vanish silently;
  otherwise 0011's validator and 0023's allow-list text come back.

Revision ID: 0024_typed_entry_mark
Revises: 0023_version_evidence
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0024_typed_entry_mark"
down_revision = "0023_version_evidence"
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


_M11 = _load("0011_strategy_planned_entry.py", "ofo_migration_0011_for_0024")
_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0024")  # 0023
_M8 = _M11._M8
_M4 = _M11._M4
_BASE = _M11._BASE  # 0001
_M22 = _load("0022_strategy_versions.py", "ofo_migration_0022_for_0024")

#: Every table that stores a strategy definition (a JSONB ``definition`` column whose legs may carry the mark). The
#: downgrade refuses while ANY of them holds a mark; tests_app/test_migration_0024_typed_entry.py reads every migration's
#: CREATE TABLE and fails when a definition table is missing here.
DEFINITION_TABLES = (_M8.STRATEGIES, _M8.HISTORY, _M22.VERSIONS)

#: ofo.strategy.stored_form will name the same two values in part 21a (a migration never imports application code).
ENTRY_SOURCE_KEY = "entry_source"
ENTRY_SOURCES = ("typed", "captured")
_SOURCES_SQL = ", ".join(f"'{s}'" for s in ENTRY_SOURCES)

_OLD_KEY_COUNT = "WHEN coalesce(leg ?| ARRAY['planned_entry', 'captured_at'], FALSE) THEN 8 ELSE 6 END)"
_NEW_KEY_COUNT = ("WHEN coalesce(leg ?| ARRAY['planned_entry', 'captured_at'], FALSE) "
                  f"THEN (CASE WHEN leg ? '{ENTRY_SOURCE_KEY}' THEN 9 ELSE 8 END) ELSE 6 END)")
_OLD_LEG_END = """                    RETURN FALSE;
                END IF;
            END IF;
            RETURN TRUE;
        EXCEPTION WHEN others THEN"""
_NEW_LEG_END = f"""                    RETURN FALSE;
                END IF;
                IF leg ? '{ENTRY_SOURCE_KEY}' AND NOT coalesce(jsonb_typeof(leg -> '{ENTRY_SOURCE_KEY}') = 'string'
                                AND (leg ->> '{ENTRY_SOURCE_KEY}') IN ({_SOURCES_SQL}), FALSE) THEN
                    RETURN FALSE;
                END IF;
            END IF;
            RETURN TRUE;
        EXCEPTION WHEN others THEN"""

LEG_SIGNATURE = _M11.LEG_SIGNATURE


def _replaced_once(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"migration 0011's validator text changed shape: {old!r} found {sql.count(old)} times")
    return sql.replace(old, new, 1)


def _old_leg_sql() -> str:
    """0011's leg validator (CREATE OR REPLACE): the downgrade."""
    return _M11._new_validators()[LEG_SIGNATURE]


def _new_leg_sql() -> str:
    return _replaced_once(_replaced_once(_old_leg_sql(), _OLD_KEY_COUNT, _NEW_KEY_COUNT), _OLD_LEG_END, _NEW_LEG_END)


OLD_PIN = _M11.NEW_PINS[LEG_SIGNATURE]
NEW_PIN = _M4._md5_body(_new_leg_sql())


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0023's chain text with the leg validator's pin replaced. Fails closed when the old pin is not found once."""
    return _replaced_once(previous_allowlist_sql(), f"'{OLD_PIN}'", f"'{NEW_PIN}'")


def _install(leg_sql: str, allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(leg_sql)
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    _install(_new_leg_sql(), extended_allowlist_sql())


def _refusal_sql(table: str) -> str:
    """One table's check: a leg with the mark in any stored definition refuses the downgrade, naming the table."""
    return f"""
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {table} d, jsonb_array_elements(d.definition -> ''legs'') l
                                    WHERE l ? ''{ENTRY_SOURCE_KEY}'')' INTO has_marks;
            IF has_marks THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: a stored strategy in {table} holds an entry source mark';
            END IF;"""  # noqa: S608 constant table and key names


def downgrade() -> None:
    # A typed mark is the user's data and history is append-only: refuse rather than strip or strand it.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_marks BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {", ".join(DEFINITION_TABLES)} IN ACCESS EXCLUSIVE MODE';{"".join(_refusal_sql(t) for t in DEFINITION_TABLES)}
        END
        $down$;
        """
    )
    _install(_old_leg_sql(), previous_allowlist_sql())
