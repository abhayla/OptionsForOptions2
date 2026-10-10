"""The recorder: listens on the W-059 fan-out and writes closed one-minute bars to the history store (W-062, ADR-067).

It subscribes only to ids the feed ALREADY carries (``FanOut.subscriber_count > 0``), so it never causes a vendor
subscription (ADR-067). No raw quote is kept. Standard library only.

The feed thread never waits on the store (W-067 round 2, REQ-051 AC-5). ``on_quote`` does the bar builder's dict update
and hands what closed to a bounded queue; ONE background writer thread owns every store call. So a slow, locked or dead
database costs the feed a queue append, never a wait (round 1 measured 15.06 s per write under a held lock).
- The queue is bounded by BARS (``max_queued_bars``). When it is full the new bars are dropped, counted
  (``bars_dropped_full``) and their minute is recorded as a feed gap, so the finalize job backfills it from Kite
  (ADR-067: the drop is filled later by the existing gap path, never silently lost).
- A write that fails in the writer is counted and logged without values (``errors``/``bars_lost``) and never reaches
  the feed; the minutes of the lost bars are recorded as gaps too, retried until the store takes them.
- A recorded gap is coarse on purpose: the gap rule works per minute for every instrument, so one dropped bar turns
  that minute into a Kite-filled minute for all instruments (BACKFILLED, ADR-067). Cheap and correct beats precise.
"""
from __future__ import annotations

import datetime
import logging
import queue
import threading
from collections import Counter
from typing import Sequence

from ofo.history.bars import ONE_MINUTE, MinuteBarBuilder
from ofo.history.store import HistoryStore
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import NormalizedQuote

log = logging.getLogger("ofo.history")

MAX_QUEUED_BARS = 20_000  # about 12 full-universe minute closes (1,603 instruments); memory is bounded by this
MAX_PENDING_GAPS = 5_000  # gaps waiting for a store that cannot take them; beyond this they are counted, not kept
_STOP = object()
Gap = tuple[datetime.datetime, datetime.datetime]


class RecorderClosed(RuntimeError):
    """The recorder has been closed: nothing more is accepted."""


