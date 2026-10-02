"""Baseline: ledger_entries with the trusted database clock.

Spec basis: REQ-064 AC-2 ("Audit and timeline records are append-only."); ADR-023 Q225 clarification ("recorded at"
is stamped by the ledger from its own clock; a caller can never supply it); ADR-023 Q256 (60 seconds, both ways);
ADR-048 (application role attributes and timeouts).

The guard is three things, all in the database:
1. A BEFORE INSERT trigger that overwrites recorded_at with the server clock and refuses (SQLSTATE OF001) an
   event_at outside recorded_at +/- 60 s, or a NULL event_at (fail closed).
2. Ownership and grants: this migration runs as an owner role. The application role gets SELECT on the table, INSERT
   only on (kind, event_at, recorded_at, payload) and USAGE on the id sequence - nothing else.
3. An ALLOWLIST assertion, public.ofo_assert_app_role_allowlist(role, phase) (SQLSTATE OF002 on refusal), run at the
   start of upgrade() (phase 'pre') and again after every grant (phase 'post'). It does not list forbidden paths; it
   requires the role's whole privilege picture to equal the allowed one: plain LOGIN attributes, member of no role,
   owner of nothing, no CREATE/TEMPORARY on the database, no CREATE on schema public, and exactly the table/sequence
   privileges above. Any other path to more privilege (database ownership, schema ownership, a role membership, a
   revoke that only warned) leaves a fact the assertion sees, so the migration fails instead of shipping a weak guard.

The stamp is the server clock at INSERT time (clock_timestamp()), not the transaction's start and not its commit
time: a row inserted at 10:00:00 in a transaction that commits at 10:00:20 carries 10:00:00.

Revision ID: 0001_baseline
Revises:
"""

from __future__ import annotations

import os
import re

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# ADR-023 Q256 (owner, 2026-10-02): "the clock-skew window is 60 seconds, both ways." The one place this lives.
Q256_CLOCK_SKEW_SECONDS = 60

# SQLSTATEs (class "OF" is project-defined, not a PostgreSQL class).
LEDGER_CLOCK_SQLSTATE = "OF001"  # event outside the window, or undated
ALLOWLIST_SQLSTATE = "OF002"  # application role's privileges differ from the allowlist

# ADR-048 timeouts for the application role.
APP_ROLE_STATEMENT_TIMEOUT = "30s"
APP_ROLE_IDLE_IN_TRANSACTION_TIMEOUT = "60s"

# The application role. Overridable for a differently named role on another host.
APP_ROLE = os.environ.get("OFO_APP_DB_ROLE", "ofo_app")

TABLE = "public.ledger_entries"
SEQUENCE = "public.ledger_entries_id_seq"
TRIGGER_NAME = "ledger_entries_trusted_clock"
FUNCTION = "public.ledger_entries_trusted_clock"
ALLOWLIST_FUNCTION = "public.ofo_assert_app_role_allowlist"

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

