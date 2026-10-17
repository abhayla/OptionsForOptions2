"""The cost of one basket before it is sent (W-102): the net premium and the charges, exact Decimal.

Spec basis: ADR-097 ("the owner gives a final yes on the exact contract, side, quantity, limit price and cost");
REQ-056 AC-8 (the order plan carries margin and charges). One engine owns every money number (ADR-008): the charges come
from ``ofo.charges.calculator`` (never re-derived here) and the browser computes nothing.

Each order's premium is quantity x LIMIT price, signed by side: a BUY pays (negative), a SELL receives (positive). The
orders are ``ChargeOrder`` values, so side, quantity and price are already validated by the calculator's own type (a
side outside BUY/SELL, a quantity of 0 or below, a price of 0 or below, or a float is refused there). No rounding here:
the API boundary quantizes to the paisa.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from ofo.charges.calculator import ChargeOrder, charges_for_orders
from ofo.charges.rates import ChargeRates
from ofo.engine.legs import Action

#: The sign of each side's premium: an allow-list (a side outside it raises, never defaults to a sign).
_SIGN = {Action.BUY.value: Decimal(-1), Action.SELL.value: Decimal(1)}


@dataclass(frozen=True)
class BasketCost:
    net_premium: Decimal  # negative = paid, positive = received
    charges: Decimal | None  # None = no rate set: the charges are NOT included anywhere


def signed_premium(order: ChargeOrder) -> Decimal:
    """quantity x LIMIT price, negative for a BUY (paid), positive for a SELL (received)."""
    if type(order) is not ChargeOrder:
        raise ValueError(f"an order must be a ChargeOrder, got {type(order).__name__}")
    if order.side not in _SIGN:
        raise ValueError(f"side must be one of {sorted(_SIGN)}, got {order.side!r}")
    return _SIGN[order.side] * order.price * order.quantity


def basket_cost(orders: Sequence[ChargeOrder], rates: ChargeRates | None) -> BasketCost:
    """The basket's net premium and, when a rate set is given, its charges total from the one calculator."""
    orders = tuple(orders)
    if not orders:
        raise ValueError("no orders: a basket cost needs at least one order")
    if rates is not None and type(rates) is not ChargeRates:
        raise ValueError(f"rates must be a ChargeRates or None, got {type(rates).__name__}")
    net = sum((signed_premium(o) for o in orders), Decimal(0))
    charges = None if rates is None else charges_for_orders(orders, rates).total
    return BasketCost(net, charges)


__all__ = ["BasketCost", "basket_cost", "signed_premium"]
