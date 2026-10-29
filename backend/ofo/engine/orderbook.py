"""The paper order book: one per paper strategy; the net position per contract comes from its orders (GC-TP 1a).

Spec basis: REQ-109 AC-4 "The one engine derives the net position per contract from the orders"; ADR-207 (paper
trading the Sensibull Draft Portfolio way: Net Positions | Orderbook, Lots / Avg / LTP / Booked / Unbooked, screens
274-279); Positions 050 (booked + unbooked = total).

Rules (Zerodha F&O average-price rule):
- the AVERAGE is the weighted average of the orders that INCREASED the absolute quantity on the current side;
- an order that REDUCES the quantity books (exit - average) x qty for a long, (average - exit) x qty for a short, and
  leaves the average unchanged;
- an order that CROSSES through zero books the closing part and opens the rest at its own price;
- a contract at net 0 has unbooked 0 and only booked.

Exactness (ADR-008): the cost of the open quantity is kept as an exact fraction, so a fractional average (3 buys at
100.00, 100.00, 100.05) never loses a paisa: once a contract is flat its booked P&L equals the orders' cash exactly, and
booked + unbooked == total always. ``total`` (the cash of every order plus the net at the live price) is always a whole
number of paise. ``average`` and a partial ``booked`` are shown as Decimal; they are exact whenever the fraction
terminates and otherwise carry Decimal's 28 significant digits - never rounded to the paisa here (display rounds).
The arithmetic is the engine's leg P&L, BUY (price - entry) x qty, SELL (entry - price) x qty
(ofo.engine.legs.live_pnl); tests/tracking/test_orderbook.py proves it equals ``paper.leg_pnl`` on every real leg.

Answer states: no orders -> refused; a price finer than a paisa (an order or a live price) -> refused; a live price
absent for an open contract -> its unbooked is None and the book's unbooked and total are None (REQ-109 AC-5). Any
paisa price is accepted: legacy entries are captured LTPs (the 0.05 tick rule is for typed orders, step 1b).
A price of 0 is accepted ONLY on a ``settle`` order (GC-TP 5b, REQ-109 AC-7: an out-of-the-money option's intrinsic value at expiry;
migration 0030 allows exactly that in the database); every other kind, and every live price, is above 0.
Standard library only; no clock is read here.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from ofo.money import PAISE

Side = Literal["BUY", "SELL"]
OrderKind = Literal["open", "add", "exit", "settle", "stop"]
SIDES: tuple[Side, ...] = ("BUY", "SELL")
ORDER_KINDS: tuple[OrderKind, ...] = ("open", "add", "exit", "settle", "stop")
SETTLE_KIND: OrderKind = "settle"  # the one kind whose price may be 0 (an option expiring out of the money)


#: REQ-109 AC-1: a typed paper price is above 0, at most this (the price column is NUMERIC(14,2)) and a multiple of
#: the tick. Stored legacy entries are captured LTPs and need only be a paisa (``PaperOrder``); the tick is for typed
#: orders.
TYPED_PRICE_TICK = Decimal("0.05")
TYPED_PRICE_MAX = Decimal("10000000")


def is_typed_price(value: Decimal) -> bool:
    """Whether ``value`` is a price a user may type for a paper order (REQ-109 AC-1)."""
    return (type(value) is Decimal and value.is_finite() and 0 < value <= TYPED_PRICE_MAX
            and value % TYPED_PRICE_TICK == 0)


def _paisa_price(value: Decimal, what: str, *, zero_allowed: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value < 0 or (value == 0 and not zero_allowed):
        raise ValueError(f"{what}: a price must be a finite Decimal above 0, got {value!r}")
    if value != value.quantize(PAISE):
        raise ValueError(f"{what}: a price finer than a paisa cannot be stored exactly: {value}")
    return value


@dataclass(frozen=True)
class PaperOrder:
    instrument_id: str
    side: Side
    quantity: int  # units (lots x lot size), above 0
    price: Decimal  # to the paisa, above 0 (exactly 0 allowed only for kind settle)
    kind: OrderKind
    placed_at: datetime.datetime

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"an order side is BUY or SELL, got {self.side!r}")
        if self.kind not in ORDER_KINDS:
            raise ValueError(f"an order kind is one of {ORDER_KINDS}, got {self.kind!r}")
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError(f"an order quantity is a whole number above 0, got {self.quantity!r}")
        _paisa_price(self.price, self.instrument_id, zero_allowed=self.kind == SETTLE_KIND)

    @property
    def signed(self) -> int:
        return self.quantity if self.side == "BUY" else -self.quantity


def _decimal(value: Fraction) -> Decimal:
    """Exact when the fraction terminates; else Decimal's context precision (28 significant digits)."""
    return Decimal(value.numerator) / Decimal(value.denominator)


