"""GC-ICTRACK task 24: the 250-session daily candle cache asks Kite once per IST trading day per index."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo_app.daily_candles import RETRY_AFTER, SESSIONS, DailyCandles
from ofo_app.kite_history import CandleFetchError, DayCandle

NIFTY = "256265"
TWO_READS, FEW = 2, 40
MON_0920 = datetime.datetime(2026, 11, 9, 3, 50, tzinfo=datetime.UTC)  # 09:20 IST Monday 9 Nov


class _Kite:
    def __init__(self, rows: int = 300, fail: bool = False) -> None:
        self.calls: list[tuple[str, datetime.date, datetime.date]] = []
        self.rows, self.fail = rows, fail

    def __call__(self, token, start, end):
        self.calls.append((token, start, end))
        if self.fail:
            raise CandleFetchError("http status 500")
        return [DayCandle(end - datetime.timedelta(days=self.rows - i), Decimal(2), Decimal(1), Decimal(i + 1))
                for i in range(self.rows)]


def _clock(*times):
    it = iter(times)
    return lambda: next(it)


def test_one_fetch_per_ist_trading_day_ending_yesterday_and_the_last_250_kept():
    kite = _Kite()
    later = MON_0920 + datetime.timedelta(hours=5)              # 14:20 IST, same day
    tue = MON_0920 + datetime.timedelta(days=1)
    cache = DailyCandles(kite, _clock(MON_0920, later, tue))
    first = cache.last(NIFTY)
    assert cache.last(NIFTY) is first and len(kite.calls) == 1   # same IST day: the memo answers
    assert len(first) == SESSIONS and first[-1].close == Decimal(300)  # the newest 250 of 300
    assert kite.calls[0][2] == datetime.date(2026, 11, 8)        # ends yesterday (today's candle is half-formed)
    cache.last(NIFTY)
    assert len(kite.calls) == TWO_READS and kite.calls[1][2] == datetime.date(2026, 11, 9)  # a new day reads again


def test_the_ist_day_turns_at_ist_midnight_not_utc_midnight():
    kite = _Kite()
    before = datetime.datetime(2026, 11, 9, 18, 0, tzinfo=datetime.UTC)  # 23:30 IST Monday
    after = datetime.datetime(2026, 11, 9, 18, 31, tzinfo=datetime.UTC)  # 00:01 IST Tuesday, still Monday in UTC
    cache = DailyCandles(kite, _clock(before, after))
    cache.last(NIFTY)
    cache.last(NIFTY)
    assert len(kite.calls) == TWO_READS


def test_fewer_sessions_than_250_and_none_are_answers_not_errors():
    assert len(DailyCandles(_Kite(rows=FEW), _clock(MON_0920)).last(NIFTY)) == FEW
    assert DailyCandles(_Kite(rows=0), _clock(MON_0920)).last(NIFTY) == []


def test_a_failed_read_raises_and_is_not_retried_for_ten_minutes():
    kite = _Kite(fail=True)
    soon = MON_0920 + RETRY_AFTER - datetime.timedelta(seconds=1)
    cache = DailyCandles(kite, _clock(MON_0920, soon, MON_0920 + RETRY_AFTER))
    for _ in range(2):
        with pytest.raises(CandleFetchError):
            cache.last(NIFTY)
    assert len(kite.calls) == 1                                  # the second ask got the remembered failure
    kite.fail = False
    assert len(cache.last(NIFTY)) == SESSIONS and len(kite.calls) == TWO_READS  # after 10 minutes: read again


def test_two_indices_are_cached_apart():
    kite = _Kite()
    cache = DailyCandles(kite, _clock(MON_0920, MON_0920))
    cache.last(NIFTY)
    cache.last("265")
    assert [c[0] for c in kite.calls] == [NIFTY, "265"]
