"""TEST-ONLY replay mode for the outcome route (W-064 step 1; REQ-035, ADR-008).

When ``OUTCOME_REPLAY`` is set AND ``APP_ENV`` is ``test``, the outcome route's provider dependency is wired to the W-059
``KiteProvider`` fed from the real recorded frames file (tests/fixtures/kite_ws), valued at the recording's last frame.
Any other ``APP_ENV`` refuses the setting at start-up (``ofo_app.config.Settings`` validator, and again here), so a
production process can never serve recorded data as if it were live.
"""
from __future__ import annotations

import datetime
import gzip
import inspect
import os
import pathlib
import time
from decimal import Decimal
from typing import Callable, Optional

from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.kite_frames import iter_recording
from ofo.marketdata.kite_provider import IST, KiteProvider

from ofo_app.live_push import LiveFeed
from ofo_app.routes.outcome import MarketContext

REPLAY_RATE = Decimal("0.065")
_FIXTURES = pathlib.Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "kite_ws"
FRAMES = _FIXTURES / "frames-2026-10-08-092000-10s.bin.gz"
INSTRUMENTS = _FIXTURES / "instruments-2026-10-08-subscribed.csv"


class ReplayRefused(RuntimeError):
    """Replay mode was requested outside APP_ENV=test."""


def replay_requested() -> bool:
    return os.environ.get("OUTCOME_REPLAY", "").strip().lower() in {"1", "true", "yes", "on"}


def require_test_env(app_env: str) -> None:
    if app_env != "test":
        raise ReplayRefused("OUTCOME_REPLAY is a test-only setting: it needs APP_ENV=test")


def _load_recording() -> tuple[list, list[tuple[datetime.datetime, bytes]]]:
    items = list(parse_instruments_csv(INSTRUMENTS))
    with gzip.open(FRAMES) as f:
        frames = [(datetime.datetime.fromtimestamp(ns / 1e9, IST), fr) for ns, fr in iter_recording(f)]
    return items, frames


def _fed_provider(items: list, frames: list[tuple[datetime.datetime, bytes]],
                  clock: Optional[Callable[[], datetime.datetime]] = None) -> KiteProvider:
    """A KiteProvider holding every recorded frame, as at the last frame."""
    provider = KiteProvider(items, clock=clock or (lambda: frames[-1][0]))
    provider.subscribe([f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in items])
    provider.on_connected(frames[0][0])
    for at, frame in frames:
        provider.on_frame(frame, at)
    return provider


def build_replay_context() -> MarketContext:
    """Replays the recorded frames into a KiteProvider; the valuation clock is fixed at the last frame."""
    items, frames = _load_recording()
    valuation = frames[-1][0]
    return MarketContext(_fed_provider(items, frames), lambda: valuation, REPLAY_RATE)


# ---- W-065: the strategy socket on the replay (TEST-ONLY) -----------------------------------------------------------
#
# Every socket connection gets its OWN provider and fan-out built from the recording, so one connection's release (which
# drops its quotes, ADR-077) never empties the next connection's prices: a browser can reconnect and pushes resume. The
# connection starts at the REST snapshot (all frames, valued at the last frame), so its first push is byte-for-byte the
# REST answer; after that the recording is played again in real time, looping, with the clock moved forward each loop,
# so quotes change and the push sends new numbers (at most one a second, ADR-068 (2)).
#
# The REST route of a replay app answers "not live" (REQ-049 AC-5's message; ADR-077) for a strategy whose legs a socket
# held and released with no socket holding them now - the replay's stand-in for the live market's "no subscriber on the
# shared feed" (issue #206). A leg no socket ever held reads as streaming (the REST snapshot), so REST-only screens keep
# their numbers; the index never drops in the recording, so it always reads as streaming.


class ReplayStreaming:
    """Which replay legs are held by a socket now, and which were held and released. ``ctx`` names the REST context the
    predicate belongs to (ofo_app.routes.outcome applies the not-live check only to its own context)."""

    def __init__(self, ctx: MarketContext, index_ids: frozenset[str]) -> None:
        self.ctx = ctx
        self._index_ids = index_ids
        self._held: dict[str, int] = {}
        self._released: set[str] = set()

    def hold(self, ids) -> None:
        for i in ids:
            self._held[i] = self._held.get(i, 0) + 1

    def release(self, ids) -> None:
        for i in ids:
            left = self._held.get(i, 0) - 1
            if left > 0:
                self._held[i] = left
            else:
                self._held.pop(i, None)
                self._released.add(i)

    def __call__(self, instrument_id: str) -> bool:
        if instrument_id in self._index_ids:
            return True
        return self._held.get(instrument_id, 0) > 0 or instrument_id not in self._released


