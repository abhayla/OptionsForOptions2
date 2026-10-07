"""Contract lifecycle: identity holds while a contract is live; its token retires after its expiry (W-057, ADR-057).

Spec basis: REQ-054 AC-3 ("The identity is (exchange segment, exchange token) while the contract is live: an exchange
change of a live contract's expiry, strike or lot is a revision with history; after the contract's expiry has passed
its token is retired, and a later row with that token is a new contract (ADR-057, correcting ADR-052).");
ADR-057 ("Once the stored contract's expiry has passed, the token is retired for it; a later row with the same token
creates a new contract with its own identity, and any record linked to the old one keeps pointing at the old one.");
findings F-21 (62964 / 61746 expiry moved under a live token; 67245 reused after expiry; 79199 strike 410 -> 390.75).
REQ-053 Q257's "strike never changes" is superseded for live contracts by ADR-057. ADR-058 / REQ-054 AC-3 (round 2):
"A contract the daily list stops carrying before its expiry is marked delisted and kept, and its token is free for
reuse (ADR-058)."

Copy from: none - algochanakya keys every broker on a Zerodha symbol string (legacy-reuse.md M2 rows SKIP, F-09).

Changes (owner-run, one transaction):
- public.catalogue_contracts: gains delisted (BOOLEAN, default FALSE) and delisted_on (the database's IST date,
  stamped by the guard, with a history row field delisted_on); a delisted contract never changes and is never
  retired. Live = NOT retired AND NOT delisted.
- public.catalogue_contracts: gains retired (BOOLEAN, default FALSE) and retired_at (stamped by the guard);
  CHECK retired contracts are unlisted and retired = (retired_at IS NOT NULL). UNIQUE (exchange_segment,
  exchange_token) becomes a partial unique index over live rows only (catalogue_contracts_live_identity_key).
  Identity = id, exchange_segment, exchange_token, name, instrument_type; revisable (with a history row, broker NULL)
  = expiry and strike. The guard refuses: retiring a contract whose expiry has not passed on the database's IST date,
  retiring while changing terms or listed, any change to a retired contract (so never un-retired), any delete. On
  retiring it retires the contract's broker rows.
- public.broker_instruments: gains retired (BOOLEAN, default FALSE: the row's contract has left the market, retired
  or delisted; set only by the contract guard's cascade, which marks itself with the transaction-local setting
  ofo.contract_leaving; no application grant). UNIQUE (broker, broker_segment, broker_token) becomes a partial unique index over live rows
  (broker_instruments_live_token_key): Zerodha's instrument_token is derived from the exchange token and is reused
  with it. The guard refuses: a broker row on a retired contract, retiring a row whose contract has not expired, any
  change to a retired row.
- public.catalogue_term_changes: field list gains strike (broker NULL for expiry and strike).
- Grants: the application role gains column UPDATE on catalogue_contracts.strike and .retired.
- Data: existing rows are kept as they are and become live contracts (retired = FALSE); the next load retires each
  one whose expiry is before its date. Nothing is deleted or rewritten. The downgrade refuses while any contract,
  broker row or history row exists (as 0004 does).
- public.ofo_assert_app_role_allowlist: rebuilt from 0002's text with blocks 8 and 9 re-rendered for this schema
  (column lists, both live-key indexes, re-pinned guard bodies).

Revision ID: 0005_contract_lifecycle
Revises: 0004_broker_instruments
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0005_contract_lifecycle"
down_revision = "0004_broker_instruments"
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


_M4 = _load("0004_broker_instruments.py", "ofo_migration_0004_for_0005")
_M3 = _M4._M3
_PREV = _M4._PREV  # 0002
_BASE = _M4._BASE  # 0001

CATALOGUE_SQLSTATE = _M4.CATALOGUE_SQLSTATE
SEARCH_PATH = _M4.SEARCH_PATH
GUARD_DATESTYLE = _M4.GUARD_DATESTYLE

TABLE = _M4.TABLE
SEQUENCE = _M4.SEQUENCE
GUARD_FUNCTION = _M4.GUARD_FUNCTION
GUARD_TRIGGER = _M4.GUARD_TRIGGER
HISTORY = _M4.HISTORY
HISTORY_SEQUENCE = _M4.HISTORY_SEQUENCE
HISTORY_FUNCTION = _M4.HISTORY_FUNCTION
BROKER_TABLE = _M4.BROKER_TABLE
BROKER_SEQUENCE = _M4.BROKER_SEQUENCE
BROKER_FUNCTION = _M4.BROKER_FUNCTION
BROKER_TRIGGER = _M4.BROKER_TRIGGER

EXCHANGE_SEGMENTS = _M4.EXCHANGE_SEGMENTS
ZERODHA_EXCHANGE_TO_SEGMENT = _M4.ZERODHA_EXCHANGE_TO_SEGMENT
BROKER_CODES = _M4.BROKER_CODES
SUPPORTED = _M4.SUPPORTED
SEEN_ON_TIMEZONE = _M4.SEEN_ON_TIMEZONE

CONTRACT_COLUMNS = _M4.CONTRACT_COLUMNS
CONTRACT_REVISABLE = ("expiry", "strike")
CONTRACT_IDENTITY = ("id", "exchange_segment", "exchange_token", "name", "instrument_type")
APP_INSERT_COLUMNS = CONTRACT_COLUMNS
APP_UPDATE_COLUMNS = ("currently_listed",) + CONTRACT_REVISABLE + ("retired", "delisted")

BROKER_COLUMNS = _M4.BROKER_COLUMNS
BROKER_REVISABLE = _M4.BROKER_REVISABLE
BROKER_IDENTITY = _M4.BROKER_IDENTITY
APP_BROKER_INSERT_COLUMNS = BROKER_COLUMNS
APP_BROKER_UPDATE_COLUMNS = BROKER_REVISABLE

#: Contract-level history fields (broker NULL): the revisable terms and the delisting date (ADR-058).
CONTRACT_HISTORY_FIELDS = CONTRACT_REVISABLE + ("delisted_on",)
HISTORY_FIELDS = CONTRACT_HISTORY_FIELDS + BROKER_REVISABLE
#: Transaction-local setting the contract guard sets while it frees the broker rows of a contract leaving the market.
LEAVING_SETTING = "ofo.contract_leaving"
MOVED_COLUMNS = _M4.MOVED_COLUMNS

LIVE_IDENTITY_INDEX = "public.catalogue_contracts_live_identity_key"
LIVE_BROKER_TOKEN_INDEX = "public.broker_instruments_live_token_key"
OLD_IDENTITY_CONSTRAINT = "catalogue_contracts_identity_key"
#: Live = neither retired after expiry (ADR-057) nor delisted before it (ADR-058).
LIVE_PREDICATE = "NOT retired AND NOT delisted"
OLD_BROKER_TOKEN_CONSTRAINT = "broker_instruments_broker_token_key"

GUARDED_TRIGGERS = _M4.GUARDED_TRIGGERS  # the same triggers; only the two guard bodies change
GUARDED_TABLES = _M4.GUARDED_TABLES

CATALOGUE_BLOCK_MARKER = _M4.CATALOGUE_BLOCK_MARKER  # "-- 8. catalogue store"
ALLOWLIST_BLOCK_MARKER = _M4.ALLOWLIST_BLOCK_MARKER  # "-- 9. broker instruments"

_TODAY = _M4._seen_on()  # the database's IST date, never the caller's


def _free_broker_rows() -> str:
    """The contract guard's cascade: free the broker rows of a contract leaving the market (retired or delisted)."""
    return f"""                PERFORM set_config('{LEAVING_SETTING}', OLD.id::text, TRUE);
                UPDATE {BROKER_TABLE} SET retired = TRUE WHERE contract_id = OLD.id AND NOT retired;
                PERFORM set_config('{LEAVING_SETTING}', '', TRUE);"""


