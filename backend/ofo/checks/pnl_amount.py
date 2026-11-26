"""ADR-330 (5): a plan's rupee level, whole-trade and before charges (owner Q3). Pure: the pnl is passed in, never read.

Met / NotMet / NotComputable. An absent pnl is NotComputable, never NotMet. A met level only informs: the caller raises
an actionable alert and nothing exits by itself (ADR-003). Money is Decimal, never float (ADR-008).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

LOSS: Final = "loss"
PROFIT: Final = "profit"


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


def _usable(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def level_of(text: str | None) -> Decimal | None:
    """The stored text level -> a positive finite Decimal; blank/absent -> None (no check); anything else -> ValueError."""
    if text is None or not text.strip():
        return None
    try:
        level = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError(f"rupee level is not a number: {text!r}") from None
    if not level.is_finite() or level <= 0:
        raise ValueError(f"rupee level must be a positive number: {text!r}")
    return level


def pnl_amount(level: Decimal, pnl: Decimal | None, side: str) -> Outcome:
    """Loss: met when pnl <= -level. Profit: met when pnl >= level. ``level`` must be a positive finite Decimal."""
    if not _usable(level) or level <= 0:
        raise ValueError(f"rupee level must be a positive finite Decimal: {level!r}")
    if pnl is None:
        return NotComputable("no P&L figure")
    if not _usable(pnl):
        return NotComputable("P&L figure unreadable")
    if side == LOSS:
        return Met() if pnl <= -level else NotMet()
    if side == PROFIT:
        return Met() if pnl >= level else NotMet()
    return NotComputable("unknown side")
