"""Catalogue store: NIFTY (NFO) and SENSEX (BFO) option and future contracts, never deleted.

Spec basis: REQ-053 AC-2 ("The contract catalogue (what exists) is stored separately from current eligibility (what
Zerodha permits); contracts are never permanently deleted because they are unavailable today."); REQ-053 owner
decision Q244 (an update that would remove a not-yet-expired contract is refused - enforced in
ofo.instruments.catalogue.Catalogue.update, called by ofo_app.catalogue_store.apply_update); ADR-008 (money and
prices exact: NUMERIC, never float); ADR-048 (application role, schema-qualified tables, column-level grants);
finding privilege-guard-as-denylist (every new table joins the privilege allowlist).

Copy from (legacy-reuse.md M2): abhayla/algochanakya@bf9faf7:backend/app/models/instruments.py (ADAPT): strike
NUMERIC(12,2) (legacy DECIMAL(10,2)) and tick_size NUMERIC(10,4) with no float default (legacy default=0.05), unique
(exchange, instrument_token) instead of (instrument_token, source_broker), no source_broker, no option_type (the
instrument type already says CE/PE), plus currently_listed / first_seen_at / last_seen_at. Eligibility (what Zerodha
permits today) is NOT a column here (REQ-053 AC-2).

Objects:
- public.catalogue_contracts: one row per contract. CHECKs keep it to the two supported underlyings on their
  exchanges (NIFTY/NFO, SENSEX/BFO) and to CE/PE/FUT, a positive tick and lot, a non-negative strike, no NaN.
- BEFORE ROW INSERT/UPDATE/DELETE trigger public.catalogue_contracts_guard (SQLSTATE OF006), for every role:
  INSERT stamps first_seen_at = last_seen_at = clock_timestamp(); UPDATE refuses a change to any contract column
  (a contract is immutable by identity: ofo.instruments.models.Contract), keeps first_seen_at, and stamps
  last_seen_at with clock_timestamp() when the row is (still) listed, else keeps it; DELETE is refused.
- The application role gets SELECT, INSERT on exactly the eleven contract columns (not id, currently_listed or the
  stamps), UPDATE on exactly currently_listed (last_seen_at is stamped by the trigger, so the app never writes it),
  USAGE on the id sequence; no DELETE, no TRUNCATE.
- public.ofo_assert_app_role_allowlist gains block 8, built on 0002's text through the chain helper. Besides the
  catalogue privileges it closes two owner-level gaps the W-052 round-2 review found: every guarded trigger's tgtype
  (timing, level and events) must equal the intended value, and every guarded function's body must have the md5 it
  had when the migrations wrote it (PINNED_BODIES below, computed from the migrations' own SQL, not typed).

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

CATALOGUE_SQLSTATE = "OF006"  # a change to a contract's terms, or a delete

TABLE = "public.catalogue_contracts"
SEQUENCE = "public.catalogue_contracts_id_seq"
GUARD_FUNCTION = "public.catalogue_contracts_guard"
GUARD_TRIGGER = "catalogue_contracts_guard"
SEARCH_PATH = _PREV.SEARCH_PATH

SUPPORTED = (("NIFTY", "NFO"), ("SENSEX", "BFO"))  # ofo.instruments.catalogue.SUPPORTED_UNDERLYINGS; test asserts equal
INSTRUMENT_TYPES = ("CE", "PE", "FUT")
STRIKE_TYPE = "NUMERIC(12,2)"
TICK_TYPE = "NUMERIC(10,4)"

#: The contract's terms: inserted by the app, never changed afterwards.
CONTRACT_COLUMNS = (
    "exchange", "instrument_token", "exchange_token", "tradingsymbol", "name", "expiry", "strike", "tick_size",
    "lot_size", "instrument_type", "segment",
)
APP_INSERT_COLUMNS = CONTRACT_COLUMNS
APP_UPDATE_COLUMNS = ("currently_listed",)

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
)

#: The marker this migration's allowlist block starts with; the head test requires markers 1-8 in the live function.
ALLOWLIST_BLOCK_MARKER = "-- 8. catalogue store"


def _guard_function_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in ("id",) + CONTRACT_COLUMNS)
    return f"""
        CREATE FUNCTION {GUARD_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
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
                RAISE EXCEPTION 'catalogue store: the terms of contract % (%) never change',
                    OLD.tradingsymbol, OLD.instrument_token USING ERRCODE = '{CATALOGUE_SQLSTATE}';
            END IF;
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
    bodies = {**_bodies(_recorded_sql(_BASE)), **_bodies(_recorded_sql(_PREV)), **_bodies([_guard_function_sql()])}
    wanted = [f"{_BASE.FUNCTION}()", *_PREV.FUNCTIONS, f"{GUARD_FUNCTION}()"]
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


def _columns_exactly(privilege: str, allowed: tuple[str, ...]) -> str:
    """Every column of the table (from pg_attribute, so a column added later is covered): the role holds
    ``privilege`` on it if and only if it is in ``allowed``."""
    allowed_sql = ", ".join(f"'{c}'" for c in allowed)
    word = privilege
    return f"""            FOR col IN SELECT attname FROM pg_attribute
                       WHERE attrelid = '{TABLE}'::regclass AND attnum > 0 AND NOT attisdropped LOOP
                IF col = ANY(ARRAY[{allowed_sql}]::TEXT[]) THEN
                    IF NOT has_column_privilege(r.oid, '{TABLE}', col, '{privilege}') THEN
                        problems := problems || ('lacks {word} on catalogue_contracts column ' || col);
                    END IF;
                ELSIF has_column_privilege(r.oid, '{TABLE}', col, '{privilege}') THEN
                    problems := problems || ('has {word} on catalogue_contracts column ' || col);
                END IF;
            END LOOP;
            FOREACH col IN ARRAY ARRAY[{allowed_sql}] LOOP
                IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = '{TABLE}'::regclass AND attname = col
                               AND attnum > 0 AND NOT attisdropped) THEN
                    problems := problems || ('catalogue_contracts column ' || col || ' is missing');
                END IF;
            END LOOP;"""


def _trigger_checks() -> str:
    lines = []
    for table, trigger, fn, tgtype, words in GUARDED_TRIGGERS:
        name = fn.split("(")[0]
        lines.append(
            f"""            IF to_regclass('{table}') IS NULL THEN
                problems := problems || 'table {table} is missing'::TEXT;
            ELSIF NOT EXISTS (SELECT 1 FROM pg_trigger
                              WHERE tgrelid = '{table}'::regclass AND tgname = '{trigger}' AND tgenabled = 'O') THEN
                problems := problems || 'trigger {trigger} is missing or not enabled'::TEXT;
            ELSE
                IF (SELECT tgfoid FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND tgname = '{trigger}')
                   IS DISTINCT FROM to_regprocedure('{fn}') THEN
                    problems := problems || 'trigger {trigger} does not call {name}'::TEXT;
                END IF;
                IF (SELECT tgtype::int FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND tgname = '{trigger}')
                   IS DISTINCT FROM {tgtype} THEN
                    problems := problems || 'trigger {trigger} is not {words}'::TEXT;
                END IF;
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
    {ALLOWLIST_BLOCK_MARKER} (W-053): SELECT + column INSERT on the contract terms + column UPDATE on currently_listed
    --    only, USAGE only on the id sequence, no EXECUTE on the guard function (pins search_path, owned by the
    --    table owner); every guarded trigger present, enabled, calling its function with its intended tgtype; every
    --    guarded function's body equal to its pinned md5
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'catalogue table {TABLE} is missing'::TEXT;
        ELSE
{_PREV._privilege_checks(TABLE, "catalogue_contracts", {"SELECT"})}
{_columns_exactly("INSERT", APP_INSERT_COLUMNS)}
{_columns_exactly("UPDATE", APP_UPDATE_COLUMNS)}
            IF to_regclass('{SEQUENCE}') IS NULL THEN
                problems := problems || 'sequence {SEQUENCE} is missing'::TEXT;
            ELSE
                IF NOT has_sequence_privilege(r.oid, '{SEQUENCE}', 'USAGE') THEN
                    problems := problems || 'lacks USAGE on the catalogue id sequence'::TEXT;
                END IF;
                IF has_sequence_privilege(r.oid, '{SEQUENCE}', 'SELECT') THEN
                    problems := problems || 'has SELECT on the catalogue id sequence'::TEXT;
                END IF;
                IF has_sequence_privilege(r.oid, '{SEQUENCE}', 'UPDATE') THEN
                    problems := problems || 'has UPDATE on the catalogue id sequence'::TEXT;
                END IF;
            END IF;
            IF to_regprocedure('{GUARD_FUNCTION}()') IS NULL THEN
                problems := problems || 'function {GUARD_FUNCTION}() is missing'::TEXT;
            ELSE
                IF has_function_privilege(r.oid, '{GUARD_FUNCTION}()', 'EXECUTE') THEN
                    problems := problems || 'has EXECUTE on {GUARD_FUNCTION}'::TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_proc p, unnest(p.proconfig) AS c(setting)
                               WHERE p.oid = '{GUARD_FUNCTION}()'::regprocedure
                                 AND replace(c.setting, ' ', '') = 'search_path={SEARCH_PATH.replace(" ", "")}') THEN
                    problems := problems || 'function {GUARD_FUNCTION} does not pin search_path'::TEXT;
                END IF;
                IF (SELECT proowner FROM pg_proc WHERE oid = '{GUARD_FUNCTION}()'::regprocedure)
                   IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass) THEN
                    problems := problems || 'function {GUARD_FUNCTION} is not owned by the catalogue table owner'::TEXT;
                END IF;
            END IF;
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
    op.execute(_guard_function_sql())
    op.execute(
        f"CREATE TRIGGER {GUARD_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION {GUARD_FUNCTION}()"
    )

    op.execute(f"REVOKE ALL ON FUNCTION {GUARD_FUNCTION}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD_FUNCTION}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON SEQUENCE {SEQUENCE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'REVOKE ALL ON SEQUENCE {SEQUENCE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    insert_columns = ", ".join(f'"{c}"' for c in APP_INSERT_COLUMNS)
    update_columns = ", ".join(f'"{c}"' for c in APP_UPDATE_COLUMNS)
    op.execute(f'GRANT INSERT ({insert_columns}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({update_columns}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while the catalogue holds contracts (never deleted, REQ-053 AC-2); the lock comes first.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            IF to_regclass('{TABLE}') IS NOT NULL THEN
                EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
                EXECUTE 'SELECT EXISTS (SELECT 1 FROM {TABLE})' INTO has_rows;
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
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {GUARD_FUNCTION}()")
