"""Baseline: ledger_entries with the trusted database clock.

Spec basis: REQ-064 AC-2 ("Audit and timeline records are append-only."); ADR-023 Q225 clarification ("recorded at"
is stamped by the ledger from its own clock; a caller can never supply it); ADR-023 Q256 (60 seconds, both ways).

The guard is two things, both in the database:
1. A BEFORE INSERT trigger that overwrites recorded_at with the server clock and refuses (SQLSTATE OF001) an
   event_at outside recorded_at +/- 60 s, or a NULL event_at (fail closed).
2. Ownership and grants: this migration runs as an owner role, never as the application role, so the application
   role is not the owner and cannot ALTER/DISABLE/DROP the trigger; it gets only SELECT, INSERT on the table and
   USAGE on its sequence, so UPDATE, DELETE and TRUNCATE are refused.

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

# The application role that receives SELECT, INSERT only. Overridable for a differently named role on another host.
APP_ROLE = os.environ.get("OFO_APP_DB_ROLE", "ofo_app")

TRIGGER_NAME = "ledger_entries_trusted_clock"
FUNCTION_NAME = "ledger_entries_trusted_clock"

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _app_role() -> str:
    if not _IDENT.match(APP_ROLE):
        raise ValueError(f"OFO_APP_DB_ROLE must be a plain lower-case identifier, got {APP_ROLE!r}")
    return APP_ROLE


def upgrade() -> None:
    role = _app_role()

    # Fail closed: refuse to build the guard as the application role (it would own the table and could disable the
    # trigger), or for an application role that is a superuser (it bypasses every grant).
    op.execute(
        f"""
        DO $guard$
        BEGIN
            IF current_user = '{role}' THEN
                RAISE EXCEPTION 'run migrations as the owner role, not as the application role {role}';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                RAISE EXCEPTION 'application role {role} does not exist; create it first (ADR-048)';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}' AND (rolsuper OR rolbypassrls)) THEN
                RAISE EXCEPTION 'application role {role} must not be a superuser (ADR-048)';
            END IF;
        END
        $guard$;
        """
    )

    op.execute(
        """
        CREATE TABLE ledger_entries (
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
        CREATE FUNCTION {FUNCTION_NAME}() RETURNS trigger
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
        BEFORE INSERT ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION {FUNCTION_NAME}()
        """
    )

    op.execute("REVOKE ALL ON TABLE ledger_entries FROM PUBLIC")
    op.execute("REVOKE ALL ON SEQUENCE ledger_entries_id_seq FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION_NAME}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE ledger_entries FROM "{role}"')
    op.execute(f'GRANT SELECT, INSERT ON TABLE ledger_entries TO "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE ledger_entries_id_seq TO "{role}"')


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ledger_entries")
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}()")
