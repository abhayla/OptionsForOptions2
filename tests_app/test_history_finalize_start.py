"""W-067 round 3 (REQ-051, ADR-067): the after-close job - the earliest start, a final day left alone, and the chunk size
changing nothing. Lives in tests_app because it imports ofo_app (importing it installs the W-024 root log redaction, which
must not leak into the domain suite under tests/). No database: an in-memory store."""
import datetime
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "history"))

from _history_fixture import DAY, at  # noqa: E402

from ofo.history.bars import BarSource, MinuteBar  # noqa: E402
from ofo.history.candles import InMemoryCandleSource  # noqa: E402
from ofo.history.store import DayStatus, InMemoryHistoryStore  # noqa: E402
from ofo_app.history_finalize import FinalizeRefused, finalize_trading_day  # noqa: E402

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


def day_store():
    store = InMemoryHistoryStore()
    store.put_bars([bar(i, m, BarSource.LIVE) for i in IDS for m in minutes(OPEN, LAST)])
    return store


def candles():
    return [bar(i, m, BarSource.KITE) for i in IDS for m in minutes(OPEN, LAST)]


def run(store, now=at(16, 5), **kw):
    return finalize_trading_day(store, DAY, InMemoryCandleSource(candles()), IDS, now=now, **kw)


def test_the_earliest_start_is_1600_ist_and_nothing_is_fetched_or_written_before_it():
    for now in (at(15, 39, 59), at(15, 45), at(15, 59, 59)):
        store, source = day_store(), InMemoryCandleSource(candles())
        with pytest.raises(FinalizeRefused):
            finalize_trading_day(store, DAY, source, IDS, now=now)
        assert source.calls == 0 and store.day_status(DAY) is DayStatus.PROVISIONAL
    assert run(day_store(), now=at(16, 0)).status is DayStatus.FINAL


def test_chunk_size_changes_nothing_about_the_result_only_the_number_of_batches():
    results = {}
    for chunk in (1, 2, 50):
        store = day_store()
        r = run(store, chunk=chunk)
        results[chunk] = (r.status, r.counts, store.bars_for_day(DAY))
        assert len(r.batch_seconds) == -(-len(IDS) // chunk)
    assert results[1] == results[2] == results[50] and results[1][1].replaced == 3 * 375


def test_a_final_day_is_not_fetched_or_rewritten_again():
    store = day_store()
    source = InMemoryCandleSource(candles())
    assert finalize_trading_day(store, DAY, source, IDS, now=at(16, 5)).status is DayStatus.FINAL
    calls = source.calls
    again = finalize_trading_day(store, DAY, source, IDS, now=at(16, 30))
    assert again.status is DayStatus.FINAL and again.counts is None and source.calls == calls
