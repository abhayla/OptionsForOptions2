"""Order-book store: platform fill prices and adopted holdings survive a restart (#313, GC-6).

NOTE (stacking): ``down_revision`` names held PR #419's CURRENT stem ``0018_reconciliation_store``. GC-3F renumbers #419
to 0019 (because #438 took 0018); when it does, change ``down_revision`` below to #419's renumbered stem. The
predecessor is loaded by FILE NAME from ``down_revision``, so the stem must match the file exactly.

Basis: issue #313 ("it must be stored (fills AND adopted holdings, in the same transaction as the strategy version)
before any route uses send_guard or the partial assessment"); ADR-096 (adopted holdings count in the strategy's
position exactly as a fill would); ADR-109 (a strategy owns exactly the fills of orders this app placed, matched by
tag; two holders of one contract stay separate, Q224); ADR-105 (held units = the net of filled units over every
stored plan); ADR-048 (the limited application role); ADR-023 (the database clock); ADR-008 (money is exact decimal).

Copy from: none - new store, modelled on 0018's tables, guards, grants and allow-list block.

Technical decision (#313 builder, recorded in the PR body): fill prices are a NEW insert-only table of trades keyed by
the order's tag, not an average_price column on execution_plan_orders. A column would need a new UPDATE grant and a
new body for 0016's pinned order guard, i.e. rewriting allow-list block 15; a separate table leaves 0016 untouched.

Changes (owner-run, one transaction):
- public.execution_plan_fills: one row per Zerodha trade of a tagged plan order (tag -> execution_plan_orders.tag,
  Zerodha's order id and trade id, units, trade price NUMERIC(14,2) > 0), recorded_at from the database clock. The
  trades are stored, not an average: an average of trades at 7.00 and 7.05 is not exact in paise, the trades are.
  PRIMARY KEY (broker_order_id, trade_id): a trade id is unique only per Zerodha order (FillLedger's key), and the key
  leaves out the tag so one trade is never stored under two tags (ADR-109: a strategy owns exactly the fills of the
  orders this app placed). Guard trigger (SQLSTATE OF020): insert-only; READ COMMITTED only; it locks the tag's order
  row FOR NO KEY UPDATE (two inserters for one tag wait for each other, so the second sums the first's committed
  trade) and an insert is refused unless that order's stored filled_quantity is above 0 and the stored trades of the
  tag, with this one, do not exceed it; it also takes a transaction advisory lock on the Zerodha order id and refuses
  an order id already stored under another tag.
- public.adopted_holdings: units a strategy holds without a platform fill (ADR-096): strategy, contract key (the app's
  instrument id), side, units, product, average price, a unique reference, the strategy version number that adopted
  them, adopted_at from the database clock. The average price is NUMERIC with NO declared scale (ADR-126): Zerodha
  reports a position's average_price as a JSON float with no fixed number of decimals (an average of whole-paisa trades
  is 7.025 for 65 at 7.00 + 65 at 7.05, or 7.016666666666667 for 2 x 7.00 + 1 x 7.05), the app keeps it as
  Decimal(str(float)) (kite_replies.kite_money exact=True, ADR-102), and any fixed scale would round some of those
  silently. The > 0 and < 10^12 CHECK still bounds it (NaN and Infinity fail the upper bound). Trade prices stay
  NUMERIC(14,2): a single Zerodha trade is a whole paisa.
  UNIQUE (strategy_id, instrument_id): a strategy never nets a second
  holding into a contract it already holds, while two strategies may each hold the same contract (Q224). Guard
  trigger (OF020): insert-only.
- Grants (column-limited): SELECT on both; INSERT on the written columns (never the clock columns or the id); USAGE
  on the holdings id sequence. No UPDATE, DELETE or TRUNCATE.
- public.ofo_assert_app_role_allowlist: the predecessor's text plus block 17 for the two tables.
- downgrade: refuses while any row is stored in either table; otherwise restores the predecessor's state exactly.

Revision ID: 0020_order_book_store
Revises: 0018_reconciliation_store (to become #419's renumbered stem)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0020_order_book_store"
down_revision = "0018_reconciliation_store"  # change to #419's renumbered stem when GC-3F renumbers it
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0020")
_M16 = _PREVIOUS._M16
_M8 = _PREVIOUS._M8
_M4 = _PREVIOUS._M4
_M3 = _PREVIOUS._M3
_PREV = _PREVIOUS._PREV  # 0002
_BASE = _PREVIOUS._BASE  # 0001

SEARCH_PATH = _PREVIOUS.SEARCH_PATH
SQLSTATE = "OF020"
ORDERS = _M16.ORDERS
FILLS = "public.execution_plan_fills"
HOLDINGS = "public.adopted_holdings"
HOLDING_SEQUENCE = "public.adopted_holdings_id_seq"
FILL_GUARD = "public.execution_plan_fills_guard"
HOLDING_GUARD = "public.adopted_holdings_guard"
FILL_TRIGGER = "execution_plan_fills_guard"
HOLDING_TRIGGER = "adopted_holdings_guard"
HOLDING_KEY = "adopted_holdings_one_per_contract"
FILL_KEY = "execution_plan_fills_one_per_trade"  # (order id, trade id): a trade is stored once, under one tag
FILL_TAG_INDEX = "execution_plan_fills_by_tag"  # the guard's per-tag sum
SIDES = ("BUY", "SELL")
PRODUCTS = ("NRML", "MIS")  # ofo.engine.product.Product values (a migration carries its own literal)
MAX_UNITS = _PREVIOUS.MAX_UNITS
MAX_TEXT = _PREVIOUS.MAX_TEXT
CONTRACT_KEY_REGEX = _PREVIOUS.CONTRACT_KEY_REGEX
PRICE_LIMIT = "1000000000000"  # below 10^12, as execution_plan_store.PRICE_LIMIT (both price columns)
FILL_INSERT_COLUMNS = ("tag", "broker_order_id", "trade_id", "quantity", "price")
HOLDING_INSERT_COLUMNS = ("strategy_id", "instrument_id", "transaction_type", "quantity", "product", "average_price",
                          "reference", "version_number")
ALLOWLIST_BLOCK_MARKER = "-- 17. order book store"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _fill_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {FILL_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            filled INTEGER;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'fill prices are insert-only' USING ERRCODE = '{SQLSTATE}';
            END IF;
            -- the locks below serialise writers only if each later statement takes a fresh snapshot
            IF current_setting('transaction_isolation') <> 'read committed' THEN
                RAISE EXCEPTION 'fill prices need READ COMMITTED (stored trades are summed after the lock)'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            -- a self-conflicting row lock: two inserters for one tag wait for each other (a share lock would not:
            -- share locks coexist, both would sum 0), and so does a filled_quantity write; the RI check's key-share
            -- lock does not. The app role may take it: it holds UPDATE (filled_quantity) on the orders table.
            SELECT filled_quantity INTO filled FROM {ORDERS} WHERE tag = NEW.tag FOR NO KEY UPDATE;
            IF coalesce(filled, 0) <= 0 THEN  -- no such tag, still open (NULL), or nothing filled (0)
                RAISE EXCEPTION 'a fill price needs an order that filled' USING ERRCODE = '{SQLSTATE}';
            END IF;
            -- one Zerodha order belongs to one tag: serialise on the order id across tags (a hash collision only
            -- serialises two unrelated writers, it never lets one through)
            PERFORM pg_advisory_xact_lock(hashtextextended('{FILLS}:' || NEW.broker_order_id, 0));
            IF EXISTS (SELECT 1 FROM {FILLS} WHERE broker_order_id = NEW.broker_order_id AND tag <> NEW.tag) THEN
                RAISE EXCEPTION 'a Zerodha order is stored under one tag only' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF (SELECT coalesce(sum(quantity), 0) FROM {FILLS} WHERE tag = NEW.tag) + NEW.quantity > filled THEN
                RAISE EXCEPTION 'stored trades exceed the order''s filled quantity' USING ERRCODE = '{SQLSTATE}';
            END IF;
            NEW.recorded_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """  # noqa: S608 constant table names


