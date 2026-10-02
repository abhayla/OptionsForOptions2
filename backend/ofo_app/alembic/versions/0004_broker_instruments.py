"""Broker instruments: the catalogue keyed on (exchange segment, exchange token); Zerodha's ids move to a per-broker table.

Spec basis: REQ-054 AC-3 ("Each broker's own token, trading symbol and segment code for a contract are stored in a
per-broker table keyed to the contract's identity (exchange segment, exchange token), with one broker code
vocabulary; a contract with no row for a broker cannot be traded at that broker - no symbol is guessed or derived.");
AC-4 ("Lot size, tick size and freeze limit are stored per broker with the date the broker's list showed them.");
REQ-054 "Exchange segment vocabulary" (V1: NSE_FO, BSE_FO; Zerodha NFO -> NSE_FO, BFO -> BSE_FO); ADR-050; findings
F-01..F-04, F-10. REQ-053 AC-2 and Q244/Q257 (never deleted; revisable terms follow the source with history; identity
never changes) carry over from 0003. Orchestrator decision (W-056 stage 2 brief): current lot_size, tick_size,
freeze_limit and broker_symbol live on the broker row; their history goes into the existing append-only
catalogue_term_changes, extended with a nullable `broker` column (NULL = contract-level term, i.e. expiry).

Copy from: none - algochanakya's per-broker token table is SKIP (findings F-09, ADR-050).

Changes (owner-run, one transaction):
- public.catalogue_contracts: gains exchange_segment (CHECK in NSE_FO/BSE_FO; unique with exchange_token); loses
  exchange, instrument_token, tradingsymbol, segment, lot_size and tick_size (moved to the Zerodha broker row). Its
  guard is re-created: identity = id, exchange_segment, exchange_token, name, strike, instrument_type; the only
  revisable column is expiry (history row with broker NULL); never deleted.
- public.broker_instruments (new): one row per (contract, broker); broker CHECK in ('zerodha'); broker_token TEXT,
  broker_symbol, broker_segment, lot_size, tick_size NUMERIC(10,4), freeze_limit (nullable), seen_on /
  first_seen_at / last_seen_at stamped by its guard (SECURITY DEFINER, OF006): identity (id, contract_id, broker,
  broker_token, broker_segment) never changes; broker_symbol, lot_size, tick_size, freeze_limit follow the list with
  one history row each (broker named); never deleted. Unique (broker, broker_segment, broker_token) and
  (contract_id, broker).
- public.catalogue_term_changes: keyed by contract_id (FK) instead of (exchange, instrument_token); gains broker;
  field in (expiry, broker_symbol, lot_size, tick_size, freeze_limit), broker NULL exactly for expiry.
- Data: none is migrated (orchestrator decision M1, W-056 fix round 1: no database holds 0003 rows). The upgrade
  refuses, before any change, while catalogue_contracts or catalogue_term_changes holds a row, the same way the
  downgrade refuses.
- public.ofo_assert_app_role_allowlist: rebuilt from 0002's text with block 8 re-rendered for the re-keyed
  catalogue (its 0003 pins and column lists no longer describe the schema) and block 9 for broker_instruments.

Revision ID: 0004_broker_instruments
Revises: 0003_catalogue_store
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

from alembic import op

revision = "0004_broker_instruments"
down_revision = "0003_catalogue_store"
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


_M3 = _load("0003_catalogue_store.py", "ofo_migration_0003_for_0004")
_PREV = _M3._PREV  # 0002
_BASE = _M3._BASE  # 0001

CATALOGUE_SQLSTATE = _M3.CATALOGUE_SQLSTATE
SEARCH_PATH = _M3.SEARCH_PATH
GUARD_DATESTYLE = _M3.GUARD_DATESTYLE
TICK_TYPE = _M3.TICK_TYPE

TABLE = _M3.TABLE
SEQUENCE = _M3.SEQUENCE
GUARD_FUNCTION = _M3.GUARD_FUNCTION
GUARD_TRIGGER = _M3.GUARD_TRIGGER
HISTORY = _M3.HISTORY
HISTORY_SEQUENCE = _M3.HISTORY_SEQUENCE
HISTORY_FUNCTION = _M3.HISTORY_FUNCTION
HISTORY_TRIGGER = _M3.HISTORY_TRIGGER
BROKER_TABLE = "public.broker_instruments"
BROKER_SEQUENCE = "public.broker_instruments_id_seq"
BROKER_FUNCTION = "public.broker_instruments_guard"
BROKER_TRIGGER = "broker_instruments_guard"

#: The platform's exchange segment vocabulary (REQ-054) and Zerodha's `exchange` value for each.
EXCHANGE_SEGMENTS = ("NSE_FO", "BSE_FO")
ZERODHA_EXCHANGE_TO_SEGMENT = (("NFO", "NSE_FO"), ("BFO", "BSE_FO"))
#: One broker code vocabulary (REQ-054 AC-3); ofo.instruments.models.BROKER_CODES, a test asserts equal.
BROKER_CODES = ("zerodha",)
#: ofo.instruments.catalogue.SUPPORTED_UNDERLYINGS by segment; a test asserts equal.
SUPPORTED = (("NIFTY", "NSE_FO"), ("SENSEX", "BSE_FO"))
#: The local calendar of the exchanges (ADR-007): seen_on is the IST date the database saw the broker's row.
SEEN_ON_TIMEZONE = "Asia/Kolkata"

CONTRACT_COLUMNS = ("exchange_segment", "exchange_token", "name", "expiry", "strike", "instrument_type")
CONTRACT_REVISABLE = ("expiry",)
CONTRACT_IDENTITY = ("id", "exchange_segment", "exchange_token", "name", "strike", "instrument_type")
APP_INSERT_COLUMNS = CONTRACT_COLUMNS
APP_UPDATE_COLUMNS = ("currently_listed",) + CONTRACT_REVISABLE

BROKER_COLUMNS = ("contract_id", "broker", "broker_token", "broker_symbol", "broker_segment", "lot_size", "tick_size",
                  "freeze_limit")
BROKER_REVISABLE = ("broker_symbol", "lot_size", "tick_size", "freeze_limit")
BROKER_IDENTITY = ("id", "contract_id", "broker", "broker_token", "broker_segment")
APP_BROKER_INSERT_COLUMNS = BROKER_COLUMNS
APP_BROKER_UPDATE_COLUMNS = BROKER_REVISABLE

HISTORY_FIELDS = CONTRACT_REVISABLE + BROKER_REVISABLE
#: Columns of catalogue_contracts that must never exist again (the class this migration closes).
MOVED_COLUMNS = ("exchange", "instrument_token", "tradingsymbol", "segment", "lot_size", "tick_size")

BEFORE_ROW_INSERT_UPDATE_DELETE = _M3.BEFORE_ROW_INSERT_UPDATE_DELETE
GUARDED_TRIGGERS = _M3.GUARDED_TRIGGERS + (
    (BROKER_TABLE, BROKER_TRIGGER, f"{BROKER_FUNCTION}()", BEFORE_ROW_INSERT_UPDATE_DELETE,
     "BEFORE ROW INSERT OR UPDATE OR DELETE"),
)
GUARDED_TABLES = tuple(
    (table, tuple(t for tab, t, *_ in GUARDED_TRIGGERS if tab == table))
    for table in (_BASE.TABLE, _PREV.EVENTS, _PREV.ANCHOR, TABLE, HISTORY, BROKER_TABLE)
)

CATALOGUE_BLOCK_MARKER = _M3.ALLOWLIST_BLOCK_MARKER  # "-- 8. catalogue store", re-rendered here
ALLOWLIST_BLOCK_MARKER = "-- 9. broker instruments"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _seen_on() -> str:
    return f"(clock_timestamp() AT TIME ZONE '{SEEN_ON_TIMEZONE}')::date"


def _guard_function_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in CONTRACT_IDENTITY)
    history = "\n".join(
        f"""            IF NEW.{c} IS DISTINCT FROM OLD.{c} THEN
                INSERT INTO {HISTORY} (contract_id, broker, field, old_value, new_value)
                VALUES (OLD.id, NULL, '{c}', OLD.{c}::text, NEW.{c}::text);
            END IF;"""
        for c in CONTRACT_REVISABLE
    )
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = {SEARCH_PATH}
        SET DateStyle = '{GUARD_DATESTYLE}'
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'catalogue store: contract % % is never deleted (REQ-053 AC-2)',
                    OLD.exchange_segment, OLD.exchange_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                NEW.first_seen_at := clock_timestamp();
                NEW.last_seen_at := NEW.first_seen_at;
                RETURN NEW;
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'catalogue store: the identity of contract % % never changes',
                    OLD.exchange_segment, OLD.exchange_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
{history}
            NEW.first_seen_at := OLD.first_seen_at;
            IF NEW.currently_listed THEN
                NEW.last_seen_at := clock_timestamp();
            ELSE
                NEW.last_seen_at := OLD.last_seen_at;
            END IF;
            RETURN NEW;
        END
        $fn$
        """


