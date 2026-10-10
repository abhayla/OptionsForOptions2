"""Minute history: the one-minute bar tier (REQ-051 AC-3) in PostgreSQL, final days immutable (W-067).

Spec basis: REQ-051 AC-3 ("Tiers: real-time, aggregated intraday (1-minute/5-minute), daily, strategy snapshots");
REQ-051 AC-4 ("Aggregated history is built from the live feed where practical and licensed (Q169)"); ADR-067 (live
first, final from Kite's candles; a day that could not be made final stays provisional); ADR-008 (decimals are exact:
NUMERIC, never float); ADR-048 (the limited application role).

Copy from: none - legacy-reuse row 70 (the daily snapshot's Decimal shape) was read for column naming only.

Changes (owner-run, one transaction):
- public.history_minute_bars: (instrument_id as the catalogue holds it, minute = the start of the minute, tz-aware)
  is the key; trade_date (the IST date of the minute, CHECKed); open/high/low/close NUMERIC(14,2); volume and oi BIGINT
  (NULL for an index); source CHECK in live / backfilled / kite; removed (a LIVE bar the gap rule or a day replacement
  took out: the application role cannot DELETE, so a removal is a flag the reads honour).
- public.history_day_status: trade_date -> provisional | final; finalized_at stamped by the guard.
- public.history_feed_gaps (session-clipped gaps) and public.history_gap_dropped (LIVE bars a gap kept out; what makes
  gap_minutes_missing answerable after a restart): insert-only.
- Guards (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF009, search_path pinned, md5-pinned in the allowlist): no
  delete anywhere; no insert/update of a bar, gap or dropped key on a FINAL day; a bar's identity never changes and
  its source never goes down (KITE > BACKFILLED > LIVE); a FINAL day never goes back; insert-only tables never update.
- Grants: the application role gets SELECT everywhere; INSERT on the key and value columns; UPDATE only on the bar
  value columns (open, high, low, close, volume, oi, source, removed) and the day status. No DELETE, no TRUNCATE.
- public.ofo_assert_app_role_allowlist: 0008's text plus block 12 for these tables.

Revision ID: 0009_minute_history
Revises: 0008_strategy_store
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0009_minute_history"
down_revision = "0008_strategy_store"
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


_M8 = _load("0008_strategy_store.py", "ofo_migration_0008_for_0009")
_M7 = _M8._M7
_M4 = _M8._M4
_M3 = _M8._M3
_PREV = _M8._PREV  # 0002
_BASE = _M8._BASE  # 0001

SEARCH_PATH = _M8.SEARCH_PATH
HISTORY_SQLSTATE = "OF009"  # a delete, a change to a final day, a lowered source, or a rewrite of an insert-only row
TIMEZONE = "Asia/Kolkata"

BARS = "public.history_minute_bars"
STATUS = "public.history_day_status"
GAPS = "public.history_feed_gaps"
DROPPED = "public.history_gap_dropped"
BARS_GUARD, STATUS_GUARD, APPEND_GUARD = ("public.history_bars_guard", "public.history_day_status_guard",
                                          "public.history_append_guard")
SOURCES = ("live", "backfilled", "kite")
STATUSES = ("provisional", "final")

BARS_INSERT = ("instrument_id", "minute", "trade_date", "open", "high", "low", "close", "volume", "oi", "source",
               "removed")
BARS_UPDATE = ("open", "high", "low", "close", "volume", "oi", "source", "removed")
STATUS_INSERT = ("trade_date", "status")
STATUS_UPDATE = ("status",)
GAPS_INSERT = ("gap_start", "gap_end", "trade_date")
DROPPED_INSERT = ("instrument_id", "minute", "trade_date")
NO_UPDATE: tuple[str, ...] = ()

#: (table, trigger, guard, insert columns, update columns, label)
TABLE_SPECS = (
    (BARS, "history_minute_bars_guard", BARS_GUARD, BARS_INSERT, BARS_UPDATE, "history_minute_bars"),
    (STATUS, "history_day_status_guard", STATUS_GUARD, STATUS_INSERT, STATUS_UPDATE, "history_day_status"),
    (GAPS, "history_feed_gaps_guard", APPEND_GUARD, GAPS_INSERT, NO_UPDATE, "history_feed_gaps"),
    (DROPPED, "history_gap_dropped_guard", APPEND_GUARD, DROPPED_INSERT, NO_UPDATE, "history_gap_dropped"),
)

ALLOWLIST_BLOCK_MARKER = "-- 12. minute history"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _final_day_check(day: str, what: str) -> str:
    return f"""IF EXISTS (SELECT 1 FROM {STATUS} AS s WHERE s.trade_date = {day} AND s.status = 'final') THEN
                RAISE EXCEPTION 'history: {what} on final day % is refused (ADR-067)', {day}
                    USING ERRCODE = '{HISTORY_SQLSTATE}';
            END IF;"""


def _rank(expr: str) -> str:
    return f"(CASE {expr} WHEN 'live' THEN 0 WHEN 'backfilled' THEN 1 ELSE 2 END)"


def _bars_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {BARS_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'history: a minute bar is never deleted (a removal is the removed flag)'
                    USING ERRCODE = '{HISTORY_SQLSTATE}';
            END IF;
            {_final_day_check("NEW.trade_date", "a write to a bar")}
            IF TG_OP = 'UPDATE' THEN
                IF NEW.instrument_id IS DISTINCT FROM OLD.instrument_id OR NEW.minute IS DISTINCT FROM OLD.minute
                   OR NEW.trade_date IS DISTINCT FROM OLD.trade_date THEN
                    RAISE EXCEPTION 'history: the identity of a minute bar never changes'
                        USING ERRCODE = '{HISTORY_SQLSTATE}';
                END IF;
                IF {_rank("NEW.source")} < {_rank("OLD.source")} THEN
                    RAISE EXCEPTION 'history: a bar source is never lowered (% to %)', OLD.source, NEW.source
                        USING ERRCODE = '{HISTORY_SQLSTATE}';
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """


