"""Audit store: the hash-chained audit log in PostgreSQL, with a separate head anchor.

Spec basis: REQ-064 AC-2 ("Audit and timeline records are append-only."); REQ-063 AC-5 (per-event-type field
ALLOWLIST, "anything else is dropped before storage"); ADR-023 Q225/Q256 (recorded_at stamped by the database clock;
the event's own time within +/- 60 s of it); ADR-048 (application role, schema-qualified tables, column-level INSERT,
no TEMPORARY); finding privilege-guard-as-denylist (every new append-only table joins the privilege allowlist).

Objects:
- public.audit_events: one row per event; seq is gap-free (1, 2, 3, ...) and must equal the anchor's count + 1;
  previous_hash must equal the anchor's last hash. payload is the canonical tagged JSON ($decimal / $datetime);
  canonical is the exact text the hash is the SHA-256 of (ofo.audit.models canonical JSON of event_type, actor,
  timestamp, correlation_id, payload, previous_hash).
- public.audit_anchor: a single row (event_count, last_hash), separate from the events (ofo.audit.log HeadAnchor).
  The application role holds SELECT only; the anchor moves only through the SECURITY DEFINER trigger function
  public.audit_events_advance_anchor, which sets it to the row just inserted.
- BEFORE INSERT trigger public.audit_events_link_and_clock (SECURITY DEFINER), for every inserter, in this order:
  1. stamps recorded_at with clock_timestamp() and applies the Q256 window (OF001) through
     public.ofo_assert_within_clock_window (the 60 s constant is imported from 0001, not copied);
  2. refuses an event type with no allowlist entry, a payload key not declared for its type (top level and inside
     declared nested objects), a declared scalar field holding an object other than a one-key $decimal/$datetime
     tag, or a non-integer JSON number (OF004). The key lists come from public.ofo_audit_payload_allowlist(),
     generated from ofo_app.audit_allowlist.allowlist_spec() (single source; a head test asserts they are equal);
  3. refuses unless hash = sha256(canonical) and canonical, parsed, has exactly the six keys and equals the row's
     event_type, actor, timestamp, correlation_id, payload and previous_hash (OF005);
  4. locks the anchor row (FOR UPDATE) and refuses a row that does not extend it (OF003). A multi-row INSERT is
     refused at its second row: AFTER ROW triggers run at the end of the statement, so the anchor has not moved.
- What the database cannot check: that canonical is in canonical FORM (sorted keys, no spaces, ASCII escapes). A
  self-consistent text with spaces and its true SHA-256 is stored; ofo_app.audit_store.load_log then refuses the
  whole log naming that row's seq (it rebuilds the canonical text in Python and compares it byte for byte).
- The application role gets SELECT on both tables and INSERT on exactly (seq, event_type, actor, "timestamp",
  correlation_id, payload, previous_hash, hash, canonical) - not recorded_at, nothing on the anchor.
- public.ofo_assert_app_role_allowlist is replaced (built on the previous migration's text; see
  extended_allowlist_sql) so its 'post' phase also asserts the audit store's privileges, triggers and functions; it
  runs at the start ('pre') and end ('post') of upgrade.

Recovery, if load_log ever names a seq: stop appending (load_log already refuses to hand out the log). Do not edit,
delete or re-hash rows - re-chaining forward would erase the tamper evidence. As the owner, read row seq N (its
columns, canonical and hash) and the anchor, and compare them with the last backup in which load_log passed. Restore
the database (or, for an owner-side corruption of row N only, row N's original values) from that backup, run load_log
again until it passes, and record the incident with the row, the cause and the backup used.

Revision ID: 0002_audit_store
Revises: 0001_baseline
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from alembic import op

from ofo_app.audit_allowlist import allowlist_spec

revision = "0002_audit_store"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _load_previous():
    """Import 0001 by path (the versions folder is not a package) so its constants are shared, never copied."""
    path = Path(__file__).with_name("0001_baseline_ledger_clock.py")
    spec = importlib.util.spec_from_file_location("ofo_migration_0001_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the baseline migration from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE = _load_previous()

#: The payload allowlist, generated from ofo_app.audit_allowlist (single source).
PAYLOAD_ALLOWLIST = allowlist_spec()
DECLARED_EVENT_TYPES = tuple(sorted(PAYLOAD_ALLOWLIST))

AUDIT_LINK_SQLSTATE = "OF003"  # a row that does not extend the anchored chain
AUDIT_PAYLOAD_SQLSTATE = "OF004"  # payload outside the event type's allowlist
AUDIT_HASH_SQLSTATE = "OF005"  # hash is not sha256(canonical), or canonical does not match the row

EVENTS = "public.audit_events"
ANCHOR = "public.audit_anchor"
CLOCK_FUNCTION = "public.ofo_assert_within_clock_window"
LINK_FUNCTION = "public.audit_events_link_and_clock"
ANCHOR_FUNCTION = "public.audit_events_advance_anchor"
ALLOWED_FUNCTION = "public.ofo_audit_payload_allowlist"
SCALAR_FUNCTION = "public.ofo_audit_value_is_scalar"
CONFORMS_FUNCTION = "public.ofo_audit_payload_conforms"
LINK_TRIGGER = "audit_events_link_and_clock"
ANCHOR_TRIGGER = "audit_events_advance_anchor"
GENESIS_HASH = "0" * 64  # ofo.audit.models.GENESIS_HASH; asserted equal in tests_app/test_audit_store.py
SEARCH_PATH = "pg_catalog, pg_temp"

#: Every function this migration creates, by signature; the app role may EXECUTE none of them.
FUNCTIONS = (
    f"{CLOCK_FUNCTION}(timestamptz, timestamptz)",
    f"{ALLOWED_FUNCTION}()",
    f"{SCALAR_FUNCTION}(jsonb)",
    f"{CONFORMS_FUNCTION}(jsonb, jsonb)",
    f"{LINK_FUNCTION}()",
    f"{ANCHOR_FUNCTION}()",
)
#: trigger -> the SECURITY DEFINER function it must call.
TRIGGERS = ((LINK_TRIGGER, f"{LINK_FUNCTION}()"), (ANCHOR_TRIGGER, f"{ANCHOR_FUNCTION}()"))

APP_INSERT_COLUMNS = (
    "seq", "event_type", "actor", "timestamp", "correlation_id", "payload", "previous_hash", "hash", "canonical",
)
CANONICAL_KEYS = ("actor", "correlation_id", "event_type", "payload", "previous_hash", "timestamp")

#: The marker each migration's allowlist block starts with; a head test requires all of them in the live function.
ALLOWLIST_BLOCK_MARKER = "-- 7. audit store"


def _privilege_checks(table: str, label: str, allowed: set[str]) -> str:
    lines = []
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        if privilege in allowed:
            lines.append(
                f"""            IF NOT has_table_privilege(r.oid, '{table}', '{privilege}') THEN
                problems := problems || 'lacks {privilege} on {label}'::TEXT;
            END IF;"""
            )
        else:
            word = "table-wide INSERT" if privilege == "INSERT" else privilege
            lines.append(
                f"""            IF has_table_privilege(r.oid, '{table}', '{privilege}') THEN
                problems := problems || 'has {word} on {label}'::TEXT;
            END IF;"""
            )
    # MAINTAIN exists from PostgreSQL 17; the branch is only planned there.
    lines.append(
        f"""            IF current_setting('server_version_num')::int >= 170000 THEN
                IF has_table_privilege(r.oid, '{table}', 'MAINTAIN') THEN
                    problems := problems || 'has MAINTAIN on {label}'::TEXT;
                END IF;
            END IF;"""
    )
    return "\n".join(lines)


def _function_checks() -> str:
    lines = []
    for fn in FUNCTIONS:
        name = fn.split("(")[0]
        lines.append(
            f"""            IF to_regprocedure('{fn}') IS NULL THEN
                problems := problems || 'function {fn} is missing'::TEXT;
            ELSE
                IF has_function_privilege(r.oid, '{fn}', 'EXECUTE') THEN
                    problems := problems || 'has EXECUTE on {name}'::TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_proc p, unnest(p.proconfig) AS c(setting)
                               WHERE p.oid = '{fn}'::regprocedure
                                 AND replace(c.setting, ' ', '') = 'search_path={SEARCH_PATH.replace(" ", "")}') THEN
                    problems := problems || 'function {name} does not pin search_path'::TEXT;
                END IF;
                IF (SELECT proowner FROM pg_proc WHERE oid = '{fn}'::regprocedure)
                   IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{EVENTS}'::regclass) THEN
                    problems := problems || 'function {name} is not owned by the audit table owner'::TEXT;
                END IF;
            END IF;"""
        )
    for trigger, fn in TRIGGERS:
        name = fn.split("(")[0]
        lines.append(
            f"""            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                           WHERE tgrelid = '{EVENTS}'::regclass AND tgname = '{trigger}' AND tgenabled = 'O') THEN
                problems := problems || 'trigger {trigger} is missing or not enabled'::TEXT;
            ELSIF (SELECT tgfoid FROM pg_trigger WHERE tgrelid = '{EVENTS}'::regclass AND tgname = '{trigger}')
                  IS DISTINCT FROM to_regprocedure('{fn}') THEN
                problems := problems || 'trigger {trigger} does not call {name}'::TEXT;
            ELSIF NOT (SELECT prosecdef FROM pg_proc WHERE oid = to_regprocedure('{fn}')) THEN
                problems := problems || 'function {name} is not SECURITY DEFINER'::TEXT;
            END IF;"""
        )
    return "\n".join(lines)


def _audit_allowlist_block() -> str:
    """The block added to the allowlist. It runs inside public.ofo_assert_app_role_allowlist, where `r` is the
    role's pg_roles row, `problems` the refusal list and `col` a TEXT loop variable."""
    columns = ", ".join(f"'{c}'" for c in APP_INSERT_COLUMNS)
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-052): SELECT + column INSERT on the events, SELECT only on the anchor, no EXECUTE
    --    on the store's functions (each pins search_path and is owned by the table owner), both triggers present,
    --    enabled and calling their SECURITY DEFINER function
    IF phase = 'post' THEN
        IF to_regclass('{EVENTS}') IS NULL OR to_regclass('{ANCHOR}') IS NULL THEN
            problems := problems || 'audit table {EVENTS} or {ANCHOR} is missing'::TEXT;
        ELSE
{_privilege_checks(EVENTS, "audit_events", {"SELECT"})}
            IF has_any_column_privilege(r.oid, '{EVENTS}', 'UPDATE') THEN
                problems := problems || 'has column UPDATE on audit_events'::TEXT;
            END IF;
            IF has_column_privilege(r.oid, '{EVENTS}', 'recorded_at', 'INSERT') THEN
                problems := problems || 'has INSERT on audit_events column recorded_at'::TEXT;
            END IF;
            FOREACH col IN ARRAY ARRAY[{columns}] LOOP
                IF NOT has_column_privilege(r.oid, '{EVENTS}', col, 'INSERT') THEN
                    problems := problems || ('lacks INSERT on audit_events column ' || col);
                END IF;
            END LOOP;
{_privilege_checks(ANCHOR, "audit_anchor", {"SELECT"})}
            IF has_any_column_privilege(r.oid, '{ANCHOR}', 'INSERT') THEN
                problems := problems || 'has INSERT on audit_anchor'::TEXT;
            END IF;
            IF has_any_column_privilege(r.oid, '{ANCHOR}', 'UPDATE') THEN
                problems := problems || 'has UPDATE on audit_anchor'::TEXT;
            END IF;
{_function_checks()}
        END IF;
    END IF;
