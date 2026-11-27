"""ADR-330 (50), (52), (58): the lots-per-leg limit, ONE function both order doors call (the paper door through
``paper_limit.check_order_size``, the real door's review step in ``routes/execute.py``). Pure: it reads nothing and
places nothing; the caller hands it each leg's held units and the signed units of the orders it prepared.
Quantities are ints (units); a leg's lots are its units over its lot size, rounded up."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ofo.errors import render

from ofo_app.strategy_refused import StrategyRefused


@dataclass(frozen=True)
class LegLots:
    """One leg: its display ``name``, ``lot_size`` (units, above 0), ``held`` signed units before the batch and
    ``orders`` the batch's signed units (BUY +, SELL -) for the leg, in order."""

    name: str
    lot_size: int
    held: int
    orders: Sequence[int]


def check_lots(top: int, legs: Iterable[LegLots]) -> None:
    """Per leg: the lots it will hold after EACH order, in order (held + added, signed net), may not exceed ``top``
    (``limits.max_lots``). An order that does not grow the leg's net (a cut back of a leg already over a lowered
    limit) passes; a flip long to short counts as growth. Over the limit -> ``StrategyRefused``
    ``paper_leg_total_over_limit`` naming the leg; nothing is placed by this function."""
    for leg in legs:
        held_lots = -(-abs(leg.held) // leg.lot_size)
        running = leg.held
        for units in leg.orders:
            before, running = running, running + units
            total = -(-abs(running) // leg.lot_size)
            if total > top and abs(running) > abs(before):
                raise StrategyRefused("paper_leg_total_over_limit", message=render(
                    "paper_leg_total_over_limit", contract=leg.name, total=total, max_lots=top,
                    held=held_lots, added=max(total - held_lots, 0), room=max(top - held_lots, 0)))