@dataclass(frozen=True)
class NetPosition:
    instrument_id: str
    net_quantity: int  # signed: above 0 long, below 0 short, 0 flat
    average: Decimal | None  # None when flat
    booked: Decimal
    unbooked: Decimal | None  # 0 when flat; None when open with no live price (REQ-109 AC-5)
    total: Decimal | None  # booked + unbooked, only when unbooked is known
    last_price: Decimal  # the price of the contract's last order (a flat contract's closing price)
    last_at: datetime.datetime
    first_at: datetime.datetime
    first_side: Side


@dataclass(frozen=True)
class BookView:
    positions: tuple[NetPosition, ...]  # in order of each contract's first order
    booked: Decimal
    unbooked: Decimal | None
    total: Decimal | None
    #: The cash of every order: SELL price x qty in, BUY price x qty out - always a whole number of paise. Equals
    #: booked minus the cost of the open quantity at its exact average (signed), so booked + the open contracts'
    #: P&L at their average entry is ``cash`` + the open contracts' value (ofo.engine.extremes).
    cash: Decimal


class _Running:
    __slots__ = ("booked", "cost", "first", "last", "net")

    def __init__(self, first: PaperOrder) -> None:
        self.net = 0
        self.cost = Fraction(0)  # exact cost of the open quantity (always >= 0)
        self.booked = Fraction(0)
        self.last = first
        self.first = first

    def apply(self, order: PaperOrder) -> None:
        signed = order.signed
        price = Fraction(order.price)
        if self.net == 0 or (self.net > 0) == (signed > 0):
            self.net += signed
            self.cost += price * order.quantity
        else:
            closing = min(order.quantity, abs(self.net))
            average = self.cost / abs(self.net)
            # long: (exit - average) x q; short: (average - exit) x q - the engine's leg P&L at the average entry
            self.booked += (price - average) * closing if self.net > 0 else (average - price) * closing
            self.cost -= average * closing
            self.net += closing if self.net < 0 else -closing
            rest = order.quantity - closing
            if rest:
                self.net = rest if signed > 0 else -rest
                self.cost = price * rest
        self.last = order

    def position(self, live: Decimal | None) -> NetPosition:
        booked = self.booked
        if self.net == 0:
            return NetPosition(self.first.instrument_id, 0, None, _decimal(booked), Decimal(0), _decimal(booked),
                               self.last.price, self.last.placed_at, self.first.placed_at, self.first.side)
        average = self.cost / abs(self.net)
        unbooked: Fraction | None = None
        if live is not None:
            mark = Fraction(_paisa_price(live, self.first.instrument_id))
            unbooked = (mark - average) * self.net  # signed net: a short's sign flips the difference
        total = None if unbooked is None else booked + unbooked
        return NetPosition(self.first.instrument_id, self.net, _decimal(average), _decimal(booked),
                           None if unbooked is None else _exact_split(total, booked),
                           None if total is None else _decimal(total), self.last.price, self.last.placed_at,
                           self.first.placed_at, self.first.side)


def _exact_split(total: Fraction, booked: Fraction) -> Decimal:
    """Unbooked shown so that booked + unbooked == total exactly in Decimal."""
    return _decimal(total) - _decimal(booked)


def net_positions(orders: Sequence[PaperOrder], live_prices: Mapping[str, Decimal]) -> BookView:
    """The net position of every contract in ``orders`` (in placement order), at ``live_prices`` (instrument id ->
    live price; an open contract absent from it has no unbooked figure)."""
    if not orders:
        raise ValueError("a paper order book needs at least one order")
    running: dict[str, _Running] = {}
    for order in orders:
        running.setdefault(order.instrument_id, _Running(order)).apply(order)
    positions = tuple(r.position(live_prices.get(iid)) for iid, r in running.items())
    booked_f = sum((r.booked for r in running.values()), Fraction(0))
    cash = sum((-o.signed * o.price for o in orders), Decimal(0))
    unknown = any(p.unbooked is None for p in positions)
    if unknown:
        return BookView(positions, _decimal(booked_f), None, None, cash)
    total = sum((p.total for p in positions if p.total is not None), Decimal(0))
    booked = _decimal(booked_f)
    return BookView(positions, booked, total - booked, total, cash)
