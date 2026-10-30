"""U23 (REQ-151): a contract is shown as "NIFTY 3 Nov 22650 PE", never with an ISO date."""
import datetime
from decimal import Decimal

from ofo.engine.legs import Instrument
from ofo.errors.explanations import render_explanation, restore_explanation
from ofo.strategy.definition import display_contract


def test_option_contract_has_short_date_and_plain_strike():
    c = ("NIFTY", Instrument.PE, Decimal("22650.00"), datetime.date(2026, 11, 3))
    assert str(display_contract(c)) == "NIFTY 3 Nov 22650 PE"


def test_future_contract_has_no_strike():
    c = ("NIFTY", Instrument.FUT, None, datetime.date(2026, 11, 24))
    assert str(display_contract(c)) == "NIFTY 24 Nov FUT"


def test_alert_body_has_no_repeated_title_and_old_rows_still_restore():
    what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="below", level=Decimal("22845"))
    leg = render_explanation("paper_alert_leg", contract=display_contract(("NIFTY", Instrument.PE, Decimal("22650"), datetime.date(2026, 11, 3))), price=render_explanation("cell_dash"))
    body = str(render_explanation("paper_alert_body", what=what, count=1, prices=leg))
    assert not body.startswith("Paper strategy")
    assert "2026-" not in body
    old = 'Paper strategy - "X": ' + body
    assert str(restore_explanation("paper_alert_body", old)) == old
