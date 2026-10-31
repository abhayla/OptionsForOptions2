"""REQ-156 AC-2 (ADR-008): the money figures of the approach compare's "money now" and "reward after" rows.

The one engine owns every rupee figure, so the compare (``ofo.adjustment.compare``) reads these and only words them.
Every input is exact Decimal; quantities are units (lots x lot size).

- ``trade_credit``: the approach's own trades at their planned prices, SELL +, BUY - (no trade: 0).
- ``cost_with_spread``: this adjustment's own charges plus half the bid-ask spread of each traded contract times its
  quantity (the cost of trading at bid or ask rather than mid).
- ``margin_change``: the After's basket margin minus the current legs'.
- ``closed_booked``: the P&L booked by the legs an approach closes, at their planned exit prices.
- ``premium_left``: short legs' current price x quantity minus long legs' (the premium still left to earn).
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from ofo.money import PAISE

_SIGN = {"SELL": 1, "BUY": -1}


def _sign(side: str) -> int:
    try:
        return _SIGN[side]
    except KeyError:
        raise ValueError(f"side must be BUY or SELL, got {side!r}") from None


def trade_credit(trades: Iterable[tuple[str, Decimal, int]]) -> Decimal:
    """(action, price, quantity) per trade -> net credit (+) or debit (-)."""
    return sum((price * quantity * _sign(action) for action, price, quantity in trades), Decimal(0))


def cost_with_spread(charges: Decimal, quotes: Iterable[tuple[Decimal, Decimal, int]]) -> Decimal:
    """``charges`` plus (ask - bid) / 2 x quantity for each (bid, ask, quantity) traded."""
    return charges + sum(((ask - bid) / 2 * quantity for bid, ask, quantity in quotes), Decimal(0))


def margin_change(after: Decimal, before: Decimal) -> Decimal:
    return after - before


def closed_booked(legs: Iterable[tuple[str, Decimal, Decimal, int]]) -> Decimal:
    """(side, entry, planned exit, quantity) per leg the approach closes -> the P&L it books: (exit - entry) x
    quantity, + for a BUY leg, - for a SELL leg (nothing closed: 0)."""
    return sum(((exit_ - entry) * quantity * -_sign(side) for side, entry, exit_, quantity in legs), Decimal(0))


def with_booked(booked: Decimal, figure: Decimal) -> Decimal:
    """A P&L figure of the open legs plus the P&L already booked."""
    return booked + figure


def pnl_now(booked: Decimal, legs: Iterable[tuple[str, Decimal, Decimal, int]]) -> Decimal:
    """Booked P&L plus the open legs marked at their current price: ``booked`` + ``closed_booked(legs)`` over
    (side, entry, current price, quantity). A missing booked figure or price is the caller's to refuse."""
    return with_booked(booked, closed_booked(legs))


def adjustment_cost(spreads: Iterable[tuple[Decimal, Decimal, int]], per_leg_charge: Decimal) -> Decimal:
    """(bid, ask, quantity) per open leg -> sum of (ask - bid) x quantity + ``per_leg_charge`` for each leg."""
    return sum(((ask - bid) * quantity + per_leg_charge for bid, ask, quantity in spreads), Decimal(0))


def premium_left(legs: Iterable[tuple[str, Decimal, int]]) -> Decimal:
    """(side, current price, quantity) per open leg -> shorts' value minus longs' value."""
    return sum((price * quantity * _sign(side) for side, price, quantity in legs), Decimal(0))


SELL_MARGIN_RATE = Decimal("0.12")  # TEST DATA ONLY: a stand-in rate, not Zerodha's SPAN


def stand_in_basket_margin(legs: Iterable[tuple[str, Decimal, int]]) -> Decimal:
    """TEST DATA, not Zerodha's SPAN (scenario mode only): (side, strike for a SELL / premium for a BUY, quantity) per
    leg -> SELL strike x quantity x 0.12 minus BUY premium x quantity, floored at 0, to the paisa."""
    total = Decimal(0)
    for side, figure, quantity in legs:
        total += figure * quantity * SELL_MARGIN_RATE if _sign(side) == 1 else -(figure * quantity)
    return max(total, Decimal(0)).quantize(PAISE)
