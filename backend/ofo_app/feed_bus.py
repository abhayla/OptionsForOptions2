"""REQ-113 AC-3, AC-5: the bus between the market-data process and the API process (Redis Streams, finding F-58).

Feed -> API: stream ``ofo:feed:<user_ref>:ticks``. Each entry is ``u`` (the user it belongs to), ``k`` (``frame`` /
``connected`` / ``dropped`` / ``ended``), ``t`` (the time the FEED received it, epoch microseconds) and, for a
frame, ``d`` (the raw Kite bytes: one frame parser, in ``KiteProvider``). The stream is capped (MAXLEN) and a
reader starts at the stream's tail, so the bus holds nothing that cannot be rebuilt.
API -> feed: key ``ofo:feed:<user_ref>:want`` = the FULL set of wanted instrument tokens, with an expiry (a
snapshot, never add/remove deltas); an absent or expired key means nothing is wanted.
Feed status: key ``ofo:feed:<user_ref>:status`` with an expiry (connections, connected, last frame time, phase).
API -> feed control: stream ``ofo:feed:<user_ref>:control``, entries ``u`` / ``k`` (``login`` / ``disconnect``) / ``t``.
It is only a wake-up: the encrypted token store decides, so it never carries a token or a fingerprint (REQ-113 AC-7).

A frame is stamped with the feed's receive time, never the API's arrival time, so a frame that sat on the bus is
read as the old price it is (ADR-015). Every answer state of Redis has one behaviour, none of them "live":
value present -> used; key absent or expired -> nothing wanted (feed) / feed down (API); connection refused or
dropped mid-read -> the API marks the feed disconnected (stale) and retries; empty stream -> keep waiting;
malformed or foreign-user message -> counted and skipped. No token is ever written to the bus: only frames,
events, token numbers and counts.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import functools
import json
import logging
import re
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from ofo.timeutil import IST_UNNAMED as IST
from redis.exceptions import RedisError

from ofo_app import feed_mode

log = logging.getLogger("ofo_app.feed_bus")

KEY_PREFIX = "ofo:feed"
STREAM_MAXLEN = 20_000  # entries kept per user (about a minute of a busy feed); older ones are dropped
WANT_TTL_MS = 10_000  # the API refreshes the snapshot every WANT_REFRESH_S; a dead API's wishes lapse after this
WANT_REFRESH_S = 1.0
CONTROL_MAXLEN = 100  # a wake-up stream: a lost or trimmed entry is rebuilt by the feed's fixed re-check
STATUS_TTL_MS = 5_000  # the feed refreshes every STATUS_EVERY_S; a dead feed's status lapses after this
STATUS_EVERY_S = 0.5
READ_BLOCK_MS = 200  # blocking reads stay short so a coarse timer (the test stand-in) adds no seconds
WANT_POLL_S = 0.2
MAX_FRAME_BYTES = 65_536
MAX_STAMP_DIGITS = 18  # epoch microseconds: 16 digits today
MAX_WANTED_TOKENS = 100_000  # a sanity cap on a snapshot; Kite's own per-connection cap is applied by KiteSocket
OUTBOX_MAX = 5_000
PUBLISH_BATCH = 200
CALL_TIMEOUT_S = 2.0
BACKOFF_START, BACKOFF_MAX = 0.2, 2.0

KIND_FRAME, KIND_CONNECTED, KIND_DROPPED, KIND_ENDED = "frame", "connected", "dropped", "ended"
KIND_RECONNECTED = "reconnected"  # the feed's Kite socket connected again (REQ-015 AC-5); its time is its event id
KINDS = frozenset({KIND_FRAME, KIND_CONNECTED, KIND_DROPPED, KIND_ENDED, KIND_RECONNECTED})
CONTROL_LOGIN, CONTROL_DISCONNECT = "login", "disconnect"
CONTROL_KINDS = frozenset({CONTROL_LOGIN, CONTROL_DISCONNECT})
PHASE_LIVE, PHASE_STOPPED = "live", "stopped"
SESSION_ENDED, STOPPED = "session ended", "stopped"  # the same words KiteSocket.run returns

_USER_REF = re.compile(r"[A-Za-z0-9_.-]{1,64}")


def valid_user_ref(user_ref: str) -> str:
    """The user ref as a plain key part, or ValueError (a ref with a colon or space could address another key)."""
    if type(user_ref) is not str or not _USER_REF.fullmatch(user_ref):
        raise ValueError("a bus user ref is 1-64 characters of a-z A-Z 0-9 _ . -")
    return user_ref


def ticks_key(user_ref: str) -> str:
    return f"{KEY_PREFIX}:{valid_user_ref(user_ref)}:ticks"


def want_key(user_ref: str) -> str:
    return f"{KEY_PREFIX}:{valid_user_ref(user_ref)}:want"


def status_key(user_ref: str) -> str:
    return f"{KEY_PREFIX}:{valid_user_ref(user_ref)}:status"


def control_key(user_ref: str) -> str:
    return f"{KEY_PREFIX}:{valid_user_ref(user_ref)}:control"


def to_micros(at: datetime.datetime) -> int:
    return int(at.timestamp() * 1_000_000)


def from_micros(micros: int) -> datetime.datetime:
    whole, rest = divmod(micros, 1_000_000)
    return datetime.datetime.fromtimestamp(whole, IST) + datetime.timedelta(microseconds=rest)


def new_client(url: str) -> aioredis.Redis:
    return aioredis.Redis.from_url(url, socket_timeout=CALL_TIMEOUT_S, socket_connect_timeout=CALL_TIMEOUT_S)


@dataclass(frozen=True)
class BusMessage:
    kind: str
    at: datetime.datetime  # the feed's receive time
    data: bytes = b""


def encode_message(user_ref: str, kind: str, at: datetime.datetime, data: bytes = b"") -> dict[str, Any]:
    fields: dict[str, Any] = {"u": valid_user_ref(user_ref), "k": kind, "t": str(to_micros(at))}
    if kind == KIND_FRAME:
        fields["d"] = data
    return fields


def _text(value: Any) -> str | None:
    if isinstance(value, bytes):
        try:
            return value.decode("ascii")
        except UnicodeDecodeError:
            return None
    return value if isinstance(value, str) else None


def decode_message(user_ref: str, fields: dict) -> tuple[BusMessage | None, str]:
    """(message, "") or (None, reason). Allow-list: exactly the keys of its kind, the right user, a plain integer time,
    a frame within the size cap. Anything else is refused with a reason word the caller counts."""
    plain = {_text(k): v for k, v in fields.items()}
    user, kind, stamp = _text(plain.get("u")), _text(plain.get("k")), _text(plain.get("t"))
    if user is None or kind is None or stamp is None:
        return None, "malformed"
    if user != user_ref:
        return None, "foreign_user"
    if kind not in KINDS or not stamp.isascii() or not stamp.isdigit() or len(stamp) > MAX_STAMP_DIGITS:
        return None, "malformed"
    expected = {"u", "k", "t", "d"} if kind == KIND_FRAME else {"u", "k", "t"}
    if set(plain) != expected:
        return None, "malformed"
    data = b""
    if kind == KIND_FRAME:
        data = plain["d"]
        if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_FRAME_BYTES:
            return None, "malformed"
    return BusMessage(kind, from_micros(int(stamp)), data), ""


async def publish_control(client: Any, user_ref: str, kind: str, at: datetime.datetime) -> None:
    """API -> feed wake-up. Only a kind word and a time: no token, no fingerprint, no session detail."""
    if kind not in CONTROL_KINDS:
        raise ValueError("a control message is one of login / disconnect")
    fields = {"u": valid_user_ref(user_ref), "k": kind, "t": str(to_micros(at))}
    await client.xadd(control_key(user_ref), fields, maxlen=CONTROL_MAXLEN, approximate=True)


def valid_control(user_ref: str, fields: dict) -> bool:
    """Allow-list: exactly ``u`` / ``k`` / ``t``, this user, a known kind, a plain integer time."""
    plain = {_text(k): _text(v) for k, v in fields.items()}
    if set(plain) != {"u", "k", "t"} or plain["u"] != user_ref or plain["k"] not in CONTROL_KINDS:
        return False
    stamp = plain["t"]
    return stamp is not None and stamp.isascii() and stamp.isdigit() and len(stamp) <= MAX_STAMP_DIGITS


def encode_want(user_ref: str, tokens: list[int]) -> str:
    return json.dumps({"u": valid_user_ref(user_ref), "tokens": sorted(set(tokens))}, separators=(",", ":"))


def decode_want(user_ref: str, raw: Any) -> set[int] | None:
    """The wanted tokens, or None when the snapshot is malformed or another user's (treated as nothing wanted)."""
    text = _text(raw)
    try:
        body = json.loads(text) if text is not None else None
    except ValueError:
        return None
    if not isinstance(body, dict) or set(body) != {"u", "tokens"} or body["u"] != user_ref:
        return None
    tokens = body["tokens"]
    if not isinstance(tokens, list) or len(tokens) > MAX_WANTED_TOKENS:
        return None
    if not all(type(t) is int and 0 < t < 2**32 for t in tokens):
        return None
    return set(tokens)


