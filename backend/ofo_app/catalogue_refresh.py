"""Scheduled catalogue refresh: today's Zerodha list, reloaded during the trading day (W-133; REQ-053 AC-3).

Spec basis: REQ-053 AC-3 (the add-time check reads what Zerodha data allows now), F-33 / finding
daily-load-misses-intraday-additions ("a once-a-day catalogue load misses strikes listed after it ran"), ADR-058/059
(the guarded update). Nothing here is a Zerodha rule: the window below is this product's own refresh timetable.

One in-process asyncio task started by the app lifespan when ``CATALOGUE_REFRESH`` is on (explicitly "1", or by default
when ``LIVE_MARKET`` is on). It loads once at start-up (any day, any hour: a restarted app must not wait for the next
window), then every ``REFRESH_INTERVAL`` between 08:15 and 15:45 IST on weekdays. There is no exchange holiday
calendar in this project yet (``routes.execute.market_open`` says the same), so a weekday holiday runs the load too;
Zerodha's list is the same that day and the load is harmless.

Each run is ``catalogue_load.load_once`` unchanged, so every guard of ``apply_update`` applies (truncated-list refusal
per index and per expiry, identity rules, retirement). A failed or refused run keeps the previous list (nothing is
written), logs a CODE only (never a message, a URL or a row) and the next run retries on schedule. That is a reload of
a public list, not an order retry. Time-budgeted: a run has ``RUN_TIMEOUT_SECONDS``; the download is a thread and the
database work is async, so a slow or hung load never blocks the live feed or a request. Two runs never overlap.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, Final

from ofo.timeutil import IST

log = logging.getLogger(__name__)

ENV_NAME: Final = "CATALOGUE_REFRESH"
_TRUE: Final = frozenset({"1", "true", "yes", "on"})
WINDOW_OPEN: Final = datetime.time(8, 15)
WINDOW_CLOSE: Final = datetime.time(15, 45)
REFRESH_INTERVAL: Final = datetime.timedelta(minutes=60)
RUN_TIMEOUT_SECONDS: Final = 120.0
POLL_SECONDS: Final = 30.0
_SATURDAY: Final = 5  # datetime.weekday(): Monday is 0

#: The outcome codes a run reports (and logs): nothing else is ever logged about a run.
LOADED: Final = "loaded"
REFUSED: Final = "refused"
FAILED: Final = "failed"
TIMED_OUT: Final = "timed_out"
BUSY: Final = "busy"


def refresh_requested(environ: Any = None) -> bool:
    """CATALOGUE_REFRESH decides when it is set to anything; otherwise on exactly when LIVE_MARKET is on."""
    env = os.environ if environ is None else environ
    value = env.get(ENV_NAME, "").strip().lower()
    if value:
        return value in _TRUE
    return env.get("LIVE_MARKET", "").strip().lower() in _TRUE


def in_window(now: datetime.datetime) -> bool:
    """A weekday between 08:15 and 15:45 IST (no holiday calendar exists yet)."""
    local = now.astimezone(IST)
    return local.weekday() < _SATURDAY and WINDOW_OPEN <= local.time() <= WINDOW_CLOSE


class RefreshScheduler:
    """Decides when to load and runs one load at a time. ``load_once`` returns 0 on a load, non-zero on a refusal, and
    raises on a download or database failure; ``now`` is a clock returning an aware datetime."""

    def __init__(self, load_once: Callable[[], Awaitable[int]], *, now: Callable[[], datetime.datetime],
                 timeout: float = RUN_TIMEOUT_SECONDS, interval: datetime.timedelta = REFRESH_INTERVAL) -> None:
        self._load_once = load_once
        self._now = now
        self._timeout = timeout
        self._interval = interval
        self._lock = asyncio.Lock()
        self._last_started: datetime.datetime | None = None

    async def attempt(self) -> str:
        """One run now; ``BUSY`` (nothing started) when another run is still going."""
        if self._lock.locked():
            return BUSY
        async with self._lock:
            self._last_started = self._now()
            try:
                code = await asyncio.wait_for(self._load_once(), self._timeout)
            except TimeoutError:
                outcome = TIMED_OUT
            except Exception as exc:  # noqa: BLE001 - network, database; the previous list stays; type only
                log.error("catalogue refresh failed: %s", type(exc).__name__)
                return FAILED
            else:
                outcome = LOADED if code == 0 else REFUSED
            if outcome != LOADED:
                log.error("catalogue refresh %s", outcome)
            return outcome

    def due(self) -> bool:
        """Start-up (never run) is always due; afterwards a run is due only inside the window, one interval after the
        previous run STARTED (a failed run therefore retries on schedule, not in a loop)."""
        if self._last_started is None:
            return True
        now = self._now()
        return in_window(now) and now - self._last_started >= self._interval

    async def step(self) -> str | None:
        """One scheduling decision; the outcome of a run, or None when nothing was due."""
        return await self.attempt() if self.due() else None

    async def run_forever(self, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                          poll: float = POLL_SECONDS) -> None:
        """Until cancelled (shutdown): a cancel stops the loop and any run in flight (its transaction rolls back)."""
        while True:
            await self.step()
            await sleep(poll)


def start() -> asyncio.Task[None]:
    """The lifespan's entry: the real loader (``catalogue_load.load_once``) on the real clock, as one task."""
    from ofo_app import catalogue_load  # noqa: PLC0415 - late: the loader imports the database module
    from ofo_app.config import get_settings  # noqa: PLC0415

    async def load() -> int:
        return await catalogue_load.load_once(get_settings(), _Silent())

    scheduler = RefreshScheduler(load, now=lambda: datetime.datetime.now(datetime.UTC))
    return asyncio.create_task(scheduler.run_forever(), name="catalogue-refresh")


class _Silent:
    """A sink for ``catalogue_load.run``'s printed line: the refusal text names rows, so it is never logged."""

    def write(self, _text: str) -> int:
        return 0

    def flush(self) -> None:
        return None


async def stop(task: asyncio.Task[None] | None) -> None:
    """Cancel the task and wait for it, so shutdown leaves no run behind."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
