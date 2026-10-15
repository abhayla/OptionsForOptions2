"""The charges calculator: exact Decimal, no rounding at order level (ADR-082, F-35).

Per order (premium = price x quantity): brokerage (flat per order), STT (SELL only, on premium), exchange transaction
(per segment, on premium), SEBI (on premium), stamp duty (BUY only, on premium), GST on brokerage + SEBI + transaction.
Kite's order-level reply shows stamp 0 on every buy; the rate is applied anyway (F-35: contract-note rounding
unmeasured until the 4b order).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ofo.charges.rates import ChargeRates

SIDES = ("BUY", "SELL")
MAX_QUANTITY = 10_000_000  # absurd-size cap (a lot is 65 units; this is ~150,000 lots)
MAX_PRICE = Decimal("100000000")


def _money(name: str, value: object, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a Decimal built from a string, got {type(value).__name__}")
    if not value.is_finite() or value < 0 or value > MAX_PRICE or (positive and value == 0):
        raise ValueError(f"{name} must be a finite Decimal {'above' if positive else 'from'} 0 up to {MAX_PRICE}, "
                         f"got {value}")
    return value


def _quantity(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"quantity must be an int, got {type(value).__name__}")
    if value <= 0 or value > MAX_QUANTITY:
        raise ValueError(f"quantity must be between 1 and {MAX_QUANTITY}, got {value}")
    return value


@dataclass(frozen=True)
class ChargeOrder:
    segment: str  # NSE_FO / BSE_FO
    side: str  # BUY / SELL
    quantity: int  # units (lots x lot size)
    price: Decimal

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"side must be one of {SIDES}, got {self.side!r}")
        if not isinstance(self.segment, str):
            raise ValueError("segment must be a string")
        _quantity(self.quantity)
        _money("price", self.price, positive=True)


@dataclass(frozen=True)
class OrderCharges:
    brokerage: Decimal
    stt: Decimal
    exchange_transaction: Decimal
    sebi: Decimal
    stamp: Decimal
    gst: Decimal
    total: Decimal


@dataclass(frozen=True)
class StrategyCharges:
    orders: tuple[OrderCharges, ...]
    total: Decimal


def charges_for_order(order: ChargeOrder, rates: ChargeRates) -> OrderCharges:
    if order.segment not in rates.transaction_rates:
        raise ValueError(f"unknown exchange segment {order.segment!r}: no rate, none is assumed")
    premium = order.price * order.quantity
    brokerage = rates.brokerage_per_order
    stt = premium * rates.stt_sell_rate if order.side == "SELL" else Decimal("0")
    transaction = premium * rates.transaction_rates[order.segment]
    sebi = premium * rates.sebi_rate
    stamp = premium * rates.stamp_buy_rate if order.side == "BUY" else Decimal("0")
    gst = (brokerage + sebi + transaction) * rates.gst_rate
    total = brokerage + stt + transaction + sebi + stamp + gst
    return OrderCharges(brokerage, stt, transaction, sebi, stamp, gst, total)


def charges_for_orders(orders: list[ChargeOrder] | tuple[ChargeOrder, ...], rates: ChargeRates) -> StrategyCharges:
    if not orders:
        raise ValueError("no orders: a strategy total needs at least one order")
    per_order = tuple(charges_for_order(o, rates) for o in orders)
    return StrategyCharges(per_order, sum((c.total for c in per_order), Decimal("0")))


def exercise_stt(intrinsic_per_unit: Decimal, quantity: int, rates: ChargeRates) -> Decimal:
    """STT on a BOUGHT option that finishes in the money and is exercised: rate x intrinsic value x quantity."""
    _money("intrinsic_per_unit", intrinsic_per_unit)
    _quantity(quantity)
    return intrinsic_per_unit * quantity * rates.stt_exercise_rate