def _guard_function_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in CONTRACT_IDENTITY)
    terms_changed = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in CONTRACT_REVISABLE)
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
                NEW.retired := FALSE;
                NEW.retired_at := NULL;
                NEW.delisted := FALSE;
                NEW.delisted_on := NULL;
                NEW.first_seen_at := clock_timestamp();
                NEW.last_seen_at := NEW.first_seen_at;
                RETURN NEW;
            END IF;
            IF OLD.retired OR OLD.delisted THEN
                RAISE EXCEPTION 'catalogue store: contract id % (% %) has left the market and never changes (ADR-057, ADR-058)',
                    OLD.id, OLD.exchange_segment, OLD.exchange_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'catalogue store: the identity of contract % % never changes',
                    OLD.exchange_segment, OLD.exchange_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            IF NEW.delisted THEN
                IF NEW.retired OR {terms_changed} OR NEW.currently_listed THEN
                    RAISE EXCEPTION 'catalogue store: contract id % is delisted unlisted, unretired, with its last terms (ADR-058)',
                        OLD.id USING ERRCODE = '{CATALOGUE_SQLSTATE}';
                END IF;
                NEW.delisted_on := {_TODAY};
                NEW.retired_at := OLD.retired_at;
                NEW.first_seen_at := OLD.first_seen_at;
                NEW.last_seen_at := OLD.last_seen_at;
                INSERT INTO {HISTORY} (contract_id, broker, field, old_value, new_value)
                VALUES (OLD.id, NULL, 'delisted_on', NULL, NEW.delisted_on::text);
{_free_broker_rows()}
                RETURN NEW;
            END IF;
            IF NEW.retired THEN
                IF OLD.expiry IS NULL OR OLD.expiry >= {_TODAY} THEN
                    RAISE EXCEPTION 'catalogue store: contract id % (% %) expires % and is still live; it cannot be retired (ADR-057)',
                        OLD.id, OLD.exchange_segment, OLD.exchange_token, OLD.expiry USING ERRCODE = '{CATALOGUE_SQLSTATE}';
                END IF;
                IF {terms_changed} OR NEW.currently_listed THEN
                    RAISE EXCEPTION 'catalogue store: contract id % is retired unlisted with its last terms (ADR-057)',
                        OLD.id USING ERRCODE = '{CATALOGUE_SQLSTATE}';
                END IF;
                NEW.retired_at := clock_timestamp();
                NEW.delisted_on := OLD.delisted_on;
                NEW.first_seen_at := OLD.first_seen_at;
                NEW.last_seen_at := OLD.last_seen_at;
{_free_broker_rows()}
                RETURN NEW;
            END IF;
            NEW.retired_at := OLD.retired_at;
            NEW.delisted_on := OLD.delisted_on;
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
    terms_changed = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in BROKER_REVISABLE)
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
                IF (SELECT c.retired OR c.delisted FROM {TABLE} AS c WHERE c.id = NEW.contract_id) IS TRUE THEN
                    RAISE EXCEPTION 'broker instruments: contract % has left the market; no % row is added to it (ADR-057)',
                        NEW.contract_id, NEW.broker USING ERRCODE = '{CATALOGUE_SQLSTATE}';
                END IF;
                NEW.retired := FALSE;
                NEW.first_seen_at := clock_timestamp();
                NEW.last_seen_at := NEW.first_seen_at;
                NEW.seen_on := {_TODAY};
                RETURN NEW;
            END IF;
            IF OLD.retired THEN
                RAISE EXCEPTION 'broker instruments: % row % of contract % is retired and never changes (ADR-057)',
                    OLD.broker, OLD.broker_token, OLD.contract_id USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'broker instruments: the identity of % row % never changes',
                    OLD.broker, OLD.broker_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            IF NEW.retired THEN
                IF current_setting('{LEAVING_SETTING}', TRUE) IS DISTINCT FROM OLD.contract_id::text THEN
                    RAISE EXCEPTION 'broker instruments: % row % is freed only when contract % leaves the market (ADR-057, ADR-058)',
                        OLD.broker, OLD.broker_token, OLD.contract_id USING ERRCODE = '{CATALOGUE_SQLSTATE}';
                END IF;
                IF {terms_changed} THEN
                    RAISE EXCEPTION 'broker instruments: % row % is retired with its last terms (ADR-057)',
                        OLD.broker, OLD.broker_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
                END IF;
                NEW.first_seen_at := OLD.first_seen_at;
                NEW.last_seen_at := OLD.last_seen_at;
                NEW.seen_on := OLD.seen_on;
                RETURN NEW;
            END IF;
{history}
            NEW.first_seen_at := OLD.first_seen_at;
            NEW.last_seen_at := clock_timestamp();
            NEW.seen_on := {_TODAY};
            RETURN NEW;
        END
        $fn$
        """


def _pinned_bodies() -> dict[str, str]:
    pins = dict(_M4.PINNED_BODIES)
    for signature in (f"{GUARD_FUNCTION}()", f"{BROKER_FUNCTION}()"):
        if signature not in pins:
            raise RuntimeError(f"0004 does not pin {signature}: cannot rebuild the pins")
    pins[f"{GUARD_FUNCTION}()"] = _M4._md5_body(_guard_function_sql())
    pins[f"{BROKER_FUNCTION}()"] = _M4._md5_body(_broker_function_sql())
    return pins


PINNED_BODIES = _pinned_bodies()


# ---------------------------------------------------------------------------------------------------------------
# Allowlist: blocks 8 and 9 re-rendered for this schema
# ---------------------------------------------------------------------------------------------------------------


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


def _live_index_check(index: str, table: str, columns: str, predicate: str) -> str:
    """The index exists on `table`, is UNIQUE, valid, and partial (WHERE `predicate`): two live rows never share it."""
    return f"""            IF NOT EXISTS (SELECT 1 FROM pg_index AS i WHERE i.indexrelid = to_regclass('{index}')
                           AND i.indrelid = '{table}'::regclass AND i.indisunique AND i.indisvalid
                           AND i.indpred IS NOT NULL
                           AND replace(replace(pg_get_expr(i.indpred, i.indrelid), '(', ''), ')', '') = '{predicate}'
                           AND pg_get_indexdef(i.indexrelid) LIKE '%({columns})%') THEN
                problems := problems || 'live key {index} is missing or not UNIQUE ({columns}) WHERE {predicate} (ADR-057)'::TEXT;
            END IF;"""


def _catalogue_block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {CATALOGUE_BLOCK_MARKER} (W-053, re-keyed by W-056, lifecycle W-057): catalogue_contracts: SELECT + column INSERT
    --    on the contract columns + column UPDATE on currently_listed, expiry, strike and retired only, USAGE only on its
    --    sequence, no broker column on it, and the live identity key (unique WHERE NOT retired);
    --    catalogue_term_changes: SELECT only, nothing on its sequence; no EXECUTE on either guard function; every
    --    guarded trigger present, enabled, calling its function, with its intended tgtype, no WHEN, no column list,
    --    no arguments, no other trigger or rule on a guarded table; every guarded function's body equal to its pin
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL OR to_regclass('{HISTORY}') IS NULL THEN
            problems := problems || 'catalogue table {TABLE} or {HISTORY} is missing'::TEXT;
        ELSE
{_PREV._privilege_checks(TABLE, "catalogue_contracts", {"SELECT"})}
{_M3._columns_exactly(TABLE, "catalogue_contracts", "INSERT", APP_INSERT_COLUMNS)}
{_M3._columns_exactly(TABLE, "catalogue_contracts", "UPDATE", APP_UPDATE_COLUMNS)}
{_M4._moved_columns_check()}
{_live_index_check(LIVE_IDENTITY_INDEX, TABLE, "exchange_segment, exchange_token", LIVE_PREDICATE)}
{_M3._sequence_checks(SEQUENCE, "catalogue id", usage=True)}
{_PREV._privilege_checks(HISTORY, "catalogue_term_changes", {"SELECT"})}
{_M3._columns_exactly(HISTORY, "catalogue_term_changes", "INSERT", ())}
{_M3._columns_exactly(HISTORY, "catalogue_term_changes", "UPDATE", ())}
{_M3._sequence_checks(HISTORY_SEQUENCE, "term-change id", usage=False)}
{_M3._guard_function_checks(GUARD_FUNCTION, security_definer=True)}
{_M3._guard_function_checks(HISTORY_FUNCTION, security_definer=False)}
        END IF;
{_M4._trigger_checks()}
{_pin_checks()}
    END IF;
"""