def _holding_guard_sql() -> str:
    return _PREVIOUS._insert_only_guard_sql(HOLDING_GUARD, "adopted holdings", "adopted_at").replace(
        f"'{_PREVIOUS.SQLSTATE}'", f"'{SQLSTATE}'")


FILL_PIN = _M4._md5_body(_fill_guard_sql())
HOLDING_PIN = _M4._md5_body(_holding_guard_sql())


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (#313): execution_plan_fills and adopted_holdings: SELECT, column-limited INSERT
    --    exactly as granted, no UPDATE / DELETE / TRUNCATE; the guard triggers enabled with their pinned bodies, no
    --    EXECUTE on a guard
    IF phase = 'post' THEN
{_PREVIOUS._table_block(FILLS, "execution_plan_fills", FILL_INSERT_COLUMNS, (), FILL_GUARD, FILL_TRIGGER, FILL_PIN)}
{_PREVIOUS._table_block(HOLDINGS, "adopted_holdings", HOLDING_INSERT_COLUMNS, (), HOLDING_GUARD, HOLDING_TRIGGER,
                        HOLDING_PIN, HOLDING_SEQUENCE)}
    END IF;
"""


_INSERT_BEFORE = _PREVIOUS._INSERT_BEFORE


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The predecessor's allowlist text plus block 17. Fails closed (RuntimeError) on a changed shape or a block 17
    already in."""
    previous = previous_allowlist_sql()
    headers = previous.count("CREATE FUNCTION") + previous.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the order book store checks safely")
    sql = previous.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {FILLS} (
            tag             TEXT          NOT NULL REFERENCES {ORDERS} (tag),
            broker_order_id TEXT          NOT NULL
                                          CHECK (broker_order_id <> '' AND length(broker_order_id) <= {MAX_TEXT}),
            trade_id        TEXT          NOT NULL CHECK (trade_id <> '' AND length(trade_id) <= {MAX_TEXT}),
            quantity        INTEGER       NOT NULL CHECK (quantity BETWEEN 1 AND {MAX_UNITS}),
            price           NUMERIC(14,2) NOT NULL CHECK (price > 0 AND price < {PRICE_LIMIT}),
            recorded_at     TIMESTAMPTZ   NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT {FILL_KEY} PRIMARY KEY (broker_order_id, trade_id)
        )
        """
    )
    op.execute(f"CREATE INDEX {FILL_TAG_INDEX} ON {FILLS} (tag)")
    op.execute(
        f"""
        CREATE TABLE {HOLDINGS} (
            id               BIGSERIAL     PRIMARY KEY,
            strategy_id      BIGINT        NOT NULL REFERENCES public.strategies (id),
            instrument_id    TEXT          NOT NULL CHECK (instrument_id ~ '{CONTRACT_KEY_REGEX}'),
            transaction_type TEXT          NOT NULL CHECK (transaction_type IN ({_quoted(SIDES)})),
            quantity         INTEGER       NOT NULL CHECK (quantity BETWEEN 1 AND {MAX_UNITS}),
            product          TEXT          NOT NULL CHECK (product IN ({_quoted(PRODUCTS)})),
            average_price    NUMERIC       NOT NULL CHECK (average_price > 0 AND average_price < {PRICE_LIMIT}),
            reference        TEXT          NOT NULL UNIQUE CHECK (reference <> '' AND length(reference) <= {MAX_TEXT}),
            version_number   INTEGER       NOT NULL CHECK (version_number > 0),
            adopted_at       TIMESTAMPTZ   NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT {HOLDING_KEY} UNIQUE (strategy_id, instrument_id)
        )
        """
    )
    op.execute(_fill_guard_sql())
    op.execute(_holding_guard_sql())
    for table, guard, trigger in ((FILLS, FILL_GUARD, FILL_TRIGGER), (HOLDINGS, HOLDING_GUARD, HOLDING_TRIGGER)):
        op.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {guard}()")
        op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
    for table, insert_cols in ((FILLS, FILL_INSERT_COLUMNS), (HOLDINGS, HOLDING_INSERT_COLUMNS)):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
        op.execute(f'GRANT INSERT ({", ".join(insert_cols)}) ON TABLE {table} TO "{role}"')
    op.execute(f"REVOKE ALL ON SEQUENCE {HOLDING_SEQUENCE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON SEQUENCE {HOLDING_SEQUENCE} FROM "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {HOLDING_SEQUENCE} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Fill prices and adopted holdings are what a strategy holds: refuse rather than drop them.
    op.execute(
        f"""
        DO $down$
        BEGIN
            EXECUTE 'LOCK TABLE {FILLS}, {HOLDINGS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {FILLS}) OR EXISTS (SELECT 1 FROM {HOLDINGS}) THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: order book records are stored';
            END IF;
        END
        $down$;
        """  # noqa: S608 constant table names
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {FILLS}")
    op.execute(f"DROP TABLE {HOLDINGS}")
    op.execute(f"DROP FUNCTION {FILL_GUARD}()")
    op.execute(f"DROP FUNCTION {HOLDING_GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
