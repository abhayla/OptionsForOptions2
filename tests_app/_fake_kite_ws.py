"""A scripted Kite socket for the silence / reconnect tests (REQ-114): the REAL ``KiteSocket`` runs on an injected clock
against a fake connection that replays recorded frames, then goes silent. Nothing here sleeps for real time: the fake
``recv`` advances the injected clock by one poll step and raises ``TimeoutError`` exactly as the socket's own 0.5 s poll
does, so a 60 s silence takes microseconds and is measured on the injected clock only. No network, no order ever
sent."""
from __future__ import annotations

import datetime
import gzip
import json
import pathlib
from collections.abc import Callable

from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_frames import iter_recording
from ofo.marketdata.kite_provider import IST, KiteProvider

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
API_KEY, TOKEN = "KEY-abc123", "TOK-xyz789"
START = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=IST)  # a Thursday inside the session, not a holiday


class SimClock:
    def __init__(self, start: datetime.datetime = START) -> None:
        self.now = start

    def __call__(self) -> datetime.datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += datetime.timedelta(seconds=seconds)


class NoJitter:
    """A random source whose draw is always the low end: the wait is then exactly the nominal back-off."""

    def uniform(self, low: float, high: float) -> float:
        return low


def recorded_frames(n: int) -> list[bytes]:
    with gzip.open(FIXTURES / "frames-2026-10-08-092000-10s.bin.gz") as f:
        return [frame for _, frame in iter_recording(f)][:n]


def new_provider(clock: Callable[[], datetime.datetime]) -> KiteProvider:
    listed = list(parse_instruments_csv(FIXTURES / "instruments-2026-10-08-subscribed.csv"))
    provider = KiteProvider(listed, clock=clock)
    provider.subscribe([f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in listed[:5]]
                       + ["NSE_INDEX:1001"])
    return provider


class FakeWs:
    """``script`` items: ``("bytes", data)`` delivered at once; ``("text", str)``; ``("call", fn)`` runs a probe;
    ``("silence", seconds)`` = the poll
    times out every ``step`` seconds of the injected clock until that much time has passed."""

    def __init__(self, clock: SimClock, script: list[tuple], *, step: float = 0.5, on_end: Callable[[], None]) -> None:
        self.clock, self.script, self.step, self.on_end = clock, list(script), step, on_end
        self.sent: list[dict] = []
        self.closed_at: datetime.datetime | None = None
        self.opened_at = clock.now
        self._silence_left = 0.0

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self):
        if self._silence_left > 0:
            return self._tick_silence()
        if not self.script:
            self.on_end()
            return self._tick_silence(force=True)
        kind, value = self.script.pop(0)
        if kind == "call":  # a probe run at this point of the connection's life (reads state, changes nothing)
            value()
            return await self.recv()
        if kind == "silence":
            self._silence_left = float(value)
            return self._tick_silence()
        return value

    def _tick_silence(self, force: bool = False):
        step = self.step if force else min(self.step, self._silence_left)
        self.clock.advance(step)
        self._silence_left = max(0.0, self._silence_left - step)
        raise TimeoutError


class FakeConnect:
    """The injected ``connect``: hands out one scripted ``FakeWs`` per connection, in order."""

    def __init__(self, clock: SimClock, scripts: list[list[tuple]], *, step: float = 0.5) -> None:
        self.clock, self.scripts, self.step = clock, list(scripts), step
        self.sockets: list[FakeWs] = []
        self.on_end: Callable[[], None] = lambda: None

    def __call__(self, url: str, **kwargs):
        if not self.scripts:
            self.on_end()
            raise OSError("no scripted connection left")
        ws = FakeWs(self.clock, self.scripts.pop(0), step=self.step, on_end=self.on_end)
        self.sockets.append(ws)
        return _Cm(ws)


class _Cm:
    def __init__(self, ws: FakeWs) -> None:
        self.ws = ws

    async def __aenter__(self) -> FakeWs:
        return self.ws

    async def __aexit__(self, *exc) -> bool:
        self.ws.closed_at = self.ws.clock.now
        return False


class Sleeper:
    """The injected ``sleep``: records the wait and moves the injected clock by it."""

    def __init__(self, clock: SimClock) -> None:
        self.clock, self.sleeps = clock, []
        self.on_sleep: Callable[[], None] = lambda: None

    async def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.on_sleep()
        self.clock.advance(seconds)
