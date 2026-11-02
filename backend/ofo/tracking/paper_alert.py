"""The body of a paper stop / conditional-exit alert (#614): one function behind the monitor so the wording is testable.

One exited leg is not "1 legs", and a leg stop's reason already names the contract, so the body does not say it twice:
"Stop-loss: SENSEX 5 Nov 76000 CE crossed above 224.50; exited at 225.00. A paper exit only: ...". Two or more legs keep
the count and list each contract with its price.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.outcome.price_text import price_text

__all__ = ["alert_body"]


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
