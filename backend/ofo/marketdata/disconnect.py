"""The disconnect status text for an affected strategy (REQ-049 AC-5, ADR-015 Q182).

Exact wording, owner-cited: 'Live market data disconnected. Last updated: <time>. Live strategy monitoring is
paused.' The time is the quote's last update, shown in IST (ADR-015's own example: '10:42:17 AM'); a trigger is
never claimed for the gap (handled by :mod:`ofo.rules`, which cannot evaluate on a non-``available`` input).
"""
from __future__ import annotations

import datetime

from ofo.rules.inputs import IST

_MESSAGE = "Live market data disconnected. Last updated: {time}. Live strategy monitoring is paused."


def disconnect_message(last_updated: datetime.datetime) -> str:
    """Build the AC-5 status text; ``last_updated`` must be timezone-aware, shown converted to IST."""
    if not isinstance(last_updated, datetime.datetime) or last_updated.tzinfo is None:
        raise ValueError(f"last_updated must be a timezone-aware datetime, got {last_updated!r}")
    ist_time = last_updated.astimezone(IST).strftime("%I:%M:%S %p")
    return _MESSAGE.format(time=ist_time)
