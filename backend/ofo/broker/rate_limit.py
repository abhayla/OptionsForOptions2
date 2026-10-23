"""The one rate limiter every Kite REST call passes at the door (REQ-118 AC-1..AC-6, ADR-017; F-60).

Adapted from abhayla/algochanakya@bf9faf7 backend/app/services/market_data/rate_limiter.py (map row
``market_data/rate_limiter.py``, COPY): the bucket idea only. The legacy value (3 req/s) is NOT used; the limits are
Kite's own (``GROUP_RATES``, source and date in ``ofo_app.order_limits_registry``).

How it works. Each (endpoint group, api key) has a bucket that hands out time slots ``1 / rate`` seconds apart
(``reserve``); the caller sleeps until its slot (``acquire`` / ``aacquire``, through an injected ``Pacer`` so tests
never really sleep), then re-checks that no cooldown started meanwhile. Both door modules call the SAME module-level
limiter, so one quote through urllib and one through httpx share one bucket.

- AC-3: a request whose slot is later than its deadline (5 s for a user action, 30 s for a background job) or that
  would be one waiter too many is refused at once with ``KiteBusy`` ("Zerodha is busy - try again in a moment"). A
  background job may keep only ``BACKGROUND_QUEUE_SECONDS`` of slots booked ahead, so a user action never queues behind
  a long background burst.
- AC-4 / F-60: a 429 starts a ``COOLDOWN_SECONDS`` cooldown for that group; nothing is booked or sent into it (a
  request already waiting re-books after it), so the sliding window is never extended. A read is retried after it, at
  most ``MAX_READ_RETRIES`` times (the door decides; a call that creates something is never retried).
- AC-6: 429s are counted per group and user (a short hash of the access token, never the token) and logged; the
  ``ALERT_THRESHOLD``-th inside ``ALERT_WINDOW_SECONDS`` raises ONE alert through a ``Notifier`` adapter (ADR-029).
  An alert failure never blocks a read.

Standard library only (the domain layer imports no HTTP package).
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import hashlib
import json
import logging
import math
import os
import threading
import time
from collections.abc import Iterator, Mapping
from typing import Final, Protocol
from urllib.parse import parse_qs

from ofo.errors import KITE_RATE_LIMIT_ALERT_BODY, KITE_RATE_LIMIT_ALERT_TITLE, ZERODHA_BUSY_TEXT

log = logging.getLogger("ofo.broker.rate_limit")

GROUP_QUOTE: Final = "quote"
GROUP_HISTORICAL: Final = "historical"
GROUP_OTHER: Final = "other"
#: requests per second for each endpoint group (Kite docs, F-60); a group not named here is refused
GROUP_RATES: Final[Mapping[str, int]] = {GROUP_QUOTE: 1, GROUP_HISTORICAL: 3, GROUP_OTHER: 10}
COOLDOWN_SECONDS: Final = 10.0
USER_MAX_WAIT_SECONDS: Final = 5.0
BACKGROUND_MAX_WAIT_SECONDS: Final = 30.0
BACKGROUND_QUEUE_SECONDS: Final = 2.0
MAX_READ_RETRIES: Final = 2
ALERT_THRESHOLD: Final = 3
ALERT_WINDOW_SECONDS: Final = 60.0
_USER_REF_CHARS: Final = 8
#: ``identity`` names this when a request carries no api key (the public instrument-list download)
NO_KEY: Final = "-"

_BACKGROUND: Final = contextvars.ContextVar("ofo_kite_background", default=False)


class KiteBusy(Exception):
    """Nothing was sent: the group's wait or queue limit would be exceeded (AC-3). ``str()`` is the user text."""

    def __init__(self, reason: str) -> None:
        super().__init__(ZERODHA_BUSY_TEXT)
        self.reason = reason


class Notifier(Protocol):
    """The alert adapter (ADR-029). ``send`` returns False (or raises) when the alert did not go out."""

    def send(self, payload: Mapping[str, str]) -> bool: ...


class LogNotifier:
    """No ``NOTIFIER_URL`` / no transport wired: the alert is logged as not sent."""

    def send(self, payload: Mapping[str, str]) -> bool:
        log.warning("alert NOT sent (no Notifier transport): %s", payload.get("title", ""))
        return False