class _ReplayFanOut(FanOut):
    """One connection's fan-out over its own replay provider. ``pump_one`` (called by the push loop every poll) first
    feeds the frames that are due by the wall clock, then delivers them; subscribe / unsubscribe report to the shared
    ``ReplayStreaming``."""

    def __init__(self, provider: KiteProvider, frames: list[tuple[datetime.datetime, bytes]], clock: "_ReplayClock",
                 streaming: ReplayStreaming, monotonic: Callable[[], float]) -> None:
        super().__init__(provider)
        self._replay_provider = provider
        self._frames = frames
        self._clock = clock
        self._streaming = streaming
        self._monotonic = monotonic
        self._start: Optional[float] = None
        self._fed = 0  # frames fed so far (over every loop)
        self._inputs: set[int] = set()  # handles that hold a strategy's inputs (see subscribe)
        first, last = frames[0][0], frames[-1][0]
        self._loop = (last - first) + LOOP_GAP

    def subscribe(self, listener, instrument_ids, **kw) -> int:
        handle = super().subscribe(listener, instrument_ids, **kw)
        # Only a hold that RECEIVES quotes (the strategy socket's legs + index, a bound ``_on_quote``) is a strategy's
        # input for the not-live stand-in. The no-listener holds (D-C33 forward strikes, REQ-083 AC-5 OI-bar contracts,
        # the chain / index / picker leases: module-level no-op functions) are not legs: releasing them must never make
        # another strategy's REST answer not live (GC-UI land fix, CI run 40806301948: 83 OI contracts released).
        if inspect.ismethod(listener):
            self._inputs.add(handle)
            self._streaming.hold(self._subs[handle].ids)
        return handle

    def unsubscribe(self, handle: int) -> None:
        sub = self._subs.get(handle)
        super().unsubscribe(handle)
        if sub is not None and handle in self._inputs:
            self._inputs.discard(handle)
            self._streaming.release(sub.ids)

    def _advance(self) -> None:
        now = self._monotonic()
        if self._start is None:  # the first pump: nothing played yet, so the first push is the REST snapshot
            self._start = now
            return
        elapsed = datetime.timedelta(seconds=now - self._start)
        first = self._frames[0][0]
        n = len(self._frames)
        while True:
            loop, idx = divmod(self._fed, n)
            at, frame = self._frames[idx]
            due = (at - first) + loop * self._loop
            if due > elapsed:
                return
            shifted = at + (loop + 1) * self._loop  # loop 0 plays after the snapshot's last frame
            self._clock.now = shifted
            self._replay_provider.on_frame(frame, shifted)
            self._fed += 1

    def pump_one(self, handle: int, *, limit: int | None = None) -> int:
        self._advance()
        return super().pump_one(handle, limit=limit)


class _ReplayClock:
    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now


#: the pause between the end of one play of the recording and the start of the next (both in replay time and real time)
LOOP_GAP = datetime.timedelta(milliseconds=500)


class ReplayFeeds:
    """Builds one replay feed per socket connection (``live.set_replay_feed`` takes this as a factory)."""

    def __init__(self, ctx: MarketContext, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._items, self._frames = _load_recording()
        provider = ctx.provider
        index_ids = frozenset(i for i in (getattr(provider, "index_id", lambda _u: None)(u)
                                           for u in SUPPORTED_UNDERLYINGS)
                              if i)
        self.streaming = ReplayStreaming(ctx, index_ids)
        self._monotonic = monotonic

    def __call__(self) -> LiveFeed:
        clock = _ReplayClock(self._frames[-1][0])
        provider = _fed_provider(self._items, self._frames, clock)  # health is read at the connection's replay clock
        ctx = MarketContext(provider, clock, REPLAY_RATE)
        return LiveFeed(ctx, _ReplayFanOut(provider, self._frames, clock, self.streaming, self._monotonic))
