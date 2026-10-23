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
- AC-4 / F-60: a 429 starts a cooldown for that group of the wait Kite states (``stated_wait``: a ``Retry-After``
  header in plain seconds up to ``MAX_STATED_WAIT_SECONDS``, a larger or unreadable one clamped to it and logged; no
  header: Kite's documented ``COOLDOWN_SECONDS``, "a cooldown period of 10s that must be respected"); nothing is booked or sent into it (a request already waiting re-books after it), so the sliding window
  is never extended. A read is retried after it, at most ``MAX_READ_RETRIES`` times, and only while the retry starts
  inside the call's ONE wait limit (``DoorCall``: the 5 s or 30 s is the whole call's, fixed at its first send, so AC-3
  and AC-4 hold together); a call that creates something is never retried (AC-5).
- AC-6: 429s are counted per group and user (a short hash of the access token, never the token) and logged; the
  ``ALERT_THRESHOLD``-th inside ``ALERT_WINDOW_SECONDS`` raises ONE alert through a ``Notifier`` adapter (ADR-029).
  An alert failure never blocks a read.
- AC-7 (RD-063): a read of one kind for one user has a minimum period (``READ_PERIOD_SECONDS``: 30 s for numbers such
  as the available margin, 45 s for positions). ``read_once_per_period`` sends at most one read of that call per user
  per period; any ask inside the period gets the last answer with ITS read time (or the last failure again), never a
  new Kite call. A "user" is the short hash of the access token, so a new login is a new user and never sees the old
  session's answer. This is a memo inside the one limiter, not a second limiter: the read it guards still passes the
  bucket above at the door.

Standard library only (the domain layer imports no HTTP package).
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import copy
import datetime
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
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
#: a ``Retry-After`` Kite may send, read only as plain ASCII delta-seconds (RFC 9110); anything else is not a wait
_RETRY_AFTER: Final = re.compile(r"[0-9]+", re.ASCII)
#: the longest stated wait honoured (orchestrator technical decision, chunk 1 review round 2): one header must not block
#: an endpoint group for hours; a larger or unreadable ``Retry-After`` cools the group this long, and is logged
MAX_STATED_WAIT_SECONDS: Final = 60.0
ALERT_THRESHOLD: Final = 3
ALERT_WINDOW_SECONDS: Final = 60.0
_USER_REF_CHARS: Final = 8
#: ``identity`` names this when a request carries no api key (the public instrument-list download)
NO_KEY: Final = "-"
READ_NUMBERS: Final = "numbers"
READ_POSITIONS: Final = "positions"
#: AC-7 (RD-063): the minimum seconds between two reads of one kind for one user; a kind not named here is refused
READ_PERIOD_SECONDS: Final[Mapping[str, float]] = MappingProxyType({READ_NUMBERS: 30.0, READ_POSITIONS: 45.0})

@dataclass(frozen=True)
class PeriodAnswer[T]:
    """One read's answer and the wall-clock time it was read. ``fresh`` is True only for the call that read Zerodha."""

    value: T
    read_at: datetime.datetime
    fresh: bool


@dataclass(frozen=True)
class _Failure:
    """A failed read kept as a pattern, never re-raised itself: each ask inside the period raises a NEW copy (same
    class, arguments and code; no traceback), so tracebacks never pile up on one shared object (review F2 item 3)."""

    pattern: BaseException

    @classmethod
    def of(cls, exc: BaseException) -> _Failure:
        return cls(copy.copy(exc))

    def new(self) -> BaseException:
        return copy.copy(self.pattern)


@dataclass(frozen=True)
class _LastRead:
    at: float  # the pacer's clock when the read was sent
    read_at: datetime.datetime
    value: object
    error: _Failure | None

_BACKGROUND: Final = contextvars.ContextVar("ofo_kite_background", default=False)
#: inside one periodic read (``read_once_per_period``): [slots granted, limiter refusals]; a refusal and no slot
#: granted means the limiter refused and nothing was sent to Kite
_SENDS: Final[contextvars.ContextVar[list[int] | None]] = contextvars.ContextVar("ofo_kite_sends", default=None)
_SENT, _REFUSED = 0, 1


