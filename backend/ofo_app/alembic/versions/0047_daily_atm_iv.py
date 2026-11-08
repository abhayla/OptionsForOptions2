"""The app's own ATM IV, once per underlying per trading day (GC-ICTRACK task 28; ADR-277 (4)).

Spec basis: ADR-277 (4) ("The app writes its own ATM IV once per underlying per trading day from now on, so a true IV
percentile can replace the stand-in later"); ADR-008 (exact decimals); ADR-048 (the limited application role).
Copy from: 0039_strategy_entry_facts.py (insert-only guard, statement-level truncate trigger, grants, allow-list block).

Changes (owner-run, one transaction; ADDITIVE: a new table, no existing table or row changed):
- public.daily_atm_iv: underlying TEXT ('NIFTY' / 'SENSEX'), trading_day DATE, expiry DATE (the expiry whose ATM IV
  this is), atm_iv NUMERIC > 0, recorded_at DEFAULT clock_timestamp(); PRIMARY KEY (underlying, trading_day): at most
  one row per underlying per day (the store keeps the first value of the day, ON CONFLICT DO NOTHING).
- Insert-only guard (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF047, search_path pinned, md5-pinned in the
  allow-list) plus the same function on a statement-level BEFORE TRUNCATE trigger: a stored day is never changed.
- Grants: the application role gets SELECT and column INSERT on underlying, trading_day, expiry, atm_iv.
- public.ofo_assert_app_role_allowlist: 0046's chain text plus block 33 (block 32 is 0043's scenario frames).
- downgrade: refuses (OF047, counted) while any row exists.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable the guard, then edit rows.

Revision ID: 0047_daily_atm_iv
Revises: 0046_entry_atm_iv
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0047_daily_atm_iv"
down_revision = "0046_entry_atm_iv"
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


_M46 = _load("0046_entry_atm_iv.py", "ofo_migration_0046_for_0047")
_M39 = _M46._M39
_M16 = _M39._M16
_M4 = _M39._M4
_BASE = _M46._BASE
_INSERT_BEFORE = _M39._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF047"  # an update, a delete or a truncate of a stored daily ATM IV

TABLE = "public.daily_atm_iv"
GUARD = "public.daily_atm_iv_guard"
TRIGGER = "daily_atm_iv_guard"
TRUNCATE_TRIGGER = "daily_atm_iv_no_truncate"
LABEL = "daily_atm_iv"
INSERT_COLUMNS = ("underlying", "trading_day", "expiry", "atm_iv")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 33. daily ATM IV"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'a daily ATM IV is written once and never changed'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())
BEFORE_STATEMENT_TRUNCATE = _M39.BEFORE_STATEMENT_TRUNCATE


def _trigger_checks() -> str:
    """0039's check shape for this table's row and truncate triggers."""
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
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is not a plain BEFORE TRUNCATE trigger'::TEXT;
            END IF;"""  # noqa: S608 - constant names only


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (ADR-277 (4)): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
    --    no UPDATE / DELETE / TRUNCATE; the guard trigger enabled with its pinned body, no EXECUTE on it
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
    return _M46.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0046's chain text plus block 33. Fails closed (RuntimeError) on a changed shape or a block 33 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 33." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the daily ATM IV checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            underlying  TEXT        NOT NULL CHECK (underlying IN ('NIFTY', 'SENSEX')),
            trading_day DATE        NOT NULL,
            expiry      DATE        NOT NULL,
            atm_iv      NUMERIC     NOT NULL CHECK (atm_iv > 0),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (underlying, trading_day)
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
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored daily ATM IVs', n
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
