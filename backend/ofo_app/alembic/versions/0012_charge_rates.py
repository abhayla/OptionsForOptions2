"""Charge rates: Zerodha's published F&O options rates as dated, append-only admin settings (W-074, ADR-082 part 1).

Spec basis: ADR-082 ("The rates are admin settings with the date they were read; every amount is exact Decimal; STT
and stamp duty are not rounded at order level"); REQ-032 AC-6 ("The engine exposes margin-planning and charges
interfaces (IC §5)."); REQ-032 AC-4 ("All money is computed in exact decimal or integer paise, never binary floating
point"); ADR-023 (the database clock); ADR-048 (the limited application role); finding F-35 (the rate text).

Copy from: none - spec/technical-design/legacy-reuse.md has no charges row.

Changes (owner-run, one transaction):
- public.charge_rates: one row per (component, read_on) with value NUMERIC (never float; finite and >= 0), the URL the
  rate was read from and a note. component is a closed list (CHECK): brokerage_per_order, stt_sell_rate,
  stt_exercise_rate, transaction_rate_nse_fo, transaction_rate_bse_fo, sebi_rate, stamp_buy_rate, gst_rate. The
  newest read_on that is not after the day asked about wins (a future-dated set is not in force; history is kept).
  Append-only: the guard (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF012, search_path pinned, md5-pinned in the
  allowlist) refuses every update and delete, so a correction is a new row on a later date.
- Seed: the 2026-10-15 rates of F-35 (brokerage 20; STT 0.15% sell and 0.15% of intrinsic on exercise; NSE
  transaction 0.03553% as one rate (Zerodha's 0.03503% + 0.0005% IPFT split is in the note); BSE 0.0325%; SEBI Rs 10
  per crore; stamp 0.003% buy side; GST 18%).
- Grants: the application role gets SELECT and INSERT on the data columns; no UPDATE, no DELETE, no TRUNCATE.
- public.ofo_assert_app_role_allowlist: 0011's text plus block 13 for this table.

Revision ID: 0012_charge_rates
Revises: 0011_strategy_planned_entry
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from alembic import op

revision = "0012_charge_rates"
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


_M11 = _load("0011_strategy_planned_entry.py", "ofo_migration_0011_for_0012")
_M8 = _M11._M8
_M4 = _M11._M4
_M3 = _M8._M3
_PREV = _M8._PREV  # 0002
_BASE = _M11._BASE  # 0001

SEARCH_PATH = _M8.SEARCH_PATH
CHARGES_SQLSTATE = "OF012"  # an update or a delete of a stored charge rate

TABLE = "public.charge_rates"
GUARD = "public.charge_rates_guard"
TRIGGER = "charge_rates_guard"
LABEL = "charge_rates"

#: ofo.charges component names as stored; a test asserts the app store's list equal.
COMPONENTS = ("brokerage_per_order", "stt_sell_rate", "stt_exercise_rate", "transaction_rate_nse_fo",
              "transaction_rate_bse_fo", "sebi_rate", "stamp_buy_rate", "gst_rate")
INSERT_COLUMNS = ("component", "read_on", "value", "source_url", "note")
NO_UPDATE: tuple[str, ...] = ()

SEED_DATE = date(2026, 10, 15)
SEED_SOURCE = "https://zerodha.com/charges (F&O options), read 2026-10-15; F-35"
SEED = (
    ("brokerage_per_order", "20", "Flat Rs 20 per executed order"),
    ("stt_sell_rate", "0.0015", "0.15% on the sell-side premium"),
    ("stt_exercise_rate", "0.0015", "0.15% of the intrinsic value of a bought option that is exercised"),
    ("transaction_rate_nse_fo", "0.0003553",
     "NSE 0.03553% of premium as one rate (Kite reports one exchange_turnover_charge); Zerodha's split is 0.03503% "
     "+ 0.0005% IPFT"),
    ("transaction_rate_bse_fo", "0.000325", "BSE 0.0325% of premium"),
    ("sebi_rate", "0.000001", "SEBI Rs 10 per crore"),
    ("stamp_buy_rate", "0.00003", "0.003% (Rs 300 per crore) on the buy side"),
    ("gst_rate", "0.18", "18% on brokerage + SEBI charges + transaction charges"),
)

ALLOWLIST_BLOCK_MARKER = "-- 13. charge rates"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'charge rates are insert-only: a correction is a new row on a later date'
                    USING ERRCODE = '{CHARGES_SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-074): charge_rates: SELECT + column INSERT on component, read_on, value, source_url,
    --    note only; no UPDATE / DELETE / TRUNCATE; the guard trigger enabled with its pinned body, no EXECUTE on it
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'table {TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M3.TABLE}'::regclass) THEN
                problems := problems || 'table {TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_PREV._privilege_checks(TABLE, LABEL, {"SELECT"})}
{_M3._columns_exactly(TABLE, LABEL, "INSERT", INSERT_COLUMNS)}
{_M3._columns_exactly(TABLE, LABEL, "UPDATE", NO_UPDATE)}
{_M3._guard_function_checks(GUARD, security_definer=False)}
{_M8._trigger_check(TABLE, TRIGGER, GUARD, PIN)}
        END IF;
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """0011 allowlist text plus block 13. Fails closed (RuntimeError) on a changed shape or a block 13 already in."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous_sql:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the charge rates checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _M11.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def _seed_sql() -> str:
    values = ",\n            ".join(
        f"('{c}', DATE '{SEED_DATE.isoformat()}', {v}::numeric, '{SEED_SOURCE}', '{n.replace(chr(39), chr(39) * 2)}')"
        for c, v, n in SEED)
    return f"INSERT INTO {TABLE} ({', '.join(INSERT_COLUMNS)}) VALUES\n            {values}"


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            component   TEXT        NOT NULL CHECK (component IN ({_quoted(COMPONENTS)})),
            read_on     DATE        NOT NULL,
            value       NUMERIC     NOT NULL CHECK (value <> 'NaN'::numeric AND value >= 0),
            source_url  TEXT        NOT NULL CHECK (btrim(source_url) <> ''),
            note        TEXT        NOT NULL DEFAULT '',
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (component, read_on)
        )
        """
    )
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(_seed_sql())
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
    # Refuses once an admin has added any set beyond the seed: a stored rate is history nobody can re-read.
    op.execute(
        f"""
        DO $down$
        DECLARE
            extra BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {TABLE} WHERE read_on <> DATE ''{SEED_DATE.isoformat()}'')'
                INTO extra;
            IF extra THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: charge rates beyond the seed are stored';
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
