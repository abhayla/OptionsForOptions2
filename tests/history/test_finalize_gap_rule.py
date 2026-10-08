"""W-062 AC-4 fix round 1: the gap rule lives in finalize_into, the one door that makes a day FINAL (ADR-067)."""
import datetime
from decimal import Decimal

from _history_fixture import DAY, at, candle_bars, replay_window
from test_finalize_from_candles import END, START, W, kite_all

from ofo.history.bars import BarSource, MinuteBar
from ofo.history.candles import InMemoryCandleSource
from ofo.history.finalize import finalize_into
from ofo.history.recorder import Recorder
from ofo.history.store import DayStatus, InMemoryHistoryStore


def one_bar(minute, source=BarSource.LIVE):
    return MinuteBar("X:1", minute, Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), 1, 1, source)


def recorded_store():
    """The real 15:06-15:12 replay through the Recorder: the store learns the feed gaps as they happen."""
    store, holder = InMemoryHistoryStore(), {}

    def wire(fan, ids):
        fan.subscribe(lambda q: None, ids)
        holder["rec"] = Recorder(store)
        holder["rec"].attach(fan, ids)

    _, _, last = replay_window(W, wire)
    holder["rec"].flush(last + datetime.timedelta(minutes=1))
    return store


def test_real_fixture_with_the_1509_candle_removed_is_absent_not_live_and_neighbours_are_backfilled():
    store = recorded_store()
    assert store.gaps(DAY)  # the recorder gave the store the gaps, not the caller
    kite = [k for k in kite_all(W) if k.minute != at(15, 9)]
    result = finalize_into(store, DAY, list(candle_bars()), InMemoryCandleSource(kite), start=START, end=END)
    bars = store.bars_for_day(DAY)
    assert not any(b.minute == at(15, 9) for b in bars)
    assert not any(b.source is BarSource.LIVE and at(15, 8) <= b.minute <= at(15, 10) for b in bars)
    by = {(b.instrument_id, b.minute): b for b in bars}
    for iid in candle_bars():
        assert by[(iid, at(15, 8))].source is BarSource.BACKFILLED
        assert by[(iid, at(15, 10))].source is BarSource.BACKFILLED
    assert result.status is DayStatus.FINAL


def test_a_live_gap_minute_kite_lacks_is_dropped_and_counted_once():
    store = InMemoryHistoryStore()
    store.put_bars([one_bar(at(10, 0))])  # stored while the feed was still thought healthy
    store.record_gaps([(at(10, 0, 5), at(10, 1, 59))])  # the gap is learned afterwards: the stored LIVE bar is removed
    store.put_bars([one_bar(at(10, 1))])  # and a late LIVE bar there never gets in
    result = finalize_into(store, DAY, ["X:1"], InMemoryCandleSource([]), start=START, end=END)
    assert result.gap_minutes_missing == 2  # both minutes (10:00 and 10:01) are inside the gap and Kite has neither
    assert not any(b.source is BarSource.LIVE for b in store.bars_for_day(DAY)) and store.bars_for_day(DAY) == []


def test_a_late_live_bar_inside_a_recorded_gap_never_reaches_the_store():
    store = InMemoryHistoryStore()
    store.record_gaps([(at(15, 8, 14), at(15, 10, 8))])
    store.put_bars([one_bar(at(15, 9))])
    assert store.bars_for_day(DAY) == [] and store.dropped_in_gap == 1


def test_a_store_that_raises_while_finalizing_leaves_the_day_provisional_without_raising():
    class ReadFails(InMemoryHistoryStore):
        def day_status(self, day):
            raise RuntimeError("db down")

    class WriteFails(InMemoryHistoryStore):
        def apply_candles(self, day, candles):
            raise RuntimeError("db down")

    for store in (ReadFails(), WriteFails()):
        result = finalize_into(store, DAY, list(candle_bars()), InMemoryCandleSource(kite_all(W)), start=START, end=END)
        assert result.status is DayStatus.PROVISIONAL and result.errors == {"store_failed": 1}
        assert InMemoryHistoryStore.day_status(store, DAY) is DayStatus.PROVISIONAL
