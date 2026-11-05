"""Scenario frame index + scenario marker on strategies (IC e2e paper contract 2026-11-05, design decisions 2, 3, 16).

Spec basis: goal contract ic-e2e-paper-2026-11-05 decisions 2 ("one shared frame index in the DB: public.scenario_frames
(scenario_id TEXT PRIMARY KEY, frame INT NOT NULL CHECK (frame >= 0), moved_at TIMESTAMPTZ NOT NULL)"), 3 (``public.
strategies.scenario_id TEXT NULL``, set by the SERVER, never from the client) and 16 (existing "Scenario <id>" seeds
get the marker from their exact name); ADR-048 (the limited application role).

Copy from: 0039_strategy_entry_facts.py (new table, grants, allow-list block appended before the final check).

Changes (owner-run, one transaction):
- public.scenario_frames (new): the application role gets SELECT, column INSERT on scenario_id, frame, moved_at and
  column UPDATE on frame, moved_at (the dev/test frame route upserts it). No DELETE / TRUNCATE.
- public.strategies.scenario_id TEXT NULL, DEFAULT ``NULLIF(current_setting('ofo.scenario_id', true), '')``. The
  application role gets NO INSERT or UPDATE on the column: the only writer at create time is the default, read from
  the transaction-local setting the server sets from ``scenario_mode.current_id()`` (``strategy_store.save_draft``).
  A client value has no path into it (no grant, no request field).
- Back-fill (decision 16): rows found by their REASON, the seed's exact name ``'Scenario ' || id`` with an id of the
  scenario shapes (ADJ-nn, ADJ-nna..e, PATH-nn); never by id or version number. The strategies guard (0025) refuses
  only FIXED_COLUMNS changes and keeps ``updated_at`` / ``revision`` when the definition is unchanged.
- public.ofo_assert_app_role_allowlist: 0041's chain text (the head) plus block 32 (scenario frames).
- downgrade: drops the column and the table, re-installs 0041's chain text; both end with the ``'post'`` check.

Known bypasses (out of the threat model): a developer hand-editing scenario_id in the database; the application role
setting ``ofo.scenario_id`` itself in a transaction (only server code runs as that role).

Revision ID: 0043_scenario_frames_and_marker
Revises: 0042_ic_s08_s09_guidance_adr244
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0043_scenario_frames_and_marker"
down_revision = "0042_ic_s08_s09_guidance_adr244"
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


_M41 = _load("0041_plan_switch_is_acceptance.py", "ofo_migration_0041_for_0043")
_M39 = _load("0039_strategy_entry_facts.py", "ofo_migration_0039_for_0043")
_M16 = _M39._M16
_BASE = _M39._BASE
_INSERT_BEFORE = _M39._INSERT_BEFORE

TABLE = "public.scenario_frames"
LABEL = "scenario_frames"
STRATEGIES = "public.strategies"
COLUMN = "scenario_id"
SETTING = "ofo.scenario_id"
INSERT_COLUMNS = ("scenario_id", "frame", "moved_at")
UPDATE_COLUMNS = ("frame", "moved_at")
ALLOWLIST_BLOCK_MARKER = "-- 32. scenario frames"
#: The reason a row gets the marker: the seed's exact name. Shapes of scenario_mode._ID, anchored.
SEED_NAME_PATTERN = r"^Scenario (ADJ-[0-9]{2}[a-e]?|PATH-[0-9]{2})$"
BACKFILL_SQL = (
    f"UPDATE {STRATEGIES} SET {COLUMN} = substr(name, length('Scenario ') + 1) "  # noqa: S608 - constant names only
    f"WHERE {COLUMN} IS NULL AND name ~ '{SEED_NAME_PATTERN}'"
)


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (IC e2e decision 2): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} + column
    --    UPDATE on {", ".join(UPDATE_COLUMNS)} only; no DELETE / TRUNCATE; no grant on strategies.{COLUMN}
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'table {TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M16._M3.TABLE}'::regclass) THEN
                problems := problems || 'table {TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_M16._PREV._privilege_checks(TABLE, LABEL, {"SELECT"})}
{_M16._M3._columns_exactly(TABLE, LABEL, "INSERT", INSERT_COLUMNS)}
{_M16._M3._columns_exactly(TABLE, LABEL, "UPDATE", UPDATE_COLUMNS)}
        END IF;
        IF has_column_privilege(r.oid, '{STRATEGIES}', '{COLUMN}', 'INSERT')
           OR has_column_privilege(r.oid, '{STRATEGIES}', '{COLUMN}', 'UPDATE') THEN
            problems := problems || 'the application role may write strategies.{COLUMN}'::TEXT;
        END IF;
    END IF;
"""  # noqa: S608 - constant table and function names only


def previous_allowlist_sql() -> str:
    return _M41.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0041's chain text plus block 32. Fails closed (RuntimeError) on a changed shape or a block 32 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 32." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the scenario-frames checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            scenario_id TEXT        PRIMARY KEY,
            frame       INTEGER     NOT NULL CHECK (frame >= 0),
            moved_at    TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(UPDATE_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f"ALTER TABLE {STRATEGIES} ADD COLUMN {COLUMN} TEXT NULL "
               f"DEFAULT NULLIF(current_setting('{SETTING}', true), '')")
    op.execute(BACKFILL_SQL)
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"ALTER TABLE {STRATEGIES} DROP COLUMN {COLUMN}")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"SELECT {allowlist}('{_BASE._app_role()}', 'post')")
