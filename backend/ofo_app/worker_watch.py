"""The API process watches the background worker and tells the platform owner (ADR-286, REQ-115 AC-6, ADR-285 (1)).

Once a minute: in market hours the worker's heartbeat (``feed_bus.read_heartbeat_state``) is fresh, stale or unreadable.
Every CHANGE of that judged state is logged, and sent as one alert: fresh -> stale "stopped", stale or unreadable ->
fresh "running again", any -> unreadable "cannot be read". An alert counts as delivered only when the Notifier client
answers ``sent``; a send that failed is tried again each later minute while that state still holds (a Notifier that is
not configured, or whose address is refused up front, cannot get better until a restart: logged once, not retried).
At most MAX_SENDS Notifier sends a day for worker changes: the last one says the rest are logged only. Outside market
hours and on days the calendar does not open nothing is sent and the state does not move. Separately, once a day from 30
days before the market calendar's last covered date, one log line and one alert (retried the same way). The alert texts
are fixed words: no account figure, strategy id, symbol or token ever reaches the Notifier. A Notifier that fails never
stops the next minute's check.
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
MAX_SENDS = 6  # a day; the sixth is the "logged only" notice, so a flapping worker cannot flood the owner

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
    "worker-capped": ("warning", "Background watcher: further changes today are logged only",
                      "The background watcher's state has changed several times today. Further changes today are "
                      "written to the log and not sent."),
    "calendar-ends": ("warning", "Market calendar ends on {end}",
                      "The market calendar lists dates only up to {end}. The next year's holiday list must be loaded "
                      "before then."),
}
_KIND_OF = {feed_bus.STALE: "worker-stopped", feed_bus.UNREADABLE: "worker-unreadable"}
#: answers that can change on a later minute; the others (not configured, bad address) need a restart
_RETRY = frozenset({notifier.REFUSED, notifier.SERVER_ERROR, notifier.UNREACHABLE})


class WorkerWatch:
    def __init__(self, *, read_state: Callable[[datetime.datetime], Awaitable[str]],
                 notify: Callable[..., Awaitable[str]], clock: Callable[[], datetime.datetime],
                 market_open: Callable[[datetime.datetime], bool]) -> None:
        self._read_state, self._notify, self._clock, self._market_open = read_state, notify, clock, market_open
        self._day: datetime.date | None = None
        self._new_day()

    def _new_day(self) -> None:
        self._judged: str | None = None  # the last judged state; None = none yet today, so the first one counts
        self._owed: tuple[str, int] | None = None  # (kind, change number) of the alert not yet delivered
        self._changes = self._sends = 0
        self._calendar_logged = self._calendar_done = False

    async def check(self) -> None:
        now = self._clock()
        today = now.astimezone(IST).date()
        if today != self._day:
            self._day = today
            self._new_day()
        if self._market_open(now):
            self._judge(await self._read_state(now))
            await self._deliver(today)
        end = calendar_end_warning(today)
        if end is not None and not self._calendar_done:
            if not self._calendar_logged:
                self._calendar_logged = True
                log.warning("the market calendar ends on %s; the next year's list must be loaded", end)
            self._calendar_done = await self._attempt("calendar-ends", f"calendar-ends-{today.isoformat()}",
                                                      end=f"{end:%d %B %Y}")

    def _judge(self, state: str) -> None:
        if state not in (feed_bus.FRESH, feed_bus.STALE):  # unreadable, or any answer this code does not know
            state = feed_bus.UNREADABLE
        if state == self._judged:
            return
        previous, self._judged = self._judged, state
        kind = _KIND_OF.get(state) or ("worker-recovered" if previous else None)  # first fresh of the day: no news
        if kind is None:
            self._owed = None
            return
        self._changes += 1
        self._owed = (kind, self._changes)
        log.warning("background worker: %s", TEXTS[kind][1])

    async def _deliver(self, today: datetime.date) -> None:
        if self._owed is None:
            return
        kind, number = self._owed
        if self._sends >= MAX_SENDS:  # the notice went out; the change is in the log
            self._owed = None
            return
        self._sends += 1
        if self._sends == MAX_SENDS:
            self._owed = None
            await self._attempt("worker-capped", f"worker-capped-{today.isoformat()}")
        elif await self._attempt(kind, f"{kind}-{today.isoformat()}-{number}"):
            self._owed = None

    async def _attempt(self, kind: str, dedupe_key: str, **words: str) -> bool:
        """One send. True when it needs no retry: delivered, or an answer that a later minute cannot change."""
        severity, title, body = TEXTS[kind]
        result = await self._notify(severity, title.format(**words), body.format(**words), type=kind,
                                    dedupe_key=dedupe_key)
        if result != notifier.SENT:
            log.warning("worker watch: the %s alert was not sent: %s", kind, result)
        return result not in _RETRY

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

    notifier.warn_if_guard_mismatch()
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
