"""ADR-330 (64): is a strategy's position REAL or PAPER, in one place (owner 27 Nov evening).

While real order placing is on hold (ADR-281) a real position has no stop, no watcher and no exit in the app, so its row
shows its P&L and ONE line (position_kind_real: "Real position: exit and protect it in Kite. Stops and alerts here
cover paper trades only.") and offers no Exit and no Stops; an alert never offers "Exit the position" for it. A stated
exception to ADR-330 (58) until one door for paper and real exists.

The tag is the stored fact, never the name: a held entry exists (ADR-292: a condor held at the broker is a REAL position
stored as practice orders) -> real; an order exists and no paper order -> real (a basket was sent); a paper order and
no held entry -> paper; no order -> none (a draft: no row to protect); any fact that could not be read -> unknown
(fail closed: neither Exit nor Stops, and the line says why).
"""
from __future__ import annotations

from typing import Final, Literal

from ofo.errors.explanations import ExplanationText, render_explanation

PositionKind = Literal["paper", "real", "none", "unknown"]
PAPER: Final = "paper"
REAL: Final = "real"
NONE: Final = "none"
UNKNOWN: Final = "unknown"


def kind_of(has_order: bool | None, has_paper_order: bool | None, held_at_broker: bool | None) -> PositionKind:
    if has_order is None or has_paper_order is None or held_at_broker is None:
        return UNKNOWN
    if held_at_broker:
        return REAL
    if not has_order:
        return NONE
    return PAPER if has_paper_order else REAL


def line_of(kind: str) -> ExplanationText | None:
    """The one sentence a row carries: real and unknown only; paper and none carry none (unchanged rows)."""
    if kind == REAL:
        return render_explanation("position_kind_real")
    if kind == UNKNOWN:
        return render_explanation("position_kind_unknown")
    return None