class HttpNotifier:
    """``POST {url}/notify`` through an injected ``post(url, headers, body_json) -> bool``; URL and key come from the
    environment, never the repo. The body never carries a token."""

    def __init__(self, url: str, key: str, post: Post) -> None:
        self._url, self._key, self._post = url.rstrip("/"), key, post

    def send(self, payload: Mapping[str, str]) -> bool:
        return self._post(self._url + "/notify", {"X-Notifier-Key": self._key, "Content-Type": "application/json"},
                          json.dumps(dict(payload)))


class Post(Protocol):
    def __call__(self, url: str, headers: dict[str, str], body: str) -> bool: ...


def notifier_from_env(environ: Mapping[str, str], post: Post | None = None) -> Notifier:
    url = environ.get("NOTIFIER_URL", "").strip()
    if not url or post is None:
        return LogNotifier()
    return HttpNotifier(url, environ.get("NOTIFIER_KEY", ""), post)


class Pacer(Protocol):
    """The clock and the sleeps, injected: tests never really sleep."""

    def now(self) -> float: ...
    def sleep_until(self, at: float) -> None: ...
    async def asleep_until(self, at: float) -> None: ...


class RealPacer:
    def now(self) -> float:
        return time.monotonic()

    def sleep_until(self, at: float) -> None:
        if (wait := at - self.now()) > 0:
            time.sleep(wait)

    async def asleep_until(self, at: float) -> None:
        if (wait := at - self.now()) > 0:
            await asyncio.sleep(wait)


class _Bucket:
    __slots__ = ("booked", "cooldown_until", "next_free")

    def __init__(self) -> None:
        self.next_free = 0.0
        self.cooldown_until = 0.0
        self.booked: list[float] = []  # start times still in the future: the waiters

    def drop_started(self, now: float) -> None:
        self.booked = [s for s in self.booked if s > now]

    def book(self, start: float) -> None:
        self.booked.append(start)

    def take(self, start: float, rate: int) -> None:
        self.next_free = start + 1 / rate

    def cool(self, until: float) -> None:
        self.cooldown_until = until


class RateLimiter:
    def __init__(self, *, pacer: Pacer | None = None, notifier: Notifier | None = None, app_key: str = "") -> None:
        self._app_key = app_key  # the app's one api key: a request that names none (the instrument file) is the app's
        self._pacer = pacer or RealPacer()
        self._notifier = notifier or LogNotifier()
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._counts: dict[tuple[str, str], int] = {}
        self._recent: list[float] = []
        self._last_alert = -math.inf

    # -- slots ----------------------------------------------------------------------------------------------------

    def _bucket(self, group: str, key: str) -> _Bucket:
        if group not in GROUP_RATES:
            raise ValueError(f"unknown Kite endpoint group {group!r}")  # fail closed: nothing is sent
        if key == NO_KEY and self._app_key:  # F-60: one bucket per group for the whole app, never a stray "-" bucket
            key = self._app_key
        return self._buckets.setdefault((group, key), _Bucket())

    def _reserve(self, group: str, key: str, background: bool, deadline: float) -> float:
        with self._lock:
            now = self._pacer.now()
            bucket = self._bucket(group, key)
            bucket.drop_started(now)
            start = max(now, bucket.next_free, bucket.cooldown_until)
            if start > deadline:
                raise KiteBusy("wait")
            if start > now:
                seconds = BACKGROUND_QUEUE_SECONDS if background else USER_MAX_WAIT_SECONDS
                if len(bucket.booked) >= math.ceil(GROUP_RATES[group] * seconds):
                    raise KiteBusy("queue")
                bucket.book(start)
            bucket.take(start, GROUP_RATES[group])
            return start

    def _still_valid(self, group: str, key: str) -> bool:
        with self._lock:
            return self._bucket(group, key).cooldown_until <= self._pacer.now()

    def _deadline(self, background: bool) -> float:
        return self._pacer.now() + (BACKGROUND_MAX_WAIT_SECONDS if background else USER_MAX_WAIT_SECONDS)

    def acquire(self, group: str, key: str, *, background: bool = False) -> None:
        """Block until this request may be sent, or raise ``KiteBusy`` (nothing is sent)."""
        deadline = self._deadline(background)
        while True:
            self._pacer.sleep_until(self._reserve(group, key, background, deadline))
            if self._still_valid(group, key):  # a cooldown that began while this request waited: book again
                return

    async def aacquire(self, group: str, key: str, *, background: bool = False) -> None:
        deadline = self._deadline(background)
        while True:
            await self._pacer.asleep_until(self._reserve(group, key, background, deadline))
            if self._still_valid(group, key):
                return

    # -- a 429 ----------------------------------------------------------------------------------------------------

    def note_429(self, group: str, key: str, user_ref: str) -> None:
        """Kite said 429: start the group's cooldown (not extended while one runs), count, log, maybe alert once."""
        with self._lock:
            now = self._pacer.now()
            bucket = self._bucket(group, key)
            if bucket.cooldown_until <= now:
                bucket.cool(now + COOLDOWN_SECONDS)
            self._counts[(group, user_ref)] = count = self._counts.get((group, user_ref), 0) + 1
            self._recent = [t for t in self._recent if now - t < ALERT_WINDOW_SECONDS] + [now]
            alert = len(self._recent) >= ALERT_THRESHOLD and now - self._last_alert >= ALERT_WINDOW_SECONDS
            if alert:
                self._last_alert = now
            recent = len(self._recent)
        log.warning("kite 429 group=%s user=%s count=%d", group, user_ref, count)
        if alert:
            self._alert(recent)

    def in_cooldown(self, group: str, key: str) -> bool:
        with self._lock:
            return self._bucket(group, key).cooldown_until > self._pacer.now()

    def count(self, group: str, user_ref: str) -> int:
        with self._lock:
            return self._counts.get((group, user_ref), 0)

    def _alert(self, recent: int) -> None:
        payload = {"project": "optionsforoptions2", "severity": "warning", "type": "kite_rate_limit",
                   "title": KITE_RATE_LIMIT_ALERT_TITLE,
                   "body": KITE_RATE_LIMIT_ALERT_BODY.format(recent=recent),
                   "dedupeKey": "kite-429-burst"}
        try:
            sent = self._notifier.send(payload)
        except Exception:  # noqa: BLE001 - an alert failure must never block or fail a Kite read
            log.warning("alert raised an error and was NOT sent")
            return
        if not sent:
            log.warning("alert NOT sent")