def _broker_function_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in BROKER_IDENTITY)
    history = "\n".join(
        f"""            IF NEW.{c} IS DISTINCT FROM OLD.{c} THEN
                INSERT INTO {HISTORY} (contract_id, broker, field, old_value, new_value)
                VALUES (OLD.contract_id, OLD.broker, '{c}', OLD.{c}::text, NEW.{c}::text);
            END IF;"""
        for c in BROKER_REVISABLE
    )
    return f"""
        CREATE OR REPLACE FUNCTION {BROKER_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = {SEARCH_PATH}
        SET DateStyle = '{GUARD_DATESTYLE}'
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'broker instruments: % row % of contract % is never deleted (REQ-054 AC-3)',
                    OLD.broker, OLD.broker_token, OLD.contract_id USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                NEW.first_seen_at := clock_timestamp();
                NEW.last_seen_at := NEW.first_seen_at;
                NEW.seen_on := {_seen_on()};
                RETURN NEW;
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'broker instruments: the identity of % row % never changes',
                    OLD.broker, OLD.broker_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
{history}
            NEW.first_seen_at := OLD.first_seen_at;
            NEW.last_seen_at := clock_timestamp();
            NEW.seen_on := {_seen_on()};
            RETURN NEW;
        END
        $fn$
        """


