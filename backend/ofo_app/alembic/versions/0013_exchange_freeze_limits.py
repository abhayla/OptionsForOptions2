"""Exchange freeze limits: the freeze limit per exchange contract, with the date of the exchange file (W-076).

Basis: REQ-054 AC-4 ("Lot size, tick size and freeze limit are stored per broker with the date the broker's list
showed them."); ADR-081 ("Zerodha publishes none, so the freeze limit is stored per exchange from the exchange's
file, with its date"); findings F-36 (NSE's contract file: ``MaxTradQty`` joined on the exchange token); ADR-023 (the
database clock, never the application's); ADR-048 (the limited application role).

Copy from: none - modelled on 0009's table, guard and allowlist block.

CHAIN NOTE: built on this branch with down_revision ``0011_strategy_planned_entry``. W-074 adds ``0012_charge_rates``
in parallel; the orchestrator re-chains this file at merge (down_revision -> ``0012_charge_rates`` and the allowlist
base -> that migration's ``extended_allowlist_sql()``).

Changes (owner-run, one transaction):
- public.exchange_freeze_limits: (exchange_segment, exchange_token, file_date) is the key; freeze_limit INTEGER > 0;
  file_name TEXT. Append-only: the guard (SQLSTATE OF013, search_path pinned, md5-pinned in the allowlist) refuses any
  UPDATE or DELETE and refuses a file_date later than today on the database clock (IST). The newest file date is the
  one in force (the read picks it); an older file never replaces a newer limit.
- Grants: the application role gets SELECT and INSERT on every column. No UPDATE, DELETE or TRUNCATE.
- public.ofo_assert_app_role_allowlist: 0011's text plus block 13 for this table.

Revision ID: 0013_exchange_freeze_limits
Revises: 0011_strategy_planned_entry
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0013_exchange_freeze_limits"
down_revision = "0011_strategy_planned_entry"
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


_PREVIOUS = _load("0011_strategy_planned_entry.py", "ofo_migration_0011_for_0013")
_M8 = _PREVIOUS._M8
_M4 = _M8._M4
_M3 = _M8._M3
_PREV = _M8._PREV  # 0002
_BASE = _M8._BASE  # 0001

SEARCH_PATH = _M8.SEARCH_PATH
FREEZE_SQLSTATE = "OF013"
TIMEZONE = "Asia/Kolkata"
TABLE = "public.exchange_freeze_limits"
TRIGGER = "exchange_freeze_limits_guard"
GUARD = "public.exchange_freeze_limits_guard"
SEGMENTS = ("NSE_FO", "BSE_FO")  # ofo.instruments.models DERIVATIVE_SEGMENTS
INSERT_COLUMNS = ("exchange_segment", "exchange_token", "file_date", "freeze_limit", "file_name")
ALLOWLIST_BLOCK_MARKER = "-- 13. exchange freeze limits"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'freeze limits: % rows are insert-only', TG_TABLE_NAME
                    USING ERRCODE = '{FREEZE_SQLSTATE}';
            END IF;
            IF NEW.file_date > (clock_timestamp() AT TIME ZONE '{TIMEZONE}')::date THEN
                RAISE EXCEPTION 'freeze limits: a file dated % is later than today', NEW.file_date
                    USING ERRCODE = '{FREEZE_SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-076): exchange_freeze_limits: SELECT + INSERT on every column, no UPDATE / DELETE /
    --    TRUNCATE; the guard trigger enabled with its pinned body, no EXECUTE on the guard
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'table {TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M3.TABLE}'::regclass) THEN
                problems := problems || 'table {TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_PREV._privilege_checks(TABLE, "exchange_freeze_limits", {"SELECT"})}
{_M3._columns_exactly(TABLE, "exchange_freeze_limits", "INSERT", INSERT_COLUMNS)}
{_M3._columns_exactly(TABLE, "exchange_freeze_limits", "UPDATE", ())}
{_M3._guard_function_checks(GUARD, security_definer=False)}
{_M8._trigger_check(TABLE, TRIGGER, GUARD, PIN)}
        END IF;
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extended_allowlist_sql() -> str:
    """0011's allowlist text plus block 13. Fails closed (RuntimeError) on a changed shape or a block 13 already in."""
    previous = previous_allowlist_sql()
    headers = previous.count("CREATE FUNCTION") + previous.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the freeze limit checks safely")
    sql = previous.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    segments = ", ".join(f"'{s}'" for s in SEGMENTS)
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            exchange_segment TEXT    NOT NULL CHECK (exchange_segment IN ({segments})),
            exchange_token   BIGINT  NOT NULL CHECK (exchange_token > 0),
            file_date        DATE    NOT NULL,
            freeze_limit     INTEGER NOT NULL CHECK (freeze_limit > 0),
            file_name        TEXT    NOT NULL CHECK (file_name <> ''),
            PRIMARY KEY (exchange_segment, exchange_token, file_date)
        )
        """
    )
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
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
    # Refuses while any limit is stored: a stored limit is the record of what an exchange file showed on its date.
    op.execute(
        f"""
        DO $down$
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {TABLE}) THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: freeze limits are stored';
            END IF;
        END
        $down$;
        """
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
