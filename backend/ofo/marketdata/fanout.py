"""One provider stream fanned out to any number of in-process subscribers (REQ-048 AC-4).

There is one vendor subscription per instrument no matter how many subscribers want it: the provider's ``subscribe``
is called when the first subscriber for an instrument arrives and ``unsubscribe`` when the last leaves. Delivery to
each subscriber keeps arrival order. A subscriber that raises is counted and skipped; it never stops the others.
"""
from __future__ import annotations

from typing import Sequence

from ofo.marketdata.provider import MarketDataProvider, QuoteListener
from ofo.marketdata.quote import NormalizedQuote


class FanOut:
    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider
        self._by_instrument: dict[str, list[int]] = {}
        self._listeners: dict[int, tuple[QuoteListener, tuple[str, ...]]] = {}
        self._next = 1
        self.listener_errors = 0
        provider.live_quote_stream(self._publish)

    def subscribe(self, listener: QuoteListener, instrument_ids: Sequence[str]) -> int:
        handle = self._next
        self._next += 1
        ids = tuple(dict.fromkeys(instrument_ids))
        self._listeners[handle] = (listener, ids)
        new = []
        for i in ids:
            handles = self._by_instrument.setdefault(i, [])
            if not handles:
                new.append(i)
            handles.append(handle)
        if new:
            self._provider.subscribe(new)
        return handle

    def unsubscribe(self, handle: int) -> None:
        entry = self._listeners.pop(handle, None)
        if entry is None:
            return
        gone = []
        for i in entry[1]:
            handles = self._by_instrument[i]
            handles.remove(handle)
            if not handles:
                del self._by_instrument[i]
                gone.append(i)
        if gone:
            self._provider.unsubscribe(gone)

    def subscriber_count(self, instrument_id: str) -> int:
        return len(self._by_instrument.get(instrument_id, ()))

    def _publish(self, quote: NormalizedQuote) -> None:
        for handle in tuple(self._by_instrument.get(quote.instrument_id, ())):
            entry = self._listeners.get(handle)
            if entry is None:
                continue
            try:
                entry[0](quote)
            except Exception:  # a bad subscriber must not stop the others
                self.listener_errors += 1
