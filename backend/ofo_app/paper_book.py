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

COLUMNS = "id, strategy_id, contract_id, side, quantity, price, kind, placed_at, created_at, reason, trigger_id"
_SELECT_OWNED = text(
    "SELECT o.id, o.strategy_id, o.contract_id, o.side, o.quantity, o.price, o.kind, o.placed_at, o.created_at, "
    "o.reason, o.trigger_id FROM public.paper_orders AS o JOIN public.strategies AS s ON s.id = o.strategy_id "
    "WHERE o.strategy_id = :id AND s.user_ref = :user_ref AND s.deleted_at IS NULL ORDER BY o.id")
_SELECT_OWNED_MANY = text(
    "SELECT o.id, o.strategy_id, o.contract_id, o.side, o.quantity, o.price, o.kind, o.placed_at, o.created_at, "
    "o.reason, o.trigger_id FROM public.paper_orders AS o JOIN public.strategies AS s ON s.id = o.strategy_id "
    "WHERE o.strategy_id = ANY(CAST(:ids AS BIGINT[])) AND s.user_ref = :user_ref AND s.deleted_at IS NULL "
    "ORDER BY o.id")


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
    status: str = "draft"  # the row's stored status (draft | closed): with the orders, the status word's input


def order_from_row(r: Any) -> StoredOrder:
    return StoredOrder(int(r.id), int(r.strategy_id),
                       NewOrder(int(r.contract_id), r.side, int(r.quantity), r.price, r.kind, r.placed_at, r.reason,
                                None if r.trigger_id is None else int(r.trigger_id)), r.created_at)


async def load_owned(conn: Any, user_ref: str, strategy_id: int) -> tuple[StoredOrder, ...]:
    rows = (await conn.execute(_SELECT_OWNED, {"id": strategy_id, "user_ref": user_ref})).all()
    return tuple(order_from_row(r) for r in rows)


async def load_owned_many(conn: Any, user_ref: str, strategy_ids: list[int]) -> dict[int, tuple[StoredOrder, ...]]:
    """``load_owned`` for many strategies in ONE query: same owner filter, same order (by order id) within each
    strategy. Ids that are not ``user_ref``'s, deleted, missing or without orders are absent from the result."""
    if not strategy_ids:
        return {}
    rows = (await conn.execute(_SELECT_OWNED_MANY, {"ids": list(strategy_ids), "user_ref": user_ref})).all()
    out: dict[int, list[StoredOrder]] = {}
    for r in rows:
        out.setdefault(int(r.strategy_id), []).append(order_from_row(r))
    return {sid: tuple(v) for sid, v in out.items()}


_SELECT_PLAN = text("SELECT definition -> 'legs' AS legs FROM public.strategies "
                    "WHERE id = :id AND user_ref = :user_ref AND deleted_at IS NULL")


async def load_plan_owned(conn: Any, user_ref: str, strategy_id: int) -> list[dict[str, Any]] | None:
    """GC-ICLIVE-B D-15: the legs of the plan this strategy was saved with (contract id, action, units, planned entry
    price), only when the strategy is ``user_ref``'s and not deleted (the owner check is in the query). None when it is
    not found; a leg saved without an entry price has no ``planned_entry`` key."""
    row = (await conn.execute(_SELECT_PLAN, {"id": strategy_id, "user_ref": user_ref})).one_or_none()
    return None if row is None or not isinstance(row.legs, list) else row.legs
