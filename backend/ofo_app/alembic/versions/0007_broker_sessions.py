"""Broker sessions: the Kite access token stored only as ciphertext, destroyed when the session ends (W-058).

Spec basis: REQ-015 AC-7 ("Zerodha authorization is treated as temporary (about one day; re-authentication daily);
its expiry never deletes identity, strategies or entitlements."); REQ-015 AC-9 ("Broker tokens are stored only through
the official integration's secure token mechanism."); REQ-063 AC-5 ("broker credentials are never stored beyond the
official secure-token mechanism."); core-invariants section 4 (the access token is encrypted at rest and never logged).

Copy from: none - algochanakya stored the access token in plaintext (legacy-reuse row 9, REFERENCE: the flow only).

Changes (owner-run, one transaction):
- public.broker_sessions: id, user_ref, broker (CHECK zerodha), token_ciphertext (BYTEA, NULL once ended), key_id,
  started_at (the database clock, stamped by the guard), expected_expiry (the next 06:00 IST after started_at, stamped
  by the guard: ofo.broker.session.expected_expiry; a test asserts both agree), ended_at (stamped by the guard),
  end_reason CHECK in ('expired', 'disconnected', 'replaced'). CHECKs: ended = (end_reason set), and an ended row
  holds no ciphertext. At most one active row per (user_ref, broker): partial unique index WHERE ended_at IS NULL.
- Guard (BEFORE INSERT OR UPDATE OR DELETE): refuses any delete; on insert stamps started_at / expected_expiry and
  leaves the ciphertext NULL (the app sets it once, after the id it is bound to exists, in the same transaction);
  refuses any change to an ended row, to the identity columns, a second ciphertext on an active row, dropping the
  ciphertext without ending, and an end that keeps the ciphertext; stamps ended_at with clock_timestamp().
- Grants: the application role gets SELECT, column INSERT on (user_ref, broker, key_id), column UPDATE on
  (ended_at, end_reason, token_ciphertext), USAGE on the id sequence. No DELETE, no TRUNCATE, no EXECUTE.
- public.ofo_assert_app_role_allowlist: 0005's text plus block 10 for this table (privileges, columns, sequence,
  the active-session index, the guard trigger and its pinned body). 0006_index_segments leaves the allowlist function
  unchanged, so 0005's text is still the previous one (renumbered from 0006 after main's 0006 merged).

Revision ID: 0007_broker_sessions
Revises: 0006_index_segments
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0007_broker_sessions"
down_revision = "0006_index_segments"
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


_M5 = _load("0005_contract_lifecycle.py", "ofo_migration_0005_for_0007")
_M4 = _M5._M4
_M3 = _M5._M3
_PREV = _M5._PREV  # 0002
_BASE = _M5._BASE  # 0001

SEARCH_PATH = _M5.SEARCH_PATH
BROKER_SESSION_SQLSTATE = "OF007"  # a delete, a change to an ended session, or a token kept past its end

TABLE = "public.broker_sessions"
SEQUENCE = "public.broker_sessions_id_seq"
GUARD_FUNCTION = "public.broker_sessions_guard"
GUARD_TRIGGER = "broker_sessions_guard"
ACTIVE_INDEX = "public.broker_sessions_one_active"
ACTIVE_PREDICATE = "ended_at IS NULL"

BROKER_CODES = ("zerodha",)
END_REASONS = ("expired", "disconnected", "replaced")
#: Kite's access tokens are expected to stop working at 06:00 IST (ofo.broker.session.KITE_EXPIRY_TIME_IST).
EXPIRY_TIMEZONE = "Asia/Kolkata"

IDENTITY_COLUMNS = ("id", "user_ref", "broker", "key_id", "started_at", "expected_expiry")
APP_INSERT_COLUMNS = ("user_ref", "broker", "key_id")
APP_UPDATE_COLUMNS = ("ended_at", "end_reason", "token_ciphertext")

ALLOWLIST_BLOCK_MARKER = "-- 10. broker sessions"
BEFORE_ROW_INSERT_UPDATE_DELETE = _M3.BEFORE_ROW_INSERT_UPDATE_DELETE  # 31


def _expected_expiry_sql(at: str) -> str:
    """The next 06:00 IST strictly after ``at`` (06:00 itself rolls to the next day), as TIMESTAMPTZ."""
    return (f"((date_trunc('day', ({at} AT TIME ZONE '{EXPIRY_TIMEZONE}') - interval '6 hours') "
            f"+ interval '30 hours') AT TIME ZONE '{EXPIRY_TIMEZONE}')")


def _guard_function_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in IDENTITY_COLUMNS)
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'broker sessions: session % is never deleted; ending it destroys the token (W-058)',
                    OLD.id USING ERRCODE = '{BROKER_SESSION_SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                NEW.started_at := clock_timestamp();
                NEW.expected_expiry := {_expected_expiry_sql("NEW.started_at")};
                NEW.ended_at := NULL;
                NEW.end_reason := NULL;
                NEW.token_ciphertext := NULL;
                RETURN NEW;
            END IF;
            IF OLD.ended_at IS NOT NULL THEN
                RAISE EXCEPTION 'broker sessions: session % has ended and never changes', OLD.id
                    USING ERRCODE = '{BROKER_SESSION_SQLSTATE}';
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'broker sessions: the identity of session % never changes', OLD.id
                    USING ERRCODE = '{BROKER_SESSION_SQLSTATE}';
            END IF;
            IF NEW.end_reason IS NOT NULL OR NEW.ended_at IS NOT NULL THEN
                IF NEW.end_reason IS NULL THEN
                    RAISE EXCEPTION 'broker sessions: session % ends only with a reason', OLD.id
                        USING ERRCODE = '{BROKER_SESSION_SQLSTATE}';
                END IF;
                IF NEW.token_ciphertext IS NOT NULL THEN
                    RAISE EXCEPTION 'broker sessions: ending session % destroys its token in the same statement',
                        OLD.id USING ERRCODE = '{BROKER_SESSION_SQLSTATE}';
                END IF;
                NEW.ended_at := clock_timestamp();
                RETURN NEW;
            END IF;
            IF OLD.token_ciphertext IS NOT NULL AND NEW.token_ciphertext IS DISTINCT FROM OLD.token_ciphertext THEN
                RAISE EXCEPTION 'broker sessions: the token of active session % is set once', OLD.id
                    USING ERRCODE = '{BROKER_SESSION_SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PINNED_BODY = _M4._md5_body(_guard_function_sql())


def _trigger_check() -> str:
    row = f"FROM pg_trigger WHERE tgrelid = '{TABLE}'::regclass AND tgname = '{GUARD_TRIGGER}'"
    return f"""            IF NOT EXISTS (SELECT 1 {row} AND tgenabled = 'O') THEN
                problems := problems || 'trigger {GUARD_TRIGGER} is missing or not enabled'::TEXT;
            ELSIF (SELECT tgfoid {row}) IS DISTINCT FROM to_regprocedure('{GUARD_FUNCTION}()')
                  OR (SELECT tgtype::int {row}) IS DISTINCT FROM {BEFORE_ROW_INSERT_UPDATE_DELETE}
                  OR (SELECT tgqual IS NOT NULL OR tgattr::text <> '' OR tgnargs <> 0 {row}) THEN
                problems := problems || 'trigger {GUARD_TRIGGER} is not a plain BEFORE INSERT/UPDATE/DELETE row trigger on {GUARD_FUNCTION}'::TEXT;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = '{TABLE}'::regclass AND NOT tgisinternal
                       AND tgname <> '{GUARD_TRIGGER}') THEN
                problems := problems || 'table {TABLE} has an unexpected trigger'::TEXT;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_rewrite WHERE ev_class = '{TABLE}'::regclass AND rulename <> '_RETURN') THEN
                problems := problems || 'table {TABLE} has a rewrite rule'::TEXT;
            END IF;
            IF (SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('{GUARD_FUNCTION}()'))
               IS DISTINCT FROM '{PINNED_BODY}' THEN
                problems := problems || 'function {GUARD_FUNCTION} body differs from its pinned body'::TEXT;
            END IF;"""


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-058): broker_sessions: SELECT + column INSERT on user_ref, broker, key_id + column
    --    UPDATE on ended_at, end_reason, token_ciphertext only (no DELETE / TRUNCATE), USAGE only on its sequence,
    --    one active session per (user_ref, broker), the guard trigger enabled with its pinned body, no EXECUTE on it
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'table {TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M3.TABLE}'::regclass) THEN
                problems := problems || 'table {TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_PREV._privilege_checks(TABLE, "broker_sessions", {"SELECT"})}
{_M3._columns_exactly(TABLE, "broker_sessions", "INSERT", APP_INSERT_COLUMNS)}
{_M3._columns_exactly(TABLE, "broker_sessions", "UPDATE", APP_UPDATE_COLUMNS)}
{_M5._live_index_check(ACTIVE_INDEX, TABLE, "user_ref, broker", ACTIVE_PREDICATE)}
{_M3._sequence_checks(SEQUENCE, "broker session id", usage=True)}
{_M3._guard_function_checks(GUARD_FUNCTION, security_definer=False)}
{_trigger_check()}
        END IF;
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """0005's allowlist text plus block 10. Fails closed (RuntimeError) on a changed shape or a block 10 already in."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous_sql:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the broker session checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _M5.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            id               BIGSERIAL   PRIMARY KEY,
            user_ref         TEXT        NOT NULL CHECK (user_ref <> ''),
            broker           TEXT        NOT NULL CHECK (broker IN ({_quoted(BROKER_CODES)})),
            token_ciphertext BYTEA       NULL,
            key_id           TEXT        NOT NULL CHECK (key_id <> ''),
            started_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            expected_expiry  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            ended_at         TIMESTAMPTZ NULL,
            end_reason       TEXT        NULL CHECK (end_reason IN ({_quoted(END_REASONS)})),
            CONSTRAINT broker_sessions_end_has_reason CHECK ((ended_at IS NULL) = (end_reason IS NULL)),
            CONSTRAINT broker_sessions_ended_holds_no_token CHECK (ended_at IS NULL OR token_ciphertext IS NULL)
        )
        """
    )
    op.execute(f"CREATE UNIQUE INDEX {ACTIVE_INDEX.split('.')[1]} ON {TABLE} (user_ref, broker) "
               f"WHERE {ACTIVE_PREDICATE}")
    op.execute(_guard_function_sql())
    op.execute(f"CREATE TRIGGER {GUARD_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD_FUNCTION}()")

    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON SEQUENCE {SEQUENCE} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD_FUNCTION}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'REVOKE ALL ON SEQUENCE {SEQUENCE} FROM "{role}"')
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD_FUNCTION}() FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(APP_INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(APP_UPDATE_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while any session row exists: an ended row is the record that a token existed and was destroyed.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {TABLE})' INTO has_rows;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: broker_sessions holds rows';
            END IF;
        END
        $down$;
        """
    )
    role = _BASE._app_role()
    op.execute(_M5.extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"DROP FUNCTION {GUARD_FUNCTION}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