def _broker_block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-056, lifecycle W-057): broker_instruments: SELECT + column INSERT on the broker row
    --    columns + column UPDATE on broker_symbol, lot_size, tick_size and freeze_limit only (identity, retired and
    --    stamps never), USAGE only on its sequence, no DELETE / TRUNCATE; owned by the catalogue table owner; the live
    --    token key (unique WHERE NOT retired); its guard SECURITY DEFINER, search_path and DateStyle pinned, no EXECUTE
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
{_live_index_check(LIVE_BROKER_TOKEN_INDEX, BROKER_TABLE, "broker, broker_segment, broker_token", "NOT retired")}
{_M3._sequence_checks(BROKER_SEQUENCE, "broker instruments id", usage=True)}
{_M3._guard_function_checks(BROKER_FUNCTION, security_definer=True)}
        END IF;
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """CREATE OR REPLACE text: 0002's allowlist ``previous_sql`` plus blocks 8 and 9 for this schema. Fails closed
    (RuntimeError) if the previous text does not have exactly one header and one insertion point, or already holds
    block 8 or 9."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if (headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or CATALOGUE_BLOCK_MARKER in previous_sql
            or ALLOWLIST_BLOCK_MARKER in previous_sql):
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the contract lifecycle checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _catalogue_block() + _broker_block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _M4.previous_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def _history_checks(revisable: tuple[str, ...], fields: tuple[str, ...]) -> list[str]:
    codes = _M4._quoted(BROKER_CODES)
    return [
        f"ALTER TABLE {HISTORY} DROP CONSTRAINT IF EXISTS catalogue_term_changes_field_check",
        f"ALTER TABLE {HISTORY} DROP CONSTRAINT IF EXISTS catalogue_term_changes_broker_check",
        f"ALTER TABLE {HISTORY} ADD CONSTRAINT catalogue_term_changes_field_check "
        f"CHECK (field IN ({_M4._quoted(fields)}))",
        f"ALTER TABLE {HISTORY} ADD CONSTRAINT catalogue_term_changes_broker_check "
        f"CHECK ((broker IS NULL) = (field IN ({_M4._quoted(revisable)})) "
        f"AND (broker IS NULL OR broker IN ({codes})))",
    ]


#: Column UPDATE grants this migration adds on catalogue_contracts (0004 granted currently_listed and expiry).
ADDED_UPDATE_COLUMNS = tuple(c for c in APP_UPDATE_COLUMNS if c not in _M4.APP_UPDATE_COLUMNS)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"LOCK TABLE {TABLE}, {BROKER_TABLE}, {HISTORY} IN ACCESS EXCLUSIVE MODE")

    # Existing rows stay as they are and become live contracts (retired = FALSE); nothing is rewritten.
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN retired BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN retired_at TIMESTAMPTZ")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN delisted BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN delisted_on DATE")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT catalogue_contracts_retired_unlisted "
               f"CHECK (NOT ((retired OR delisted) AND currently_listed) AND NOT (retired AND delisted))")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT catalogue_contracts_delisted_stamped "
               f"CHECK (delisted = (delisted_on IS NOT NULL))")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT catalogue_contracts_retired_stamped "
               f"CHECK (retired = (retired_at IS NOT NULL))")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {OLD_IDENTITY_CONSTRAINT}")
    op.execute(f"CREATE UNIQUE INDEX {LIVE_IDENTITY_INDEX.split('.')[1]} ON {TABLE} "
               f"(exchange_segment, exchange_token) WHERE {LIVE_PREDICATE}")

    op.execute(f"ALTER TABLE {BROKER_TABLE} ADD COLUMN retired BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(f"ALTER TABLE {BROKER_TABLE} DROP CONSTRAINT {OLD_BROKER_TOKEN_CONSTRAINT}")
    op.execute(f"CREATE UNIQUE INDEX {LIVE_BROKER_TOKEN_INDEX.split('.')[1]} ON {BROKER_TABLE} "
               f"(broker, broker_segment, broker_token) WHERE NOT retired")

    for statement in _history_checks(CONTRACT_HISTORY_FIELDS, HISTORY_FIELDS):
        op.execute(statement)

    op.execute(_guard_function_sql())
    op.execute(_broker_function_sql())
    for fn in (GUARD_FUNCTION, BROKER_FUNCTION):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {fn}() FROM "{role}"')
    cols = ", ".join(f'"{c}"' for c in ADDED_UPDATE_COLUMNS)
    op.execute(f'GRANT UPDATE ({cols}) ON TABLE {TABLE} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while any contract, broker row or history row exists (never deleted; a retired contract cannot be
    # expressed in 0004's shape, where a token is unique for ever).
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
                RAISE EXCEPTION 'refusing to downgrade {revision}: the catalogue holds contracts (never deleted)';
            END IF;
        END
        $down$;
        """
    )
    role = _BASE._app_role()
    op.execute(_M4.extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f'REVOKE UPDATE ("strike") ON TABLE {TABLE} FROM "{role}"')  # "retired"/"delisted" go with columns
    op.execute(_M4._guard_function_sql())
    op.execute(_M4._broker_function_sql())
    for fn in (GUARD_FUNCTION, BROKER_FUNCTION):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {fn}() FROM "{role}"')
    for statement in _history_checks(_M4.CONTRACT_REVISABLE, _M4.HISTORY_FIELDS):
        op.execute(statement)
    op.execute(f"DROP INDEX {LIVE_BROKER_TOKEN_INDEX}")
    op.execute(f"ALTER TABLE {BROKER_TABLE} ADD CONSTRAINT {OLD_BROKER_TOKEN_CONSTRAINT} "
               f"UNIQUE (broker, broker_segment, broker_token)")
    op.execute(f"ALTER TABLE {BROKER_TABLE} DROP COLUMN retired")
    op.execute(f"DROP INDEX {LIVE_IDENTITY_INDEX}")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT {OLD_IDENTITY_CONSTRAINT} UNIQUE (exchange_segment, exchange_token)")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT catalogue_contracts_retired_stamped")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT catalogue_contracts_delisted_stamped")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT catalogue_contracts_retired_unlisted")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN retired_at")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN retired")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN delisted_on")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN delisted")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
