"""AC-5: the exact disconnect status text for affected strategies, time shown in IST (ADR-015 Q182)."""
import datetime

import pytest

from ofo.marketdata.disconnect import disconnect_message

UTC = datetime.timezone.utc


def test_ac5_exact_message_text_with_time_converted_to_ist():
    """ADR-015's own example format: 'Live market data disconnected. Last updated: 10:42:17 AM. Live strategy
    monitoring is paused.' UTC 05:12:17 -> IST (+5:30) 10:42:17."""
    last_updated_utc = datetime.datetime(2026, 9, 29, 5, 12, 17, tzinfo=UTC)
    msg = disconnect_message(last_updated_utc)
    assert msg == "Live market data disconnected. Last updated: 10:42:17 AM. Live strategy monitoring is paused."


def test_ac5_message_uses_the_given_last_updated_time_not_now():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    last_updated = datetime.datetime(2026, 9, 29, 9, 5, 0, tzinfo=ist)
    msg = disconnect_message(last_updated)
    assert "09:05:00 AM" in msg
    assert msg.startswith("Live market data disconnected.")
    assert msg.endswith("Live strategy monitoring is paused.")


def test_ac5_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        disconnect_message(datetime.datetime(2026, 9, 29, 9, 5, 0))
