"""Strategy store: Save Draft definitions and their pre-execution activity history; no live-market column (W-061).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); REQ-038 AC-1 (definition and live state are separate objects); REQ-038 AC-2 (before the first execution,
definition changes are simple activity-history entries with restore, not versions); ADR-008 (decimals are exact).

Copy from: legacy-reuse row ``app/models/strategies.py`` (REFERENCE only: the Decimal leg shape). Its loose order id
string, float columns and missing history are not copied.

Changes (owner-run, one transaction):
- public.strategies: id, user_ref, underlying (CHECK NIFTY/SENSEX), status (CHECK 'draft'), created_at and updated_at
  (the database clock, stamped by the guard), definition JSONB (ofo.strategy.stored_form), definition_schema_version.
- public.strategy_history (append-only): id, strategy_id (FK), seq (assigned by the guard, 1, 2, ...), at (database
  clock), change_summary, definition JSONB (the definition the change replaced), definition_schema_version.
- CHECKs on both tables: the definition is a JSON object whose schema_version equals the column; a leg strike or a risk
  limit is never a JSON number (decimals are strings); strategies: the definition's underlying equals the column.
- Guard public.strategies_guard (BEFORE INSERT OR UPDATE OR DELETE): refuses any delete; on insert stamps created_at /
  updated_at and status 'draft'; refuses a change to id, user_ref, underlying, status, created_at or the schema
  version; refuses a definition change unless the newest history entry of the strategy holds the definition being
  replaced (an update never skips its history entry); stamps updated_at.
- Guard public.strategy_history_guard (BEFORE INSERT OR UPDATE OR DELETE): refuses any update or delete; on insert
  refuses an entry whose definition is not the strategy's current definition, stamps at and assigns seq.
- Grants: the application role gets SELECT on both; column INSERT on strategies (user_ref, underlying, definition,
  definition_schema_version) and on strategy_history (strategy_id, change_summary, definition,
  definition_schema_version); column UPDATE on strategies (definition, updated_at) only; USAGE on both id sequences.
  No DELETE, no TRUNCATE, no UPDATE on history, no EXECUTE.
- public.ofo_assert_app_role_allowlist: 0006's text plus block 11 for these tables.

Revision ID: 0007_strategy_store
Revises: 0006_broker_sessions
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0007_strategy_store"
down_revision = "0006_broker_sessions"
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


_M6 = _load("0006_broker_sessions.py", "ofo_migration_0006_for_0007")
_M5 = _M6._M5
_M4 = _M6._M4
_M3 = _M6._M3
_PREV = _M6._PREV  # 0002
_BASE = _M6._BASE  # 0001

SEARCH_PATH = _M6.SEARCH_PATH
STRATEGY_SQLSTATE = "OF008"  # a delete, a rewrite of history, or a definition change that skips its history entry

STRATEGIES = "public.strategies"
STRATEGIES_SEQUENCE = "public.strategies_id_seq"
STRATEGIES_GUARD = "public.strategies_guard"
STRATEGIES_TRIGGER = "strategies_guard"
HISTORY = "public.strategy_history"
HISTORY_SEQUENCE = "public.strategy_history_id_seq"
HISTORY_GUARD = "public.strategy_history_guard"
HISTORY_TRIGGER = "strategy_history_guard"

UNDERLYINGS = ("NIFTY", "SENSEX")
STATUSES = ("draft",)
FIXED_COLUMNS = ("id", "user_ref", "underlying", "status", "created_at", "definition_schema_version")

STRATEGIES_INSERT_COLUMNS = ("user_ref", "underlying", "definition", "definition_schema_version")
STRATEGIES_UPDATE_COLUMNS = ("definition", "updated_at")
HISTORY_INSERT_COLUMNS = ("strategy_id", "change_summary", "definition", "definition_schema_version")
HISTORY_UPDATE_COLUMNS: tuple[str, ...] = ()

ALLOWLIST_BLOCK_MARKER = "-- 11. strategy store"
BEFORE_ROW_INSERT_UPDATE_DELETE = _M3.BEFORE_ROW_INSERT_UPDATE_DELETE  # 31


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _definition_checks(prefix: str) -> str:
    """CHECKs shared by both tables: the stored form's shape and version, and no JSON number where a decimal goes."""
    return f"""
            CONSTRAINT {prefix}_definition_is_versioned CHECK (
                jsonb_typeof(definition) = 'object'
                AND (definition ->> 'schema_version') IS NOT DISTINCT FROM definition_schema_version::text),
            CONSTRAINT {prefix}_decimals_are_strings CHECK (
                NOT jsonb_path_exists(definition, '$.legs[*].strike ? (@.type() == "number")')
                AND NOT jsonb_path_exists(definition, '$.risk_limits.* ? (@.type() == "number")'))"""