def decode_status(user_ref: str, raw: Any) -> dict | None:
    """The feed's status as a dict with exactly ``connected`` / ``ended`` (bool) and ``connections`` (int), or None."""
    text = _text(raw)
    try:
        body = json.loads(text) if text is not None else None
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("u") != user_ref:
        return None
    if type(body.get("connected")) is not bool or type(body.get("ended")) is not bool:
        return None
    if type(body.get("connections")) is not int or body["connections"] < 0:
        return None
    last, phase, capped = body.get("last_frame_us"), body.get("phase", PHASE_LIVE), body.get("capped", False)
    if (last is not None and type(last) is not int) or phase not in {PHASE_LIVE, PHASE_STOPPED} \
            or type(capped) is not bool:
        return None
    return {"connected": body["connected"], "ended": body["ended"], "connections": body["connections"],
            "last_frame_us": last, "phase": phase, "capped": capped}


class BusSocket:
    """The API's side of the bus, with the interface of ``KiteSocket`` (``run`` / ``stop`` / ``connections``): it
    feeds the raw frames and events into the SAME ``KiteProvider`` methods, so there is one frame parser. It opens
    no Kite socket."""

    def __init__(self, provider: Any, *, user_ref: str, clock: Callable[[], datetime.datetime],  # noqa: PLR0913
                 redis_url: str | None = None, client_factory: Callable[[], Any] | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 on_reconnect: Callable[[], Awaitable[None]] | None = None) -> None:
        self._provider = provider
        self._on_reconnect = on_reconnect  # REQ-015 AC-5: one REST positions read per reconnect event
        self._reconnect_tasks: set[asyncio.Task] = set()
        self._last_reconnect_at: datetime.datetime | None = None
        self._floor: datetime.datetime | None = None  # the newest bus loss: no frame received before it is live
        self._user = valid_user_ref(user_ref)
        self._clock = clock
        self._factory = client_factory or functools.partial(new_client, redis_url or feed_mode.redis_url())
        self._sleep = sleep
        self._stop = False
        self._feed_up = False
        self._backoff = BACKOFF_START
        self._last_want: list[int] | None = None
        self._last_want_at = 0.0
        self.connections = 0  # the feed's own count of Kite connections, from its status
        self.last_frame_at: datetime.datetime | None = None  # the feed's receive time of the newest frame
        self.counters: Counter = Counter()

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> str:
        """Run until stopped or the feed reports the Zerodha session ended. A lost Redis marks the feed disconnected."""
        self._backoff = BACKOFF_START
        try:
            return await self._run_loop()
        finally:
            for task in self._reconnect_tasks:
                task.cancel()

    async def _run_loop(self) -> str:
        while not self._stop:
            client = None
            try:
                client = self._factory()
                result = await self._session(client)
                if result is not None:
                    return result
            except (RedisError, OSError, TimeoutError) as exc:  # refused, dropped mid-read, timed out: all one state
                self._lost(type(exc).__name__)
            finally:
                if client is not None:
                    with contextlib.suppress(Exception):
                        await client.aclose()
            if self._stop:
                break
            await self._sleep(self._backoff)
            self._backoff = min(self._backoff * 2, BACKOFF_MAX)
        return STOPPED

    def _lost(self, reason: str) -> None:
        self.counters["redis_lost"] += 1
        self._floor = self._clock()
        self._set_feed(False, self._floor)  # stale (ADR-015) until the feed is seen up AND a fresh frame arrives
        log.warning("feed bus unreachable: %s", reason)

    def _set_feed(self, up: bool, at: datetime.datetime) -> None:
        if up and not self._feed_up:
            self._provider.on_connected(at)
        elif not up and self._feed_up:
            self._provider.on_disconnected(at)
        self._feed_up = up

    async def _session(self, client: Any) -> str | None:
        await client.ping()
        self._backoff = BACKOFF_START
        newest = await client.xrevrange(ticks_key(self._user), count=1)
        last_id: Any = newest[0][0] if newest else "0-0"  # only entries after this moment: no backlog is replayed
        self._last_want, self._last_want_at = None, 0.0
        if await self._read_status(client):
            return SESSION_ENDED
        next_status = time.monotonic() + STATUS_EVERY_S
        while not self._stop:
            entries = await client.xread({ticks_key(self._user): last_id}, count=PUBLISH_BATCH, block=READ_BLOCK_MS)
            for _stream, items in entries or []:
                for entry_id, fields in items:
                    last_id = entry_id
                    if self._handle(fields):
                        return SESSION_ENDED
            await self._publish_want(client)
            if time.monotonic() >= next_status:
                if await self._read_status(client):
                    return SESSION_ENDED
                next_status = time.monotonic() + STATUS_EVERY_S
        return None

    def _handle(self, fields: dict) -> bool:
        """One stream entry. True when it says the session ended."""
        message, reason = decode_message(self._user, fields)
        if message is None:
            self.counters[f"bus_{reason}"] += 1
            return False
        if message.kind == KIND_FRAME:
            if self._floor is not None and message.at <= self._floor:
                self.counters["bus_frame_before_outage"] += 1  # received by the feed before the bus was lost: not live
                return False
            self._provider.on_frame(message.data, message.at)  # stamped with the FEED's receive time
            if self.last_frame_at is None or message.at > self.last_frame_at:
                self.last_frame_at = message.at
        elif message.kind == KIND_CONNECTED:
            self._set_feed(True, message.at)
        elif message.kind == KIND_DROPPED:
            self._set_feed(False, message.at)
        elif message.kind == KIND_RECONNECTED:
            self._reconnected(message.at)
        else:
            self._provider.on_session_ended(message.at)
            return True
        return False

    def _reconnected(self, at: datetime.datetime) -> None:
        """One positions read per event; the event's time is its id, so a repeat of the same event reads nothing."""
        if self._on_reconnect is None or (self._last_reconnect_at is not None and at <= self._last_reconnect_at):
            self.counters["reconnect_ignored"] += 1
            return
        self._last_reconnect_at = at
        task = asyncio.get_running_loop().create_task(self._guarded_read(), name="bus-reconnect-read")
        self._reconnect_tasks = {t for t in self._reconnect_tasks if not t.done()} | {task}

    async def _guarded_read(self) -> None:
        try:
            await self._on_reconnect()  # type: ignore[misc]
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a failed read never ends the bus; class name only
            log.warning("reconnect read failed: %s", type(exc).__name__)

    async def _read_status(self, client: Any) -> bool:
        """The feed's status key. A missing, expired or malformed one means the feed is down. True when ended."""
        raw = await client.get(status_key(self._user))
        status = None if raw is None else decode_status(self._user, raw)
        now = self._clock()
        if status is None:
            self.counters["status_missing" if raw is None else "bus_malformed"] += 1
            self._set_feed(False, now)
            return False
        self.connections = status["connections"]
        self._provider.set_capped(status["capped"])  # REQ-113 AC-6: refused over the cap -> phase capped, never silent
        if status["ended"]:
            self._provider.on_session_ended(now)
            return True
        self._set_feed(status["connected"] and status["phase"] == PHASE_LIVE, now)
        return False

    async def _publish_want(self, client: Any) -> None:
        """Write the FULL wanted set (a snapshot with an expiry) when it changed, and refresh it once a second."""
        tokens = self._provider.subscribed_tokens()
        self._provider.drain_subscription_changes()  # the feed is told below: nothing is left pending on this side
        now = time.monotonic()
        if tokens == self._last_want and now - self._last_want_at < WANT_REFRESH_S:
            return
        await client.set(want_key(self._user), encode_want(self._user, tokens), px=WANT_TTL_MS)
        self._last_want, self._last_want_at = tokens, now


