"""The paper order book shown as tracking legs: one leg per contract (GC-TP step 1a part 4; REQ-109 AC-4; ADR-207).

Spec basis: REQ-109 AC-4 "The one engine derives the net position per contract from the orders". Every figure here comes
from ofo.engine.orderbook.net_positions; this module only picks which of its values a leg shows.

- One leg per contract, in the order of the contract's first order.
- An open contract (net not 0): side = the side of its net, quantity = its open quantity, average = the engine's exact
  average; its booked part (a partial exit) stays in the book's booked figure.
- A flat contract (net 0, exited): side, quantity and average are those of the position just before the order that
  closed it (the engine run on the orders before that one), exit price and time = that closing order's.
Answer states: no orders -> refused (ValueError, the engine's); open / partly exited / fully exited as above.
Standard library only; no clock is read here.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from ofo.tracking.orderbook import NetPosition, PaperOrder, Side, net_positions


@dataclass(frozen=True)
class ContractLeg:
    instrument_id: str  # the order book's key (the stored contract id)
    side: Side
    quantity: int  # open quantity; for an exited contract the quantity it closed
    average: Decimal  # exact (display rounds)
    entry_at: datetime.datetime  # the contract's first order
    exit_price: Decimal | None  # set only when exited (net 0)
    exited_at: datetime.datetime | None
    booked: Decimal  # every closed part of this contract, exact

    @property
    def exited(self) -> bool:
        return self.exit_price is not None


def _side(net: int) -> Side:
    return "BUY" if net > 0 else "SELL"


def _before_close(orders: Sequence[PaperOrder], position: NetPosition) -> NetPosition:
    """The contract's position just before its last (closing) order."""
    last = max(i for i, o in enumerate(orders) if o.instrument_id == position.instrument_id)
    found = [p for p in net_positions(orders[:last], {}).positions if p.instrument_id == position.instrument_id] \
        if last else []
    if not found or found[0].net_quantity == 0 or found[0].average is None:
        raise ValueError(f"contract {position.instrument_id}: flat with no open position before its last order")
    return found[0]


def contract_legs(orders: Sequence[PaperOrder]) -> tuple[ContractLeg, ...]:
    """The legs of a paper book (module docstring), in the order of each contract's first order."""
    legs = []
    for p in net_positions(orders, {}).positions:
        if p.net_quantity != 0 and p.average is not None:
            legs.append(ContractLeg(p.instrument_id, _side(p.net_quantity), abs(p.net_quantity), p.average,
                                    p.first_at, None, None, p.booked))
            continue
        before = _before_close(orders, p)
        if before.average is None:  # narrowed above; kept for the type checker
            raise ValueError(f"contract {p.instrument_id}: no average before its close")
        legs.append(ContractLeg(p.instrument_id, _side(before.net_quantity), abs(before.net_quantity),
                                before.average, p.first_at, p.last_price, p.last_at, p.booked))
    return tuple(legs)
