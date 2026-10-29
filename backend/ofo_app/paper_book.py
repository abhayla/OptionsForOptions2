"""Read-only leaf of the paper order book (GC-CLEAN 2026-10-30; GC-TP step 1a, REQ-109 AC-4; REQ-073 AC-6).

The order-book row types and the owner-checked read live here, with NO import of ``strategy_store``: that store
reaches the order modules (``execute_plan``, ``execution_plan_store``), so the outcome route, which must reach order
code only through pinned edges, reads a strategy's booked P&L through this module instead of ``paper_store``.

- load_owned: one strategy's orders in placement order, only when the strategy is ``user_ref``'s and not deleted (the
  owner check is in the query, the same filter as ``strategy_store.load``); another user's or a missing strategy
  reads as no orders.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.tracking.orderbook import PaperOrder
from sqlalchemy import text

_COLUMNS = "id, strategy_id, contract_id, side, quantity, price, kind, placed_at, created_at, reason, trigger_id"
_SELECT_OWNED = text(
    "SELECT o.id, o.strategy_id, o.contract_id, o.side, o.quantity, o.price, o.kind, o.placed_at, o.created_at, "
    "o.reason, o.trigger_id FROM public.paper_orders AS o JOIN public.strategies AS s ON s.id = o.strategy_id "
    "WHERE o.strategy_id = :id AND s.user_ref = :user_ref AND s.deleted_at IS NULL ORDER BY o.id")


@dataclass(frozen=True)
class NewOrder:
    contract_id: int
    side: str
    quantity: int
    price: Decimal
    kind: str
    placed_at: datetime.datetime
    reason: str | None = None
    trigger_id: int | None = None

    def as_paper(self) -> PaperOrder:
        """The engine's view (validates side, kind, quantity and the paisa price); the contract id is the key."""
        return PaperOrder(str(self.contract_id), self.side, self.quantity, self.price, self.kind, self.placed_at)


@dataclass(frozen=True)
class StoredOrder:
    id: int
    strategy_id: int
    order: NewOrder
    created_at: datetime.datetime


@dataclass(frozen=True)
class UserBook:
    strategy_id: int
    name: str | None
    underlying: str
    orders: tuple[StoredOrder, ...]


def _row(r: Any) -> StoredOrder:
    return StoredOrder(int(r.id), int(r.strategy_id),
                       NewOrder(int(r.contract_id), r.side, int(r.quantity), r.price, r.kind, r.placed_at, r.reason,
                                None if r.trigger_id is None else int(r.trigger_id)), r.created_at)


async def load_owned(conn: Any, user_ref: str, strategy_id: int) -> tuple[StoredOrder, ...]:
    rows = (await conn.execute(_SELECT_OWNED, {"id": strategy_id, "user_ref": user_ref})).all()
    return tuple(_row(r) for r in rows)