# -- the process-wide limiter both doors share ---------------------------------------------------------------------

_installed: dict[str, RateLimiter | None] = {"limiter": None}  # a holder, not a rebound global
_current_lock = threading.Lock()


def process_limiter(environ: Mapping[str, str]) -> RateLimiter:
    """The one limiter a process runs: the app's api key (``KITE_API_KEY``) is the bucket of keyless requests."""
    return RateLimiter(app_key=environ.get("KITE_API_KEY", "").strip())


def current() -> RateLimiter:
    with _current_lock:
        if _installed["limiter"] is None:
            _installed["limiter"] = process_limiter(os.environ)
        return _installed["limiter"]


@contextlib.contextmanager
def use(limiter: RateLimiter) -> Iterator[RateLimiter]:
    """Install ``limiter`` for a block (tests; the app's startup)."""
    with _current_lock:
        previous, _installed["limiter"] = _installed["limiter"], limiter
    try:
        yield limiter
    finally:
        with _current_lock:
            _installed["limiter"] = previous


def acquire(group: str, key: str) -> None:
    """The door's call: wait for a slot (user or background by context) or raise ``KiteBusy``."""
    current().acquire(group, key, background=_BACKGROUND.get())


async def aacquire(group: str, key: str) -> None:
    await current().aacquire(group, key, background=_BACKGROUND.get())


def note_429(group: str, key: str, user_ref: str) -> None:
    current().note_429(group, key, user_ref)


@contextlib.contextmanager
def background() -> Iterator[None]:
    """A background job (catalogue load, history finalize): waits up to 30 s and books few slots ahead."""
    token = _BACKGROUND.set(True)
    try:
        yield
    finally:
        _BACKGROUND.reset(token)


def identity(authorization: str | None, form: bytes | None) -> tuple[str, str]:
    """(api key, user ref) of a request: from ``Authorization: token <key>:<access token>``, else the ``api_key`` form
    field (the login exchange), else ``("-", "-")``. The user ref is a short hash of the access token."""
    if authorization and authorization.startswith("token ") and ":" in authorization:
        api_key, _, access = authorization[len("token "):].partition(":")
        return api_key or "-", hashlib.sha256(access.encode()).hexdigest()[:_USER_REF_CHARS]
    if form:
        fields = parse_qs(form.decode("utf-8", "replace")).get("api_key")
        if fields and fields[0]:
            return fields[0], "-"
    return NO_KEY, "-"
