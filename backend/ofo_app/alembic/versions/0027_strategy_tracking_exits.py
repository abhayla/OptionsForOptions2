"""Paper exit of a tracked strategy's legs: one append-only row per exited leg (GC-BP step 5; REQ-109 AC-4).

Basis: REQ-109 AC-4 ("Paper exit records each leg's exit price at that moment on the same basis and freezes the paper
P&L; a paper exit can be partial by leg"); ADR-201 (2) (booked / unbooked; paper never added to real); ADR-048 (the
limited application role); ADR-023 (the database clock); money NUMERIC(14,2) (decimal-money-boundaries).

Copy from: none - modelled on 0021's tables, insert-only guard trigger, grants and allow-list block.

Changes (owner-run, one transaction):
- public.strategy_tracking_exits: PRIMARY KEY (strategy_id, leg_index) - a leg exits once, enforced by the database;
  FOREIGN KEY (strategy_id, leg_index) -> strategy_tracking_legs (only a tracked leg exits); exit_price
  NUMERIC(14,2) > 0 (a live price only, REQ-109 AC-5); price_at = the exit quote's time; exited_at from the database
  clock. The rows live only in the tracking tables: they are labelled paper by where they are, never an order.
- Guard trigger (SQLSTATE OF027): insert-only (no UPDATE, no DELETE).
- Grants: the application role gets SELECT and column-limited INSERT; no UPDATE, DELETE or TRUNCATE.
- public.ofo_assert_app_role_allowlist: the predecessor's chain text (read from down_revision) plus block 20.
- downgrade: refuses while any exit row is stored (a paper exit is a record); otherwise drops what upgrade made.

Revision ID: 0027_strategy_tracking_exits
Revises: 0026_strategy_deleted_at
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0027_strategy_tracking_exits"
down_revision = "0026_strategy_deleted_at"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0027")  # 0026
_M23 = _load("0023_version_evidence.py", "ofo_migration_0023_for_0027")  # publishes the chain's insert point
_M16 = _M23._M16  # 0016: the table block helper
_M4 = _M23._M4  # 0004: _md5_body
_BASE = _PREVIOUS._BASE  # 0001
_INSERT_BEFORE = _M23._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF027"
EXITS = "public.strategy_tracking_exits"
LEGS = "public.strategy_tracking_legs"
GUARD = "public.strategy_tracking_exits_guard"
TRIGGER = "strategy_tracking_exits_guard"
INSERT_COLUMNS = ("strategy_id", "leg_index", "exit_price", "price_at")
ALLOWLIST_BLOCK_MARKER = "-- 20. strategy tracking exits"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'strategy tracking exits are insert-only' USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (GC-BP): strategy_tracking_exits: SELECT and column-limited INSERT exactly as granted,
    --    no UPDATE / DELETE / TRUNCATE; the insert-only guard enabled with its pinned body
    IF phase = 'post' THEN
{_M16._table_block(EXITS, "strategy_tracking_exits", INSERT_COLUMNS, (), GUARD, TRIGGER, PIN)}
    END IF;
"""


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The predecessor's chain text plus block 20. Fails closed (RuntimeError) on a changed shape or a block 20 already
    in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 20." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the tracking exit checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {EXITS} (
            strategy_id BIGINT        NOT NULL,
            leg_index   INTEGER       NOT NULL CHECK (leg_index >= 0),
            exit_price  NUMERIC(14,2) NOT NULL CHECK (exit_price > 0),
            price_at    TIMESTAMPTZ   NOT NULL,
            exited_at   TIMESTAMPTZ   NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (strategy_id, leg_index),
            FOREIGN KEY (strategy_id, leg_index) REFERENCES {LEGS} (strategy_id, leg_index)
        )
        """
    )
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {EXITS} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {EXITS} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {EXITS} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {EXITS} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {EXITS} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # A paper exit is a record of what the user did: refuse rather than drop it.
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE 'LOCK TABLE {EXITS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {EXITS}) THEN
                RAISE EXCEPTION 'refusing downgrade: {EXITS} holds paper exits';
            END IF;
        END
        $$
        """  # noqa: S608 constant table name
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {EXITS}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