ALLOWLIST_SQL = f"""
CREATE FUNCTION {ALLOWLIST_FUNCTION}(app_role TEXT, phase TEXT) RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    r        pg_roles%ROWTYPE;
    problems TEXT[] := ARRAY[]::TEXT[];
    col      TEXT;
BEGIN
    IF phase NOT IN ('pre', 'post') THEN
        RAISE EXCEPTION 'allowlist: phase must be pre or post, got %', phase USING ERRCODE = '{ALLOWLIST_SQLSTATE}';
    END IF;
    SELECT * INTO r FROM pg_roles WHERE rolname = app_role;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'app role allowlist refused for %: role does not exist (ADR-048)', app_role
            USING ERRCODE = '{ALLOWLIST_SQLSTATE}';
    END IF;
    IF r.rolname = current_user THEN
        problems := problems || 'is the role running the migration'::TEXT;
    END IF;

    -- 1. attributes: a plain login role
    IF r.rolsuper       THEN problems := problems || 'is SUPERUSER'::TEXT; END IF;
    IF r.rolcreatedb    THEN problems := problems || 'has CREATEDB'::TEXT; END IF;
    IF r.rolcreaterole  THEN problems := problems || 'has CREATEROLE'::TEXT; END IF;
    IF r.rolreplication THEN problems := problems || 'has REPLICATION'::TEXT; END IF;
    IF r.rolbypassrls   THEN problems := problems || 'has BYPASSRLS'::TEXT; END IF;
    IF NOT r.rolcanlogin THEN problems := problems || 'cannot LOGIN'::TEXT; END IF;

    -- 2. membership: member of no role at all
    IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = r.oid) THEN
        problems := problems || 'is a member of another role'::TEXT;
    END IF;

    -- 3. ownership: owns nothing
    IF EXISTS (SELECT 1 FROM pg_database WHERE datname = current_database() AND datdba = r.oid) THEN
        problems := problems || 'owns the database'::TEXT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner = r.oid) THEN
        problems := problems || 'owns a schema'::TEXT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE relowner = r.oid) THEN
        problems := problems || 'owns a relation or sequence'::TEXT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proowner = r.oid) THEN
        problems := problems || 'owns a function'::TEXT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_type WHERE typowner = r.oid) THEN
        problems := problems || 'owns a type'::TEXT;
    END IF;

    IF phase = 'post' THEN
        -- 4. database privileges (catches a REVOKE ... FROM PUBLIC that only warned)
        IF has_database_privilege(r.oid, current_database(), 'CREATE') THEN
            problems := problems || 'has CREATE on the database'::TEXT;
        END IF;
        IF has_database_privilege(r.oid, current_database(), 'TEMPORARY') THEN
            problems := problems || 'has TEMPORARY on the database'::TEXT;
        END IF;
        -- 5. schema public
        IF has_schema_privilege(r.oid, 'public', 'CREATE') THEN
            problems := problems || 'has CREATE on schema public'::TEXT;
        END IF;
        -- 6. exactly SELECT + column INSERT on the ledger; USAGE only on its sequence; the trigger is enabled
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'ledger table {TABLE} is missing'::TEXT;
        ELSE
            IF NOT has_table_privilege(r.oid, '{TABLE}', 'SELECT') THEN
                problems := problems || 'lacks SELECT on the ledger'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{TABLE}', 'INSERT') THEN
                problems := problems || 'has table-wide INSERT on the ledger'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{TABLE}', 'UPDATE') THEN
                problems := problems || 'has UPDATE on the ledger'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{TABLE}', 'DELETE') THEN
                problems := problems || 'has DELETE on the ledger'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{TABLE}', 'TRUNCATE') THEN
                problems := problems || 'has TRUNCATE on the ledger'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{TABLE}', 'REFERENCES') THEN
                problems := problems || 'has REFERENCES on the ledger'::TEXT;
            END IF;
            IF has_table_privilege(r.oid, '{TABLE}', 'TRIGGER') THEN
                problems := problems || 'has TRIGGER on the ledger'::TEXT;
            END IF;
            IF has_any_column_privilege(r.oid, '{TABLE}', 'UPDATE') THEN
                problems := problems || 'has column UPDATE on the ledger'::TEXT;
            END IF;
            IF has_column_privilege(r.oid, '{TABLE}', 'id', 'INSERT') THEN
                problems := problems || 'has INSERT on ledger column id'::TEXT;
            END IF;
            FOREACH col IN ARRAY ARRAY['kind', 'event_at', 'recorded_at', 'payload'] LOOP
                IF NOT has_column_privilege(r.oid, '{TABLE}', col, 'INSERT') THEN
                    problems := problems || ('lacks INSERT on ledger column ' || col);
                END IF;
            END LOOP;
            IF NOT has_sequence_privilege(r.oid, '{SEQUENCE}', 'USAGE') THEN
                problems := problems || 'lacks USAGE on the id sequence'::TEXT;
            END IF;
            IF has_sequence_privilege(r.oid, '{SEQUENCE}', 'UPDATE') THEN
                problems := problems || 'has UPDATE on the id sequence'::TEXT;
            END IF;
            IF has_sequence_privilege(r.oid, '{SEQUENCE}', 'SELECT') THEN
                problems := problems || 'has SELECT on the id sequence'::TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                           WHERE tgrelid = '{TABLE}'::regclass AND tgname = '{TRIGGER_NAME}' AND tgenabled = 'O') THEN
                problems := problems || 'trigger {TRIGGER_NAME} is missing or not enabled'::TEXT;
            END IF;
        END IF;
    END IF;

    IF cardinality(problems) > 0 THEN
        RAISE EXCEPTION 'app role allowlist refused for % (%): %', app_role, phase, array_to_string(problems, '; ')
            USING ERRCODE = '{ALLOWLIST_SQLSTATE}';
    END IF;
END
$fn$
"""


