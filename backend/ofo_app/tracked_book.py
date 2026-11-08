"""A real Zerodha strategy's book as tracking reads it (ADR-275, ADR-276): READ ONLY, and it imports no order module.

REQ-073 AC-6: the background worker, the paper book and the tracking routes reach no order door (pinned by
``tests_app/test_order_closure_all_routes.py`` and ``tests_app/test_paper_order_door.py``). So this module does not
import ``execution_plan_store``, ``order_book_store`` or ``execute_plan``: it reads the stored trades and adopted
holdings with three plain SELECTs and checks every value itself (the stores' own checks are not on this path).

- ``real_book``: the owner check, then one row per stored Zerodha trade and per adopted holding, as the paper book's
  ``NewOrder`` rows, so the ONE netter (``net_positions``) answers for paper and real alike. Not this user's strategy
  (or no such strategy, or deleted) -> None; nothing traded -> ().
- ``real_orders`` (pure): a trade is placed at its plan's creation time (a trade row has no time of its own); the
  strategy's first filled ENTRY plan opens, a later ENTRY adds, an EXIT exits; an adopted holding opens at its
  adoption time. Fails closed (``RealBookUnreadable``, tracking answers "not available", never a guessed leg): a
  contract with no live id, a row that is not exact (side, whole positive quantity, Decimal price), or an adopted
  average finer than a paisa (ADR-126 keeps Zerodha's decimals; the netter takes whole paise, #673).
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.instruments.models import InstrumentId
from ofo.money import PAISE
from sqlalchemy import text

from ofo_app import catalogue_store
from ofo_app.paper_book import NewOrder

_SIDES = ("BUY", "SELL")
_OWNED = text("SELECT 1 FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL")
_FILLS = text(
    "SELECT p.plan_number, p.action, p.created_at, o.instrument_id, o.transaction_type, f.quantity, f.price "
    "FROM public.execution_plan_fills f JOIN public.execution_plan_orders o ON o.tag = f.tag "
    "JOIN public.execution_plans p ON p.strategy_id = o.strategy_id AND p.plan_number = o.plan_number "
    "WHERE o.strategy_id = :s ORDER BY p.plan_number, f.tag, f.broker_order_id, f.trade_id")
_HELD = text("SELECT instrument_id, transaction_type, quantity, average_price, reference, adopted_at "
             "FROM public.adopted_holdings WHERE strategy_id = :s ORDER BY id")


class RealBookUnreadable(ValueError):
    """A real strategy's book cannot become orders exactly (tracking answers "not available", no leg guessed)."""


@dataclass(frozen=True)
class FillRow:
    """One stored Zerodha trade with its plan's number, action and creation time."""

    plan_number: int
    action: str
    placed_at: datetime.datetime
    instrument_id: str
    side: str
    quantity: int
    price: Decimal


@dataclass(frozen=True)
class HeldRow:
    """One adopted holding (ADR-096)."""

    instrument_id: str
    side: str
    quantity: int
    average_price: Decimal
    reference: str
    adopted_at: datetime.datetime | None


def instrument_key(text_id: str) -> InstrumentId:
    """A stored plan / adopted ``instrument_id`` ("NSE_FO:51392") as the exchange identity."""
    segment, token = text_id.split(":")
    return InstrumentId(segment, int(token))


def _exact(side: object, quantity: object, price: object, what: str) -> None:
    if side not in _SIDES or type(quantity) is not int or quantity <= 0 \
            or not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise RealBookUnreadable(f"{what}: a stored row is not exact")


def real_orders(fills: Sequence[FillRow], held: Sequence[HeldRow],
                contract_of: Mapping[str, int]) -> tuple[NewOrder, ...]:
    """The rows as the paper book's orders, oldest first (module docstring)."""
    def contract(instrument_id: str) -> int:
        if instrument_id not in contract_of:
            raise RealBookUnreadable(f"{instrument_id} has no live contract")
        return contract_of[instrument_id]

    entries = [f.plan_number for f in fills if f.action == "ENTRY"]
    first = min(entries) if entries else None
    out: list[NewOrder] = []
    for f in fills:
        _exact(f.side, f.quantity, f.price, f"plan {f.plan_number}")
        kind = "exit" if f.action == "EXIT" else "open" if f.plan_number == first else "add"
        out.append(NewOrder(contract(f.instrument_id), f.side, f.quantity, f.price, kind, f.placed_at))
    for h in held:
        _exact(h.side, h.quantity, h.average_price, f"adopted {h.reference}")
        if h.average_price != h.average_price.quantize(PAISE) or h.adopted_at is None:
            raise RealBookUnreadable(f"adopted {h.reference}: average {h.average_price} or its time is not usable")
        out.append(NewOrder(contract(h.instrument_id), h.side, h.quantity, h.average_price, "open", h.adopted_at))
    return tuple(sorted(out, key=lambda o: o.placed_at))


async def real_book(conn: Any, user_ref: str, strategy_id: int) -> tuple[NewOrder, ...] | None:
    """``real_orders`` over the strategy's stored trades and adopted holdings; None when not this user's strategy."""
    if (await conn.execute(_OWNED, {"s": strategy_id, "u": user_ref})).first() is None:
        return None
    fills = [FillRow(int(r.plan_number), r.action, r.created_at, r.instrument_id, r.transaction_type, r.quantity,
                     r.price) for r in (await conn.execute(_FILLS, {"s": strategy_id})).all()]
    held = [HeldRow(r.instrument_id, r.transaction_type, r.quantity, r.average_price, r.reference, r.adopted_at)
            for r in (await conn.execute(_HELD, {"s": strategy_id})).all()]
    ids = {f.instrument_id for f in fills} | {h.instrument_id for h in held}
    live = await catalogue_store.live_contract_ids(conn, [instrument_key(i) for i in ids])
    return real_orders(fills, held, {i: live[instrument_key(i)] for i in ids if instrument_key(i) in live})


__all__ = ["FillRow", "HeldRow", "RealBookUnreadable", "instrument_key", "real_book", "real_orders"]
