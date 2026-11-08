"""The index's day open for the check (GC-IC1 step 5b, #627 item 1, T-13): ONE rule both the screen's reader
(``adjustment_readers.read_market``) and the background worker (``background.read_prices``) apply to the feed's own
day values of the index (``QuoteBook.latest_day_stats``, REQ-080 AC-7), read in the same read as the index quote.

Answer states (``DayOpen.reason``; the value is set only for STATED):
- STATED: the day values are dated today (IST) and state an open;
- PREVIOUS_SESSION: dated another day (after a restart, before today's first index tick, the packet Kite sends on
  subscribe still carries yesterday's values): never used;
- UNDATED: the day values carry no time (a 28-byte index packet), so today cannot be told: never used;
- NO_OPEN: dated today but the packet states no open;
- NOT_HELD / FEED_NOT_HEALTHY / PACKET_WITHOUT_DAY_FIELDS / NOT_OFFERED: the provider's own reason;
- NOT_READ: no index quote, so nothing was asked.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo.timeutil import IST

STATED: Final = "STATED"
PREVIOUS_SESSION: Final = "PREVIOUS_SESSION"
UNDATED: Final = "UNDATED"
NO_OPEN: Final = "NO_OPEN"
NOT_READ: Final = "NOT_READ"


@dataclass(frozen=True)
class DayOpen:
    value: Decimal | None
    reason: str


def index_day_open(answer: Any, now: datetime.datetime) -> DayOpen:
    """``answer``: the provider's ``DayStatsAnswer`` for the index (None: not read). ``now``: the reading check's
    clock; "today" is its IST date."""
    if answer is None:
        return DayOpen(None, NOT_READ)
    stats = answer.stats
    if stats is None:
        return DayOpen(None, str(answer.reason))
    if stats.last_trade_ts is None:
        return DayOpen(None, UNDATED)
    dated = datetime.datetime.fromtimestamp(stats.last_trade_ts, IST).date()
    if dated != now.astimezone(IST).date():
        return DayOpen(None, PREVIOUS_SESSION)
    if stats.day_open is None:
        return DayOpen(None, NO_OPEN)
    return DayOpen(stats.day_open, STATED)
