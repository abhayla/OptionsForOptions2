"""ONE shared, cached, single-flight reading of a vendor REST quote (REQ-118 Kite rate budget; ADR-330 (39)).

Class fixed: "a page poll calls the vendor REST before the tick store". The REST index quote is a FALLBACK for a spot
the tick store cannot give; every caller that needs it goes through one ``SharedReading`` per process, so twelve
requests inside the TTL are ONE vendor call (single flight + a positive TTL), and a FAILED answer (a 429 cooldown, a
timeout) is remembered for ``failed_ttl`` so nothing is sent inside the vendor's cooldown. A failure here is only
"no REST spot": it never touches a leg's or the feed's health. ``ABSENT`` (no session) is not cached: asking costs
nothing. ``clock`` is the seam (monotonic seconds); a test injects it and never sleeps.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from ofo.marketdata.spot_source import SourceReading, SourceState

READ_TTL_SECONDS = 5.0  # a stated reading is reused this long (well under the 1 request/s quote bucket)
FAILED_TTL_SECONDS = 10.0  # Kite's documented cooldown after a 429 (rate_limit.COOLDOWN_SECONDS)
_NOT_CACHED = frozenset({SourceState.ABSENT})


class SharedReading:
    def __init__(self, *, ttl: float = READ_TTL_SECONDS, failed_ttl: float = FAILED_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._failed_ttl, self._clock = ttl, failed_ttl, clock
        self._kept: dict[str, tuple[float, SourceReading]] = {}
        self._flying: dict[str, asyncio.Future[SourceReading]] = {}
        self.calls = 0  # vendor reads started (the counter a test reads)

    def peek(self, key: str) -> SourceReading | None:
        held = self._kept.get(key)
        return held[1] if held is not None and self._clock() < held[0] else None

    async def get(self, key: str, fetch: Callable[[], Awaitable[SourceReading]]) -> SourceReading:
        kept = self.peek(key)
        if kept is not None:
            return kept
        flying = self._flying.get(key)
        if flying is None:
            self.calls += 1
            flying = self._flying[key] = asyncio.ensure_future(self._fly(key, fetch))
            flying.add_done_callback(lambda f: f.cancelled() or f.exception())  # retrieved: no warning if all left
        # The fetch is its OWN task: a caller whose request is cancelled (a shorter deadline) drops only its own wait,
        # never the flight the other waiters share; the result is still kept for the next caller.
        return await asyncio.shield(flying)

    async def _fly(self, key: str, fetch: Callable[[], Awaitable[SourceReading]]) -> SourceReading:
        try:
            reading = await fetch()
        finally:
            self._flying.pop(key, None)  # an exception is shared with the waiters and never kept
        if reading.state not in _NOT_CACHED:
            ttl = self._failed_ttl if reading.state is SourceState.FAILED else self._ttl
            self._kept[key] = (self._clock() + ttl, reading)
        return reading
