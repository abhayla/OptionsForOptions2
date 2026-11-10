"""The API process watches the background worker and tells the platform owner (ADR-286, REQ-115 AC-6, ADR-285 (1)).

Once a minute: in market hours the worker's heartbeat (``feed_bus.read_heartbeat_state``) is fresh, stale or unreadable.
Stale and unreadable are each ONE alert per day; fresh again after stale is ONE "recovered" alert. Outside market hours
and on days the calendar does not open nothing is sent and the state does not move. Separately, once a day from 30 days
before the market calendar's last covered date, one log line and one alert. The alert texts are fixed words: no
account figure, strategy id, symbol or token ever reaches the Notifier. A Notifier that fails never stops the next
minute's check.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from collections.abc import Awaitable, Callable

from ofo.market_calendar import calendar_end_warning
from ofo.timeutil import IST_UNNAMED as IST

from ofo_app import feed_bus, feed_mode, notifier

log = logging.getLogger("ofo_app.worker_watch")

POLL_SECONDS = 60

#: kind -> (severity, title, body); the kind is the alert's ``type`` and the start of its dedupe key
TEXTS = {
    "worker-stopped": ("critical", "Background watcher stopped",
                       "The background watcher has not reported for more than 2 minutes while the market is open. "
                       "Strategy monitoring is paused until it runs again."),
    "worker-recovered": ("info", "Background watcher is running again",
                         "The background watcher is reporting again. Strategy monitoring has resumed."),
    "worker-unreadable": ("critical", "Background watcher state cannot be read",
                          "The app cannot read the background watcher's report, so it cannot tell whether strategy "
                          "monitoring is running. Check the watcher and the shared store."),
    "calendar-ends": ("warning", "Market calendar ends on {end}",
                      "The market calendar lists dates only up to {end}. The next year's holiday list must be loaded "
                      "before then."),
}


class WorkerWatch:
    def __init__(self, *, read_state: Callable[[datetime.datetime], Awaitable[str]], notify: Callable[..., Awaitable[str]],
                 clock: Callable[[], datetime.datetime], market_open: Callable[[datetime.datetime], bool]) -> None:
        self._read_state, self._notify, self._clock, self._market_open = read_state, notify, clock, market_open
        self._day: datetime.date | None = None
        self._sent: set[str] = set()  # the kinds already sent today
        self._was_stale = False  # the last readable state was stale, and its alert is owed a "recovered"

    async def check(self) -> None:
        now = self._clock()
        today = now.astimezone(IST).date()
        if today != self._day:
            self._day, self._sent = today, set()
        if self._market_open(now):
            await self._check_worker(now, today)
        end = calendar_end_warning(today)
        if end is not None and self._first_today("calendar-ends"):
            log.warning("the market calendar ends on %s; the next year's list must be loaded", end)
            await self._send("calendar-ends", today, end=f"{end:%d %B %Y}")

    async def _check_worker(self, now: datetime.datetime, today: datetime.date) -> None:
        state = await self._read_state(now)
        if state == feed_bus.STALE:
            self._was_stale, kind = True, "worker-stopped"
        elif state == feed_bus.FRESH:
            if not self._was_stale:
                return
            self._was_stale, kind = False, "worker-recovered"
        else:  # unreadable, or any answer this code does not know: never "fine"
            kind = "worker-unreadable"
        if self._first_today(kind):
            await self._send(kind, today)

    def _first_today(self, kind: str) -> bool:
        """True once per kind per day. Marked before the send: a Notifier that is down is not retried every minute."""
        if kind in self._sent:
            return False
        self._sent.add(kind)
        return True

    async def _send(self, kind: str, today: datetime.date, **words: str) -> None:
        severity, title, body = TEXTS[kind]
        await self._notify(severity, title.format(**words), body.format(**words), type=kind,
                           dedupe_key=f"{kind}-{today.isoformat()}")

    async def run_forever(self, sleep: Callable[[float], Awaitable[object]] = asyncio.sleep) -> None:
        while True:
            try:
                await self.check()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the next minute checks again; the type only
                log.error("worker watch check failed: %s", type(exc).__name__)
            await sleep(POLL_SECONDS)


async def _serve(watch: WorkerWatch, client: object) -> None:
    try:
        await watch.run_forever()
    finally:
        await client.aclose()  # type: ignore[attr-defined]


def start_if(market: object | None) -> asyncio.Task[None] | None:
    """The lifespan's entry: only with the live market on and the feed on the bus (the worker exists only then). The
    real bus client, Notifier, clock and market calendar, as one task."""
    if market is None or feed_mode.feed_mode() != feed_mode.BUS:
        return None
    from ofo_app import live_market  # noqa: PLC0415 - late: live_market imports the routes

    client = feed_bus.new_client(feed_mode.redis_url())
    watch = WorkerWatch(read_state=lambda now: feed_bus.read_heartbeat_state(client, now), notify=notifier.notify,
                        clock=lambda: datetime.datetime.now(IST), market_open=live_market.market_open_at)
    return asyncio.get_running_loop().create_task(_serve(watch, client), name="worker-watch")


async def stop(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