def _app_role() -> str:
    if not _IDENT.match(APP_ROLE):
        raise ValueError(f"OFO_APP_DB_ROLE must be a plain lower-case identifier, got {APP_ROLE!r}")
    return APP_ROLE


def upgrade() -> None:
    role = _app_role()

    op.execute(ALLOWLIST_SQL)
    op.execute(f"REVOKE ALL ON FUNCTION {ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    # Phase 'pre': attributes, membership, ownership - before anything is built on the role.
    op.execute(f"SELECT {ALLOWLIST_FUNCTION}('{role}', 'pre')")

    # No temp table may shadow the ledger and nothing new may be created in public. These revokes can only warn
    # when run by a non-owner; phase 'post' below checks the effective privileges, so a warning fails the migration.
    op.execute(
        """
        DO $tmp$
        BEGIN
            EXECUTE format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
        END
        $tmp$;
        """
    )
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")

    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            id          BIGSERIAL PRIMARY KEY,
            kind        TEXT        NOT NULL,
            event_at    TIMESTAMPTZ NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload     JSONB       NOT NULL
        )
        """
    )

    # clock_timestamp() is the server's wall clock at the moment of the insert. now() would be the start of the
    # caller's transaction, which a caller could hold open to stamp an older time.
    op.execute(
        f"""
        CREATE FUNCTION {FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, pg_temp
        AS $fn$
        BEGIN
            NEW.recorded_at := clock_timestamp();
            IF NEW.event_at IS NULL
               OR NEW.event_at < NEW.recorded_at - make_interval(secs => {Q256_CLOCK_SKEW_SECONDS})
               OR NEW.event_at > NEW.recorded_at + make_interval(secs => {Q256_CLOCK_SKEW_SECONDS}) THEN
                RAISE EXCEPTION 'ledger clock: event_at % is outside recorded_at % +/- % seconds (ADR-023 Q256)',
                    NEW.event_at, NEW.recorded_at, {Q256_CLOCK_SKEW_SECONDS}
                    USING ERRCODE = '{LEDGER_CLOCK_SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {TRIGGER_NAME}
        BEFORE INSERT ON {TABLE}
        FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()
        """
    )

    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON SEQUENCE {SEQUENCE} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'REVOKE ALL ON SEQUENCE {SEQUENCE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    # Column-level INSERT: no id column, so the caller cannot pick (or collide) ids; recorded_at is listed only so a
    # caller-supplied value is accepted and then overwritten by the trigger.
    op.execute(f'GRANT INSERT (kind, event_at, recorded_at, payload) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')

    # ADR-048 timeouts, set by the owner/admin so they hold on every host, not only in CI.
    op.execute(f"ALTER ROLE \"{role}\" SET statement_timeout = '{APP_ROLE_STATEMENT_TIMEOUT}'")
    op.execute(f"ALTER ROLE \"{role}\" SET idle_in_transaction_session_timeout = '{APP_ROLE_IDLE_IN_TRANSACTION_TIMEOUT}'")

    # Phase 'post': the whole privilege picture equals the allowlist, or the migration fails.
    op.execute(f"SELECT {ALLOWLIST_FUNCTION}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while the ledger holds rows: an append-only record is never dropped by a schema rollback. The lock is
    # taken first, so no insert can land between the check and the drop.
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
                RAISE EXCEPTION 'refusing to drop {TABLE}: it holds ledger rows (append-only, REQ-064 AC-2)';
            END IF;
        END
        $down$;
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")
    op.execute(f"DROP FUNCTION IF EXISTS {ALLOWLIST_FUNCTION}(TEXT, TEXT)")
