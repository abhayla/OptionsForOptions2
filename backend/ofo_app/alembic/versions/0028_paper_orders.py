"""The paper order book: one append-only row per paper order; the tracked legs and exits migrate into it (GC-TP 1a).

Basis: REQ-109 AC-4 ("The one engine derives the net position per contract from the orders"); ADR-207 (paper trading
the Sensibull Draft Portfolio way); ADR-048 (the limited application role); ADR-023 (the database clock); money
NUMERIC(14,2) (decimal-money-boundaries).

Copy from: none - modelled on 0027's table, insert-only guard trigger, grants and allow-list block.

Changes (owner-run, one transaction, the API stopped):
- public.paper_orders: id BIGSERIAL (placement order), strategy_id -> strategies, contract_id -> catalogue_contracts,
  side BUY/SELL, quantity > 0 (units), price NUMERIC(14,2) > 0, kind open|add|exit|settle|stop, placed_at, created_at
  from the database clock, reason, trigger_id; UNIQUE (trigger_id, contract_id) where trigger_id is set (one
  conditional-exit trigger writes one stop order per open contract, never two for the same contract).
- Guard trigger (SQLSTATE OF028): insert-only (no UPDATE, no DELETE).
- Grants: the application role gets SELECT and column-limited INSERT; no UPDATE, DELETE or TRUNCATE.
- Data: each strategy_tracking_legs row -> one `open` order (its side, quantity, entry_price, placed_at = price_at), in
  (strategy_id, leg_index) order; then each strategy_tracking_exits row -> one `exit` order of the leg's contract,
  opposite side, same quantity, at exit_price, placed_at = exited_at, in (strategy_id, exited_at, leg_index) order.
  Refused (nothing written) when a strategy tracks the same contract on two legs: the book would merge them into one
  position and the shown legs would change.
- The three old tables become read-only for the application role (INSERT revoked; dropped by a later migration).
- public.ofo_assert_app_role_allowlist: the predecessor's chain text, blocks 18 and 20 made read-only, plus block 21.
- downgrade: refuses while paper_orders holds an order that is not a copy of an old row (counted); otherwise drops the
  table and restores the old grants and allow-list.

Revision ID: 0028_paper_orders
Revises: 0027_strategy_tracking_exits
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0028_paper_orders"
down_revision = "0027_strategy_tracking_exits"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0028")  # 0027
_M21 = _load("0021_strategy_tracking.py", "ofo_migration_0021_for_0028")
_M23 = _load("0023_version_evidence.py", "ofo_migration_0023_for_0028")
_M16 = _M23._M16
_M4 = _M23._M4
_BASE = _PREVIOUS._BASE
_INSERT_BEFORE = _M23._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF028"
ORDERS = "public.paper_orders"
GUARD = "public.paper_orders_guard"
TRIGGER = "paper_orders_guard"
TRIGGER_INDEX = "paper_orders_trigger_contract"
SEQUENCE = "public.paper_orders_id_seq"
KINDS = ("open", "add", "exit", "settle", "stop")
INSERT_COLUMNS = ("strategy_id", "contract_id", "side", "quantity", "price", "kind", "placed_at", "reason",
                  "trigger_id")
ALLOWLIST_BLOCK_MARKER = "-- 21. paper orders"
# The old tables and the columns the application role could insert (0021, 0027); read-only from here.
OLD_INSERTS = ((_M21.TRACKING, _M21.TRACKING_INSERT_COLUMNS), (_M21.LEGS, _M21.LEGS_INSERT_COLUMNS),
               (_PREVIOUS.EXITS, _PREVIOUS.INSERT_COLUMNS))


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'paper orders are insert-only' USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (GC-TP): paper_orders: SELECT and column-limited INSERT exactly as granted,
    --    no UPDATE / DELETE / TRUNCATE; the insert-only guard enabled with its pinned body
    IF phase = 'post' THEN
{_M16._table_block(ORDERS, "paper_orders", INSERT_COLUMNS, (), GUARD, TRIGGER, PIN)}
{_M16._M3._sequence_checks(SEQUENCE, "paper order id", usage=True)}
    END IF;
"""


def _read_only_block_18() -> str:
    """Block 18 (0021) with no INSERT column: strategy_tracking and strategy_tracking_legs are read-only now."""
    return f"""
    {_M21.ALLOWLIST_BLOCK_MARKER} (W-122; read-only since GC-TP 0028): strategy_tracking and strategy_tracking_legs:
    --    SELECT only, no INSERT / UPDATE / DELETE / TRUNCATE; the insert-only guards enabled with their pinned bodies
    IF phase = 'post' THEN
{_M16._table_block(_M21.TRACKING, "strategy_tracking", (), (), _M21.TRACKING_GUARD, _M21.TRACKING_TRIGGER,
                   _M21.TRACKING_PIN)}
{_M16._table_block(_M21.LEGS, "strategy_tracking_legs", (), (), _M21.LEGS_GUARD, _M21.LEGS_TRIGGER, _M21.LEGS_PIN)}
    END IF;
"""


