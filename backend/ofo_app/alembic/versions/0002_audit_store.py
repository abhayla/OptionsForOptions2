"""Audit store: the hash-chained audit log in PostgreSQL, with a separate head anchor.

Spec basis: REQ-064 AC-2 ("Audit and timeline records are append-only."); REQ-063 AC-5 (per-event-type field
allowlist; the allowlist itself lives in ofo_app/audit_allowlist.py and is mirrored here as a CHECK on event_type);
ADR-023 Q225/Q256 (recorded_at stamped by the database clock; the event's own time within +/- 60 s of it); ADR-048
(application role, schema-qualified tables, column-level INSERT, no TEMPORARY); finding privilege-guard-as-denylist
(every new append-only table joins the privilege allowlist).

Objects:
- public.audit_events: one row per event; seq is gap-free (1, 2, 3, ...) and must equal the anchor's count + 1;
  previous_hash must equal the anchor's last hash. payload is the canonical tagged JSON ($decimal / $datetime) so the
  hash recomputes byte for byte in ofo.audit.
- public.audit_anchor: a single row (event_count, last_hash), separate from the events (ofo.audit.log HeadAnchor).
  The application role holds SELECT only; the anchor moves only through the SECURITY DEFINER trigger function
  public.audit_events_advance_anchor, owned by the owner role, which sets it to the row just inserted.
- public.audit_events_link_and_clock (BEFORE INSERT, SECURITY DEFINER): stamps recorded_at with clock_timestamp(),
  applies the Q256 window through public.ofo_assert_within_clock_window (the 60 s constant is imported from 0001, not
  copied), locks the anchor row (FOR UPDATE) and refuses (SQLSTATE OF003) a row that does not link to it.
- The application role gets SELECT on both tables and INSERT on exactly (seq, event_type, actor, "timestamp",
  correlation_id, payload, previous_hash, hash) - not recorded_at, nothing on the anchor.
- public.ofo_assert_app_role_allowlist is replaced so its 'post' phase also asserts the exact privileges on both
  tables and that the role cannot EXECUTE the new functions; it runs at the start ('pre') and end ('post') of upgrade.

Revision ID: 0002_audit_store
Revises: 0001_baseline
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0002_audit_store"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _load_baseline():
    """Import 0001 by path (the versions folder is not a package) so its constants are shared, never copied."""
    path = Path(__file__).with_name("0001_baseline_ledger_clock.py")
    spec = importlib.util.spec_from_file_location("ofo_migration_0001_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the baseline migration from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE = _load_baseline()

# The audit event types that have a declared payload field allowlist (ofo_app/audit_allowlist.py). The database
# refuses every other type as a second layer; tests_app/test_audit_store.py asserts the two lists are equal.
DECLARED_EVENT_TYPES = (
    "entitlement_changed",
    "trial_started",
    "trial_expired",
    "direct_customer_eligibility_granted",
    "direct_customer_eligibility_revoked",
    "referral_reward_granted",
    "subscription_started",
    "subscription_expired",
    "admin_change_recorded",
)

AUDIT_LINK_SQLSTATE = "OF003"  # a row that does not extend the anchored chain

EVENTS = "public.audit_events"
ANCHOR = "public.audit_anchor"
CLOCK_FUNCTION = "public.ofo_assert_within_clock_window"
LINK_FUNCTION = "public.audit_events_link_and_clock"
ANCHOR_FUNCTION = "public.audit_events_advance_anchor"
LINK_TRIGGER = "audit_events_link_and_clock"
ANCHOR_TRIGGER = "audit_events_advance_anchor"
GENESIS_HASH = "0" * 64  # ofo.audit.models.GENESIS_HASH; asserted equal in tests_app/test_audit_store.py

APP_INSERT_COLUMNS = (
    "seq", "event_type", "actor", "timestamp", "correlation_id", "payload", "previous_hash", "hash",
)

# The block added to the allowlist's 'post' phase. It runs inside public.ofo_assert_app_role_allowlist, where `r`
# is the role's pg_roles row, `problems` the refusal list and `col` a TEXT loop variable.
_AUDIT_ALLOWLIST_BLOCK = f"""
        -- 7. audit store (W-052): exactly SELECT + column INSERT on the events, SELECT only on the anchor,
        --    no EXECUTE on the store's functions, both triggers present and enabled
        IF to_regclass('{EVENTS}') IS NULL OR to_regclass('{ANCHOR}') IS NULL THEN
            problems := problems || 'audit table {EVENTS} or {ANCHOR} is missing'::TEXT;
        ELSE
            IF NOT has_table_privilege(r.oid, '{EVENTS}', 'SELECT') THEN
                problems := problems || 'lacks SELECT on audit_events'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{EVENTS}', 'INSERT') THEN
                problems := problems || 'has table-wide INSERT on audit_events'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{EVENTS}', 'UPDATE') THEN
                problems := problems || 'has UPDATE on audit_events'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{EVENTS}', 'DELETE') THEN
                problems := problems || 'has DELETE on audit_events'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{EVENTS}', 'TRUNCATE') THEN
                problems := problems || 'has TRUNCATE on audit_events'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{EVENTS}', 'REFERENCES') THEN
                problems := problems || 'has REFERENCES on audit_events'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{EVENTS}', 'TRIGGER') THEN
                problems := problems || 'has TRIGGER on audit_events'::TEXT;
            END IF;
            IF has_any_column_privilege(r.oid, '{EVENTS}', 'UPDATE') THEN
                problems := problems || 'has column UPDATE on audit_events'::TEXT;
            END IF;
            IF has_column_privilege(r.oid, '{EVENTS}', 'recorded_at', 'INSERT') THEN
                problems := problems || 'has INSERT on audit_events column recorded_at'::TEXT;
            END IF;
            FOREACH col IN ARRAY ARRAY[{", ".join(f"'{c}'" for c in APP_INSERT_COLUMNS)}] LOOP
                IF NOT has_column_privilege(r.oid, '{EVENTS}', col, 'INSERT') THEN
                    problems := problems || ('lacks INSERT on audit_events column ' || col);
                END IF;
            END LOOP;
            IF NOT has_table_privilege(r.oid, '{ANCHOR}', 'SELECT') THEN
                problems := problems || 'lacks SELECT on audit_anchor'::TEXT;
            END IF;
            IF has_any_column_privilege(r.oid, '{ANCHOR}', 'INSERT') THEN
                problems := problems || 'has INSERT on audit_anchor'::TEXT;
            END IF;
            IF has_any_column_privilege(r.oid, '{ANCHOR}', 'UPDATE') THEN
                problems := problems || 'has UPDATE on audit_anchor'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{ANCHOR}', 'DELETE') THEN
                problems := problems || 'has DELETE on audit_anchor'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{ANCHOR}', 'TRUNCATE') THEN
                problems := problems || 'has TRUNCATE on audit_anchor'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{ANCHOR}', 'REFERENCES') THEN
                problems := problems || 'has REFERENCES on audit_anchor'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{ANCHOR}', 'TRIGGER') THEN
                problems := problems || 'has TRIGGER on audit_anchor'::TEXT;
            END IF;
            IF has_function_privilege(r.oid, '{CLOCK_FUNCTION}(timestamptz, timestamptz)', 'EXECUTE') THEN
                problems := problems || 'has EXECUTE on {CLOCK_FUNCTION}'::TEXT;
            END IF;
            IF has_function_privilege(r.oid, '{LINK_FUNCTION}()', 'EXECUTE') THEN
                problems := problems || 'has EXECUTE on {LINK_FUNCTION}'::TEXT;
            END IF;
            IF has_function_privilege(r.oid, '{ANCHOR_FUNCTION}()', 'EXECUTE') THEN
                problems := problems || 'has EXECUTE on {ANCHOR_FUNCTION}'::TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                           WHERE tgrelid = '{EVENTS}'::regclass AND tgname = '{LINK_TRIGGER}' AND tgenabled = 'O') THEN
                problems := problems || 'trigger {LINK_TRIGGER} is missing or not enabled'::TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                           WHERE tgrelid = '{EVENTS}'::regclass AND tgname = '{ANCHOR_TRIGGER}' AND tgenabled = 'O') THEN
                problems := problems || 'trigger {ANCHOR_TRIGGER} is missing or not enabled'::TEXT;
            END IF;
        END IF;
