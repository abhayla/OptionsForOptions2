"""W-067 round 2, AC-5 (REQ-051): the recorder never makes the feed thread wait on the history store.

Spec basis (quoted): REQ-051 AC-5 "Historical data and simulation never block live strategy creation, Option Chain,
execution or monitoring"; ADR-067 (a minute the live feed could not keep is filled from Kite's candles by the gap path).
Round 1 waited on the store from the feed thread (15.06 s under a held database lock). These tests use a store that
blocks, fails, or recovers on demand; the PostgreSQL proof is tests_app/test_history_nonblocking.py.
"""
import datetime
import threading
from decimal import Decimal

import pytest
from _history_fixture import DAY, at
from test_session_gaps import index_quote

from ofo.history.bars import BarSource
from ofo.history.recorder import Recorder, RecorderClosed
from ofo.history.store import InMemoryHistoryStore

LIVENESS_S = 60  # a generous liveness bound for a feed that must not wait at all


class BlockableStore(InMemoryHistoryStore):
    """Behaves like the in-memory store, but every write first waits for ``open`` (a locked database) or raises."""

    def __init__(self):
        super().__init__()
        self.open = threading.Event()
        self.open.set()
        self.fail = 0  # raise on the next N put_bars calls
        self.entered = threading.Event()
        self.threads: set[str] = set()

    def put_bars(self, bars):
        self.entered.set()
        self.threads.add(threading.current_thread().name)
        self.open.wait(30)
        if self.fail:
            self.fail -= 1
            raise RuntimeError("secret-looking-value 123.45")
        super().put_bars(bars)

    def record_gaps(self, gaps):
        self.entered.set()
        self.threads.add(threading.current_thread().name)
        self.open.wait(30)
        super().record_gaps(gaps)


def feed_minutes(rec, first=(10, 0), minutes=8, ltp=100):
    """Twenty quotes a minute (no quiet spell, so no feed gap); each minute's first quote closes the previous bar."""
    for i in range(minutes):
        for sec in range(1, 60, 3):
            ts = at(first[0], first[1]) + datetime.timedelta(minutes=i, seconds=sec)
            rec.on_quote(index_quote(ts, str(ltp + i)))


def feed_finishes_while_the_store_is_blocked(rec, **kw) -> bool:
    """Runs the feed on its own thread; True when every feed call returned while the store stays blocked. A feed that
    waited on the store would never finish (the store is opened only after this returns) - a liveness check, not a
    timing threshold (finding wall-clock-assertion-flakes-under-load)."""
    feeder = threading.Thread(target=feed_minutes, args=(rec,), kwargs=kw, daemon=True)
    feeder.start()
    feeder.join(LIVENESS_S)
    return not feeder.is_alive()


def test_a_store_that_blocks_never_blocks_the_feed_thread_and_nothing_is_lost_when_it_frees():
    store = BlockableStore()
    store.open.clear()
    rec = Recorder(store)
    assert feed_finishes_while_the_store_is_blocked(rec), "the feed thread waited on a blocked store"
    assert store.entered.wait(5) and rec.counters["bars_written"] == 0  # the writer is stuck, the feed is not
    store.open.set()
    assert rec.drain(10)
    assert [b.minute.minute for b in store.bars("NSE_INDEX:1001", DAY)] == list(range(0, 7))  # 7 closed bars, in order
    assert rec.counters["bars_lost"] == 0 and rec.counters["bars_written"] == 7
    assert store.threads == {"ofo-history-writer"}  # every store call ran on the writer, none on the feed thread
    rec.close()


def test_the_queue_is_bounded_and_a_dropped_bar_becomes_a_gap_for_the_kite_backfill():
    store = BlockableStore()
    store.open.clear()
    rec = Recorder(store, max_queued_bars=2)
    assert feed_finishes_while_the_store_is_blocked(rec, minutes=8)
    assert store.entered.wait(5)
    assert rec._queued_bars <= 2  # never more than the bound in memory
    assert rec.counters["bars_dropped_full"] >= 4 and rec.counters["bars_lost"] == rec.counters["bars_dropped_full"]
    store.open.set()
    assert rec.drain(10) and rec.close(10)
    assert rec.pending_gaps == []  # the store took every recorded gap
    dropped_minutes = {m for m in range(0, 7)} - {b.minute.minute for b in store.bars("NSE_INDEX:1001", DAY)}
    assert len(dropped_minutes) == rec.counters["bars_dropped_full"]  # every drop is accounted for
    covered = {g[0].minute for g in store.gaps(DAY)}
    assert dropped_minutes <= covered  # and each dropped minute is a recorded gap: finalize backfills it from Kite


def test_a_failed_write_is_counted_never_reaches_the_feed_and_its_minutes_become_gaps(caplog):
    store = BlockableStore()
    store.fail = 1
    rec = Recorder(store)
    with caplog.at_level("WARNING"):
        feed_minutes(rec, minutes=3)  # must not raise
        assert rec.drain(10)
        feed_minutes(rec, first=(10, 3), minutes=3)  # the writer is still alive after the failure
        assert rec.drain(10)
    assert rec.counters["errors"] >= 1 and rec.counters["bars_lost"] >= 1 and rec.counters["bars_written"] >= 1
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in text and "secret-looking-value" not in text and "123.45" not in text
    lost = {g[0].minute for g in store.gaps(DAY)}
    assert lost and not any(b.minute.minute in lost and b.source is BarSource.LIVE
                            for b in store.bars("NSE_INDEX:1001", DAY))  # the failed minute is a gap, not a LIVE bar
    rec.close()


def test_a_gap_the_store_cannot_take_is_kept_and_retried_not_lost():
    class GapDown(BlockableStore):
        down = True

        def record_gaps(self, gaps):
            if self.down:
                raise RuntimeError("down")
            super().record_gaps(gaps)

    store = GapDown()
    rec = Recorder(store)
    for ts in (at(10, 0, 0), at(10, 1, 54), at(10, 1, 55)):  # a 114 s quiet spell at 10:00 is a feed gap
        rec.on_quote(index_quote(ts))
    assert rec.drain(10) and rec.builder.gaps and store.gaps(DAY) == []
    assert rec.pending_gaps == list(rec.builder.gaps)  # kept, not dropped
    store.down = False
    rec.on_quote(index_quote(at(10, 3, 0)))
    assert rec.drain(10) and rec.pending_gaps == [] and store.gaps(DAY) == rec.builder.gaps
    rec.close()


def test_the_gap_counter_advances_only_after_the_gap_was_handed_over():
    store = BlockableStore()
    rec = Recorder(store)
    rec.on_quote(index_quote(at(10, 0, 0)))
    rec.close()
    with pytest.raises(RecorderClosed):
        rec._hand_over(("gaps", []), 0)
    rec.on_quote(index_quote(at(10, 1, 54)))  # the builder now holds a gap; the closed recorder cannot take it
    rec.on_quote(index_quote(at(10, 1, 55)))
    assert rec.builder.gaps and rec._gaps_sent == 0 and rec.counters["errors"] >= 1


def test_the_default_recorder_writes_nothing_on_the_feed_thread_even_with_a_fast_store():
    store = BlockableStore()
    rec = Recorder(store)
    feed_minutes(rec, minutes=4)
    assert rec.drain(10)
    assert Decimal("100") == store.bars("NSE_INDEX:1001", DAY)[0].open
    assert threading.current_thread().name not in store.threads
    rec.close()
