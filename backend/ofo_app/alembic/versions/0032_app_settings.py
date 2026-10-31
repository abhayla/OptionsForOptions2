"""App-wide admin settings as dated, append-only rows (REQ-167 AC-1, AC-2; ADR-222).

Spec basis: ADR-222 (1) "Each is a setting with a default value, the date it was set and who set it"; (5) admin
Settings hold only APP-WIDE values; REQ-167 AC-1 "The store keeps each change as a new dated row (append-only, like
the charge rates of ADR-082); the value in force at a time is the newest row not after that time, else the default";
AC-2 "Reset to default is a new row, never a delete"; ADR-048 (the limited application role); ADR-023 (database clock).

Copy from: 0012_charge_rates.py (append-only guard, grants, allow-list block) - the same shape on a timestamp.

Changes (owner-run, one transaction):
- public.app_settings: key (text, dotted lower-case shape; NOT a closed CHECK list - the registry file
  backend/ofo/settings/registry.json is the closed list and the store refuses unknown keys), value NUMERIC (finite:
  abs(value) < 1e30 also refuses NaN and +/-Infinity), effective_from TIMESTAMPTZ, set_by (non-empty), note (at most
  500), created_at DEFAULT clock_timestamp(). PRIMARY KEY (key, effective_from): two values never take effect for one
  key at the same instant.
- Append-only guard (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF032, search_path pinned, md5-pinned in the
  allow-list): every UPDATE and DELETE is refused; a correction or a reset is a new row. The same function also
  refuses an INSERT whose effective_from is more than 5 seconds in the past (a back-dated row; the grace covers the
  store reading "now" one statement before its insert) and runs on a statement-level BEFORE TRUNCATE trigger
  (app_settings_no_truncate), so even the table owner cannot truncate.
- Grants: the application role gets SELECT and column INSERT on key, value, effective_from, set_by, note; no UPDATE,
  no DELETE, no TRUNCATE.
- public.ofo_assert_app_role_allowlist: 0031's chain text plus block 24.
- downgrade: refuses (OF032) while any row exists (stored settings are history nobody can re-read).

Known bypasses (out of the threat model): the table owner or a superuser can drop the guard or edit rows.

Revision ID: 0032_app_settings
Revises: 0031_adjustment_playbooks
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0032_app_settings"
down_revision = "0031_adjustment_playbooks"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    found = importlib.util.spec_from_file_location(name, path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


_M31 = _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0032")
_M16 = _M31._M16
_M4 = _M31._M4
_BASE = _M31._BASE
_INSERT_BEFORE = _M31._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF032"  # an update, a delete, a truncate or a back-dated insert of a stored setting
BACKDATE_GRACE_SECONDS = 5  # the store reads "now" one statement before its insert; a row older than this is back-dated

TABLE = "public.app_settings"
GUARD = "public.app_settings_guard"
TRIGGER = "app_settings_guard"
TRUNCATE_TRIGGER = "app_settings_no_truncate"
LABEL = "app_settings"
KEY_SHAPE = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
KEY_MAX = 80
NOTE_MAX = 500
SET_BY_MAX = 200
INSERT_COLUMNS = ("key", "value", "effective_from", "set_by", "note")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 24. app settings"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'app settings are insert-only: a change or a reset is a new dated row'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.effective_from < clock_timestamp() - interval '{BACKDATE_GRACE_SECONDS} seconds' THEN
                RAISE EXCEPTION 'a setting takes effect now or later: a back-dated row would change figures already shown'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


BEFORE_STATEMENT_TRUNCATE = 2 + 32  # pg_trigger.tgtype bits: BEFORE (2) + TRUNCATE (32), statement level (no ROW bit)


def _trigger_checks() -> str:
    """0008's shared check (guard trigger, pinned body, no rule) with the one extra trigger this table allows, and
    the truncate trigger checked in its own right. Fails closed if the shared text changed shape."""
    shared = _M16._M8._trigger_check(TABLE, TRIGGER, GUARD, PIN)
    plain = f"AND tgname <> '{TRIGGER}')"
    if shared.count(plain) != 1:
        raise RuntimeError("the shared trigger check changed shape: cannot allow the truncate trigger safely")
    shared = shared.replace(plain, f"AND tgname NOT IN ('{TRIGGER}', '{TRUNCATE_TRIGGER}'))")
    row = f"FROM pg_trigger WHERE tgrelid = '{TABLE}'::regclass AND tgname = '{TRUNCATE_TRIGGER}'"
    return shared + f"""
            IF NOT EXISTS (SELECT 1 {row} AND tgenabled = 'O') THEN
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is missing or not enabled'::TEXT;
            ELSIF (SELECT tgfoid {row}) IS DISTINCT FROM to_regprocedure('{GUARD}()')
                  OR (SELECT tgtype::int {row}) IS DISTINCT FROM {BEFORE_STATEMENT_TRUNCATE}
                  OR (SELECT tgqual IS NOT NULL OR tgattr::text <> '' OR tgnargs <> 0 {row}) THEN
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is not a plain BEFORE TRUNCATE statement trigger on {GUARD}'::TEXT;
            END IF;"""


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (REQ-167): app_settings: SELECT + column INSERT on key, value, effective_from, set_by,
    --    note only; no UPDATE / DELETE / TRUNCATE; the guard trigger enabled with its pinned body, no EXECUTE on it
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'table {TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M16._M3.TABLE}'::regclass) THEN
                problems := problems || 'table {TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_M16._PREV._privilege_checks(TABLE, LABEL, {"SELECT"})}
{_M16._M3._columns_exactly(TABLE, LABEL, "INSERT", INSERT_COLUMNS)}
{_M16._M3._columns_exactly(TABLE, LABEL, "UPDATE", NO_UPDATE)}
{_M16._M3._guard_function_checks(GUARD, security_definer=False)}
{_trigger_checks()}
        END IF;
    END IF;
"""  # noqa: S608 - constant table and function names only


def previous_allowlist_sql() -> str:
    return _M31.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0031's chain text plus block 24. Fails closed (RuntimeError) on a changed shape or a block 24 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 24." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the app settings checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            key            TEXT        NOT NULL CHECK (key ~ '{KEY_SHAPE}' AND length(key) <= {KEY_MAX}),
            value          NUMERIC     NOT NULL CHECK (abs(value) < 1e30),
            effective_from TIMESTAMPTZ NOT NULL,
            set_by         TEXT        NOT NULL CHECK (btrim(set_by) <> '' AND length(set_by) <= {SET_BY_MAX}),
            note           TEXT        NOT NULL DEFAULT '' CHECK (length(note) <= {NOTE_MAX}),
            created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (key, effective_from)
        )
        """
    )
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"CREATE TRIGGER {TRUNCATE_TRIGGER} BEFORE TRUNCATE ON {TABLE} FOR EACH STATEMENT "
               f"EXECUTE FUNCTION {GUARD}()")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT count(*) FROM {TABLE}' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored app settings rows', n
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