def stated_wait(retry_after: str | None) -> float:
    """The seconds to cool a group after a 429 (ADR-179, F-60). No ``Retry-After`` (absent or blank): Kite's documented
    cooldown ``COOLDOWN_SECONDS`` (F-60: no header was found; Kite staff state 10 s). Plain ASCII seconds up to
    ``MAX_STATED_WAIT_SECONDS``: that wait. Anything else (more than 60 s, an HTTP date, a fraction, a sign, other
    text): ``MAX_STATED_WAIT_SECONDS``, logged by its value - never a shorter wait than Kite may have asked, and never
    the hours one header could otherwise block the group for."""
    text = (retry_after or "").strip()
    if not text:
        return COOLDOWN_SECONDS
    if _RETRY_AFTER.fullmatch(text):
        seconds = float(text)  # digits only: float() never raises here (a huge value is inf, clamped below)
        if seconds <= MAX_STATED_WAIT_SECONDS:
            return seconds
    log.warning("Kite Retry-After %r is not a wait of at most %.0f s: the group cools for %.0f s",
                text[:40], MAX_STATED_WAIT_SECONDS, MAX_STATED_WAIT_SECONDS)
    return MAX_STATED_WAIT_SECONDS


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
        self._last_reads: dict[tuple[str, str, str], _LastRead] = {}
        self._read_locks: dict[tuple[str, str, str], threading.Lock] = {}
        self._read_holders: dict[tuple[str, str, str], bool] = {}  # key -> True while a background read holds its lock

    # -- AC-7: one read per period per user ------------------------------------------------------------------------

    def read_once_per_period[T](self, kind: str, call: str, user_ref: str, fetch: Callable[[], T],
                             stamp: Callable[[], datetime.datetime]) -> PeriodAnswer[T]:
        """``fetch()`` at most once per ``READ_PERIOD_SECONDS[kind]`` for this (call, user); inside the period the last
        answer comes back with its own read time (a failed read raises a new copy of its error), and nothing is sent.
        The key is the guarded call's name and the user, so two calls or two users never share an answer or a period.
        Many tabs asking at once wait on one lock per key and the later ones get the first one's answer.

        Review F2 item 2: a refusal where NOTHING was sent (the limiter's own busy, however the caller wrapped it) is
        never kept as the period's answer, and a user's ask never waits on the lock while a background read holds it
        (that read may sit in the limiter's queue up to 30 s): the user reads for itself, through the same bucket."""
        if kind not in READ_PERIOD_SECONDS:
            raise ValueError(f"unknown read kind {kind!r}")  # fail closed: no unbounded read
        if not call or not isinstance(call, str) or not user_ref or not isinstance(user_ref, str) or user_ref == NO_KEY:
            raise ValueError("a periodic read needs the call's name and a known user")  # never one answer for all
        key = (kind, call, user_ref)
        background = _BACKGROUND.get()
        with self._lock:
            lock = self._read_locks.setdefault(key, threading.Lock())
        if not lock.acquire(blocking=False):
            with self._lock:
                held_by_background = self._read_holders.get(key, False)
            if held_by_background and not background:
                return self._read(key, kind, fetch, stamp)  # the bucket still paces it; the newer answer is kept
            lock.acquire()
        try:
            with self._lock:
                self._read_holders[key] = background
            return self._read(key, kind, fetch, stamp)
        finally:
            with self._lock:
                self._read_holders.pop(key, None)
            lock.release()

    def _read[T](self, key: tuple[str, str, str], kind: str, fetch: Callable[[], T],
                 stamp: Callable[[], datetime.datetime]) -> PeriodAnswer[T]:
        now = self._pacer.now()
        with self._lock:
            last = self._last_reads.get(key)
        if last is not None and now - last.at < READ_PERIOD_SECONDS[kind]:
            if last.error is not None:
                raise last.error.new()
            return PeriodAnswer(last.value, last.read_at, fresh=False)  # type: ignore[arg-type]
        read_at = stamp()
        sends = [0, 0]
        token = _SENDS.set(sends)
        try:
            value = fetch()
        except Exception as exc:  # the attempt counts: a failing broker is not asked again inside the period
            if sends[_SENT] or not sends[_REFUSED]:  # the limiter refused and nothing went out: not an answer
                self._remember(key, _LastRead(now, read_at, None, _Failure.of(exc)), now)
            raise
        finally:
            _SENDS.reset(token)
        self._remember(key, _LastRead(now, read_at, value, None), now)
        return PeriodAnswer(value, read_at, fresh=True)

    def _remember(self, key: tuple[str, str, str], last: _LastRead, now: float) -> None:
        with self._lock:
            longest = max(READ_PERIOD_SECONDS.values())
            self._last_reads = {k: v for k, v in self._last_reads.items() if now - v.at < longest}  # bounded memory
            kept = self._last_reads.get(key)
            if kept is None or kept.at <= last.at:  # an older read finishing late never replaces a newer answer
                self._last_reads[key] = last

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

    def acquire(self, group: str, key: str, *, background: bool = False, deadline: float | None = None) -> None:
        """Block until this request may be sent, or raise ``KiteBusy`` (nothing is sent). ``deadline``: the call's own
        (``DoorCall``, one limit across a read's retries); none = this context's limit from now."""
        limit = self._deadline(background) if deadline is None else deadline
        while True:
            self._pacer.sleep_until(self._counted_reserve(group, key, background, limit))
            if self._still_valid(group, key):  # a cooldown that began while this request waited: book again
                _count(_SENT)
                return

    async def aacquire(self, group: str, key: str, *, background: bool = False, deadline: float | None = None) -> None:
        limit = self._deadline(background) if deadline is None else deadline
        while True:
            await self._pacer.asleep_until(self._counted_reserve(group, key, background, limit))
            if self._still_valid(group, key):
                _count(_SENT)
                return

    def _counted_reserve(self, group: str, key: str, background: bool, deadline: float) -> float:
        try:
            return self._reserve(group, key, background, deadline)
        except KiteBusy:
            _count(_REFUSED)
            raise

    # -- a 429 ----------------------------------------------------------------------------------------------------

    def note_429(self, group: str, key: str, user_ref: str, wait: float = COOLDOWN_SECONDS) -> None:
        """Kite said 429: the group cools for the ``wait`` Kite stated (``stated_wait``); a cooldown already running is
        not extended (row 10, F-60: a 429 on a request already in flight; we send nothing into it). Count, log, maybe
        alert once."""
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not 0 <= wait < math.inf:
            raise ValueError("a 429's wait is a finite number of seconds")  # fail closed: never an endless or NaN wait
        with self._lock:
            now = self._pacer.now()
            bucket = self._bucket(group, key)
            if bucket.cooldown_until <= now:
                bucket.cool(now + wait)
            self._counts[(group, user_ref)] = count = self._counts.get((group, user_ref), 0) + 1
            self._recent = [t for t in self._recent if now - t < ALERT_WINDOW_SECONDS] + [now]
            alert = len(self._recent) >= ALERT_THRESHOLD and now - self._last_alert >= ALERT_WINDOW_SECONDS
            if alert:
                self._last_alert = now
            recent = len(self._recent)
        log.warning("kite 429 group=%s user=%s count=%d", group, user_ref, count)
        if alert:
            self._alert(recent)

    def set_app_key(self, app_key: str) -> None:
        """The app's api key, installed at startup from the broker settings (``.env`` included): keyless requests
        (the instrument file) share the app's bucket, never a stray '-' one (review F2 item 4)."""
        if type(app_key) is not str:
            raise TypeError("the app key is a plain str")
        with self._lock:
            self._app_key = app_key.strip()

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