"""

# The allowlist body's last check before the refusal; the audit block is inserted just before its END IF.
_ALLOWLIST_INSERT_AFTER = "                problems := problems || 'trigger {trigger} is missing or not enabled'::TEXT;\n            END IF;\n        END IF;\n".format(
    trigger=_BASE.TRIGGER_NAME
)


def extended_allowlist_sql() -> str:
    """0001's allowlist function, CREATE OR REPLACE, with the audit block in its 'post' phase. Fails closed if the
    0001 text no longer has exactly one insertion point (the replacement would otherwise silently drop the block)."""
    base = _BASE.ALLOWLIST_SQL
    if base.count("CREATE FUNCTION") != 1 or base.count(_ALLOWLIST_INSERT_AFTER) != 1:
        raise RuntimeError("0001 allowlist SQL changed shape: cannot add the audit store checks safely")
    sql = base.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_ALLOWLIST_INSERT_AFTER, _ALLOWLIST_INSERT_AFTER + _AUDIT_ALLOWLIST_BLOCK, 1)


def baseline_allowlist_sql() -> str:
    return _BASE.ALLOWLIST_SQL.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    skew = _BASE.Q256_CLOCK_SKEW_SECONDS
    clock_sqlstate = _BASE.LEDGER_CLOCK_SQLSTATE

    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    types = ", ".join(f"'{t}'" for t in DECLARED_EVENT_TYPES)
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
        SET search_path = pg_catalog, pg_temp
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

    op.execute(
        f"""
        CREATE FUNCTION {LINK_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $fn$
        DECLARE
            a {ANCHOR}%ROWTYPE;
        BEGIN
            NEW.recorded_at := clock_timestamp();
            PERFORM {CLOCK_FUNCTION}(NEW."timestamp", NEW.recorded_at);
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
        SET search_path = pg_catalog, pg_temp
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

    for fn in (f"{CLOCK_FUNCTION}(TIMESTAMPTZ, TIMESTAMPTZ)", f"{LINK_FUNCTION}()", f"{ANCHOR_FUNCTION}()"):
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
    op.execute(baseline_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE IF EXISTS {EVENTS}")
    op.execute(f"DROP TABLE IF EXISTS {ANCHOR}")
    op.execute(f"DROP FUNCTION IF EXISTS {LINK_FUNCTION}()")
    op.execute(f"DROP FUNCTION IF EXISTS {ANCHOR_FUNCTION}()")
    op.execute(f"DROP FUNCTION IF EXISTS {CLOCK_FUNCTION}(TIMESTAMPTZ, TIMESTAMPTZ)")
