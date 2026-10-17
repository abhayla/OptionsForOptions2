"""Execution plans: the persisted order intent, one open plan per strategy, tags never reused (W-094).

Basis: ADR-050 item 4 ("(b) persist the order intent before sending"); ADR-054 (confirmation and reconciliation run on
the result, by tag lookup); REQ-073 AC-2 (every order carries our own tag, at most 20 alphanumeric characters,
identifying the strategy and plan version); ADR-048 (the limited application role); ADR-023 (the database clock).
The plan number is minted per strategy for every Execute (entry 1, exit 2 on the real order of 2026-10-16).

Copy from: none - modelled on 0013's table, guard and grants.

Changes (owner-run, one transaction):
- public.execution_plans: PRIMARY KEY (strategy_id, plan_number); a PARTIAL UNIQUE INDEX on (strategy_id) WHERE
  status = 'open' (one open plan per strategy, enforced by the database, not by the store); closed <=> closed_at and
  close_reason set. Guard trigger (SQLSTATE OF016): no DELETE; the only UPDATE is open -> closed with the identity
  columns unchanged; closed_at is set from the database clock, never from the application.
- public.execution_plan_orders: tag UNIQUE, CHECK 1..20 ASCII alphanumerics AND equal to OFS<strategy>V<plan>L<leg>;
  quantity > 0; price NUMERIC(14,2) > 0. Guard trigger (OF016): insert-only (only filled_quantity is set, once,
  at close), and only into an open plan.
- Grants: the application role gets SELECT and INSERT on both tables, UPDATE (status, close_reason) on the plans and
  UPDATE (filled_quantity) on the orders.
- downgrade: refuses while any plan is stored (order intent is a record); otherwise drops what upgrade created.

Revision ID: 0016_execution_plans
Revises: 0015_audit_broker_allowlist
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0016_execution_plans"
down_revision = "0015_audit_broker_allowlist"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0016")
_AUDIT = _PREVIOUS._AUDIT  # 0002
_BASE = _PREVIOUS._BASE  # 0001

SEARCH_PATH = _AUDIT.SEARCH_PATH
PLAN_SQLSTATE = "OF016"
PLANS = "public.execution_plans"
ORDERS = "public.execution_plan_orders"
OPEN_INDEX = "execution_plans_one_open"
PLAN_GUARD = "public.execution_plans_guard"
ORDER_GUARD = "public.execution_plan_orders_guard"
PLAN_TRIGGER = "execution_plans_guard"
ORDER_TRIGGER = "execution_plan_orders_guard"
REASONS = ("filled", "exited", "nothing_placed", "partial")


def _plan_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {PLAN_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'execution plans are never deleted' USING ERRCODE = '{PLAN_SQLSTATE}';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF OLD.status <> 'open' OR NEW.status <> 'closed'
                   OR NEW.strategy_id <> OLD.strategy_id OR NEW.plan_number <> OLD.plan_number
                   OR NEW.action <> OLD.action OR NEW.created_at <> OLD.created_at THEN
                    RAISE EXCEPTION 'an execution plan only changes from open to closed'
                        USING ERRCODE = '{PLAN_SQLSTATE}';
                END IF;
                NEW.closed_at := clock_timestamp();
            END IF;
            RETURN NEW;
        END
        $fn$
        """


