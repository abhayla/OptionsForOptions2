"""REQ-146 AC-5: a contract date prints as day and month ("24 Nov"), never ISO; only an exact date is accepted."""
import datetime

import pytest

from ofo.errors.explanations import render_explanation


def test_future_label_prints_day_and_month() -> None:
    line = render_explanation("price_history_future_label", underlying="NIFTY", expiry=datetime.date(2026, 11, 24))
    assert str(line) == "NIFTY 24 Nov FUT"


def test_day_month_refuses_a_datetime_and_a_string() -> None:
    for bad in (datetime.datetime(2026, 11, 24), "2026-11-24"):
        with pytest.raises((TypeError, ValueError)):
            render_explanation("price_history_future_label", underlying="NIFTY", expiry=bad)
