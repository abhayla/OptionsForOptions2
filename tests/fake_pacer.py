"""A fake clock and fake sleeps for the Kite rate limiter tests (REQ-118): a test never really sleeps.

``FakePacer()`` is manual: ``sleep_until`` blocks the calling thread until the test calls ``advance`` far enough (the
test decides when a slot arrives, so "nothing was sent before then" is checkable). ``FakePacer(auto=True)`` jumps the
clock to the slot at once, for single-threaded tests. A real-time timeout turns a hang into a failure.
"""
from __future__ import annotations

import asyncio
import threading
import time

_EPS = 1e-9
HANG_SECONDS = 10.0  # real seconds a test waits before a stuck sleeper becomes a failure


class FakePacer:
    def __init__(self, *, auto: bool = False) -> None:
        self.t = 0.0
        self._auto = auto
        self._cond = threading.Condition()

    def now(self) -> float:
        with self._cond:
            return self.t

    def advance(self, seconds: float) -> None:
        with self._cond:
            self.t += seconds
            self._cond.notify_all()

    def sleep_until(self, at: float) -> None:
        with self._cond:
            if self._auto:
                self.t = max(self.t, at)
                return
            if not self._cond.wait_for(lambda: self.t >= at - _EPS, timeout=HANG_SECONDS):
                raise AssertionError(f"a sleeper for t={at} was never released (clock at {self.t})")

    async def asleep_until(self, at: float) -> None:
        deadline = time.monotonic() + HANG_SECONDS
        while self.now() < at - _EPS:
            if self._auto:
                self.advance(at - self.now())
                return
            if time.monotonic() > deadline:
                raise AssertionError(f"an async sleeper for t={at} was never released")
            await asyncio.sleep(0.002)


def wait_for(condition, what: str, seconds: float = HANG_SECONDS) -> None:
    """Real-time wait (event-style poll) for another thread to reach a state; fails with ``what`` on timeout."""
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for: {what}")
        time.sleep(0.002)
