"""Paper stop-loss triggers: when has a live price crossed an armed level? (GC-TP step 7a; ADR-207 (5); REQ-109 AC-8)

Spec basis: ADR-207 (5) (a Conditional Exit - the index crosses above / below a level, exit all legs - and a per-leg
stop-loss, Sensibull screens 221-224); ADR-015 (stale is never live); REQ-109 AC-5 (a stale or missing price is never
computed with). The comparison vocabulary (above / below) is the condition engine's (REQ-041,
services/autopilot/condition_engine.py, read only, no code copied), rebuilt here on exact Decimal.

- ``above``: fires when the price is AT or ABOVE the level; ``below``: AT or BELOW. A trigger is a level, not an
  edge: the first live price on the far side fires it, whatever the previous tick was (a trigger set when the price
  is already beyond its level fires on the next live tick - the route refuses such a level only if the product asks).
- Only a LIVE price fires (``paper.is_live``, the one predicate every paper decision uses): stale, missing and every
  contract reason never fire, whatever number the answer may carry.
Standard library only; no clock and no database here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.tracking import paper

Direction = Literal["above", "below"]
Kind = Literal["conditional_exit", "leg_stop"]
DIRECTIONS: tuple[Direction, ...] = ("above", "below")
KINDS: tuple[Kind, ...] = ("conditional_exit", "leg_stop")


@dataclass(frozen=True)
class Trigger:
    """An armed paper trigger as the monitor holds it."""

    id: int
    strategy_id: int
    kind: Kind
    direction: Direction
    level: Decimal
    contract_id: int | None = None  # leg_stop only
    underlying: str | None = None  # conditional_exit only

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS or self.kind not in KINDS:
            raise ValueError(f"trigger {self.id}: unknown direction {self.direction!r} or kind {self.kind!r}")
        if type(self.level) is not Decimal or not self.level.is_finite() or self.level <= 0:
            raise ValueError(f"trigger {self.id}: the level must be an exact Decimal above 0, got {self.level!r}")
        if (self.kind == "leg_stop") != (self.contract_id is not None) or \
                (self.kind == "conditional_exit") != (self.underlying is not None):
            raise ValueError(f"trigger {self.id}: a leg stop names a contract, a conditional exit names an index")


def crossed(trigger: Trigger, price: paper.Price) -> bool:
    """True when ``price`` is live and at or beyond the trigger's level on its side."""
    if not paper.is_live(price) or price.price is None:
        return False
    if trigger.direction == "above":
        return price.price >= trigger.level
    return price.price <= trigger.level