def _md5_body(sql: str) -> str:
    (match,) = _M3._FUNCTION_BODY.findall(sql)
    return hashlib.md5(match[1].encode("utf-8")).hexdigest()


def _pinned_bodies() -> dict[str, str]:
    pins = dict(_M3.PINNED_BODIES)
    for signature in (f"{GUARD_FUNCTION}()", f"{HISTORY_FUNCTION}()"):
        if signature not in pins:
            raise RuntimeError(f"0003 does not pin {signature}: cannot rebuild the pins")
    pins[f"{GUARD_FUNCTION}()"] = _md5_body(_guard_function_sql())
    pins[f"{BROKER_FUNCTION}()"] = _md5_body(_broker_function_sql())
    return pins


PINNED_BODIES = _pinned_bodies()


# ---------------------------------------------------------------------------------------------------------------
# Allowlist: block 8 re-rendered for the re-keyed catalogue, block 9 for broker_instruments
# ---------------------------------------------------------------------------------------------------------------


def _trigger_checks() -> str:
    lines = []
    for table, trigger, fn, tgtype, words in GUARDED_TRIGGERS:
        name = fn.split("(")[0]
        row = f"FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND tgname = '{trigger}'"
        lines.append(
            f"""            IF to_regclass('{table}') IS NULL THEN
                problems := problems || 'table {table} is missing'::TEXT;
            ELSIF NOT EXISTS (SELECT 1 {row} AND tgenabled = 'O') THEN
                problems := problems || 'trigger {trigger} is missing or not enabled'::TEXT;
            ELSE
                IF (SELECT tgfoid {row}) IS DISTINCT FROM to_regprocedure('{fn}') THEN
                    problems := problems || 'trigger {trigger} does not call {name}'::TEXT;
                END IF;
                IF (SELECT tgtype::int {row}) IS DISTINCT FROM {tgtype} THEN
                    problems := problems || 'trigger {trigger} is not {words}'::TEXT;
                END IF;
                IF (SELECT tgqual IS NOT NULL {row}) THEN
                    problems := problems || 'trigger {trigger} has a WHEN condition'::TEXT;
                END IF;
                IF (SELECT tgattr::text <> '' {row}) THEN
                    problems := problems || 'trigger {trigger} is limited to a column list'::TEXT;
                END IF;
                IF (SELECT tgnargs <> 0 {row}) THEN
                    problems := problems || 'trigger {trigger} has arguments'::TEXT;
                END IF;
            END IF;"""
        )
    for table, expected in GUARDED_TABLES:
        names = ", ".join(f"'{t}'" for t in expected)
        allowed = f"AND tgname NOT IN ({names})" if expected else ""
        lines.append(
            f"""            IF to_regclass('{table}') IS NOT NULL AND EXISTS (
                   SELECT 1 FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND NOT tgisinternal {allowed}) THEN
                problems := problems || 'table {table} has an unexpected trigger'::TEXT;
            END IF;
            IF to_regclass('{table}') IS NOT NULL AND EXISTS (
                   SELECT 1 FROM pg_rewrite WHERE ev_class = '{table}'::regclass AND rulename <> '_RETURN') THEN
                problems := problems || 'table {table} has a rewrite rule'::TEXT;
            END IF;"""
        )
    return "\n".join(lines)


