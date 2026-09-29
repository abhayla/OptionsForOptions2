"""Booked (realised) P&L of closed legs and the profit still left on a strategy (ADR-008; REQ-071 rows 9 and 10).

Spec: spec/technical-design/adjustment-data-contract.md row 9 ("sum of (exit - entry) x qty over closed legs") and
the owner reading of row 10 (Q246, 2026-09-29): "the position's maximum profit at expiry **minus losses already
booked** on the strategy (what is still earnable on the whole trade), computed by the one engine (ADR-008)".

Both are P&L numbers, so they live in the engine: a closed leg's booked P&L goes through the one sign convention
(:func:`ofo.engine.legs.position_pnl`, marked at its exit price) and the maximum profit is
:func:`ofo.engine.metrics.strategy_metrics` of the legs still open. Nothing here re-implements either.

Row 10 is defined by the owner for booked LOSSES. A net booked PROFIT is not covered by that reading (should it be
added to what is still earnable, or ignored?), so :func:`remaining_profit` refuses it rather than guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Sequence

from ofo.engine import legs as _legs
from ofo.engine import metrics as _metrics
from ofo.engine.legs import Leg, require_price
from ofo.engine.metrics import UNLIMITED, _Unlimited
from ofo.engine.strategy import Strategy

MAX_CLOSED_LEGS: Final = 1_000


@dataclass(frozen=True)
class ClosedLeg:
    """A leg that has been exited: the leg as entered, its exit (fill) price and the fill's reference."""

    leg: Leg
    exit_price: Decimal
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.leg, Leg):
            raise ValueError(f"a closed leg needs a Leg, got {self.leg!r}")
        require_price(self.exit_price, "exit_price")
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError("a closed leg must name its exit fill reference")


@dataclass(frozen=True)
class BookedPnl:
    """Booked P&L per closed leg (same order as given) and their running total."""

    per_leg: tuple[Decimal, ...]
    total: Decimal


def booked_pnl(closed: Sequence[ClosedLeg]) -> BookedPnl:
    """Row 9: each closed leg's P&L at its exit price (BUY (exit - entry) x qty, SELL (entry - exit) x qty), summed.

    An empty sequence books nothing (total 0). The same fill reference twice is refused: one exit cannot be booked
    twice.
    """
    items = tuple(closed)
    if len(items) > MAX_CLOSED_LEGS:
        raise ValueError(f"{len(items)} closed legs exceeds the limit of {MAX_CLOSED_LEGS}")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, ClosedLeg):
            raise ValueError(f"every closed leg must be a ClosedLeg, got {item!r}")
        if item.reference in seen:
            raise ValueError(f"exit fill {item.reference!r} appears twice; a fill is booked once")
        seen.add(item.reference)
    per_leg = tuple(_legs.position_pnl(item.leg, item.exit_price) for item in items)
    return BookedPnl(per_leg=per_leg, total=sum(per_leg, Decimal(0)))


def remaining_profit(open_strategy: Strategy, closed: Sequence[ClosedLeg]) -> Decimal | _Unlimited:
    """Row 10 (owner reading Q246): max profit at expiry of the open legs minus the losses already booked.

    ``UNLIMITED`` when the open legs' max profit is unbounded. A net booked profit raises ``ValueError``: the owner's
    reading covers booked losses only.
    """
    if not isinstance(open_strategy, Strategy):
        raise ValueError(f"open_strategy must be a Strategy, got {open_strategy!r}")
    booked = booked_pnl(closed).total
    if booked > 0:
        raise ValueError(
            f"booked P&L is a net profit ({booked}); row 10's owner reading (Q246) defines only booked losses"
        )
    max_profit = _metrics.strategy_metrics(open_strategy).max_profit
    if max_profit is UNLIMITED:
        return UNLIMITED
    return max_profit + booked