def _order_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {ORDER_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                -- the only change ever allowed: Zerodha's filled quantity, written once, while the plan is open
                IF OLD.filled_quantity IS NOT NULL OR NEW.filled_quantity IS NULL
                   OR NEW.strategy_id <> OLD.strategy_id OR NEW.plan_number <> OLD.plan_number
                   OR NEW.leg_index <> OLD.leg_index OR NEW.tag <> OLD.tag
                   OR NEW.instrument_id <> OLD.instrument_id OR NEW.tradingsymbol <> OLD.tradingsymbol
                   OR NEW.transaction_type <> OLD.transaction_type OR NEW.quantity <> OLD.quantity
                   OR NEW.price <> OLD.price THEN
                    RAISE EXCEPTION 'execution plan orders only gain a filled quantity, once'
                        USING ERRCODE = '{PLAN_SQLSTATE}';
                END IF;
            ELSIF TG_OP <> 'INSERT' OR NEW.filled_quantity IS NOT NULL THEN
                RAISE EXCEPTION 'execution plan orders are insert-only' USING ERRCODE = '{PLAN_SQLSTATE}';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM {PLANS} p WHERE p.strategy_id = NEW.strategy_id
                           AND p.plan_number = NEW.plan_number AND p.status = 'open') THEN
                RAISE EXCEPTION 'orders can only be added to an open plan' USING ERRCODE = '{PLAN_SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """  # noqa: S608 constant table name


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    reasons = ", ".join(f"'{r}'" for r in REASONS)
    op.execute(
        f"""
        CREATE TABLE {PLANS} (
            strategy_id  BIGINT      NOT NULL REFERENCES public.strategies (id),
            plan_number  INTEGER     NOT NULL CHECK (plan_number > 0),
            action       TEXT        NOT NULL CHECK (action IN ('ENTRY', 'EXIT')),
            status       TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            closed_at    TIMESTAMPTZ,
            close_reason TEXT        CHECK (close_reason IN ({reasons})),
            PRIMARY KEY (strategy_id, plan_number),
            CHECK ((status = 'closed') = (closed_at IS NOT NULL)),
            CHECK ((status = 'closed') = (close_reason IS NOT NULL))
        )
        """
    )
    op.execute(f"CREATE UNIQUE INDEX {OPEN_INDEX} ON {PLANS} (strategy_id) WHERE status = 'open'")
    op.execute(
        f"""
        CREATE TABLE {ORDERS} (
            strategy_id      BIGINT        NOT NULL,
            plan_number      INTEGER       NOT NULL,
            leg_index        INTEGER       NOT NULL CHECK (leg_index >= 0),
            tag              TEXT          NOT NULL UNIQUE CHECK (tag ~ '^[0-9A-Za-z]{{1,20}}$'),
            instrument_id    TEXT          NOT NULL CHECK (instrument_id <> ''),
            tradingsymbol    TEXT          NOT NULL CHECK (tradingsymbol <> ''),
            transaction_type TEXT          NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
            quantity         INTEGER       NOT NULL CHECK (quantity > 0),
            price            NUMERIC(14,2) NOT NULL CHECK (price > 0),
            filled_quantity  INTEGER       CHECK (filled_quantity IS NULL OR filled_quantity BETWEEN 0 AND quantity),
            PRIMARY KEY (strategy_id, plan_number, leg_index),
            FOREIGN KEY (strategy_id, plan_number) REFERENCES {PLANS} (strategy_id, plan_number),
            CHECK (tag = 'OFS' || strategy_id || 'V' || plan_number || 'L' || leg_index)
        )
        """
    )
    op.execute(_plan_guard_sql())
    op.execute(_order_guard_sql())
    op.execute(f"CREATE TRIGGER {PLAN_TRIGGER} BEFORE UPDATE OR DELETE ON {PLANS} "
               f"FOR EACH ROW EXECUTE FUNCTION {PLAN_GUARD}()")
    op.execute(f"CREATE TRIGGER {ORDER_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {ORDERS} "
               f"FOR EACH ROW EXECUTE FUNCTION {ORDER_GUARD}()")
    for guard in (PLAN_GUARD, ORDER_GUARD):
        op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
    for table in (PLANS, ORDERS):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'GRANT SELECT, INSERT ON TABLE {table} TO "{role}"')
    op.execute(f'GRANT UPDATE (status, close_reason) ON TABLE {PLANS} TO "{role}"')
    op.execute(f'GRANT UPDATE (filled_quantity) ON TABLE {ORDERS} TO "{role}"')
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Order intent is a record of what a basket was built from: refuse rather than drop it.
    op.execute(
        f"""
        DO $down$
        BEGIN
            EXECUTE 'LOCK TABLE {PLANS}, {ORDERS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {PLANS}) THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: execution plans are stored';
            END IF;
        END
        $down$;
        """  # noqa: S608 constant table name
    )
    op.execute(f"DROP TABLE {ORDERS}")
    op.execute(f"DROP TABLE {PLANS}")
    op.execute(f"DROP FUNCTION {ORDER_GUARD}()")
    op.execute(f"DROP FUNCTION {PLAN_GUARD}()")
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