def _pin_checks() -> str:
    lines = []
    for fn, digest in PINNED_BODIES.items():
        name = fn.split("(")[0]
        lines.append(
            f"""            IF to_regprocedure('{fn}') IS NULL THEN
                problems := problems || 'function {fn} is missing'::TEXT;
            ELSIF (SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('{fn}')) IS DISTINCT FROM '{digest}' THEN
                problems := problems || 'function {name} body differs from its pinned body'::TEXT;
            END IF;"""
        )
    return "\n".join(lines)


def _moved_columns_check() -> str:
    moved = f"ARRAY[{_quoted(MOVED_COLUMNS)}]::TEXT[]"
    return f"""            IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = '{TABLE}'::regclass AND attnum > 0
                       AND NOT attisdropped AND attname = ANY({moved})) THEN
                problems := problems || 'catalogue_contracts holds a broker column such as instrument_token or tradingsymbol (REQ-054 AC-3)'::TEXT;
            END IF;"""


def _catalogue_block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {CATALOGUE_BLOCK_MARKER} (W-053, re-keyed by W-056): catalogue_contracts: SELECT + column INSERT on the contract
    --    columns + column UPDATE on currently_listed and expiry only, USAGE only on its sequence, and no broker column
    --    (instrument_token, tradingsymbol, ...) on it; catalogue_term_changes: SELECT only, nothing on its sequence;
    --    no EXECUTE on either guard function; every guarded trigger present, enabled, calling its function, with its
    --    intended tgtype, no WHEN, no column list, no arguments, no other trigger or rule on a guarded table; every
    --    guarded function's body equal to its pinned md5
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL OR to_regclass('{HISTORY}') IS NULL THEN
            problems := problems || 'catalogue table {TABLE} or {HISTORY} is missing'::TEXT;
        ELSE
{_PREV._privilege_checks(TABLE, "catalogue_contracts", {"SELECT"})}
{_M3._columns_exactly(TABLE, "catalogue_contracts", "INSERT", APP_INSERT_COLUMNS)}
{_M3._columns_exactly(TABLE, "catalogue_contracts", "UPDATE", APP_UPDATE_COLUMNS)}
{_moved_columns_check()}
{_M3._sequence_checks(SEQUENCE, "catalogue id", usage=True)}
{_PREV._privilege_checks(HISTORY, "catalogue_term_changes", {"SELECT"})}
{_M3._columns_exactly(HISTORY, "catalogue_term_changes", "INSERT", ())}
{_M3._columns_exactly(HISTORY, "catalogue_term_changes", "UPDATE", ())}
{_M3._sequence_checks(HISTORY_SEQUENCE, "term-change id", usage=False)}
{_M3._guard_function_checks(GUARD_FUNCTION, security_definer=True)}
{_M3._guard_function_checks(HISTORY_FUNCTION, security_definer=False)}
        END IF;
{_trigger_checks()}
{_pin_checks()}
    END IF;
