# ruff: noqa: E501
"""GC-TP R-19a (REQ-144 AC-1..AC-4, REQ-084; Sensibull study screen 020): the texts the browser prints beside the what-if
target, made here so the browser only formats nothing (ADR-008): the move of the target level from the live spot, the days
to the first expiry, and the Projected profit / loss badge with its percent of margin needed (REQ-081 AC-9, ADR-207 (8)).

Answer states: no live spot -> the move is absent with its reason (never computed from another price); a margin that is not
CHECKED -> the badge amount stays, its percent is absent with the reason (AC-3); no target, or no Estimated view (an option
leg without IV, no live prices) -> the badge is "Projected figure not available" with the reason, never a number (AC-4).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from ofo.errors.explanations import render_explanation
from ofo.outcome import money
from ofo.outcome.target import Target, TargetOffer
from ofo.scenario.levels import move_from_spot


def move_fields(level: Decimal | None, spot: Decimal | None) -> dict[str, Any]:
    """``move_pct`` (exact, a string) and ``move_pct_display`` ("+6.1%"), or both absent with ``move_pct_reason``."""
    if level is None or spot is None or spot <= 0:
        return {"move_pct": None, "move_pct_display": None, "move_pct_reason": render_explanation("target_move_no_spot")}
    pct, display = move_from_spot(level, spot)
    return {"move_pct": f"{pct:f}", "move_pct_display": display, "move_pct_reason": None}


def days_fields(days: int | None) -> dict[str, Any]:
    """``days_to_expiry`` and its text ("4D to expiry"; "0D to expiry" on expiry day); both None when unknown."""
    if days is None:
        return {"days_to_expiry": None, "days_to_expiry_display": None}
    return {"days_to_expiry": days, "days_to_expiry_display": render_explanation("target_days_to_expiry", days=days)}


def _unavailable(reason: Any) -> dict[str, Any]:
    return {"state": "unavailable", "label": render_explanation("target_badge_unavailable"), "reason": reason,
            "amount": None, "amount_display": None, "percent": None, "percent_text": None, "percent_reason": None}


def badge(t: Target | TargetOffer, margin: Any) -> dict[str, Any]:
    """The Projected badge of one reply. ``state`` is profit (above 0), loss (below 0), zero (exactly 0) or unavailable."""
    if isinstance(t, TargetOffer):
        return _unavailable(render_explanation("target_badge_no_target"))
    if t.kind != "estimate" or t.pnl is None:  # AC-4: no Estimated view -> no figure, with why
        return _unavailable(t.at_refused_reason)
    pnl = Decimal(0) if t.pnl == 0 else t.pnl  # a true zero is 0, never -0
    state, template = ("profit", "target_badge_profit") if pnl > 0 else (
        ("loss", "target_badge_loss") if pnl < 0 else ("zero", "target_badge_zero"))
    amount = abs(pnl)
    share = money.funds_share(None, None, margin)  # present only for a CHECKED, positive margin needed
    if share is None:  # AC-3: the amount stays; the percent says why it is missing
        percent, text, reason = None, None, render_explanation("target_badge_percent_unavailable")
    else:
        percent, text = money.share_of(amount, share.margin_needed)
        reason = None
    return {"state": state, "label": render_explanation(template, amount=amount), "reason": None,
            "amount": f"{pnl:f}", "amount_display": render_explanation("cell_rupees", amount=amount),
            "percent": None if percent is None else f"{percent:f}", "percent_text": text, "percent_reason": reason,
            "output_label": t.output_label}
