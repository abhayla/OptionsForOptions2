"""The stored last close: one price per instrument per trading day, written at the close (Lane N A1/AF-02).

Spec basis: ADR-330 (36) ("the after-close figure is the last price received up to the calendar close (15:30:00)");
ADR-212 (every market-data screen shows the last close until the open; a contract with no held close stays unpriced
with its reason, ADR-200 (4)); ADR-330 (58) (paper and real differ only by tag: one table for both); ADR-008 (exact
decimals: NUMERIC, never float); ADR-048 (the limited application role).

Copy from: 0009 (the whole-paisa and range CHECKs, the application-role grants) and 0050 (the module shape).

Changes (owner-run, one transaction; ADDITIVE: ONE new table, no existing table, column, row or function changed):
- public.last_close: (instrument_id as the catalogue holds it, trade_date = the IST date of the session) is the key;
  price NUMERIC with CHECKs: a whole number of paise (round(x, 2) = x) and 0 <= x < 10^12, so a finer price is
  REFUSED, never rounded (a NUMERIC(14,2) column would round it silently); price_at = when the price was made
  (the exchange time of the frame: on trade_date, in IST, at or before 15:30:00, CHECKed like 0009's trade_date); source TEXT (what wrote it, e.g. 'feed_book').
- Grants to the application role: SELECT; INSERT on every column; UPDATE on price, price_at, source only (the
  close is written with an upsert). No DELETE, no TRUNCATE.
- The allow-list function is NOT changed: this table is a cache of what the feed book held at the close, and the
  chain text is left exactly as 0057 leaves it (no merge conflict with a branch that also extends it).
- downgrade: drops the table (a held close is re-made by the next session's close; nothing else refers to it).

Old-code compatibility: additive. Code before this migration never reads or writes the table, and no existing
table, column, constraint, trigger or grant is touched, so it keeps working with the table present.
Deploy order: migrate first or last, either is safe; new code on an un-migrated database logs one error per close
write / start-up read and serves no stored close (screens say prices are not available), never a fault.

Revision ID: 0059_last_close
Revises: 0057_history_delete_entries
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0059_last_close"
down_revision = "0057_history_delete_entries"
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


_M9 = _load("0009_minute_history.py", "ofo_migration_0009_for_0059")
_BASE = _M9._BASE

TABLE = "public.last_close"
INSERT_COLUMNS = ("instrument_id", "trade_date", "price", "price_at", "source")
UPDATE_COLUMNS = ("price", "price_at", "source")


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            instrument_id TEXT        NOT NULL CHECK (instrument_id <> ''),
            trade_date    DATE        NOT NULL,
            price         NUMERIC     NOT NULL,
            price_at      TIMESTAMPTZ NOT NULL,
            source        TEXT        NOT NULL CHECK (source <> ''),
            PRIMARY KEY (instrument_id, trade_date),
            CONSTRAINT last_close_whole_paise CHECK (price = round(price, 2)),
            CONSTRAINT last_close_price_range CHECK (price BETWEEN 0 AND 999999999999),
            CONSTRAINT last_close_price_at_day CHECK (
                trade_date = (price_at AT TIME ZONE 'Asia/Kolkata')::date
                AND (price_at AT TIME ZONE 'Asia/Kolkata')::time <= TIME '15:30:00')
        )
        """
    )
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(UPDATE_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(f"DROP TABLE {TABLE}")