"""


def _broker_block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-056): broker_instruments: SELECT + column INSERT on the broker row columns + column
    --    UPDATE on broker_symbol, lot_size, tick_size and freeze_limit only (identity and stamps never), USAGE only on
    --    its sequence, no DELETE / TRUNCATE; owned by the catalogue table owner; its guard SECURITY DEFINER, search_path and DateStyle pinned, owned by
    --    the catalogue table owner, no EXECUTE (trigger shape and body pin are in block 8's lists)
    IF phase = 'post' THEN
        IF to_regclass('{BROKER_TABLE}') IS NULL THEN
            problems := problems || 'table {BROKER_TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{BROKER_TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass) THEN
                problems := problems || 'table {BROKER_TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_PREV._privilege_checks(BROKER_TABLE, "broker_instruments", {"SELECT"})}
{_M3._columns_exactly(BROKER_TABLE, "broker_instruments", "INSERT", APP_BROKER_INSERT_COLUMNS)}
{_M3._columns_exactly(BROKER_TABLE, "broker_instruments", "UPDATE", APP_BROKER_UPDATE_COLUMNS)}
{_M3._sequence_checks(BROKER_SEQUENCE, "broker instruments id", usage=True)}
{_M3._guard_function_checks(BROKER_FUNCTION, security_definer=True)}
        END IF;
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """CREATE OR REPLACE text: 0002's allowlist ``previous_sql`` plus block 8 (re-rendered) and block 9. Fails closed
    (RuntimeError) if the previous text does not have exactly one header and one insertion point, or already holds
    block 8 or 9 (it must be 0002's text, not 0003's: 0003's block 8 pins the old catalogue guard)."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if (headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or CATALOGUE_BLOCK_MARKER in previous_sql
            or ALLOWLIST_BLOCK_MARKER in previous_sql):
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the broker instruments checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _catalogue_block() + _broker_block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _PREV.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def refuse_if_rows_sql() -> str:
    """The upgrade's first change: refuse while the 0003 catalogue holds any row (no data migration, decision M1)."""
    return f"""
        DO $refuse$
        BEGIN
            IF EXISTS (SELECT 1 FROM {TABLE}) OR EXISTS (SELECT 1 FROM {HISTORY}) THEN
                RAISE EXCEPTION 'refusing to upgrade to {revision}: the catalogue holds rows and this migration does not move 0003 data (W-056 decision M1)';
            END IF;
        END
        $refuse$;
        """


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(refuse_if_rows_sql())

    # The contract guard is re-created below with the new identity columns.
    op.execute(f"DROP TRIGGER IF EXISTS {GUARD_TRIGGER} ON {TABLE}")

    codes = _quoted(BROKER_CODES)
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BROKER_TABLE} (
            id             BIGSERIAL   PRIMARY KEY,
            contract_id    BIGINT      NOT NULL REFERENCES {TABLE} (id),
            broker         TEXT        NOT NULL CHECK (broker IN ({codes})),
            broker_token   TEXT        NOT NULL CHECK (broker_token <> ''),
            broker_symbol  TEXT        NOT NULL CHECK (broker_symbol <> ''),
            broker_segment TEXT        NOT NULL CHECK (broker_segment <> ''),
            lot_size       INTEGER     NOT NULL CHECK (lot_size > 0),
            tick_size      {TICK_TYPE} NOT NULL CHECK (tick_size > 0 AND tick_size <> 'NaN'),
            freeze_limit   INTEGER     CHECK (freeze_limit > 0),
            seen_on        DATE        NOT NULL DEFAULT CURRENT_DATE,
            first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT broker_instruments_broker_token_key UNIQUE (broker, broker_segment, broker_token),
            CONSTRAINT broker_instruments_contract_broker_key UNIQUE (contract_id, broker)
        )
        """
    )
    # History: re-keyed by contract, field list and broker rule (the tables are empty: refused above otherwise).
    op.execute(f"ALTER TABLE {HISTORY} ADD COLUMN contract_id BIGINT NOT NULL")
    op.execute(f"ALTER TABLE {HISTORY} ADD COLUMN broker TEXT")
    op.execute(f"ALTER TABLE {HISTORY} DROP CONSTRAINT IF EXISTS catalogue_term_changes_field_check")
    op.execute(f"ALTER TABLE {HISTORY} DROP CONSTRAINT IF EXISTS catalogue_term_changes_contract_fkey")
    op.execute(f"ALTER TABLE {HISTORY} DROP COLUMN IF EXISTS instrument_token")
    op.execute(f"ALTER TABLE {HISTORY} DROP COLUMN IF EXISTS exchange")
    op.execute(f"ALTER TABLE {HISTORY} ADD CONSTRAINT catalogue_term_changes_contract_fkey FOREIGN KEY (contract_id) "
               f"REFERENCES {TABLE} (id)")
    op.execute(f"ALTER TABLE {HISTORY} ADD CONSTRAINT catalogue_term_changes_field_check "
               f"CHECK (field IN ({_quoted(HISTORY_FIELDS)}))")
    op.execute(f"ALTER TABLE {HISTORY} ADD CONSTRAINT catalogue_term_changes_broker_check "
               f"CHECK ((broker IS NULL) = (field IN ({_quoted(CONTRACT_REVISABLE)})) "
               f"AND (broker IS NULL OR broker IN ({codes})))")

    # Contracts: identity on the exchange segment; broker columns gone.
    pairs = " OR ".join(f"(name = '{n}' AND exchange_segment = '{s}')" for n, s in SUPPORTED)
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN exchange_segment TEXT")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS catalogue_contracts_supported_underlying")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS catalogue_contracts_exchange_token_key")
    for column in MOVED_COLUMNS:
        op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS {column}")
    op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN exchange_segment SET NOT NULL")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT catalogue_contracts_exchange_segment_check "
               f"CHECK (exchange_segment IN ({_quoted(EXCHANGE_SEGMENTS)}))")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT catalogue_contracts_supported_underlying CHECK ({pairs})")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT catalogue_contracts_identity_key "
               f"UNIQUE (exchange_segment, exchange_token)")

    op.execute(_guard_function_sql())
    op.execute(f"CREATE TRIGGER {GUARD_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD_FUNCTION}()")
    op.execute(_broker_function_sql())
    op.execute(f"DROP TRIGGER IF EXISTS {BROKER_TRIGGER} ON {BROKER_TABLE}")
    op.execute(f"CREATE TRIGGER {BROKER_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {BROKER_TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {BROKER_FUNCTION}()")

    for fn in (GUARD_FUNCTION, BROKER_FUNCTION):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {fn}() FROM "{role}"')
    for table, sequence in ((TABLE, SEQUENCE), (BROKER_TABLE, BROKER_SEQUENCE)):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'REVOKE ALL ON SEQUENCE {sequence} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
        op.execute(f'GRANT USAGE ON SEQUENCE {sequence} TO "{role}"')
    for table, columns, privilege in ((TABLE, APP_INSERT_COLUMNS, "INSERT"), (TABLE, APP_UPDATE_COLUMNS, "UPDATE"),
                                      (BROKER_TABLE, APP_BROKER_INSERT_COLUMNS, "INSERT"),
                                      (BROKER_TABLE, APP_BROKER_UPDATE_COLUMNS, "UPDATE")):
        cols = ", ".join(f'"{c}"' for c in columns)
        op.execute(f'GRANT {privilege} ({cols}) ON TABLE {table} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while any contract, broker row or history row exists (never deleted); an empty catalogue is rebuilt in
    # 0003's shape by 0003's own upgrade.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE}, {HISTORY}, {BROKER_TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {TABLE}) OR EXISTS (SELECT 1 FROM {HISTORY})
                     OR EXISTS (SELECT 1 FROM {BROKER_TABLE})' INTO has_rows;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to drop the re-keyed catalogue: it holds contracts (never deleted)';
            END IF;
        END
        $down$;
        """
    )
    op.execute(_M3.previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {BROKER_TABLE}")
    op.execute(f"DROP TABLE {HISTORY}")
    op.execute(f"DROP TABLE {TABLE}")
    for fn in (BROKER_FUNCTION, GUARD_FUNCTION, HISTORY_FUNCTION):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}()")
    _M3.upgrade()
