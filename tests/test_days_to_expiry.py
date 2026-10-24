"""REQ-135 AC-2: the one days-to-expiry helper, from fixed dates (never the wall clock)."""
import datetime

from ofo.timeutil import days_to_expiry

TODAY = datetime.date(2026, 10, 21)


def test_27_oct_from_21_oct_is_six_days_and_expiry_day_is_zero():
    expiry = datetime.date(2026, 10, 27)
    assert days_to_expiry(expiry, TODAY) == 6
    assert days_to_expiry(expiry, expiry - datetime.timedelta(days=1)) == 1
    assert days_to_expiry(expiry, expiry) == 0


def test_a_past_or_absent_expiry_fails_closed_to_none():
    assert days_to_expiry(TODAY - datetime.timedelta(days=1), TODAY) is None
    assert days_to_expiry(None, TODAY) is None
