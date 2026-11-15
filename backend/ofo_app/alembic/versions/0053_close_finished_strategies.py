"""Strategy store: a draft whose paper book was fully exited or settled BEFORE 0049 is stored as 'closed' (GC-ICFIX).

Spec basis: ADR-259 ("closed (exited, stopped, conditionally exited or settled at expiry) is completed"); REQ-109 AC-7
(expiry settlement); audit C13 / ADR-282 (0049: ``paper_store.place`` stores 'closed' when a reducing order leaves every
contract flat). 0049 widened the CHECK and the guard but did not touch rows that were already flat: they stayed 'draft'
(the list reads that as "Running"), and the settle job never revisits them because nothing is left to settle.

Change (data only, one transaction, one UPDATE): status 'draft' -> 'closed' for every strategy that
- is deleted or not (ADR-293 Undo brings a deleted strategy back; a finished one must not return as "Running"),
- has at least one paper order of a reducing kind (exit / settle / stop: ``paper_store.REDUCING_KINDS``) and a net
  quantity of 0 on every contract (BUY +quantity, SELL -quantity; the same sum ``net_positions`` makes), and
- has no real broker order: no ``execution_plans`` row and no ``adopted_holdings`` row (real positions are closed by the
  reconciliation, not by the paper book).
Rows already 'closed' are not in the WHERE (a second run changes 0 rows). ``paper_store._CLOSE`` sets ``status`` only,
so this sets ``status`` only: no closed time exists to copy, and the guard (0049) allows exactly this one transition.

The kinds are written as literals because a migration is frozen text; a test fails when ``REDUCING_KINDS`` in the code
differs from ``REDUCING_KINDS`` here.

downgrade: nothing to undo. After this change a repaired row cannot be told apart from one closed by the store, and
reopening a finished strategy is refused by the guard anyway. It ends with the allow-list post check.

Revision ID: 0053_close_finished_strategies
Revises: 0052_strategy_held_entries
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0053_close_finished_strategies"
down_revision = "0052_strategy_held_entries"
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


_BASE = _load("0049_strategy_closed_status.py", "ofo_migration_0049_for_0053")._BASE

#: copy of ``ofo_app.paper_store.REDUCING_KINDS`` (a test compares the two)
REDUCING_KINDS = ("exit", "settle", "stop")
_KINDS = ", ".join(f"'{k}'" for k in REDUCING_KINDS)


def close_sql() -> str:
    return f"""
        UPDATE public.strategies AS s SET status = 'closed'
        WHERE s.status = 'draft'
          AND EXISTS (SELECT 1 FROM public.paper_orders AS r WHERE r.strategy_id = s.id AND r.kind IN ({_KINDS}))
          AND NOT EXISTS (SELECT 1 FROM public.paper_orders AS o WHERE o.strategy_id = s.id
                          GROUP BY o.contract_id
                          HAVING SUM(CASE WHEN o.side = 'BUY' THEN o.quantity ELSE -o.quantity END) <> 0)
          AND NOT EXISTS (SELECT 1 FROM public.execution_plans AS p WHERE p.strategy_id = s.id)
          AND NOT EXISTS (SELECT 1 FROM public.adopted_holdings AS h WHERE h.strategy_id = s.id)
        """  # noqa: S608 - constants only


def upgrade() -> None:
    op.execute(close_sql())
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{_BASE._app_role()}', 'post')")


def downgrade() -> None:
    # no-op by design (module docstring): a repaired row cannot be told apart from one the store closed
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{_BASE._app_role()}', 'post')")