async def publish_stopped(client: Any, user_ref: str, clock: Callable[[], datetime.datetime]) -> None:
    """The feed holds no socket for this user (no stored session): phase ``stopped``, 0 connections, not connected."""
    body = {"u": valid_user_ref(user_ref), "connected": False, "ended": False, "phase": PHASE_STOPPED,
            "connections": 0, "last_frame_us": None, "at_us": to_micros(clock())}
    await client.set(status_key(user_ref), json.dumps(body, separators=(",", ":")), px=STATUS_TTL_MS)


async def publish_capped(client: Any, user_ref: str, clock: Callable[[], datetime.datetime]) -> None:
    """REQ-113 AC-6: the key already holds its connection cap, so this user's socket was REFUSED (nothing connected).
    Phase ``stopped`` and ``capped`` true: the API shows that live prices are not available."""
    body = {"u": valid_user_ref(user_ref), "connected": False, "ended": False, "phase": PHASE_STOPPED, "capped": True,
            "connections": 0, "last_frame_us": None, "at_us": to_micros(clock())}
    await client.set(status_key(user_ref), json.dumps(body, separators=(",", ":")), px=STATUS_TTL_MS)


async def publish_ended(client: Any, user_ref: str, clock: Callable[[], datetime.datetime], *, event: bool) -> None:
    """REQ-113 AC-8: the user's Zerodha session ended (06:00). The status says ``ended``; ``event`` also puts the one
    ``ended`` entry on the user's stream (the API reads it as the session ending, the same as Kite's own 403)."""
    now = clock()
    if event:
        await client.xadd(ticks_key(user_ref), encode_message(user_ref, KIND_ENDED, now),
                          maxlen=STREAM_MAXLEN, approximate=True)
    body = {"u": valid_user_ref(user_ref), "connected": False, "ended": True, "phase": PHASE_LIVE,
            "connections": 0, "last_frame_us": None, "at_us": to_micros(now)}
    await client.set(status_key(user_ref), json.dumps(body, separators=(",", ":")), px=STATUS_TTL_MS)