def _count(which: int) -> None:
    sends = _SENDS.get()
    if sends is not None:
        sends[which] += 1


def install_app_key(app_key: str) -> None:
    """App startup: the process limiter's keyless bucket is the configured app key (``BrokerSettings.KITE_API_KEY``)."""
    current().set_app_key(app_key)


class DoorCall:
    """One request through a door, all its sends (REQ-118 AC-3 + AC-4); both doors use it (one helper). The wait
    limit of the context (5 s user, 30 s background) is fixed once, at the first ``acquire``, and covers every retry.
    After a 429, ``retry(retry_after)`` cools the group for Kite's stated wait and says whether the door sends again: a
    read at most ``MAX_READ_RETRIES`` times, a write never (AC-5). A retry whose slot falls past the limit is refused by
    the next ``acquire`` with ``KiteBusy('wait')``."""

    def __init__(self, group: str, key: str, user_ref: str, *, is_read: bool) -> None:
        self._limiter = current()
        self._group, self._key, self._user = group, key, user_ref
        self._is_read = is_read is True
        self._background = _BACKGROUND.get()
        self._deadline: float | None = None
        self._token: contextvars.Token[DoorCall | None] | None = None
        self.retries = 0

    def __enter__(self) -> DoorCall:
        self._token = _CALL.set(self)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            _CALL.reset(self._token)

    def limit(self) -> float:
        """The call's one deadline, fixed at its first ``acquire``."""
        if self._deadline is None:
            self._deadline = self._limiter._deadline(self._background)
        return self._deadline

    def retry(self, retry_after: str | None) -> bool:
        self._limiter.note_429(self._group, self._key, self._user, stated_wait(retry_after))
        if not self._is_read or self.retries >= MAX_READ_RETRIES:  # only a read is retried (AC-4, AC-5)
            return False
        self.retries += 1
        return True


_CALL: Final[contextvars.ContextVar[DoorCall | None]] = contextvars.ContextVar("ofo_kite_door_call", default=None)


def acquire(group: str, key: str) -> None:
    """The door's call: wait for a slot (user or background by context) or raise ``KiteBusy``; inside a ``DoorCall``
    every retry shares the call's one deadline."""
    call = _CALL.get()
    current().acquire(group, key, background=_BACKGROUND.get(), deadline=None if call is None else call.limit())


async def aacquire(group: str, key: str) -> None:
    call = _CALL.get()
    await current().aacquire(group, key, background=_BACKGROUND.get(), deadline=None if call is None else call.limit())


def note_429(group: str, key: str, user_ref: str) -> None:
    current().note_429(group, key, user_ref)


def read_once_per_period[T](kind: str, call: str, user_ref: str, fetch: Callable[[], T],
                         stamp: Callable[[], datetime.datetime]) -> PeriodAnswer[T]:
    """AC-7 through the process's one limiter (see ``RateLimiter.read_once_per_period``)."""
    return current().read_once_per_period(kind, call, user_ref, fetch, stamp)


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
