"""One provider stream fanned out to any number of in-process subscribers (REQ-048 AC-4).

There is one vendor subscription per instrument no matter how many subscribers want it: the provider's ``subscribe``
is called when the first subscriber for an instrument arrives and ``unsubscribe`` when the last leaves.

The producer (the socket's read loop) only ENQUEUES: each subscriber has its own bounded queue (drop-oldest). A
subscriber that never drains cannot slow the others or the producer; its queue stops growing at ``max_queue``, the
drops are counted (``dropped``) and it shows a ``lagging`` flag. Delivery to listeners happens in ``pump`` (or the
consumer calls ``drain`` itself), in arrival order; a listener that raises is counted and skipped.

Subscribing is atomic: the provider is asked first, and only on success is any state recorded; a provider that
half-applies a failed call is told to unsubscribe the ids it was given.
"""
from __future__ import annotations

from collections import deque
from typing import Sequence

from ofo.marketdata.provider import MarketDataProvider, QuoteListener
from ofo.marketdata.quote import NormalizedQuote

DEFAULT_MAX_QUEUE = 10_000


class _Sub:
    __slots__ = ("listener", "ids", "queue", "max_queue", "dropped", "lagging")

    def __init__(self, listener: QuoteListener, ids: tuple[str, ...], max_queue: int) -> None:
        self.listener, self.ids, self.max_queue = listener, ids, max_queue
        self.queue: deque[NormalizedQuote] = deque()
        self.dropped = 0
        self.lagging = False


class FanOut:
    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider
        self._by_instrument: dict[str, list[int]] = {}
        self._subs: dict[int, _Sub] = {}
        self._next = 1
        self.listener_errors = 0
        provider.live_quote_stream(self._publish)

    def subscribe(self, listener: QuoteListener, instrument_ids: Sequence[str], *,
                  max_queue: int = DEFAULT_MAX_QUEUE) -> int:
        if max_queue < 1:
            raise ValueError("max_queue must be >= 1")
        ids = tuple(dict.fromkeys(instrument_ids))
        new = [i for i in ids if not self._by_instrument.get(i)]
        if new:
            try:
                self._provider.subscribe(new)
            except Exception:
                try:
                    self._provider.unsubscribe(new)  # undo anything a half-applying provider already did
                except Exception:
                    pass
                raise
        handle = self._next
        self._next += 1
        self._subs[handle] = _Sub(listener, ids, max_queue)
        for i in ids:
            self._by_instrument.setdefault(i, []).append(handle)
        return handle

    def unsubscribe(self, handle: int) -> None:
        sub = self._subs.pop(handle, None)
        if sub is None:
            return
        gone = []
        for i in sub.ids:
            handles = self._by_instrument[i]
            handles.remove(handle)
            if not handles:
                del self._by_instrument[i]
                gone.append(i)
        if gone:
            self._provider.unsubscribe(gone)

    def subscriber_count(self, instrument_id: str) -> int:
        return len(self._by_instrument.get(instrument_id, ()))

    # ---- per-subscriber queue state ----
    def dropped(self, handle: int) -> int:
        return self._subs[handle].dropped

    def is_lagging(self, handle: int) -> bool:
        sub = self._subs.get(handle)
        return bool(sub and sub.lagging)

    def queue_len(self, handle: int) -> int:
        return len(self._subs[handle].queue)

    def drain(self, handle: int) -> list[NormalizedQuote]:
        """Take everything queued for one subscriber, oldest first."""
        sub = self._subs[handle]
        items = list(sub.queue)
        sub.queue.clear()
        sub.lagging = False
        return items

    def pump_one(self, handle: int, *, limit: int | None = None) -> int:
        """Deliver up to ``limit`` queued quotes to one subscriber's listener; returns how many."""
        sub = self._subs[handle]
        n = 0
        while sub.queue and (limit is None or n < limit):
            quote = sub.queue.popleft()
            n += 1
            try:
                sub.listener(quote)
            except Exception:  # a bad subscriber must not stop the others
                self.listener_errors += 1
        if not sub.queue:
            sub.lagging = False
        return n

    def pump(self) -> int:
        """Deliver everything queued to every subscriber's listener."""
        return sum(self.pump_one(h) for h in tuple(self._subs))

    def _publish(self, quote: NormalizedQuote) -> None:
        """Producer side: enqueue only, never call a subscriber, never block."""
        for handle in self._by_instrument.get(quote.instrument_id, ()):
            sub = self._subs[handle]
            if len(sub.queue) >= sub.max_queue:
                sub.queue.popleft()
                sub.dropped += 1
                sub.lagging = True
            sub.queue.append(quote)
