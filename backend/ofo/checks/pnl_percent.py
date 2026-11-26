"""ADR-330 (12): the P&L-percent condition: value = num / den against a limit (a percent), exact and inclusive,
compared as a fraction so no division rounds. Pure; Decimal only (ADR-008).

``cmp`` "ge": met when num >= limit * den; "le": met when num <= limit * den. An absent or unreadable figure, or a
denominator not above 0, is NotComputable, never NotMet."""
from __future__ import annotations

from decimal import Context, Decimal, DivisionByZero, Inexact, InvalidOperation, Overflow, localcontext
from typing import Final

from ofo.checks.outcome import Met, NotComputable, NotMet, Outcome, usable

NO_FIGURE: Final = "no_figure"
FIGURE_UNREADABLE: Final = "figure_unreadable"
BAD_DENOMINATOR: Final = "denominator_not_positive"
UNKNOWN_CMP: Final = "unknown_cmp"
_EXACT: Final = Context(prec=200, traps=[Inexact, InvalidOperation, DivisionByZero, Overflow])  # as playbook_eval did


def pnl_percent(num: Decimal | None, den: Decimal | None, limit: Decimal | None, cmp: str) -> Outcome:
    if num is None or den is None or limit is None:
        return NotComputable(NO_FIGURE)
    if not (usable(num) and usable(den) and usable(limit)):
        return NotComputable(FIGURE_UNREADABLE)
    if den <= 0:
        return NotComputable(BAD_DENOMINATOR)
    if cmp not in ("ge", "le"):
        return NotComputable(UNKNOWN_CMP)
    with localcontext(_EXACT):
        scaled = limit * den
        met = num >= scaled if cmp == "ge" else num <= scaled
    return Met() if met else NotMet()
