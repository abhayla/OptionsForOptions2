"""Order-book store (#313b): adopted holdings written and read, and a strategy's stored trades read back by tag.

Spec basis: issue #313 ("it must be stored (fills AND adopted holdings, in the same transaction as the strategy
version)"); ADR-096 (a held Zerodha position is added to an existing strategy order-free, as a new strategy version
with no order: "records the held legs (Zerodha's quantity, average price as the entry per ADR-084)"); ADR-109 (2) (a
strategy owns exactly the fills of orders this app placed, matched by tag); ADR-105 (held units = the net over every
stored plan); ADR-008 (money exact: Decimal in, NUMERIC(14,2) stored). Schema: migration 0020_order_book_store.

Copy from: none - new store over the #313a tables, modelled on ``execution_plan_store`` (row lock, id checks, errors).

- record_adopted: under the strategy's row lock (``execution_plan_store``'s lock, held until the caller commits), in
  the transaction that wrote the new strategy version; the version number stored is the strategy's OWN revision read
  under that lock, never a caller's number. Refused before the database: a contract the catalogue cannot name exactly
  once, a contract the strategy already holds (adopted or by its stored plans' net), a reference already used, a price
  with more than 2 decimals (NUMERIC(14,2) would round it), a side/product outside the closed lists.
- adopted_for: the strategy's adopted holdings, oldest first (``execute_plan.held_units`` counts them as fills).
- fills_for: the strategy's stored trades per tag (written by ``execution_plan_store.close_plan``).
Transaction control (commit) stays with the caller. Another user's strategy answers exactly like a missing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from ofo.engine.product import Product
from ofo.money import PAISE
from ofo.strategy.definition import MAX_UNITS
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app.reconciliation_store import MAX_TEXT

NOT_FOUND = "not_found"
BAD_HOLDING = "bad_holding"
ALREADY_HELD = "already_held"
REFERENCE_TAKEN = "reference_taken"

PRODUCTS = tuple(p.value for p in Product)
_HOLDING_KEY = "adopted_holdings_one_per_contract"
_REFERENCE_KEY = "adopted_holdings_reference_key"


class OrderBookError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class AdoptedHolding:
    """Units a strategy holds without a platform fill (ADR-096). ``version_number`` is set by the store (the
    strategy's revision under the lock); a holding passed to ``record_adopted`` carries None there."""

    instrument_id: str
    transaction_type: Literal["BUY", "SELL"]
    quantity: int
    product: str
    average_price: Decimal
    reference: str
    version_number: int | None = None

    def __post_init__(self) -> None:
        self.check()

    def check(self) -> None:
        """Raises OrderBookError(bad_holding) unless every field is valid; record_adopted calls it again."""
        if not isinstance(self.instrument_id, str) or not self.instrument_id:
            raise OrderBookError(BAD_HOLDING, f"instrument_id must be text, got {self.instrument_id!r}")
        if self.transaction_type not in plans.SIDES:
            raise OrderBookError(BAD_HOLDING, f"transaction_type must be BUY or SELL, got {self.transaction_type!r}")
        q = self.quantity
        if isinstance(q, bool) or not isinstance(q, int) or not 1 <= q <= MAX_UNITS:
            raise OrderBookError(BAD_HOLDING, f"quantity must be an integer from 1 to {MAX_UNITS}, got {q!r}")
        if self.product not in PRODUCTS:
            raise OrderBookError(BAD_HOLDING, f"product must be one of {PRODUCTS}, got {self.product!r}")
        px = self.average_price
        if (not isinstance(px, Decimal) or not px.is_finite() or px <= 0 or px >= plans.PRICE_LIMIT
                or px != px.quantize(PAISE)):
            raise OrderBookError(BAD_HOLDING, f"average_price must be a positive Decimal with at most 2 decimals "
                                              f"(NUMERIC(14,2) would round it), got {px!r}")
        ref = self.reference
        if not isinstance(ref, str) or not ref.strip() or ref != ref.strip() or len(ref) > MAX_TEXT:
            raise OrderBookError(BAD_HOLDING, f"reference must be trimmed text of 1..{MAX_TEXT} characters")


_REVISION = text("SELECT revision FROM public.strategies WHERE id = :s")
_HELD = text("SELECT 1 FROM public.adopted_holdings WHERE strategy_id = :s AND instrument_id = :i")
_REFERENCE = text("SELECT 1 FROM public.adopted_holdings WHERE reference = :r")
_INSERT = text(
    "INSERT INTO public.adopted_holdings (strategy_id, instrument_id, transaction_type, quantity, product, "
    "average_price, reference, version_number) VALUES (:s, :i, :side, :q, :product, :px, :ref, :v)")
_ADOPTED = text("SELECT instrument_id, transaction_type, quantity, product, average_price, reference, version_number "
                "FROM public.adopted_holdings WHERE strategy_id = :s ORDER BY id")
_FILLS = text("SELECT f.tag, f.broker_order_id, f.trade_id, f.quantity, f.price FROM public.execution_plan_fills f "
              "JOIN public.execution_plan_orders o ON o.tag = f.tag WHERE o.strategy_id = :s "
              "ORDER BY f.tag, f.broker_order_id, f.trade_id")


async def _locked(conn: Any, user_ref: str, strategy_id: Any) -> int:
    try:
        return await plans.lock_strategy(conn, user_ref, strategy_id)  # the one strategy lock of the plan store
    except plans.PlanStoreError as exc:
        raise OrderBookError(NOT_FOUND, exc.detail) from exc


async def _owned(conn: Any, user_ref: str, strategy_id: Any) -> int:
    try:
        return await plans.owned_strategy(conn, user_ref, strategy_id)  # the plan store's ownership check
    except plans.PlanStoreError as exc:
        raise OrderBookError(NOT_FOUND, exc.detail) from exc


def _row(r: Any) -> AdoptedHolding:
    return AdoptedHolding(instrument_id=r.instrument_id, transaction_type=r.transaction_type, quantity=int(r.quantity),
                          product=r.product, average_price=Decimal(r.average_price), reference=r.reference,
                          version_number=int(r.version_number))


async def record_adopted(conn: Any, user_ref: str, strategy_id: int, holding: AdoptedHolding) -> AdoptedHolding:
    """Stores one adopted holding under the strategy's row lock. Call it in the transaction that wrote the new
    strategy version (ADR-096); the caller commits. Returns the stored row (with the version number it carries)."""
    strategy_id = await _locked(conn, user_ref, strategy_id)
    if not isinstance(holding, AdoptedHolding):
        raise OrderBookError(BAD_HOLDING, f"expected an AdoptedHolding, got {holding!r}")
    holding.check()  # a frozen dataclass can still be forged with object.__setattr__
    if holding.version_number is not None:
        raise OrderBookError(BAD_HOLDING, "the version number is the strategy's own; a holding passed in carries None")
    try:
        await plans.zerodha_symbol(conn, holding.instrument_id)  # exactly one catalogue contract, or refused
    except plans.PlanStoreError as exc:
        raise OrderBookError(BAD_HOLDING, exc.detail) from exc
    if (await conn.execute(_HELD, {"s": strategy_id, "i": holding.instrument_id})).first() is not None:
        raise OrderBookError(ALREADY_HELD, f"strategy {strategy_id} already holds {holding.instrument_id} (adopted)")
    if holding.instrument_id in ep.held_units(await plans.plans_for(conn, user_ref, strategy_id)):
        raise OrderBookError(ALREADY_HELD, f"strategy {strategy_id} already holds {holding.instrument_id} (by fills)")
    if (await conn.execute(_REFERENCE, {"r": holding.reference})).first() is not None:
        raise OrderBookError(REFERENCE_TAKEN, f"reference {holding.reference!r} is already stored")
    version = int((await conn.execute(_REVISION, {"s": strategy_id})).scalar_one())
    try:
        async with conn.begin_nested():
            await conn.execute(_INSERT, {"s": strategy_id, "i": holding.instrument_id,
                                         "side": holding.transaction_type, "q": holding.quantity,
                                         "product": holding.product, "px": holding.average_price,
                                         "ref": holding.reference, "v": version})
    except DBAPIError as exc:
        message = str(exc.orig)
        if _HOLDING_KEY in message:
            raise OrderBookError(ALREADY_HELD, message) from exc
        if _REFERENCE_KEY in message:
            raise OrderBookError(REFERENCE_TAKEN, message) from exc
        raise OrderBookError(BAD_HOLDING, message) from exc
    return next(h for h in await _adopted(conn, strategy_id) if h.reference == holding.reference)


async def _adopted(conn: Any, strategy_id: int) -> tuple[AdoptedHolding, ...]:
    return tuple(_row(r) for r in (await conn.execute(_ADOPTED, {"s": strategy_id})).all())


async def adopted_for(conn: Any, user_ref: str, strategy_id: int) -> tuple[AdoptedHolding, ...]:
    """The strategy's adopted holdings, oldest first."""
    return await _adopted(conn, await _owned(conn, user_ref, strategy_id))


async def fills_for(conn: Any, user_ref: str, strategy_id: int) -> dict[str, tuple[plans.PlanFill, ...]]:
    """The strategy's stored trades per tag, each sorted by (order id, trade id); a tag with no trade is absent."""
    strategy_id = await _owned(conn, user_ref, strategy_id)
    out: dict[str, list[plans.PlanFill]] = {}
    for r in (await conn.execute(_FILLS, {"s": strategy_id})).all():
        out.setdefault(r.tag, []).append(plans.PlanFill(r.tag, r.broker_order_id, r.trade_id, int(r.quantity),
                                                        Decimal(r.price)))
    return {tag: tuple(found) for tag, found in out.items()}


__all__ = ["ALREADY_HELD", "BAD_HOLDING", "NOT_FOUND", "PRODUCTS", "REFERENCE_TAKEN", "AdoptedHolding",
           "OrderBookError", "adopted_for", "fills_for", "record_adopted"]