"""


#: Each migration's block goes just before the final refusal, which every version of the function keeps once.
_INSERT_BEFORE = "    IF cardinality(problems) > 0 THEN\n"


def extend_allowlist(previous_sql: str) -> str:
    """CREATE OR REPLACE text: ``previous_sql`` (the previous migration's allowlist function) plus this block.

    Fails closed (RuntimeError) if the previous text does not have exactly one function header and one insertion
    point, or already holds this block - the replacement would otherwise silently drop or duplicate checks.
    """
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous_sql:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the audit store checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _audit_allowlist_block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    """The previous migration's allowlist text: its extended_allowlist_sql() if it has one, else its base SQL."""
    previous = getattr(_BASE, "extended_allowlist_sql", None)
    return previous() if previous is not None else _BASE.ALLOWLIST_SQL


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    skew = _BASE.Q256_CLOCK_SKEW_SECONDS
    clock_sqlstate = _BASE.LEDGER_CLOCK_SQLSTATE

    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    types = ", ".join(_sql_literal(t) for t in DECLARED_EVENT_TYPES)
    op.execute(
        f"""
        CREATE TABLE {EVENTS} (
            seq            BIGINT      PRIMARY KEY CHECK (seq >= 1),
            event_type     TEXT        NOT NULL CHECK (event_type IN ({types})),
            actor          TEXT        NOT NULL CHECK (actor <> ''),
            "timestamp"    TIMESTAMPTZ NOT NULL,
            correlation_id TEXT        NOT NULL CHECK (correlation_id <> ''),
            payload        JSONB       NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            previous_hash  TEXT        NOT NULL CHECK (previous_hash ~ '^[0-9a-f]{{64}}$'),
            hash           TEXT        NOT NULL UNIQUE CHECK (hash ~ '^[0-9a-f]{{64}}$'),
            canonical      TEXT        NOT NULL,
            recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {ANCHOR} (
            id          SMALLINT PRIMARY KEY CHECK (id = 1),
            event_count BIGINT   NOT NULL CHECK (event_count >= 0),
            last_hash   TEXT     NOT NULL CHECK (last_hash ~ '^[0-9a-f]{{64}}$')
        )
        """
    )
    op.execute(f"INSERT INTO {ANCHOR} (id, event_count, last_hash) VALUES (1, 0, '{GENESIS_HASH}')")

    # The Q256 rule, shared: the constant comes from 0001 (imported above), never typed again.
    op.execute(
        f"""
        CREATE FUNCTION {CLOCK_FUNCTION}(event_at TIMESTAMPTZ, recorded_at TIMESTAMPTZ) RETURNS void
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF event_at IS NULL OR recorded_at IS NULL
               OR event_at < recorded_at - make_interval(secs => {skew})
               OR event_at > recorded_at + make_interval(secs => {skew}) THEN
                RAISE EXCEPTION 'clock: event time % is outside recorded_at % +/- % seconds (ADR-023 Q256)',
                    event_at, recorded_at, {skew}
                    USING ERRCODE = '{clock_sqlstate}';
            END IF;
        END
        $fn$
        """
    )

    # The payload allowlist, generated from ofo_app.audit_allowlist.allowlist_spec().
    allowed_json = json.dumps(PAYLOAD_ALLOWLIST, sort_keys=True, separators=(",", ":"))
    op.execute(
        f"""
        CREATE FUNCTION {ALLOWED_FUNCTION}() RETURNS jsonb
        LANGUAGE sql IMMUTABLE
        SET search_path = {SEARCH_PATH}
        AS $fn$ SELECT {_sql_literal(allowed_json)}::jsonb $fn$
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {SCALAR_FUNCTION}(v JSONB) RETURNS boolean
        LANGUAGE plpgsql IMMUTABLE
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            tag  TEXT;
            item JSONB;
        BEGIN
            IF jsonb_typeof(v) = 'object' THEN
                -- only a one-key $decimal / $datetime tag holding a string
                IF (SELECT count(*) FROM jsonb_object_keys(v)) <> 1 THEN
                    RETURN FALSE;
                END IF;
                SELECT k INTO tag FROM jsonb_object_keys(v) AS t(k);
                RETURN tag IN ('$decimal', '$datetime') AND jsonb_typeof(v -> tag) = 'string';
            ELSIF jsonb_typeof(v) = 'array' THEN
                FOR item IN SELECT value FROM jsonb_array_elements(v) LOOP
                    IF NOT {SCALAR_FUNCTION}(item) THEN
                        RETURN FALSE;
                    END IF;
                END LOOP;
                RETURN TRUE;
            ELSIF jsonb_typeof(v) = 'number' THEN
                RETURN v::text ~ '^-?[0-9]+$';  -- money is a tagged Decimal; a float never round-trips
            END IF;
            RETURN TRUE;  -- string, boolean, null
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {CONFORMS_FUNCTION}(payload JSONB, allowed JSONB) RETURNS boolean
        LANGUAGE plpgsql IMMUTABLE
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            k TEXT;
            v JSONB;
        BEGIN
            IF payload IS NULL OR allowed IS NULL
               OR jsonb_typeof(payload) <> 'object' OR jsonb_typeof(allowed) <> 'object' THEN
                RETURN FALSE;
            END IF;
            FOR k, v IN SELECT key, value FROM jsonb_each(payload) LOOP
                IF NOT jsonb_exists(allowed, k) THEN
                    RETURN FALSE;
                END IF;
                IF jsonb_typeof(allowed -> k) = 'object' THEN
                    IF jsonb_typeof(v) <> 'null' AND NOT {CONFORMS_FUNCTION}(v, allowed -> k) THEN
                        RETURN FALSE;
                    END IF;
                ELSIF NOT {SCALAR_FUNCTION}(v) THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            RETURN TRUE;
        END
        $fn$
        """
    )

    canonical_keys = ", ".join(f"'{k}'" for k in CANONICAL_KEYS)
    op.execute(
        f"""
        CREATE FUNCTION {LINK_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            a       {ANCHOR}%ROWTYPE;
            allowed JSONB;
            c       JSONB;
            ok      BOOLEAN;
        BEGIN
            -- 1. trusted clock (ADR-023 Q225/Q256)
            NEW.recorded_at := clock_timestamp();
            PERFORM {CLOCK_FUNCTION}(NEW."timestamp", NEW.recorded_at);

            -- 2. payload allowlist (REQ-063 AC-5)
            allowed := {ALLOWED_FUNCTION}();
            IF NEW.event_type IS NULL OR NOT jsonb_exists(allowed, NEW.event_type) THEN
                RAISE EXCEPTION 'audit store: event type % has no payload allowlist (REQ-063 AC-5)', NEW.event_type
                    USING ERRCODE = '{AUDIT_PAYLOAD_SQLSTATE}';
            END IF;
            IF NOT {CONFORMS_FUNCTION}(NEW.payload, allowed -> NEW.event_type) THEN
                RAISE EXCEPTION 'audit store: payload for % holds a field or value outside its allowlist',
                    NEW.event_type USING ERRCODE = '{AUDIT_PAYLOAD_SQLSTATE}';
            END IF;

            -- 3. hash = sha256(canonical), and canonical describes this row
            IF NEW.canonical IS NULL OR NEW.hash IS NULL
               OR encode(sha256(convert_to(NEW.canonical, 'UTF8')), 'hex') <> NEW.hash THEN
                RAISE EXCEPTION 'audit store: hash is not the SHA-256 of the canonical text'
                    USING ERRCODE = '{AUDIT_HASH_SQLSTATE}';
            END IF;
            BEGIN
                c := NEW.canonical::jsonb;
                ok := jsonb_typeof(c) = 'object'
                    AND (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(c) AS t(k)) = ARRAY[{canonical_keys}]
                    AND jsonb_typeof(c -> 'event_type') = 'string' AND c ->> 'event_type' = NEW.event_type
                    AND jsonb_typeof(c -> 'actor') = 'string' AND c ->> 'actor' = NEW.actor
                    AND jsonb_typeof(c -> 'correlation_id') = 'string' AND c ->> 'correlation_id' = NEW.correlation_id
                    AND jsonb_typeof(c -> 'previous_hash') = 'string' AND c ->> 'previous_hash' = NEW.previous_hash
                    AND jsonb_typeof(c -> 'timestamp') = 'string'
                    AND (c ->> 'timestamp')::timestamptz = NEW."timestamp"
                    AND c -> 'payload' = NEW.payload;
            EXCEPTION WHEN others THEN
                ok := FALSE;
            END;
            IF ok IS NOT TRUE THEN
                RAISE EXCEPTION 'audit store: canonical text does not match the row''s columns'
                    USING ERRCODE = '{AUDIT_HASH_SQLSTATE}';
            END IF;

            -- 4. the row extends the anchored chain
            SELECT * INTO a FROM {ANCHOR} WHERE id = 1 FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'audit store: anchor row is missing' USING ERRCODE = '{AUDIT_LINK_SQLSTATE}';
            END IF;
            IF NEW.seq IS DISTINCT FROM a.event_count + 1 OR NEW.previous_hash IS DISTINCT FROM a.last_hash THEN
                RAISE EXCEPTION 'audit store: row seq % / previous_hash % does not extend the anchor (count %, last %)',
                    NEW.seq, NEW.previous_hash, a.event_count, a.last_hash
                    USING ERRCODE = '{AUDIT_LINK_SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {ANCHOR_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            UPDATE {ANCHOR} SET event_count = NEW.seq, last_hash = NEW.hash
             WHERE id = 1 AND event_count = NEW.seq - 1 AND last_hash = NEW.previous_hash;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'audit store: anchor moved under row seq %', NEW.seq
                    USING ERRCODE = '{AUDIT_LINK_SQLSTATE}';
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        f"CREATE TRIGGER {LINK_TRIGGER} BEFORE INSERT ON {EVENTS} FOR EACH ROW EXECUTE FUNCTION {LINK_FUNCTION}()"
    )
    op.execute(
        f"CREATE TRIGGER {ANCHOR_TRIGGER} AFTER INSERT ON {EVENTS} FOR EACH ROW EXECUTE FUNCTION {ANCHOR_FUNCTION}()"
    )

    for fn in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {fn} FROM "{role}"')
    for table in (EVENTS, ANCHOR):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
    columns = ", ".join(f'"{c}"' for c in APP_INSERT_COLUMNS)
    op.execute(f'GRANT INSERT ({columns}) ON TABLE {EVENTS} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while the audit log holds events (append-only, REQ-064 AC-2); the lock comes first.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            IF to_regclass('{EVENTS}') IS NOT NULL THEN
                EXECUTE 'LOCK TABLE {EVENTS} IN ACCESS EXCLUSIVE MODE';
                EXECUTE 'SELECT EXISTS (SELECT 1 FROM {EVENTS})' INTO has_rows;
            END IF;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to drop {EVENTS}: it holds audit events (append-only, REQ-064 AC-2)';
            END IF;
        END
        $down$;
        """
    )
    previous = previous_allowlist_sql().replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    op.execute(previous)
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE IF EXISTS {EVENTS}")
    op.execute(f"DROP TABLE IF EXISTS {ANCHOR}")
    for fn in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
