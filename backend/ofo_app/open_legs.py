"""D-51 (ADR-330 (43), REQ-091 AC-8): the ONE door that answers "what is open on this strategy".

Source-neutral: the caller gets the open legs (contract id, side, units) and never learns where they came from. Today
the answer is the strategy's book (``paper_store``); when real Zerodha positions are read into the same Positions
list (ADR-330 (10)), that reader plugs in HERE and no caller changes. A strategy with no book at all (never placed)
has no open legs of its own, so its PLAN is the answer: the saved definition's legs (REQ-091 AC-2 "current legs"; a
draft is charted as drafted). A book that exists but cannot be read raises: there is no silent fallback to the saved
legs (the saved definition goes stale after an exit or adjustment, D-42 / ADR-299). A book with every leg closed
answers no legs (the caller decides the wording). Money is never touched here: units are integers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ofo.engine.legs import Action
from ofo.engine.orderbook import net_positions

from ofo_app import paper_store


@dataclass(frozen=True)
class OpenLeg:
    contract_id: int
    action: Action
    units: int  # whole units (lots x lot size), above 0; the side is the action


@dataclass(frozen=True)
class OpenLegs:
    legs: tuple[OpenLeg, ...]
    source: str  # "book" (orders exist) or "plan" (nothing placed yet: the saved legs)


async def open_legs(db: Any, stored: Any) -> OpenLegs:
    """The open legs of ``stored`` (a StoredStrategy already loaded for its owner). A failed book read raises."""
    orders = await paper_store.load(db, stored.id)
    if not orders:
        legs = tuple(OpenLeg(int(cid), leg.action, int(leg.quantity))
                     for leg, cid in zip(stored.saved.definition.legs, stored.saved.contract_ids, strict=True))
        return OpenLegs(legs, "plan")
    positions = net_positions([o.order.as_paper() for o in orders], {}).positions
    return OpenLegs(tuple(OpenLeg(int(p.instrument_id), Action.BUY if p.net_quantity > 0 else Action.SELL,
                                  abs(p.net_quantity)) for p in positions if p.net_quantity != 0), "book")