class FeedRelay:
    """What ``KiteSocket`` calls in the market-data process in place of a ``KiteProvider``: frames and events are
    published to the bus as they are; the wanted set comes from the API's snapshot. It parses nothing and
    holds no token."""

    def __init__(self, user_ref: str, clock: Callable[[], datetime.datetime]) -> None:
        self._user = valid_user_ref(user_ref)
        self._clock = clock
        self._outbox: deque[dict] = deque()
        self._wake = asyncio.Event()
        self._wanted: set[int] = set()
        self._sent: set[int] = set()
        self._socket: Any = None
        self.connected = False
        self.ended = False
        self.last_frame_at: datetime.datetime | None = None
        self.counters: Counter = Counter()

    def bind(self, socket: Any) -> None:
        self._socket = socket

    # ---- what KiteSocket calls (synchronous: they only queue) --------------------------------------------------
    def on_frame(self, data: bytes, received_at: datetime.datetime) -> list:
        self.last_frame_at = received_at
        self._queue(KIND_FRAME, received_at, data)
        return []

    def on_connected(self, now: datetime.datetime) -> None:
        self.connected = True
        self._queue(KIND_CONNECTED, now)

    def on_disconnected(self, now: datetime.datetime) -> None:
        self.connected = False
        self._queue(KIND_DROPPED, now)

    def on_session_ended(self, now: datetime.datetime) -> None:
        self.connected, self.ended = False, True
        self._queue(KIND_ENDED, now)

    async def announce_reconnect(self) -> None:
        """KiteSocket's ``on_reconnect`` in the market-data process: tell the API once per RE-connection."""
        self._queue(KIND_RECONNECTED, self._clock())

    def on_text(self, message: str) -> None:
        self.counters["text"] += 1  # order updates are a later part (REQ-113 order-update stream); nothing stored

    def subscribed_tokens(self) -> list[int]:
        return sorted(self._wanted)

    def drain_subscription_changes(self) -> tuple[list[int], list[int]]:
        added, removed = sorted(self._wanted - self._sent), sorted(self._sent - self._wanted)
        self._sent = set(self._wanted)
        return added, removed

    def _queue(self, kind: str, at: datetime.datetime, data: bytes = b"") -> None:
        if len(self._outbox) >= OUTBOX_MAX:  # never block the socket's receive loop: the oldest entry goes
            self._outbox.popleft()
            self.counters["outbox_dropped"] += 1
        self._outbox.append(encode_message(self._user, kind, at, data))
        self._wake.set()

    # ---- the three jobs the market-data process runs ----------------------------------------------------------
    def apply_want(self, raw: Any) -> None:
        """An absent or expired key means nothing is wanted; a malformed or foreign snapshot also (fail closed)."""
        tokens = set() if raw is None else decode_want(self._user, raw)
        if tokens is None:
            self.counters["bus_malformed"] += 1
            tokens = set()
        self._wanted = tokens

    async def refresh_want(self, client: Any) -> None:
        """One read of the wanted snapshot. A Redis that does not answer leaves the last wishes as they were."""
        try:
            raw = await client.get(want_key(self._user))
        except (RedisError, OSError, TimeoutError):
            self.counters["redis_failed"] += 1
            return
        self.apply_want(raw)

    def status(self) -> dict[str, Any]:
        last = self.last_frame_at
        return {"u": self._user, "connected": self.connected, "ended": self.ended, "phase": PHASE_LIVE,
                "capped": bool(getattr(self._socket, "capped", False)),
                "connections": 0 if self._socket is None else self._socket.connections,
                "last_frame_us": None if last is None else to_micros(last), "at_us": to_micros(self._clock())}

    async def publish_status(self, client: Any) -> None:
        await client.set(status_key(self._user), json.dumps(self.status(), separators=(",", ":")), px=STATUS_TTL_MS)

    async def flush(self, client: Any) -> None:
        """Publish everything queued, in order. A failed write drops that batch (ticks) and is counted; the status key
        carries the truth the API needs to recover."""
        while self._outbox:
            batch = [self._outbox.popleft() for _ in range(min(PUBLISH_BATCH, len(self._outbox)))]
            try:
                async with client.pipeline(transaction=False) as pipe:
                    for fields in batch:
                        pipe.xadd(ticks_key(self._user), fields, maxlen=STREAM_MAXLEN, approximate=True)
                    await pipe.execute()
            except (RedisError, OSError, TimeoutError) as exc:
                self.counters["publish_failed"] += 1
                log.warning("feed bus write failed: %s", type(exc).__name__)
                return

    async def publish_loop(self, client: Any) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            await self.flush(client)
            if self._outbox:
                await asyncio.sleep(BACKOFF_START)  # the write failed: wait before the next try

    async def want_loop(self, client: Any) -> None:
        while True:
            await self.refresh_want(client)
            await asyncio.sleep(WANT_POLL_S)

    async def status_loop(self, client: Any) -> None:
        while True:
            try:
                await self.publish_status(client)
            except (RedisError, OSError, TimeoutError):
                self.counters["redis_failed"] += 1
            await asyncio.sleep(STATUS_EVERY_S)