def _status_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {STATUS_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'history: a day status is never deleted'
                    USING ERRCODE = '{HISTORY_SQLSTATE}';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF NEW.trade_date IS DISTINCT FROM OLD.trade_date THEN
                    RAISE EXCEPTION 'history: the date of a day status never changes'
                        USING ERRCODE = '{HISTORY_SQLSTATE}';
                END IF;
                IF OLD.status = 'final' THEN
                    IF NEW.status IS DISTINCT FROM OLD.status THEN
                        RAISE EXCEPTION 'history: final day % never goes back (ADR-067)', OLD.trade_date
                            USING ERRCODE = '{HISTORY_SQLSTATE}';
                    END IF;
                    NEW.finalized_at := OLD.finalized_at;
                    RETURN NEW;
                END IF;
            END IF;
            NEW.finalized_at := CASE WHEN NEW.status = 'final' THEN clock_timestamp() ELSE NULL END;
            RETURN NEW;
        END
        $fn$
        """


def _append_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {APPEND_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'history: % rows are insert-only', TG_TABLE_NAME
                    USING ERRCODE = '{HISTORY_SQLSTATE}';
            END IF;
            {_final_day_check("NEW.trade_date", "an insert")}
            RETURN NEW;
        END
        $fn$
        """


GUARD_SQL = {BARS_GUARD: _bars_guard_sql, STATUS_GUARD: _status_guard_sql, APPEND_GUARD: _append_guard_sql}
PINS = {guard: _M4._md5_body(sql()) for guard, sql in GUARD_SQL.items()}


def _table_block(table: str, trigger: str, guard: str, insert_cols, update_cols, label: str) -> str:
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
{_M3._guard_function_checks(guard, security_definer=False)}
{_M8._trigger_check(table, trigger, guard, PINS[guard])}
        END IF;"""


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    tables = "\n".join(_table_block(*spec) for spec in TABLE_SPECS)
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-067): history_minute_bars: SELECT + column INSERT on the key and value columns + column
    --    UPDATE on open, high, low, close, volume, oi, source, removed only; history_day_status: SELECT + INSERT
    --    (trade_date, status) + UPDATE (status); history_feed_gaps / history_gap_dropped: SELECT + INSERT only; no
    --    DELETE / TRUNCATE anywhere; every guard trigger enabled with its pinned body, no EXECUTE on the guards
    IF phase = 'post' THEN
{tables}
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """0008 allowlist text plus block 12. Fails closed (RuntimeError) on a changed shape or a block 12 already in."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous_sql:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the minute history checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _M8.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    op.execute(
        f"""
        CREATE TABLE {BARS} (
            instrument_id TEXT        NOT NULL CHECK (instrument_id <> ''),
            minute        TIMESTAMPTZ NOT NULL CHECK (minute = date_trunc('minute', minute)),
            trade_date    DATE        NOT NULL,
            open          NUMERIC(14,2) NOT NULL,
            high          NUMERIC(14,2) NOT NULL,
            low           NUMERIC(14,2) NOT NULL,
            close         NUMERIC(14,2) NOT NULL,
            volume        BIGINT      NULL CHECK (volume >= 0),
            oi            BIGINT      NULL CHECK (oi >= 0),
            source        TEXT        NOT NULL CHECK (source IN ({_quoted(SOURCES)})),
            removed       BOOLEAN     NOT NULL DEFAULT FALSE,
            PRIMARY KEY (instrument_id, minute),
            CONSTRAINT history_bars_trade_date CHECK (trade_date = (minute AT TIME ZONE '{TIMEZONE}')::date),
            CONSTRAINT history_bars_ohlc CHECK (low <= open AND low <= close AND open <= high AND close <= high)
        )
        """
    )
    op.execute(f"CREATE INDEX history_minute_bars_day ON {BARS} (trade_date, instrument_id, minute)")
    op.execute(
        f"""
        CREATE TABLE {STATUS} (
            trade_date   DATE        PRIMARY KEY,
            status       TEXT        NOT NULL CHECK (status IN ({_quoted(STATUSES)})),
            finalized_at TIMESTAMPTZ NULL,
            CONSTRAINT history_status_finalized CHECK ((status = 'final') = (finalized_at IS NOT NULL))
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {GAPS} (
            gap_start  TIMESTAMPTZ NOT NULL,
            gap_end    TIMESTAMPTZ NOT NULL,
            trade_date DATE        NOT NULL,
            PRIMARY KEY (gap_start, gap_end),
            CONSTRAINT history_gap_order CHECK (gap_end > gap_start),
            CONSTRAINT history_gap_trade_date CHECK (trade_date = (gap_start AT TIME ZONE '{TIMEZONE}')::date)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {DROPPED} (
            instrument_id TEXT        NOT NULL CHECK (instrument_id <> ''),
            minute        TIMESTAMPTZ NOT NULL CHECK (minute = date_trunc('minute', minute)),
            trade_date    DATE        NOT NULL,
            PRIMARY KEY (instrument_id, minute),
            CONSTRAINT history_dropped_trade_date CHECK (trade_date = (minute AT TIME ZONE '{TIMEZONE}')::date)
        )
        """
    )
    for sql in GUARD_SQL.values():
        op.execute(sql())
    for table, trigger, guard, *_ in TABLE_SPECS:
        op.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {guard}()")

    for guard in GUARD_SQL:
        op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
    for table, _trigger, _guard, insert_cols, update_cols, _label in TABLE_SPECS:
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
        op.execute(f'GRANT INSERT ({", ".join(insert_cols)}) ON TABLE {table} TO "{role}"')
        if update_cols:
            op.execute(f'GRANT UPDATE ({", ".join(update_cols)}) ON TABLE {table} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while any history row exists: recorded and final bars are data nobody can re-record.
    tables = ", ".join(spec[0] for spec in TABLE_SPECS)
    any_rows = " OR ".join(f"EXISTS (SELECT 1 FROM {spec[0]})" for spec in TABLE_SPECS)
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {tables} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT {any_rows}' INTO has_rows;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: the minute history holds rows';
            END IF;
        END
        $down$;
        """
    )
    role = _BASE._app_role()
    op.execute(_M8.extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    for table, *_ in reversed(TABLE_SPECS):
        op.execute(f"DROP TABLE {table}")
    for guard in GUARD_SQL:
        op.execute(f"DROP FUNCTION {guard}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
