"""The recorder: listens on the W-059 fan-out and writes closed one-minute bars to the history store (W-062, ADR-067).

It subscribes only to ids the feed ALREADY carries (``FanOut.subscriber_count > 0``), so it never causes a vendor
subscription (ADR-067). Its work per quote is the bar builder's dict update. Any exception from the builder or the
store is caught, counted and logged without values, and never propagates (REQ-051 AC-5): the fan-out also isolates
listeners, and the recorder does not rely on that. No raw quote is kept. Standard library only.
"""
from __future__ import annotations

import datetime
import logging
from collections import Counter
from typing import Sequence

from ofo.history.bars import MinuteBarBuilder
from ofo.history.store import HistoryStore
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import NormalizedQuote

log = logging.getLogger("ofo.history")


class Recorder:
    def __init__(self, store: HistoryStore, builder: MinuteBarBuilder | None = None) -> None:
        self._store = store
        self.builder = builder or MinuteBarBuilder()
        self.counters: Counter = Counter()
        self._gaps_sent = 0
        self._handle: int | None = None
        self._fanout: FanOut | None = None

    def attach(self, fanout: FanOut, instrument_ids: Sequence[str]) -> list[str]:
        """Listen on the ids the feed already carries; returns the ids actually attached."""
        carried = [i for i in instrument_ids if fanout.subscriber_count(i) > 0]
        self.counters["not_carried"] += len(instrument_ids) - len(carried)
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

    def flush(self, now: datetime.datetime) -> None:
        try:
            bars = self.builder.flush(now)
            self._sync_gaps()
            self._store_bars(bars)
        except Exception as exc:
            self._failed(exc)

    def _sync_gaps(self) -> None:
        gaps = self.builder.gaps
        if len(gaps) > self._gaps_sent:
            new = gaps[self._gaps_sent:]
            self._gaps_sent = len(gaps)
            self._store.record_gaps(new)

    def _store_bars(self, bars) -> None:
        if not bars:
            return
        try:
            self._store.put_bars(bars)
            self.counters["bars_written"] += len(bars)
        except Exception:
            self.counters["bars_lost"] += len(bars)
            raise

    def _failed(self, exc: Exception) -> None:
        self.counters["errors"] += 1
        log.warning("history recorder error: %s", type(exc).__name__)  # the type only, never values
