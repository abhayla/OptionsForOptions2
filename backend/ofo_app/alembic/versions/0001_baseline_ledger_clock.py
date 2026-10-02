"""Baseline: ledger_entries with the trusted database clock.

Spec basis: REQ-064 AC-2 ("Audit and timeline records are append-only."); ADR-023 Q225 clarification ("recorded at"
is stamped by the ledger from its own clock; a caller can never supply it); ADR-023 Q256 (60 seconds, both ways).

The guard is two things, both in the database:
1. A BEFORE INSERT trigger that overwrites recorded_at with the server clock and refuses (SQLSTATE OF001) an
   event_at outside recorded_at +/- 60 s, or a NULL event_at (fail closed).
2. Ownership and grants: this migration runs as an owner role, never as the application role, so the application
   role is not the owner and cannot ALTER/DISABLE/DROP the trigger. It gets SELECT on the table, INSERT only on the
   columns (kind, event_at, recorded_at, payload) so it cannot choose an id, and USAGE on the id sequence; UPDATE,
   DELETE and TRUNCATE are refused. TEMPORARY on the database is revoked from PUBLIC so the role cannot create a
   temp table that shadows public.ledger_entries, and the table is always named schema-qualified.

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

# SQLSTATE the trigger raises for an event outside the window or without a date. Class "OF" is project-defined
# (not a PostgreSQL class), so a caller can tell this refusal apart from any built-in error.
LEDGER_CLOCK_SQLSTATE = "OF001"

# The application role. Overridable for a differently named role on another host.
APP_ROLE = os.environ.get("OFO_APP_DB_ROLE", "ofo_app")

TABLE = "public.ledger_entries"
SEQUENCE = "public.ledger_entries_id_seq"
TRIGGER_NAME = "ledger_entries_trusted_clock"
FUNCTION = "public.ledger_entries_trusted_clock"

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _app_role() -> str:
    if not _IDENT.match(APP_ROLE):
        raise ValueError(f"OFO_APP_DB_ROLE must be a plain lower-case identifier, got {APP_ROLE!r}")
    return APP_ROLE


def upgrade() -> None:
    role = _app_role()

    # Fail closed: refuse to build the guard for an application role that could get around it - the role itself
    # running the migration (it would own the table), a superuser/BYPASSRLS role, a role that can create roles or
    # databases, a role that inherits the owner's privileges, or a member of the predefined roles that write or
    # maintain every table (pg_write_all_data PG14+, pg_maintain PG17+; checked only where the role exists).
    op.execute(
        f"""
        DO $guard$
        DECLARE
            predefined TEXT;
        BEGIN
            IF current_user = '{role}' THEN
                RAISE EXCEPTION 'run migrations as the owner role, not as the application role {role}';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                RAISE EXCEPTION 'application role {role} does not exist; create it first (ADR-048)';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}'
                       AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb)) THEN
                RAISE EXCEPTION 'application role {role} must be NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB';
            END IF;
            IF pg_has_role('{role}', current_user, 'MEMBER') THEN
                RAISE EXCEPTION 'application role {role} is a member of the owner role %', current_user;
            END IF;
            FOREACH predefined IN ARRAY ARRAY['pg_write_all_data', 'pg_maintain'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = predefined)
                   AND pg_has_role('{role}', predefined, 'MEMBER') THEN
                    RAISE EXCEPTION 'application role {role} must not be a member of %', predefined;
                END IF;
            END LOOP;
        END
        $guard$;
        """
    )

    # No temp table may shadow the ledger: TEMPORARY is revoked from PUBLIC and never granted to the app role.
    op.execute(
        """
        DO $tmp$
        BEGIN
            EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
        END
        $tmp$;
        """
    )

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
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    # Column-level INSERT: no id column, so the caller cannot pick (or collide) ids; recorded_at is listed only so a
    # caller-supplied value is accepted and then overwritten by the trigger.
    op.execute(f'GRANT INSERT (kind, event_at, recorded_at, payload) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')


def downgrade() -> None:
    # Refuses while the ledger holds rows: an append-only record is never dropped by a schema rollback.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            IF to_regclass('{TABLE}') IS NOT NULL THEN
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
