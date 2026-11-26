"""The body of a paper stop / conditional-exit alert (#614): one function behind the monitor so the wording is testable.

One exited leg is not "1 legs", and a leg stop's reason already names the contract, so the body does not say it twice:
"Stop-loss: SENSEX 5 Nov 76000 CE crossed above 224.50; exited at 225.00. A paper exit only: ...". Two or more legs keep
the count and list each contract with its price.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ofo.errors.explanations import ExplanationText, render_explanation, restore_explanation
from ofo.outcome.price_text import price_text

__all__ = ["ALERT_BODY_TEMPLATES", "STOP_LINE_TEMPLATES", "alert_body", "restore_alert_body", "restore_order_reason",
           "settle_history_body", "stop_reason_at"]

# Every wording a stored alert body can have. The store keeps the text only, not the template id, so a read tries each
# one; rows written before #614 (7babdba9) only ever fit the multi-leg form ("exited 1 legs at ..."). Stored text is
# never rewritten.
ALERT_BODY_TEMPLATES = ("paper_alert_body_one", "paper_alert_body_one_named", "paper_alert_body")
#: Every wording the max-loss line of a fired stop can have (ADR-330 (6): the leg-stop sentences; the exit
#: confirmation's sentences and their join, which routes.paper._exit_warning builds), for reading a stored line back.
STOP_LINE_TEMPLATES = (
    "paper_leg_stop_widens_loss", "paper_leg_stop_unlimited_loss", "paper_leg_stop_from_profit",
    "paper_leg_stop_unlimited_from_profit", "paper_leg_stop_to_profit", "paper_leg_stop_still_profit",
    "paper_exit_widens_loss", "paper_exit_less_protected", "paper_exit_warning_join")


def restore_alert_body(stored: str) -> ExplanationText:
    """A stored alert body read back through whichever alert template it fits; ValueError if it fits none."""
    for template_id in ALERT_BODY_TEMPLATES:
        try:
            return restore_explanation(template_id, stored)
        except ValueError:
            continue
    raise ValueError("stored alert body fits no paper alert template")


def alert_body(what: ExplanationText | str, exits: Sequence[tuple[ExplanationText | str, Decimal]], *,
               names_contract: bool) -> ExplanationText:
    """``what`` is the stop reason; ``exits`` are (contract text, exit price) per exited leg; ``names_contract`` is True
    when ``what`` already names the (single) contract, as a leg stop's reason does."""
    legs = [render_explanation("paper_alert_leg", contract=contract, price=price_text(price))
            for contract, price in exits]
    if len(legs) == 1:
        if names_contract:
            return render_explanation("paper_alert_body_one", what=what, price=price_text(exits[0][1]))
        return render_explanation("paper_alert_body_one_named", what=what, leg=legs[0])
    joined = legs[0]
    for leg in legs[1:]:
        joined = render_explanation("paper_alert_legs", rest=joined, leg=leg)
    return render_explanation("paper_alert_body", what=what, count=len(legs), prices=joined)


def stop_reason_at(what: ExplanationText | str, underlying: str, index: Decimal | None) -> ExplanationText:
    """D-22: the stop's reason with the index value at the moment it fired; ``index`` None (no live index price) says
    the value was not available, never a guess. One wording for the stop order's reason and the alert's first part."""
    if index is None:
        return render_explanation("paper_stop_reason_index_unknown", what=what)
    return render_explanation("paper_stop_reason_index_at", what=what, underlying=underlying, level=index)


def settle_history_body(what: ExplanationText | str, legs: Sequence[tuple[ExplanationText | str, Decimal]],
                        ) -> ExplanationText:
    """D-71: an expiry settlement's record for Alerts > History: the reason (with the close) and each leg's price."""
    joined = render_explanation("paper_alert_leg", contract=legs[0][0], price=price_text(legs[0][1]))
    for contract, price in legs[1:]:
        joined = render_explanation("paper_alert_legs", rest=joined,
                                    leg=render_explanation("paper_alert_leg", contract=contract,
                                                           price=price_text(price)))
    return render_explanation("paper_settle_history_body", what=what, prices=joined)


# The wordings an order's stored reason can have, most specific first (the store keeps text only).
ORDER_REASON_TEMPLATES = ("paper_stop_reason_index_at", "paper_stop_reason_index_unknown", "paper_settle_reason",
                          "paper_settle_reason_plain", "paper_stop_reason_index", "paper_stop_reason_leg")


def restore_order_reason(stored: str | None) -> ExplanationText | None:
    """A stored order reason read back as an explanation; None when there is none or it fits no reason wording (the row
    then shows no reason, never an unreviewed sentence)."""
    if not stored:
        return None
    for template_id in ORDER_REASON_TEMPLATES:
        try:
            return restore_explanation(template_id, stored)
        except ValueError:
            continue
    return None