def _strategies_guard_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in FIXED_COLUMNS)
    return f"""
        CREATE OR REPLACE FUNCTION {STRATEGIES_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'strategies: strategy % is never deleted (W-061)', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                NEW.created_at := clock_timestamp();
                NEW.updated_at := NEW.created_at;
                NEW.status := 'draft';
                RETURN NEW;
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'strategies: only the definition of strategy % changes', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            IF NEW.definition IS DISTINCT FROM OLD.definition
               AND (SELECT h.definition FROM {HISTORY} AS h WHERE h.strategy_id = OLD.id
                    ORDER BY h.seq DESC LIMIT 1) IS DISTINCT FROM OLD.definition THEN
                RAISE EXCEPTION 'strategies: the definition of strategy % changes only after its history entry', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """


def _history_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {HISTORY_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            current_definition JSONB;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'strategy history: entry % is never changed or deleted (W-061)', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            current_definition := (SELECT s.definition FROM {STRATEGIES} AS s WHERE s.id = NEW.strategy_id);
            IF current_definition IS NULL OR current_definition IS DISTINCT FROM NEW.definition THEN
                RAISE EXCEPTION 'strategy history: an entry of strategy % holds its current definition', NEW.strategy_id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            NEW.at := clock_timestamp();
            NEW.seq := (SELECT coalesce(max(h.seq), 0) + 1 FROM {HISTORY} AS h WHERE h.strategy_id = NEW.strategy_id);
            RETURN NEW;
        END
        $fn$
        """


STRATEGIES_PINNED_BODY = _M4._md5_body(_strategies_guard_sql())
HISTORY_PINNED_BODY = _M4._md5_body(_history_guard_sql())


def _trigger_check(table: str, trigger: str, fn: str, pinned: str) -> str:
    row = f"FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND tgname = '{trigger}'"
    return f"""            IF NOT EXISTS (SELECT 1 {row} AND tgenabled = 'O') THEN
                problems := problems || 'trigger {trigger} is missing or not enabled'::TEXT;
            ELSIF (SELECT tgfoid {row}) IS DISTINCT FROM to_regprocedure('{fn}()')
                  OR (SELECT tgtype::int {row}) IS DISTINCT FROM {BEFORE_ROW_INSERT_UPDATE_DELETE}
                  OR (SELECT tgqual IS NOT NULL OR tgattr::text <> '' OR tgnargs <> 0 {row}) THEN
                problems := problems || 'trigger {trigger} is not a plain BEFORE INSERT/UPDATE/DELETE row trigger on {fn}'::TEXT;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND NOT tgisinternal
                       AND tgname <> '{trigger}') THEN
                problems := problems || 'table {table} has an unexpected trigger'::TEXT;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_rewrite WHERE ev_class = '{table}'::regclass AND rulename <> '_RETURN') THEN
                problems := problems || 'table {table} has a rewrite rule'::TEXT;
            END IF;
            IF (SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('{fn}()'))
               IS DISTINCT FROM '{pinned}' THEN
                problems := problems || 'function {fn} body differs from its pinned body'::TEXT;
            END IF;"""


def _table_block(table: str, label: str, insert_cols, update_cols, sequence: str, guard: str, trigger: str,
                 pinned: str) -> str:
    return f"""        IF to_regclass('{table}') IS NULL THEN
            problems := problems || 'table {table} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{table}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M3.TABLE}'::regclass) THEN
                problems := problems || 'table {table} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_PREV._privilege_checks(table, label, {"SELECT"})}
{_M3._columns_exactly(table, label, "INSERT", insert_cols)}
{_M3._columns_exactly(table, label, "UPDATE", update_cols)}
{_M3._sequence_checks(sequence, f"{label} id", usage=True)}
{_M3._guard_function_checks(guard, security_definer=False)}
{_trigger_check(table, trigger, guard, pinned)}
        END IF;"""


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-061): strategies: SELECT + column INSERT on user_ref, underlying, definition,
    --    definition_schema_version + column UPDATE on definition, updated_at only; strategy_history: SELECT + column
    --    INSERT on strategy_id, change_summary, definition, definition_schema_version, no UPDATE; neither has DELETE /
    --    TRUNCATE; USAGE only on their sequences; both guard triggers enabled with their pinned bodies, no EXECUTE
    IF phase = 'post' THEN
{_table_block(STRATEGIES, "strategies", STRATEGIES_INSERT_COLUMNS, STRATEGIES_UPDATE_COLUMNS, STRATEGIES_SEQUENCE,
              STRATEGIES_GUARD, STRATEGIES_TRIGGER, STRATEGIES_PINNED_BODY)}
{_table_block(HISTORY, "strategy_history", HISTORY_INSERT_COLUMNS, HISTORY_UPDATE_COLUMNS, HISTORY_SEQUENCE,
              HISTORY_GUARD, HISTORY_TRIGGER, HISTORY_PINNED_BODY)}
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """0006's allowlist text plus block 11. Fails closed (RuntimeError) on a changed shape or a block 11 already in."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous_sql:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the strategy store checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _M6.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    op.execute(
        f"""
        CREATE TABLE {STRATEGIES} (
            id                        BIGSERIAL   PRIMARY KEY,
            user_ref                  TEXT        NOT NULL CHECK (user_ref <> ''),
            underlying                TEXT        NOT NULL CHECK (underlying IN ({_quoted(UNDERLYINGS)})),
            status                    TEXT        NOT NULL DEFAULT 'draft' CHECK (status IN ({_quoted(STATUSES)})),
            created_at                TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            definition                JSONB       NOT NULL,
            definition_schema_version INTEGER     NOT NULL CHECK (definition_schema_version > 0),
            CONSTRAINT strategies_definition_underlying CHECK (
                (definition ->> 'underlying') IS NOT DISTINCT FROM underlying),{_definition_checks("strategies")}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {HISTORY} (
            id                        BIGSERIAL   PRIMARY KEY,
            strategy_id               BIGINT      NOT NULL REFERENCES {STRATEGIES} (id),
            seq                       INTEGER     NOT NULL CHECK (seq > 0),
            at                        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            change_summary            TEXT        NOT NULL CHECK (change_summary <> ''),
            definition                JSONB       NOT NULL,
            definition_schema_version INTEGER     NOT NULL CHECK (definition_schema_version > 0),
            CONSTRAINT strategy_history_one_seq UNIQUE (strategy_id, seq),{_definition_checks("strategy_history")}
        )
        """
    )
    op.execute(_strategies_guard_sql())
    op.execute(_history_guard_sql())
    op.execute(f"CREATE TRIGGER {STRATEGIES_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {STRATEGIES} "
               f"FOR EACH ROW EXECUTE FUNCTION {STRATEGIES_GUARD}()")
    op.execute(f"CREATE TRIGGER {HISTORY_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {HISTORY} "
               f"FOR EACH ROW EXECUTE FUNCTION {HISTORY_GUARD}()")

    for table, sequence, guard in ((STRATEGIES, STRATEGIES_SEQUENCE, STRATEGIES_GUARD),
                                   (HISTORY, HISTORY_SEQUENCE, HISTORY_GUARD)):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'REVOKE ALL ON SEQUENCE {sequence} FROM "{role}"')
        op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
        op.execute(f'GRANT USAGE ON SEQUENCE {sequence} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(STRATEGIES_INSERT_COLUMNS)}) ON TABLE {STRATEGIES} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(STRATEGIES_UPDATE_COLUMNS)}) ON TABLE {STRATEGIES} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(HISTORY_INSERT_COLUMNS)}) ON TABLE {HISTORY} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while any strategy exists: a saved draft is the user's data.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {STRATEGIES}, {HISTORY} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {STRATEGIES}) OR EXISTS (SELECT 1 FROM {HISTORY})' INTO has_rows;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: the strategy store holds rows';
            END IF;
        END
        $down$;
        """
    )
    role = _BASE._app_role()
    op.execute(_M6.extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {HISTORY}")
    op.execute(f"DROP TABLE {STRATEGIES}")
    op.execute(f"DROP FUNCTION {HISTORY_GUARD}()")
    op.execute(f"DROP FUNCTION {STRATEGIES_GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
