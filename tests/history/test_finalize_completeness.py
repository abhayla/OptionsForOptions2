"""W-067 round 2, AC-4 (REQ-051, ADR-067): a day is made final only when Kite's candles are COMPLETE, not after a time margin.

Spec basis (quoted): ADR-067 "A day that could not be made final (no session, Kite error) stays provisional and is named
as such, never silently treated as final." A fetch cut short (a truncated body, a rate-limited tail) returns candles
that look fine but stop early; the run must notice and leave the day provisional so it can be retried.
"""
import datetime
from decimal import Decimal

from _history_fixture import DAY, at

from ofo.history.bars import BarSource, MinuteBar
from ofo.history.candles import InMemoryCandleSource
from ofo.history.finalize import finalize_into
from ofo.history.store import DayStatus, InMemoryHistoryStore
from ofo_app.history_finalize import FinalizeRefused, finalize_trading_day

import pytest

IDS = ["NSE_FO:1", "NSE_FO:2", "NSE_FO:3"]
OPEN, LAST = at(9, 15), at(15, 29)


def bar(iid, minute, source):
    return MinuteBar(iid, minute, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), 5, 3, source)


def minutes(first, last):
    out, m = [], first
    while m <= last:
        out.append(m)
        m += datetime.timedelta(minutes=1)
    return out


def day_store(live_until=LAST):
    store = InMemoryHistoryStore()
    store.put_bars([bar(i, m, BarSource.LIVE) for i in IDS for m in minutes(OPEN, live_until)])
    return store


def candles(until, ids=IDS):
    return [bar(i, m, BarSource.KITE) for i in ids for m in minutes(OPEN, until)]


def run(store, kite, now=at(15, 45), **kw):
    return finalize_trading_day(store, DAY, InMemoryCandleSource(kite), IDS, now=now, **kw)


def test_candles_that_stop_before_the_last_minute_leave_the_day_provisional_and_retryable():
    store = day_store()
    cut = run(store, candles(at(15, 28)))  # every instrument has live bars to 15:29; Kite's stop at 15:28
    assert cut.status is DayStatus.PROVISIONAL and store.day_status(DAY) is DayStatus.PROVISIONAL
    assert cut.errors == {"incomplete": 3}
    again = run(store, candles(LAST), now=at(16, 5))  # the retry with the complete answer makes it final
    assert again.status is DayStatus.FINAL and again.errors == {}
    assert {b.source for b in store.bars_for_day(DAY)} == {BarSource.KITE}


def test_one_instrument_short_is_enough_to_refuse():
    kite = candles(LAST, IDS[:2]) + [bar(IDS[2], m, BarSource.KITE) for m in minutes(OPEN, at(15, 20))]
    result = run(day_store(), kite)
    assert result.status is DayStatus.PROVISIONAL and result.errors == {"incomplete": 1}


def test_an_instrument_whose_live_bars_stop_early_needs_candles_only_that_far():
    store = InMemoryHistoryStore()  # an illiquid contract: last trade 14:10 (Kite lists only minutes with trades)
    store.put_bars([bar(i, m, BarSource.LIVE) for i in IDS[:2] for m in minutes(OPEN, LAST)]
                   + [bar(IDS[2], m, BarSource.LIVE) for m in minutes(OPEN, at(14, 10))])
    kite = candles(LAST, IDS[:2]) + [bar(IDS[2], m, BarSource.KITE) for m in minutes(OPEN, at(14, 10))]
    assert run(store, kite).status is DayStatus.FINAL


def test_chunk_size_changes_nothing_about_the_result_only_the_number_of_batches():
    results = {}
    for chunk in (1, 2, 50):
        store = day_store()
        r = run(store, candles(LAST), chunk=chunk)
        results[chunk] = (r.status, r.counts, store.bars_for_day(DAY))
        assert len(r.batch_seconds) == -(-len(IDS) // chunk)
    assert results[1] == results[2] == results[50] and results[1][1].replaced == 3 * 375


def test_a_final_day_is_not_fetched_or_rewritten_again():
    store = day_store()
    source = InMemoryCandleSource(candles(LAST))
    assert finalize_trading_day(store, DAY, source, IDS, now=at(15, 45)).status is DayStatus.FINAL
    calls = source.calls
    again = finalize_trading_day(store, DAY, source, IDS, now=at(16, 5))
    assert again.status is DayStatus.FINAL and again.counts is None and source.calls == calls


def test_the_earliest_start_is_still_1540_ist():
    with pytest.raises(FinalizeRefused):
        run(day_store(), candles(LAST), now=at(15, 39, 59))
    assert finalize_into  # the domain function has no clock: the job owns the 15:40 rule (F-33)
