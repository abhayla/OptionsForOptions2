"""#614: the paper stop / conditional-exit alert reads right for one exited leg ("exited 1 legs" before) and for two or
more, and always keeps the safety sentence. The reference product's alert wording is not captured in the study (it
documents the feature, not the message text), so the wording follows our own stop reason."""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.engine.legs import Instrument
from ofo.errors.explanations import render_explanation
from ofo.strategy.definition import display_contract
from ofo.tracking.paper_alert import alert_body

SAFETY = "A paper exit only: no order was sent to Zerodha."
NOV5, NOV3 = datetime.date(2026, 11, 5), datetime.date(2026, 11, 3)


def _c(name: str, kind: Instrument, strike: str, expiry: datetime.date):
    return display_contract((name, kind, Decimal(strike), expiry))


LEG = _c("SENSEX", Instrument.CE, "74500", NOV5)
PE, CE = _c("NIFTY", Instrument.PE, "22700", NOV3), _c("NIFTY", Instrument.CE, "23000", NOV3)


def test_one_leg_stop_names_the_contract_once_and_is_not_plural() -> None:
    what = render_explanation("paper_stop_reason_leg", contract=LEG, direction="above", level=Decimal("679.95"))
    body = alert_body(what, [(LEG, Decimal("683.00"))], names_contract=True)
    assert str(body) == ("Stop-loss: SENSEX 5 Nov 74500 CE crossed above 679.95; exited at 683.00. " + SAFETY)
    assert "1 legs" not in str(body)
    assert str(body).count("SENSEX 5 Nov 74500 CE") == 1


def test_one_open_leg_index_exit_names_the_contract_because_the_reason_does_not() -> None:
    what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="below", level=Decimal("22845"))
    body = alert_body(what, [(PE, Decimal("41.00"))], names_contract=False)
    assert str(body) == ("Conditional exit: NIFTY crossed below 22,845.00; exited NIFTY 3 Nov 22700 PE at 41.00. "
                         + SAFETY)
    assert "1 legs" not in str(body)


def test_two_legs_keep_the_count_and_each_contract_with_its_price() -> None:
    what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="below", level=Decimal("22850"))
    body = alert_body(what, [(PE, Decimal("41.00")), (CE, Decimal("12.50"))],
                      names_contract=False)
    assert str(body) == ("Conditional exit: NIFTY crossed below 22,850.00; exited 2 legs at NIFTY 3 Nov 22700 PE "
                         "at 41.00, NIFTY 3 Nov 23000 CE at 12.50. " + SAFETY)