class Recorder:
    def __init__(self, store: HistoryStore, builder: MinuteBarBuilder | None = None, *,
                 max_queued_bars: int = MAX_QUEUED_BARS) -> None:
        self._store = store
        self.builder = builder or MinuteBarBuilder()
        self.counters: Counter = Counter()
        self._count_lock = threading.Lock()
        self._gaps_sent = 0
        self._handle: int | None = None
        self._fanout: FanOut | None = None
        self._max_queued_bars = max_queued_bars
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._cv = threading.Condition()  # guards _queued_bars, _open, _pending_gaps, _closed
        self._queued_bars = 0
        self._open = 0  # items handed over and not yet finished by the writer
        self._pending_gaps: dict[Gap, None] = {}  # gaps the store has not taken yet, in order
        self._closed = False
        self._writer: threading.Thread | None = None

    # ---- feed side: never waits on the store --------------------------------------------------------------------------
    def attach(self, fanout: FanOut, instrument_ids: Sequence[str]) -> list[str]:
        """Listen on the ids the feed already carries; returns the ids actually attached."""
        carried = [i for i in instrument_ids if fanout.subscriber_count(i) > 0]
        self._count("not_carried", len(instrument_ids) - len(carried))
        if carried:
            self._handle = fanout.subscribe(self.on_quote, carried)
            self._fanout = fanout
        return carried

    def detach(self) -> None:
        if self._fanout is not None and self._handle is not None:
            self._fanout.unsubscribe(self._handle)
        self._handle = self._fanout = None

    def on_quote(self, quote: NormalizedQuote) -> None:
        try:
            bars = self.builder.on_quote(quote)
            self._sync_gaps()  # the gap is known to the store BEFORE the bars it makes suspect arrive
            self._store_bars(bars)
        except Exception as exc:
            self._failed(exc)

    def flush(self, now: datetime.datetime, *, wait_s: float = 0.0) -> None:
        """Close the bars still open at ``now``. ``wait_s`` > 0 also waits that long for the writer (tests, shutdown;
        never on a feed thread)."""
        try:
            bars = self.builder.flush(now)
            self._sync_gaps()
            self._store_bars(bars)
        except Exception as exc:
            self._failed(exc)
        if wait_s > 0:
            self.drain(wait_s)

    def _sync_gaps(self) -> None:
        gaps = self.builder.gaps
        if len(gaps) > self._gaps_sent:
            new = gaps[self._gaps_sent:]
            self._hand_over(("gaps", list(new)), 0)  # raises when it could not be handed over: not advanced then
            self._gaps_sent = len(gaps)  # only after the hand-over succeeded

    def _store_bars(self, bars) -> None:
        if not bars:
            return
        bars = list(bars)
        with self._cv:
            room = self._max_queued_bars - self._queued_bars
            full = len(bars) > room
        if full:  # bounded: drop, count, and mark the minutes as a gap for the finalize backfill
            self._count("bars_dropped_full", len(bars))
            self._count("bars_lost", len(bars))
            self._add_gaps(_minute_gaps(bars))
            return
        self._hand_over(("bars", bars), len(bars))

    def _hand_over(self, item: tuple[str, list], bars: int) -> None:
        with self._cv:
            if self._closed:
                raise RecorderClosed("the recorder is closed")
            self._queued_bars += bars
            self._open += 1
            if self._writer is None:
                self._writer = threading.Thread(target=self._run, name="ofo-history-writer", daemon=True)
                self._writer.start()
        self._queue.put(item)

    # ---- writer side: the only code that calls the store ---------------------------------------------------------------
    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            batch = [item]
            stop = False
            while batch[-1][0] == "bars":  # coalesce queued bar batches into ONE store write (one transaction)
                try:
                    nxt = self._queue.get_nowait()
                except queue.Empty:
                    break
                if nxt is _STOP:
                    stop = True
                    break
                if nxt[0] != "bars":
                    batch.append(nxt)
                    break
                batch.append(nxt)
            try:
                self._write(batch)
            except Exception as exc:  # the writer must never die: a thread that stops silently loses every later bar
                self._failed(exc)
            with self._cv:
                self._open -= len(batch)
                self._queued_bars -= sum(len(i[1]) for i in batch if i[0] == "bars")
                self._cv.notify_all()
            if stop:
                return

    def _write(self, batch: list[tuple[str, list]]) -> None:
        self._retry_pending_gaps()
        i = 0
        while i < len(batch):
            kind = batch[i][0]
            j = i
            payload: list = []
            while j < len(batch) and batch[j][0] == kind:
                payload.extend(batch[j][1])
                j += 1
            if kind == "gaps":
                self._record_gaps(payload)
            else:
                self._put_bars(payload)
            i = j

    def _record_gaps(self, gaps: list[Gap]) -> None:
        if not gaps:
            return
        try:
            self._store.record_gaps(gaps)
        except Exception as exc:
            self._failed(exc)
            self._add_gaps(gaps)  # keep them: retried before the next write

    def _put_bars(self, bars: list) -> None:
        try:
            self._store.put_bars(bars)
            self._count("bars_written", len(bars))
        except Exception as exc:
            self._count("bars_lost", len(bars))
            self._failed(exc)
            self._add_gaps(_minute_gaps(bars))  # Kite fills these minutes at finalize (ADR-067)

    def _retry_pending_gaps(self) -> None:
        with self._cv:
            pending = list(self._pending_gaps)
        if not pending:
            return
        try:
            self._store.record_gaps(pending)
        except Exception as exc:
            self._failed(exc)
            return
        with self._cv:
            for gap in pending:
                self._pending_gaps.pop(gap, None)

    def _add_gaps(self, gaps) -> None:
        with self._cv:
            for gap in gaps:
                if gap in self._pending_gaps:
                    continue
                if len(self._pending_gaps) >= MAX_PENDING_GAPS:
                    self.counters["gaps_lost"] += 1  # under _cv; read only for reporting
                    continue
                self._pending_gaps[gap] = None

    # ---- lifecycle ------------------------------------------------------------------------------------------------------
    def drain(self, timeout: float = 5.0) -> bool:
        """Wait until the writer has finished everything handed over. Returns False on timeout. Tests and shutdown only: never call this from a feed thread."""
        with self._cv:
            done = self._cv.wait_for(lambda: self._open == 0, timeout)
        return done

    def close(self, timeout: float = 5.0) -> bool:
        """Stop accepting, let the writer finish what it holds (up to ``timeout``), stop it."""
        if self._writer is not None and self._open:
            self.drain(timeout)
        try:
            self._hand_over(("gaps", []), 0)  # one last try at the gaps the store could not take
        except RecorderClosed:
            pass
        self.drain(timeout)
        with self._cv:
            self._closed = True
            writer = self._writer
        if writer is not None:
            self._queue.put(_STOP)
            writer.join(timeout)
            return not writer.is_alive()
        return True

    @property
    def pending_gaps(self) -> list[Gap]:
        with self._cv:
            return list(self._pending_gaps)

    # ---- counting ---------------------------------------------------------------------------------------------------------
    def _count(self, key: str, n: int = 1) -> None:
        with self._count_lock:
            self.counters[key] += n

    def _failed(self, exc: Exception) -> None:
        self._count("errors")
        log.warning("history recorder error: %s", type(exc).__name__)  # the type only, never values


def _minute_gaps(bars) -> list[Gap]:
    """One gap per distinct bar minute: the minute the store could not take."""
    return [(m, m + ONE_MINUTE) for m in sorted({b.minute for b in bars})]
