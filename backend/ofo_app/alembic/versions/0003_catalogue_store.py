"""Catalogue store: NIFTY (NFO) and SENSEX (BFO) option and future contracts, never deleted.

Spec basis: REQ-053 AC-2 ("The contract catalogue (what exists) is stored separately from current eligibility (what
Zerodha permits); contracts are never permanently deleted because they are unavailable today."); REQ-053 AC-1
("Zerodha's response is final ...") and ADR-016: a contract's revisable terms follow Zerodha's list (orchestrator
decision Q257, fix round 2); REQ-053 owner decision Q244 (an update that would remove a not-yet-expired contract is
refused - enforced in ofo.instruments.catalogue.Catalogue.update, called by ofo_app.catalogue_store.apply_update);
ADR-008 (prices exact: NUMERIC, never float); ADR-048 (application role, schema-qualified tables, column-level
grants); finding privilege-guard-as-denylist (every new table joins the privilege allowlist).

Copy from (legacy-reuse.md M2): abhayla/algochanakya@bf9faf7:backend/app/models/instruments.py (ADAPT): strike
NUMERIC(12,2) (legacy DECIMAL(10,2)) and tick_size NUMERIC(10,4) with no float default (legacy default=0.05), unique
(exchange, instrument_token) instead of (instrument_token, source_broker), no source_broker, no option_type (the
instrument type already says CE/PE), plus currently_listed / first_seen_at / last_seen_at. Eligibility (what Zerodha
permits today) is NOT a column here (REQ-053 AC-2). The term-change history has no legacy counterpart.

Objects:
- public.catalogue_contracts: one row per contract. CHECKs keep it to the two supported underlyings on their
  exchanges (NIFTY/NFO, SENSEX/BFO) and to CE/PE/FUT, a positive tick and lot, a non-negative strike, no NaN.
- public.catalogue_term_changes: append-only history of revisable-term changes (instrument_token, exchange, field,
  old_value, new_value as text, changed_at stamped with clock_timestamp() by its own trigger). Written ONLY by the
  catalogue guard trigger, a SECURITY DEFINER function owned by the table owner (design choice: the application
  role holds SELECT only on the history, so it can neither forge nor omit a history row).
- BEFORE ROW INSERT/UPDATE/DELETE trigger public.catalogue_contracts_guard (SECURITY DEFINER, SQLSTATE OF006), for
  every role: INSERT stamps first_seen_at = last_seen_at = clock_timestamp(); UPDATE refuses a change to any
  IDENTITY column (id, exchange, instrument_token, exchange_token, name, strike, instrument_type, segment), lets the
  REVISABLE columns (lot_size, tick_size, expiry, tradingsymbol) change and appends one history row per changed
  revisable column, keeps first_seen_at, and stamps last_seen_at with clock_timestamp() when the row is (still)
  listed, else keeps it; DELETE is refused.
- BEFORE ROW INSERT/UPDATE/DELETE trigger public.catalogue_term_changes_guard on the history: INSERT stamps
  changed_at; UPDATE and DELETE are refused (OF006), for the owner too.
- The application role gets SELECT, INSERT on exactly the eleven contract columns (not id, currently_listed or the
  stamps), UPDATE on exactly currently_listed and the four revisable columns (last_seen_at is stamped by the trigger),
  USAGE on the contracts id sequence; SELECT only on the history and nothing on its sequence; no DELETE, no TRUNCATE.
- public.ofo_assert_app_role_allowlist gains block 8, built on 0002's text through the chain helper. Besides the
  catalogue privileges it closes owner-level gaps the W-052 round-2 review found: every guarded trigger must have its
  intended tgtype (timing, level, events), no WHEN condition (tgqual), no column list (tgattr), no arguments
  (tgnargs), and no other non-internal trigger may exist on a guarded table; every guarded function's body must
  have the md5 it had when the migrations wrote it.

Pinned bodies (PINNED_BODIES): computed at import from the migrations' own source - 0001/0002 upgrade() replayed with
a recording `op`, this file's function SQL - and, for public.ofo_audit_payload_allowlist(), from
ofo_app.audit_allowlist.allowlist_spec() as 0002 renders it. Consequence: a future change to allowlist_spec() or to
any pinned function's SQL REQUIRES a new migration that re-creates the function AND rebuilds the pins (re-creating
the allowlist function with new md5 literals); the chain helper only appends blocks, it never edits block 8's pins,
so without that migration the post-phase allowlist check fails on the next upgrade.

Revision ID: 0003_catalogue_store
Revises: 0002_audit_store
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

from alembic import op

revision = "0003_catalogue_store"
down_revision = "0002_audit_store"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    """Import an earlier migration by path (the versions folder is not a package); constants shared, never copied."""
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PREV = _load("0002_audit_store.py", "ofo_migration_0002_for_0003")
_BASE = _PREV._BASE

CATALOGUE_SQLSTATE = "OF006"  # a change to a contract's identity, a delete, or a history rewrite

TABLE = "public.catalogue_contracts"
SEQUENCE = "public.catalogue_contracts_id_seq"
GUARD_FUNCTION = "public.catalogue_contracts_guard"
GUARD_TRIGGER = "catalogue_contracts_guard"
HISTORY = "public.catalogue_term_changes"
HISTORY_SEQUENCE = "public.catalogue_term_changes_id_seq"
HISTORY_FUNCTION = "public.catalogue_term_changes_guard"
HISTORY_TRIGGER = "catalogue_term_changes_guard"
SEARCH_PATH = _PREV.SEARCH_PATH

SUPPORTED = (("NIFTY", "NFO"), ("SENSEX", "BFO"))  # ofo.instruments.catalogue.SUPPORTED_UNDERLYINGS; test asserts equal
INSTRUMENT_TYPES = ("CE", "PE", "FUT")
STRIKE_TYPE = "NUMERIC(12,2)"
TICK_TYPE = "NUMERIC(10,4)"

#: The contract's terms as inserted by the app.
CONTRACT_COLUMNS = (
    "exchange", "instrument_token", "exchange_token", "tradingsymbol", "name", "expiry", "strike", "tick_size",
    "lot_size", "instrument_type", "segment",
)
#: Terms that follow Zerodha's list (Q257); every change is recorded in the history.
REVISABLE_COLUMNS = ("lot_size", "tick_size", "expiry", "tradingsymbol")
#: Identity: never changes once stored (refused, OF006).
IDENTITY_COLUMNS = ("id", "exchange", "instrument_token", "exchange_token", "name", "strike", "instrument_type", "segment")
APP_INSERT_COLUMNS = CONTRACT_COLUMNS
APP_UPDATE_COLUMNS = ("currently_listed",) + REVISABLE_COLUMNS

# pg_trigger.tgtype bits (PostgreSQL src/include/catalog/pg_trigger.h).
TRIGGER_TYPE_ROW = 1
TRIGGER_TYPE_BEFORE = 2
TRIGGER_TYPE_INSERT = 4
TRIGGER_TYPE_DELETE = 8
TRIGGER_TYPE_UPDATE = 16
BEFORE_ROW_INSERT = TRIGGER_TYPE_ROW | TRIGGER_TYPE_BEFORE | TRIGGER_TYPE_INSERT  # 7
AFTER_ROW_INSERT = TRIGGER_TYPE_ROW | TRIGGER_TYPE_INSERT  # 5
BEFORE_ROW_INSERT_UPDATE_DELETE = BEFORE_ROW_INSERT | TRIGGER_TYPE_UPDATE | TRIGGER_TYPE_DELETE  # 31

#: (table, trigger, function it must call, tgtype it must have, wording) for every guarded trigger.
GUARDED_TRIGGERS = (
    (_BASE.TABLE, _BASE.TRIGGER_NAME, f"{_BASE.FUNCTION}()", BEFORE_ROW_INSERT, "BEFORE ROW INSERT"),
    (_PREV.EVENTS, _PREV.LINK_TRIGGER, f"{_PREV.LINK_FUNCTION}()", BEFORE_ROW_INSERT, "BEFORE ROW INSERT"),
    (_PREV.EVENTS, _PREV.ANCHOR_TRIGGER, f"{_PREV.ANCHOR_FUNCTION}()", AFTER_ROW_INSERT, "AFTER ROW INSERT"),
    (TABLE, GUARD_TRIGGER, f"{GUARD_FUNCTION}()", BEFORE_ROW_INSERT_UPDATE_DELETE,
     "BEFORE ROW INSERT OR UPDATE OR DELETE"),
    (HISTORY, HISTORY_TRIGGER, f"{HISTORY_FUNCTION}()", BEFORE_ROW_INSERT_UPDATE_DELETE,
     "BEFORE ROW INSERT OR UPDATE OR DELETE"),
)
#: Every guarded table and the only non-internal triggers it may carry (audit_anchor: none).
GUARDED_TABLES = tuple(
    (table, tuple(t for tab, t, *_ in GUARDED_TRIGGERS if tab == table))
    for table in (_BASE.TABLE, _PREV.EVENTS, _PREV.ANCHOR, TABLE, HISTORY)
)

#: The marker this migration's allowlist block starts with; the head test requires markers 1-8 in the live function.
ALLOWLIST_BLOCK_MARKER = "-- 8. catalogue store"


def _guard_function_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in IDENTITY_COLUMNS)
    history = "\n".join(
        f"""            IF NEW.{c} IS DISTINCT FROM OLD.{c} THEN
                INSERT INTO {HISTORY} (instrument_token, exchange, field, old_value, new_value)
                VALUES (OLD.instrument_token, OLD.exchange, '{c}', OLD.{c}::text, NEW.{c}::text);
            END IF;"""
        for c in REVISABLE_COLUMNS
    )
    return f"""
        CREATE FUNCTION {GUARD_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'catalogue store: contract % (%) is never deleted (REQ-053 AC-2)',
                    OLD.tradingsymbol, OLD.instrument_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                NEW.first_seen_at := clock_timestamp();
                NEW.last_seen_at := NEW.first_seen_at;
                RETURN NEW;
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'catalogue store: the identity of contract % (%) never changes',
                    OLD.tradingsymbol, OLD.instrument_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
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


def _history_function_sql() -> str:
    return f"""
        CREATE FUNCTION {HISTORY_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'catalogue store: term-change history is append-only (row %)', OLD.id
                    USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
            NEW.changed_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """


# ---------------------------------------------------------------------------------------------------------------
# Pinned function bodies: md5(prosrc) of every guarded function, computed from the SQL the migrations execute
# ---------------------------------------------------------------------------------------------------------------

_FUNCTION_BODY = re.compile(r"CREATE (?:OR REPLACE )?FUNCTION\s+([\w.]+)\(.*?\bAS \$fn\$(.*?)\$fn\$", re.DOTALL)


def _recorded_sql(module) -> list[str]:
    """Every statement ``module.upgrade()`` would execute, captured with a recording ``op`` (no database)."""
    statements: list[str] = []
    real_op = module.op
    module.op = SimpleNamespace(execute=lambda sql, *a, **k: statements.append(str(sql)))
    try:
        module.upgrade()
    finally:
        module.op = real_op
    return statements


def _bodies(statements: list[str]) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for sql in statements:
        for name, body in _FUNCTION_BODY.findall(sql):
            bodies[name] = body  # prosrc is exactly the text between the dollar quotes
    return bodies


def _pinned_bodies() -> dict[str, str]:
    """signature -> md5 of its body. Fails closed if a guarded function's body cannot be found."""
    bodies = {
        **_bodies(_recorded_sql(_BASE)),
        **_bodies(_recorded_sql(_PREV)),
        **_bodies([_guard_function_sql(), _history_function_sql()]),
    }
    wanted = [f"{_BASE.FUNCTION}()", *_PREV.FUNCTIONS, f"{GUARD_FUNCTION}()", f"{HISTORY_FUNCTION}()"]
    pins: dict[str, str] = {}
    for signature in wanted:
        name = signature.split("(")[0]
        if name not in bodies:
            raise RuntimeError(f"cannot pin {signature}: its CREATE FUNCTION body was not found in the migrations")
        pins[signature] = hashlib.md5(bodies[name].encode("utf-8")).hexdigest()
    return pins


PINNED_BODIES = _pinned_bodies()


# ---------------------------------------------------------------------------------------------------------------
# Allowlist block 8
# ---------------------------------------------------------------------------------------------------------------


def _columns_exactly(table: str, label: str, privilege: str, allowed: tuple[str, ...]) -> str:
    """Every column of the table (from pg_attribute, so a column added later is covered): the role holds
    ``privilege`` on it if and only if it is in ``allowed``."""
    allowed_sql = f"ARRAY[{', '.join(repr(c) for c in allowed)}]::TEXT[]"
    return f"""            FOR col IN SELECT attname FROM pg_attribute
                       WHERE attrelid = '{table}'::regclass AND attnum > 0 AND NOT attisdropped LOOP
                IF col = ANY({allowed_sql}) THEN
                    IF NOT has_column_privilege(r.oid, '{table}', col, '{privilege}') THEN
                        problems := problems || ('lacks {privilege} on {label} column ' || col);
                    END IF;
                ELSIF has_column_privilege(r.oid, '{table}', col, '{privilege}') THEN
                    problems := problems || ('has {privilege} on {label} column ' || col);
                END IF;
            END LOOP;
            FOREACH col IN ARRAY {allowed_sql} LOOP
                IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = '{table}'::regclass AND attname = col
                               AND attnum > 0 AND NOT attisdropped) THEN
                    problems := problems || ('{label} column ' || col || ' is missing');
                END IF;
            END LOOP;"""


def _sequence_checks(sequence: str, label: str, usage: bool) -> str:
    lines = [f"""            IF to_regclass('{sequence}') IS NULL THEN
                problems := problems || 'sequence {sequence} is missing'::TEXT;
            ELSE"""]
    for privilege in ("USAGE", "SELECT", "UPDATE"):
        if privilege == "USAGE" and usage:
            lines.append(f"""                IF NOT has_sequence_privilege(r.oid, '{sequence}', 'USAGE') THEN
                    problems := problems || 'lacks USAGE on the {label} sequence'::TEXT;
                END IF;""")
        else:
            lines.append(f"""                IF has_sequence_privilege(r.oid, '{sequence}', '{privilege}') THEN
                    problems := problems || 'has {privilege} on the {label} sequence'::TEXT;
                END IF;""")
    lines.append("            END IF;")
    return "\n".join(lines)


def _guard_function_checks(fn: str, security_definer: bool) -> str:
    sig = f"{fn}()"
    definer = (
        f"""                IF NOT (SELECT prosecdef FROM pg_proc WHERE oid = '{sig}'::regprocedure) THEN
                    problems := problems || 'function {fn} is not SECURITY DEFINER'::TEXT;
                END IF;"""
        if security_definer
        else ""
    )
    return f"""            IF to_regprocedure('{sig}') IS NULL THEN
                problems := problems || 'function {sig} is missing'::TEXT;
            ELSE
                IF has_function_privilege(r.oid, '{sig}', 'EXECUTE') THEN
                    problems := problems || 'has EXECUTE on {fn}'::TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_proc p, unnest(p.proconfig) AS c(setting)
                               WHERE p.oid = '{sig}'::regprocedure
                                 AND replace(c.setting, ' ', '') = 'search_path={SEARCH_PATH.replace(" ", "")}') THEN
                    problems := problems || 'function {fn} does not pin search_path'::TEXT;
                END IF;
                IF (SELECT proowner FROM pg_proc WHERE oid = '{sig}'::regprocedure)
                   IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass) THEN
                    problems := problems || 'function {fn} is not owned by the catalogue table owner'::TEXT;
                END IF;
{definer}
            END IF;"""


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


def _catalogue_allowlist_block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist, where `r` is the role's pg_roles row, `problems` the
    refusal list and `col` a TEXT loop variable."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-053): catalogue_contracts: SELECT + column INSERT on the contract terms + column
    --    UPDATE on currently_listed and the revisable terms only, USAGE only on its sequence; catalogue_term_changes:
    --    SELECT only, nothing on its sequence; no EXECUTE on either guard function (search_path pinned, owned by the
    --    table owner, the catalogue guard SECURITY DEFINER); every guarded trigger present, enabled, calling its
    --    function, with its intended tgtype, no WHEN, no column list, no arguments, and no other trigger on a
    --    guarded table; every guarded function's body equal to its pinned md5
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL OR to_regclass('{HISTORY}') IS NULL THEN
            problems := problems || 'catalogue table {TABLE} or {HISTORY} is missing'::TEXT;
        ELSE
{_PREV._privilege_checks(TABLE, "catalogue_contracts", {"SELECT"})}
{_columns_exactly(TABLE, "catalogue_contracts", "INSERT", APP_INSERT_COLUMNS)}
{_columns_exactly(TABLE, "catalogue_contracts", "UPDATE", APP_UPDATE_COLUMNS)}
{_sequence_checks(SEQUENCE, "catalogue id", usage=True)}
{_PREV._privilege_checks(HISTORY, "catalogue_term_changes", {"SELECT"})}
{_columns_exactly(HISTORY, "catalogue_term_changes", "INSERT", ())}
{_columns_exactly(HISTORY, "catalogue_term_changes", "UPDATE", ())}
{_sequence_checks(HISTORY_SEQUENCE, "term-change id", usage=False)}
{_guard_function_checks(GUARD_FUNCTION, security_definer=True)}
{_guard_function_checks(HISTORY_FUNCTION, security_definer=False)}
        END IF;
{_trigger_checks()}
{_pin_checks()}
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """CREATE OR REPLACE text: ``previous_sql`` plus block 8. Fails closed (RuntimeError) if the previous text does
    not have exactly one function header and one insertion point, or already holds this block."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous_sql:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the catalogue store checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _catalogue_allowlist_block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _PREV.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION

    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    pairs = " OR ".join(f"(name = '{n}' AND exchange = '{e}')" for n, e in SUPPORTED)
    types = ", ".join(f"'{t}'" for t in INSTRUMENT_TYPES)
    fields = ", ".join(f"'{c}'" for c in REVISABLE_COLUMNS)
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            id               BIGSERIAL     PRIMARY KEY,
            exchange         TEXT          NOT NULL,
            instrument_token BIGINT        NOT NULL CHECK (instrument_token > 0),
            exchange_token   BIGINT        NOT NULL CHECK (exchange_token > 0),
            tradingsymbol    TEXT          NOT NULL CHECK (tradingsymbol <> ''),
            name             TEXT          NOT NULL,
            expiry           DATE,
            strike           {STRIKE_TYPE} NOT NULL DEFAULT 0 CHECK (strike >= 0 AND strike <> 'NaN'),
            tick_size        {TICK_TYPE}   NOT NULL CHECK (tick_size > 0 AND tick_size <> 'NaN'),
            lot_size         INTEGER       NOT NULL CHECK (lot_size > 0),
            instrument_type  TEXT          NOT NULL CHECK (instrument_type IN ({types})),
            segment          TEXT          NOT NULL CHECK (segment <> ''),
            currently_listed BOOLEAN       NOT NULL DEFAULT TRUE,
            first_seen_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
            last_seen_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT catalogue_contracts_supported_underlying CHECK ({pairs}),
            CONSTRAINT catalogue_contracts_exchange_token_key UNIQUE (exchange, instrument_token)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {HISTORY} (
            id               BIGSERIAL   PRIMARY KEY,
            instrument_token BIGINT      NOT NULL,
            exchange         TEXT        NOT NULL,
            field            TEXT        NOT NULL CHECK (field IN ({fields})),
            old_value        TEXT,
            new_value        TEXT,
            changed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT catalogue_term_changes_contract_fkey FOREIGN KEY (exchange, instrument_token)
                REFERENCES {TABLE} (exchange, instrument_token)
        )
        """
    )
    op.execute(_history_function_sql())
    op.execute(
        f"CREATE TRIGGER {HISTORY_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {HISTORY} "
        f"FOR EACH ROW EXECUTE FUNCTION {HISTORY_FUNCTION}()"
    )
    op.execute(_guard_function_sql())
    op.execute(
        f"CREATE TRIGGER {GUARD_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION {GUARD_FUNCTION}()"
    )

    for fn in (GUARD_FUNCTION, HISTORY_FUNCTION):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {fn}() FROM "{role}"')
    for table, sequence in ((TABLE, SEQUENCE), (HISTORY, HISTORY_SEQUENCE)):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'REVOKE ALL ON SEQUENCE {sequence} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
    insert_columns = ", ".join(f'"{c}"' for c in APP_INSERT_COLUMNS)
    update_columns = ", ".join(f'"{c}"' for c in APP_UPDATE_COLUMNS)
    op.execute(f'GRANT INSERT ({insert_columns}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({update_columns}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while the catalogue holds contracts or history (never deleted, REQ-053 AC-2); the locks come first.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            IF to_regclass('{TABLE}') IS NOT NULL THEN
                EXECUTE 'LOCK TABLE {TABLE}, {HISTORY} IN ACCESS EXCLUSIVE MODE';
                EXECUTE 'SELECT EXISTS (SELECT 1 FROM {TABLE}) OR EXISTS (SELECT 1 FROM {HISTORY})' INTO has_rows;
            END IF;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to drop {TABLE}: it holds contracts (never deleted, REQ-053 AC-2)';
            END IF;
        END
        $down$;
        """
    )
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE IF EXISTS {HISTORY}")
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {GUARD_FUNCTION}()")
    op.execute(f"DROP FUNCTION IF EXISTS {HISTORY_FUNCTION}()")