def _read_only_block_20() -> str:
    """Block 20 (0027) with no INSERT column: strategy_tracking_exits is read-only now."""
    return f"""
    {_PREVIOUS.ALLOWLIST_BLOCK_MARKER} (GC-BP; read-only since GC-TP 0028): strategy_tracking_exits: SELECT only,
    --    no INSERT / UPDATE / DELETE / TRUNCATE; the insert-only guard enabled with its pinned body
    IF phase = 'post' THEN
{_M16._table_block(_PREVIOUS.EXITS, "strategy_tracking_exits", (), (), _PREVIOUS.GUARD, _PREVIOUS.TRIGGER,
                   _PREVIOUS.PIN)}
    END IF;
"""


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The predecessor's chain text with blocks 18 and 20 read-only, plus block 21. Fails closed (RuntimeError) on a
    changed shape or a block 21 already in."""
    previous = previous_allowlist_sql()
    old18, old20 = _M21._block(), _PREVIOUS._block()
    if (previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 21." in previous
            or previous.count(old18) != 1 or previous.count(old20) != 1):
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the paper order checks safely")
    sql = previous.replace(old18, _read_only_block_18(), 1).replace(old20, _read_only_block_20(), 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def _copy_sql() -> str:
    """The data step: legs -> open orders, exits -> exit orders, one row at a time in a fixed order (the BIGSERIAL id
    is the placement order the engine reads)."""
    legs, exits = _M21.LEGS, _PREVIOUS.EXITS
    return f"""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            IF EXISTS (SELECT 1 FROM {legs} GROUP BY strategy_id, contract_id HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'refusing the paper order copy: a strategy tracks one contract on two legs';
            END IF;
            FOR r IN SELECT strategy_id, contract_id, side, quantity, entry_price, price_at FROM {legs}
                     ORDER BY strategy_id, leg_index LOOP
                INSERT INTO {ORDERS} (strategy_id, contract_id, side, quantity, price, kind, placed_at)
                VALUES (r.strategy_id, r.contract_id, r.side, r.quantity, r.entry_price, 'open', r.price_at);
            END LOOP;
            FOR r IN SELECT l.strategy_id, l.contract_id, l.side, l.quantity, e.exit_price, e.exited_at
                     FROM {exits} e JOIN {legs} l USING (strategy_id, leg_index)
                     ORDER BY e.strategy_id, e.exited_at, e.leg_index LOOP
                INSERT INTO {ORDERS} (strategy_id, contract_id, side, quantity, price, kind, placed_at)
                VALUES (r.strategy_id, r.contract_id, CASE r.side WHEN 'BUY' THEN 'SELL' ELSE 'BUY' END, r.quantity,
                        r.exit_price, 'exit', r.exited_at);
            END LOOP;
        END
        $$
        """  # noqa: S608 constant table names


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    kinds = ", ".join(f"'{k}'" for k in KINDS)
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {ORDERS} (
            id          BIGSERIAL     PRIMARY KEY,
            strategy_id BIGINT        NOT NULL REFERENCES public.strategies (id),
            contract_id BIGINT        NOT NULL REFERENCES public.catalogue_contracts (id),
            side        TEXT          NOT NULL CHECK (side IN ('BUY', 'SELL')),
            quantity    INTEGER       NOT NULL CHECK (quantity > 0),
            price       NUMERIC(14,2) NOT NULL CHECK (price > 0),
            kind        TEXT          NOT NULL CHECK (kind IN ({kinds})),
            placed_at   TIMESTAMPTZ   NOT NULL,
            created_at  TIMESTAMPTZ   NOT NULL DEFAULT clock_timestamp(),
            reason      TEXT          NULL,
            trigger_id  BIGINT        NULL
        )
        """
    )
    op.execute(f"CREATE INDEX paper_orders_strategy ON {ORDERS} (strategy_id, id)")
    op.execute(f"CREATE UNIQUE INDEX {TRIGGER_INDEX} ON {ORDERS} (trigger_id, contract_id) "
               "WHERE trigger_id IS NOT NULL")
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {ORDERS} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {ORDERS} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {ORDERS} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {ORDERS} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {ORDERS} TO "{role}"')
    op.execute(f"REVOKE ALL ON SEQUENCE {SEQUENCE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON SEQUENCE {SEQUENCE} FROM "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')
    op.execute(_copy_sql())
    for table, columns in OLD_INSERTS:
        op.execute(f'REVOKE INSERT ({", ".join(columns)}) ON TABLE {table} FROM "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # An order placed after the copy exists nowhere else: refuse rather than drop it.
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE 'LOCK TABLE {ORDERS} IN ACCESS EXCLUSIVE MODE';
            IF (SELECT count(*) FROM {ORDERS})
               > (SELECT count(*) FROM {_M21.LEGS}) + (SELECT count(*) FROM {_PREVIOUS.EXITS}) THEN
                RAISE EXCEPTION 'refusing downgrade: {ORDERS} holds paper orders placed after the copy';
            END IF;
        END
        $$
        """  # noqa: S608 constant table names
    )
    role = _BASE._app_role()
    for table, columns in OLD_INSERTS:
        op.execute(f'GRANT INSERT ({", ".join(columns)}) ON TABLE {table} TO "{role}"')
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {ORDERS}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
