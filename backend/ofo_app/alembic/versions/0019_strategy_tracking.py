"""Strategy tracking: a paper entry of a saved strategy, one per strategy, insert-only (W-122).

Basis: REQ-109 AC-1 ("It stores a paper entry - each leg's contract, side, quantity and the entry price used ... with the
time and price health. There is no account-wide paper/live switch"); ADR-048 (the limited application role); ADR-023
(the database clock); money NUMERIC(14,2) (decimal-money-boundaries). Exits are a later step (builder scope Step 5):
this revision stores entries only.

Copy from: none - modelled on 0016's tables, guard triggers, grants and allowlist block.

Changes (owner-run, one transaction):
- public.strategy_tracking: PRIMARY KEY (strategy_id) - one tracking per strategy, enforced by the database; the
  strategy revision the entry was taken from; price_health CHECK = 'available' (a start never stores a price that was
  not live, REQ-109 AC-5); prices_at = the time of the oldest leg quote used; started_at from the database clock.
- public.strategy_tracking_legs: PRIMARY KEY (strategy_id, leg_index); contract_id -> catalogue_contracts; side
  BUY/SELL; quantity > 0; entry_price NUMERIC(14,2) > 0; price_at.
- Guard triggers (SQLSTATE OF019): both tables are insert-only (no UPDATE, no DELETE); a leg row only joins an existing
  tracking row (foreign key).
- Grants: the application role gets SELECT and column-limited INSERT on both tables; no UPDATE, DELETE or TRUNCATE.
- public.ofo_assert_app_role_allowlist: 0017's chain text (0018 changed no grant) plus block 16 for the two tables.
- downgrade: refuses while any tracking row is stored (a paper entry is a record); otherwise drops what upgrade made.

Revision ID: 0019_strategy_tracking
Revises: 0018_basket_tag_8
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0019_strategy_tracking"
down_revision = "0018_basket_tag_8"
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


#: The latest revision that publishes the allowlist chain text (0018 changed no grant and publishes none).
_CHAIN = _load("0017_audit_order_prepared.py", "ofo_migration_chain_for_0019")
_M16 = _CHAIN._PREVIOUS  # 0016: the table block helper
_BASE = _CHAIN._BASE  # 0001
_M4 = _CHAIN._M4  # 0004: _md5_body

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF019"
TRACKING = "public.strategy_tracking"
LEGS = "public.strategy_tracking_legs"
TRACKING_GUARD = "public.strategy_tracking_guard"
LEGS_GUARD = "public.strategy_tracking_legs_guard"
TRACKING_TRIGGER = "strategy_tracking_guard"
LEGS_TRIGGER = "strategy_tracking_legs_guard"
TRACKING_INSERT_COLUMNS = ("strategy_id", "strategy_revision", "price_health", "prices_at")
LEGS_INSERT_COLUMNS = ("strategy_id", "leg_index", "contract_id", "side", "quantity", "entry_price", "price_at")
ALLOWLIST_BLOCK_MARKER = "-- 16. strategy tracking"


def _guard_sql(function: str, what: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {function}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION '{what} are insert-only' USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


TRACKING_PIN = _M4._md5_body(_guard_sql(TRACKING_GUARD, "strategy tracking rows"))
LEGS_PIN = _M4._md5_body(_guard_sql(LEGS_GUARD, "strategy tracking legs"))


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-122): strategy_tracking and strategy_tracking_legs: SELECT and column-limited INSERT
    --    exactly as granted, no UPDATE / DELETE / TRUNCATE; the insert-only guards enabled with their pinned bodies
    IF phase = 'post' THEN
{_M16._table_block(TRACKING, "strategy_tracking", TRACKING_INSERT_COLUMNS, (), TRACKING_GUARD, TRACKING_TRIGGER,
                   TRACKING_PIN)}
{_M16._table_block(LEGS, "strategy_tracking_legs", LEGS_INSERT_COLUMNS, (), LEGS_GUARD, LEGS_TRIGGER, LEGS_PIN)}
    END IF;
"""


def previous_allowlist_sql() -> str:
    return _CHAIN.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0017's chain text plus block 16. Fails closed (RuntimeError) on a changed shape or a block 16 already in."""
    previous = previous_allowlist_sql()
    insert_before = _M16._INSERT_BEFORE
    if previous.count(insert_before) != 1 or ALLOWLIST_BLOCK_MARKER in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the strategy tracking checks safely")
    return previous.replace(insert_before, _block() + insert_before, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TRACKING} (
            strategy_id       BIGINT      PRIMARY KEY REFERENCES public.strategies (id),
            strategy_revision INTEGER     NOT NULL CHECK (strategy_revision > 0),
            price_health      TEXT        NOT NULL CHECK (price_health = 'available'),
            prices_at         TIMESTAMPTZ NOT NULL,
            started_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {LEGS} (
            strategy_id BIGINT        NOT NULL REFERENCES {TRACKING} (strategy_id),
            leg_index   INTEGER       NOT NULL CHECK (leg_index >= 0),
            contract_id BIGINT        NOT NULL REFERENCES public.catalogue_contracts (id),
            side        TEXT          NOT NULL CHECK (side IN ('BUY', 'SELL')),
            quantity    INTEGER       NOT NULL CHECK (quantity > 0),
            entry_price NUMERIC(14,2) NOT NULL CHECK (entry_price > 0),
            price_at    TIMESTAMPTZ   NOT NULL,
            PRIMARY KEY (strategy_id, leg_index)
        )
        """
    )
    op.execute(_guard_sql(TRACKING_GUARD, "strategy tracking rows"))
    op.execute(_guard_sql(LEGS_GUARD, "strategy tracking legs"))
    op.execute(f"CREATE TRIGGER {TRACKING_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TRACKING} "
               f"FOR EACH ROW EXECUTE FUNCTION {TRACKING_GUARD}()")
    op.execute(f"CREATE TRIGGER {LEGS_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {LEGS} "
               f"FOR EACH ROW EXECUTE FUNCTION {LEGS_GUARD}()")
    for guard in (TRACKING_GUARD, LEGS_GUARD):
        op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
    for table, insert_cols in ((TRACKING, TRACKING_INSERT_COLUMNS), (LEGS, LEGS_INSERT_COLUMNS)):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
        op.execute(f'GRANT INSERT ({", ".join(insert_cols)}) ON TABLE {table} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # A paper entry is a record of what the user tracked: refuse rather than drop it.
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE 'LOCK TABLE {TRACKING} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {TRACKING}) THEN
                RAISE EXCEPTION 'refusing downgrade: {TRACKING} holds paper entries';
            END IF;
        END
        $$
        """  # noqa: S608 constant table name
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {LEGS}")
    op.execute(f"DROP TABLE {TRACKING}")
    op.execute(f"DROP FUNCTION {LEGS_GUARD}()")
    op.execute(f"DROP FUNCTION {TRACKING_GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
