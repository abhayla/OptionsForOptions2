"""The last 250 completed daily candles of an index, read from Kite at most once per IST trading day (GC-ICTRACK task
24, ADR-277): T-11c ranks today's live India VIX against these closes and T-20b computes ADX(14) on them.

In memory only (no table, contract reuse rules): a process restart reads again, once. The range ends YESTERDAY: a
session's own candle is half-formed until the close, and a once-a-day cache would freeze it. Answer states: rows ->
the last ``SESSIONS`` of them, oldest first (fewer when Kite has fewer); none -> []; a failed or malformed read raises
``CandleFetchError`` / ``CandleError`` to the caller (the trigger answers "not checked") and is not retried for
``RETRY_AFTER`` (one failing read per index per 10 minutes, never one per check).
"""
from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Final

from ofo.history.candles import CandleError
from ofo.timeutil import IST

from ofo_app.kite_history import CandleFetchError, DayCandle

SESSIONS: Final = 250
_CALENDAR_SPAN: Final = datetime.timedelta(days=380)  # 250 sessions back, weekends and exchange holidays included
RETRY_AFTER: Final = datetime.timedelta(minutes=10)

Fetch = Callable[[str, datetime.date, datetime.date], list[DayCandle]]  # KiteHistory.day_candles(token, start, end)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class DailyCandles:
    def __init__(self, fetch: Fetch, clock: Callable[[], datetime.datetime] = _utc_now) -> None:
        self._fetch = fetch
        self._clock = clock
        self._rows: dict[str, tuple[datetime.date, list[DayCandle]]] = {}
        self._failed: dict[str, tuple[datetime.date, datetime.datetime, Exception]] = {}

    def last(self, token: str) -> list[DayCandle]:
        """The last ``SESSIONS`` completed daily candles of Kite instrument ``token`` (module docstring)."""
        now = self._clock()
        today = now.astimezone(IST).date()
        held = self._rows.get(token)
        if held is not None and held[0] == today:
            return held[1]
        failed = self._failed.get(token)
        if failed is not None and failed[0] == today and now - failed[1] < RETRY_AFTER:
            raise failed[2]
        yesterday = today - datetime.timedelta(days=1)
        try:
            rows = self._fetch(token, today - _CALENDAR_SPAN, yesterday)[-SESSIONS:]
        except (CandleFetchError, CandleError) as exc:
            self._failed[token] = (today, now, exc)
            raise
        self._failed.pop(token, None)
        self._rows[token] = (today, rows)
        return rows


__all__ = ["RETRY_AFTER", "SESSIONS", "DailyCandles"]
