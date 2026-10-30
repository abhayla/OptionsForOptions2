"""REQ-156 AC-2 (ADR-008): the money figures of the approach compare's "money now" and "reward after" rows.

The one engine owns every rupee figure, so the compare (``ofo.adjustment.compare``) reads these and only words them.
Every input is exact Decimal; quantities are units (lots x lot size).

- ``trade_credit``: the approach's own trades at their planned prices, SELL +, BUY - (no trade: 0).
- ``cost_with_spread``: this adjustment's own charges plus half the bid-ask spread of each traded contract times its
  quantity (the cost of trading at bid or ask rather than mid).
- ``margin_change``: the After's basket margin minus the current legs'.
- ``premium_left``: short legs' current price x quantity minus long legs' (the premium still left to earn).
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

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


def premium_left(legs: Iterable[tuple[str, Decimal, int]]) -> Decimal:
    """(side, current price, quantity) per open leg -> shorts' value minus longs' value."""
    return sum((price * quantity * _sign(side) for side, price, quantity in legs), Decimal(0))
