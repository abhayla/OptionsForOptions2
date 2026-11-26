"""The ONE answer type of every stand-alone check (ADR-330 (12)): Met / NotMet / NotComputable(reason).

Born in ``pnl_amount`` (Lane P); moved here so the five checks share one type, and ``pnl_amount`` re-exports it
(``pnl_amount.Met is outcome.Met``). A check only answers; it never exits, alerts or reads a store or a clock.
NotComputable never fires anything: a caller treats it as "do nothing" (fail closed).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

ABOVE: Final = "above"
BELOW: Final = "below"
NO_PRICE: Final = "no_price"  # reasons are codes: the words live in the catalogue
PRICE_UNREADABLE: Final = "price_unreadable"
NO_LEVEL: Final = "no_level"
LEVEL_UNREADABLE: Final = "level_unreadable"
UNKNOWN_DIRECTION: Final = "unknown_direction"


@dataclass(frozen=True)
class Met:
    pass


@dataclass(frozen=True)
class NotMet:
    pass


@dataclass(frozen=True)
class NotComputable:
    reason: str


Outcome = Met | NotMet | NotComputable
Direction = Literal["above", "below"]


def usable(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def at_or_beyond(level: Decimal | None, direction: str, price: Decimal | None) -> Outcome:
    """The one level comparison: ``above`` is met when price >= level, ``below`` when price <= level (a level, not an
    edge: equality is met in both directions). Anything absent or unreadable is NotComputable, never NotMet."""
    if level is None:
        return NotComputable(NO_LEVEL)
    if not usable(level):
        return NotComputable(LEVEL_UNREADABLE)
    if price is None:
        return NotComputable(NO_PRICE)
    if not usable(price):
        return NotComputable(PRICE_UNREADABLE)
    if direction == ABOVE:
        return Met() if price >= level else NotMet()
    if direction == BELOW:
        return Met() if price <= level else NotMet()
    return NotComputable(UNKNOWN_DIRECTION)
