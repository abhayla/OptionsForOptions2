"""PostgreSQL store of the paper order book (GC-TP step 1a; REQ-109 AC-4; ADR-207). Schema: migration 0028.

- place: under the strategy's row lock (one writer per strategy), inserts the orders in the given order. Another user's
  strategy answers NOT_FOUND exactly like a missing one. An order of kind exit / settle / stop must REDUCE the open
  quantity of its contract and never exceed it (EXIT_EXCEEDS_OPEN, nothing stored); the check runs on the book as
  stored plus the earlier orders of the same call, through the one engine (ofo.tracking.orderbook). Insert-only; the
  caller commits.
- load: the orders of one strategy the caller already loaded for its user, in placement order (the id).
- load_all: every order of ONE user's visible strategies with name and underlying, in ONE query whatever the count
  (finding F-3: a per-strategy loop cost 12 s). The user filter is the strategies table's owner column.
The prices come only from the server's live read or the migration; this store takes no price from a request.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.tracking.orderbook import PaperOrder, net_positions
from sqlalchemy import text

from ofo_app import strategy_store as store

EXIT_EXCEEDS_OPEN = "exit_exceeds_open"
REDUCING_KINDS = frozenset({"exit", "settle", "stop"})

_COLUMNS = "id, strategy_id, contract_id, side, quantity, price, kind, placed_at, created_at, reason, trigger_id"
_INSERT = text(
    "INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at, reason, "
    "trigger_id) VALUES (:strategy_id, :contract_id, :side, :quantity, :price, :kind, :placed_at, :reason, "
    ":trigger_id)")
_SELECT = text(f"SELECT {_COLUMNS} FROM public.paper_orders "  # noqa: S608 constant columns
               "WHERE strategy_id = :id ORDER BY id")
_SELECT_USER = text(
    "SELECT o.id, o.strategy_id, o.contract_id, o.side, o.quantity, o.price, o.kind, o.placed_at, o.created_at, "
    "o.reason, o.trigger_id, s.name, s.underlying FROM public.paper_orders AS o "
    "JOIN public.strategies AS s ON s.id = o.strategy_id "
    "WHERE s.user_ref = :user_ref AND s.deleted_at IS NULL ORDER BY o.strategy_id, o.id")


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


def _check_reducing(book: list[PaperOrder], order: PaperOrder) -> None:
    if order.kind not in REDUCING_KINDS:
        return
    net = 0
    if book:
        found = [p for p in net_positions(book, {}).positions if p.instrument_id == order.instrument_id]
        net = found[0].net_quantity if found else 0
    reduces = (net > 0 and order.side == "SELL") or (net < 0 and order.side == "BUY")
    if not reduces or order.quantity > abs(net):
        raise store.StrategyStoreError(EXIT_EXCEEDS_OPEN, f"contract {order.instrument_id}: a {order.kind} of "
                                                          f"{order.side} {order.quantity} against an open {net}")


async def place(conn: Any, user_ref: str, strategy_id: int, orders: Sequence[NewOrder]) -> tuple[StoredOrder, ...]:
    """Stores ``orders`` in order (module docstring) and returns the whole book as stored."""
    if not orders:
        raise ValueError("place needs at least one order")
    paper = [o.as_paper() for o in orders]  # refuses a bad side, kind, quantity or price before any write
    async with conn.begin_nested():
        await store.lock_strategy(conn, user_ref, strategy_id)  # NOT_FOUND for a missing or another user's strategy
        book = [o.order.as_paper() for o in await load(conn, strategy_id)]
        for new in paper:
            _check_reducing(book, new)
            book.append(new)
        for o in orders:
            await conn.execute(_INSERT, {"strategy_id": strategy_id, "contract_id": o.contract_id, "side": o.side,
                                         "quantity": o.quantity, "price": o.price, "kind": o.kind,
                                         "placed_at": o.placed_at, "reason": o.reason, "trigger_id": o.trigger_id})
    return await load(conn, strategy_id)


async def load(conn: Any, strategy_id: int) -> tuple[StoredOrder, ...]:
    return tuple(_row(r) for r in (await conn.execute(_SELECT, {"id": strategy_id})).all())


async def load_all(conn: Any, user_ref: str) -> list[UserBook]:
    """Every paper book of ``user_ref``'s visible strategies, oldest strategy first, in one query. A read failure
    raises: the caller refuses the whole list, never a partial one."""
    heads: dict[int, tuple[str | None, str]] = {}
    orders: dict[int, list[StoredOrder]] = {}
    for r in (await conn.execute(_SELECT_USER, {"user_ref": user_ref})).all():
        sid = int(r.strategy_id)
        heads.setdefault(sid, (r.name, r.underlying))
        orders.setdefault(sid, []).append(_row(r))
    return [UserBook(sid, name, underlying, tuple(orders[sid])) for sid, (name, underlying) in heads.items()]
