"""Strategy versions after the first execution: proposed, active, superseded (W-144, REQ-038 AC-2..AC-4).

Basis: REQ-038 AC-2 ("From the first execution on, every meaningful modification creates a new version"); REQ-038 AC-3
("A proposed version is separate from the active version"); REQ-038 AC-4 ("the broker's actual state wins"); ADR-019
(versions after execution); ADR-048 (the limited application role); ADR-023 (the database clock).

Copy from: none - modelled on 0016's/0021's tables, guard triggers, grants and allow-list block.

Changes (owner-run, one transaction):
- public.strategy_versions: PRIMARY KEY (strategy_id, number); state proposed | active | superseded; the saved
  definition (JSONB, the stored form) and its schema version; based_on (the version it was edited from); created_at
  from the database clock; confirmed_at (the user's confirmation), reconciled_at (the reconciled execution return that
  made it active); outcome (the domain's last ExecutionOutcome kind for it) and actual (the broker's position as
  recorded by that return: AC-4, the broker wins).
- One active and one proposed version per strategy at most (partial unique indexes); an active version always carries
  confirmed_at AND reconciled_at (CHECK): a proposed version can never read as active on confirmation alone.
- Guard trigger (SQLSTATE OF022): no DELETE; an UPDATE never changes the identity or the definition (a version is
  frozen, byte for byte), moves state only proposed -> active, proposed -> superseded or active -> superseded, and
  sets each of confirmed_at / reconciled_at at most once.
- Grants: the application role gets SELECT, column-limited INSERT and column-limited UPDATE (state, confirmed_at,
  reconciled_at, outcome, actual); no DELETE or TRUNCATE.
- public.ofo_assert_app_role_allowlist: the predecessor's chain text (read from down_revision) plus block 19.
- strategies.status is NOT widened: the version lifecycle lives in this table, the strategy row stays 'draft'.
- downgrade: refuses while any version row is stored (a version is a record); otherwise drops what upgrade made.

Revision ID: 0022_strategy_versions
Revises: 0021_strategy_tracking
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0022_strategy_versions"
down_revision = "0021_strategy_tracking"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The predecessor publishes the allow-list chain text and its helpers (read from down_revision, never named here).
_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0022")
_M16 = _PREVIOUS._M16  # 0016: the table block helper
_BASE = _PREVIOUS._BASE  # 0001
_M4 = _PREVIOUS._M4  # 0004: _md5_body
_INSERT_BEFORE = _PREVIOUS._PREVIOUS._INSERT_BEFORE  # 0021 reads it from ITS predecessor; published here for 0023

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF022"
VERSIONS = "public.strategy_versions"
GUARD = "public.strategy_versions_guard"
TRIGGER = "strategy_versions_guard"
STATES = ("proposed", "active", "superseded")
INSERT_COLUMNS = ("strategy_id", "number", "state", "based_on", "definition", "definition_schema_version",
                  "confirmed_at", "reconciled_at")
UPDATE_COLUMNS = ("state", "confirmed_at", "reconciled_at", "outcome", "actual")
ALLOWLIST_BLOCK_MARKER = "-- 19. strategy versions"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            IF TG_OP <> 'UPDATE' THEN
                RAISE EXCEPTION 'strategy versions are never deleted' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.strategy_id IS DISTINCT FROM OLD.strategy_id OR NEW.number IS DISTINCT FROM OLD.number
               OR NEW.based_on IS DISTINCT FROM OLD.based_on OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.definition::text IS DISTINCT FROM OLD.definition::text
               OR NEW.definition_schema_version IS DISTINCT FROM OLD.definition_schema_version THEN
                RAISE EXCEPTION 'a strategy version is frozen' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
                   (OLD.state = 'proposed' AND NEW.state IN ('active', 'superseded'))
                OR (OLD.state = 'active' AND NEW.state = 'superseded')) THEN
                RAISE EXCEPTION 'version state % -> % is not allowed', OLD.state, NEW.state
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF (OLD.confirmed_at IS NOT NULL AND NEW.confirmed_at IS DISTINCT FROM OLD.confirmed_at)
               OR (OLD.reconciled_at IS NOT NULL AND NEW.reconciled_at IS DISTINCT FROM OLD.reconciled_at) THEN
                RAISE EXCEPTION 'a version is confirmed and reconciled once' USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-144): strategy_versions: SELECT, column-limited INSERT and UPDATE exactly as granted,
    --    no DELETE / TRUNCATE; the guard trigger enabled with its pinned body
    IF phase = 'post' THEN
{_M16._table_block(VERSIONS, "strategy_versions", INSERT_COLUMNS, UPDATE_COLUMNS, GUARD, TRIGGER, PIN)}
    END IF;
"""


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The predecessor's chain text plus block 19. Fails closed (RuntimeError) on a changed shape or a block 19 already
    in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the strategy versions checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def _quoted(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {VERSIONS} (
            strategy_id               BIGINT      NOT NULL REFERENCES public.strategies (id),
            number                    INTEGER     NOT NULL CHECK (number > 0),
            state                     TEXT        NOT NULL CHECK (state IN ({_quoted(STATES)})),
            based_on                  INTEGER     CHECK (based_on IS NULL OR (based_on > 0 AND based_on < number)),
            definition                JSONB       NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
            definition_schema_version INTEGER     NOT NULL CHECK (definition_schema_version > 0),
            created_at                TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            confirmed_at              TIMESTAMPTZ,
            reconciled_at             TIMESTAMPTZ,
            outcome                   TEXT        CHECK (outcome IS NULL OR outcome ~ '^[a-z_]{{1,32}}$'),
            actual                    JSONB       CHECK (actual IS NULL OR jsonb_typeof(actual) = 'array'),
            PRIMARY KEY (strategy_id, number),
            CHECK (state <> 'active' OR (confirmed_at IS NOT NULL AND reconciled_at IS NOT NULL))
        )
        """
    )
    op.execute(f"CREATE UNIQUE INDEX strategy_versions_one_active ON {VERSIONS} (strategy_id) WHERE state = 'active'")
    op.execute(f"CREATE UNIQUE INDEX strategy_versions_one_proposed ON {VERSIONS} (strategy_id) "
               "WHERE state = 'proposed'")
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {VERSIONS} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {VERSIONS} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {VERSIONS} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {VERSIONS} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {VERSIONS} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(UPDATE_COLUMNS)}) ON TABLE {VERSIONS} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # A version is a record of what the user asked after an execution: refuse rather than drop it.
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE 'LOCK TABLE {VERSIONS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {VERSIONS}) THEN
                RAISE EXCEPTION 'refusing downgrade: {VERSIONS} holds strategy versions';
            END IF;
        END
        $$
        """  # noqa: S608 constant table name
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {VERSIONS}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
