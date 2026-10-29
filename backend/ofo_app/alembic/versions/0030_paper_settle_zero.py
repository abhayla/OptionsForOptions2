"""A paper `settle` order may carry a price of 0, and a contract settles once per strategy (GC-TP step 5b).

Basis: REQ-109 AC-7 ("settles with a "settle" order at its intrinsic value from the official closing value of its index
that day"): an out-of-the-money option's intrinsic value is exactly 0, which 0028's CHECK (price > 0) refuses. No fake
0.05 price: the book would then show a loss or gain of 0.05 x quantity that never happened.

Copy from: none - the smallest change on 0028's table. No grant, guard or allow-list change: the allow-list checks
grants, guards and sequences, none of which move here; the 'pre' and 'post' calls still bracket the change.

Changes (owner-run, one transaction, the API stopped):
- public.paper_orders: the price CHECK becomes ``price > 0 OR (kind = 'settle' AND price = 0)`` (every other kind is
  still above 0).
- A unique index ``paper_orders_settle_once`` on (strategy_id, contract_id) WHERE kind = 'settle': two runs or two
  processes can never both settle the same contract of the same strategy (the second insert is refused).
- downgrade: refuses (SQLSTATE OF030) while a 0-price settle order exists (restoring the old CHECK would fail on it, and
  the order is never deleted); otherwise drops the index and restores ``price > 0``.

Revision ID: 0030_paper_settle_zero
Revises: 0029_paper_triggers
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0030_paper_settle_zero"
down_revision = "0029_paper_triggers"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0030")  # 0029
_BASE = _PREVIOUS._BASE

SQLSTATE = "OF030"
ORDERS = "public.paper_orders"
PRICE_CHECK = "paper_orders_price_check"  # PostgreSQL's name for 0028's unnamed column CHECK
SETTLE_ONCE = "paper_orders_settle_once"
NEW_CHECK = "price > 0 OR (kind = 'settle' AND price = 0)"
OLD_CHECK = "price > 0"


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {ORDERS} DROP CONSTRAINT {PRICE_CHECK}")
    op.execute(f"ALTER TABLE {ORDERS} ADD CONSTRAINT {PRICE_CHECK} CHECK ({NEW_CHECK})")
    op.execute(f"CREATE UNIQUE INDEX {SETTLE_ONCE} ON {ORDERS} (strategy_id, contract_id) WHERE kind = 'settle'")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF EXISTS (SELECT 1 FROM {ORDERS} WHERE kind = 'settle' AND price = 0) THEN
                RAISE EXCEPTION 'a paper settle order at a price of 0 exists: the price > 0 rule cannot come back'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $do$
        """  # noqa: S608 - constant names only
    )
    op.execute(f"DROP INDEX public.{SETTLE_ONCE}")
    op.execute(f"ALTER TABLE {ORDERS} DROP CONSTRAINT {PRICE_CHECK}")
    op.execute(f"ALTER TABLE {ORDERS} ADD CONSTRAINT {PRICE_CHECK} CHECK ({OLD_CHECK})")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
