"""ADR-330 (5): a plan's rupee level, whole-trade and before charges (owner Q3). Pure: the pnl is passed in, never read.

Met / NotMet / NotComputable. An absent pnl is NotComputable, never NotMet. A met level only informs: the caller raises
an actionable alert and nothing exits by itself (ADR-003). Money is Decimal, never float (ADR-008).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Final

LOSS: Final = "loss"
PROFIT: Final = "profit"
NO_PNL: Final = "no_pnl"  # reasons are codes: the words live in the catalogue
PNL_UNREADABLE: Final = "pnl_unreadable"
UNKNOWN_SIDE: Final = "unknown_side"
#: the ONE shape of a typed rupee level (rupees to the paisa, ASCII digits only): the plan route's box and the stored
#: guard are both read by it (``level_of``), so "1e3", "400.005" and full-width digits never pass
LEVEL_PATTERN: Final = re.compile(r"[0-9]{1,12}([.][0-9]{1,2})?")


from ofo.checks.outcome import Met, NotComputable, NotMet, Outcome  # noqa: F401 - the one answer type, re-exported


def _usable(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def level_of(text: str | None) -> Decimal | None:
    """The stored text level -> a positive finite Decimal; blank or absent -> None (no check); else ValueError."""
    if text is None or not text.strip():
        return None
    if not LEVEL_PATTERN.fullmatch(text.strip()):
        raise ValueError(f"rupee level is not a plain amount of rupees and paise: {text!r}")
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
        return NotComputable(NO_PNL)
    if not _usable(pnl):
        return NotComputable(PNL_UNREADABLE)
    if side == LOSS:
        return Met() if pnl <= -level else NotMet()
    if side == PROFIT:
        return Met() if pnl >= level else NotMet()
    return NotComputable(UNKNOWN_SIDE)
