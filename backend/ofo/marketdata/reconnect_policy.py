"""The live-feed health and reconnect numbers, each with its REQ-114 acceptance criterion as the source (W-139).

The one home of these values: ``ofo_app.kite_ws`` imports them, nothing else restates them. Standard library only; pure
functions; the random source is passed in so a test with a fixed seed can assert the bounds (AC-3).
"""
from __future__ import annotations

import datetime
from typing import Final, Protocol

#: REQ-114 AC-1: every connection checks the time of its last frame (tick or heartbeat) this often.
CHECK_EVERY: Final = datetime.timedelta(seconds=15)
#: REQ-114 AC-2: this long with no frame of any kind and the connection is closed and reconnected.
SILENT_AFTER: Final = datetime.timedelta(seconds=60)
#: REQ-114 AC-3: reconnect waits start at 1 s, double, and are capped at 30 s.
BACKOFF_START: Final = 1
BACKOFF_MAX: Final = 30
#: REQ-114 AC-3: each wait carries random jitter of up to 50% of the wait (taken off it, so the 30 s cap always holds).
JITTER_FRACTION: Final = 0.5
#: REQ-114 AC-7: outside market hours the connection is re-opened at most this often.
CLOSED_RETRY_EVERY: Final = 5 * 60


class Uniform(Protocol):
    def uniform(self, low: float, high: float) -> float: ...


def next_backoff(current: float) -> float:
    """The nominal wait after ``current``: doubled, never above ``BACKOFF_MAX`` (AC-3)."""
    return min(current * 2, BACKOFF_MAX)


def jittered(nominal: float, rng: Uniform) -> float:
    """``nominal`` less a random 0-50% of itself: between half the wait and the whole wait, so many users' sockets
    do not reconnect in the same second and the cap is never exceeded (AC-3)."""
    return nominal * (1 - rng.uniform(0, JITTER_FRACTION))


def reconnect_wait(nominal: float, rng: Uniform, *, market_open: bool) -> float:
    """How long to wait before the next connect: the jittered back-off, and outside market hours never less than
    ``CLOSED_RETRY_EVERY`` (silence is expected then, AC-7)."""
    wait = jittered(nominal, rng)
    return wait if market_open else max(wait, float(CLOSED_RETRY_EVERY))


def is_silent(now: datetime.datetime, last_frame: datetime.datetime) -> bool:
    """AC-2: no frame of any kind for ``SILENT_AFTER`` (exactly 60 s counts)."""
    return now - last_frame >= SILENT_AFTER


def next_check(now: datetime.datetime, last_frame: datetime.datetime) -> datetime.datetime:
    """When the connection is checked next: within ``CHECK_EVERY`` (AC-1), and never later than the moment 60 s of
    silence would be reached, so the close happens at 60 s and not at the next 15 s step."""
    deadline = last_frame + SILENT_AFTER
    return min(now + CHECK_EVERY, deadline) if deadline > now else now + CHECK_EVERY
