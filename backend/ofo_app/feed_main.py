"""REQ-113: the market-data process. It holds the owner's Kite price socket, so restarting or redeploying the API
process never cuts it (AC-1, AC-2). Run it with ``python -m ofo_app.feed_main`` (FEED_MODE=bus on the API side).

It reuses the REAL ``KiteSocket`` unchanged (a listed broker-adapter file, REQ-063 AC-1); a ``FeedRelay`` stands
where the socket expects its provider, publishes the raw frames to the bus and applies the API's wanted-token
snapshot. It parses nothing (the API owns the one frame parser) and it holds the Kite token only in memory,
loaded from the encrypted token store (REQ-015). The egress gate is
installed BEFORE any Kite call, exactly as ``create_app`` does (REQ-073 AC-4); the database must not be the
test database (ADR-078); the pool is checked against the role's connection limit like the API's.

``supervise`` (A1) keeps that socket in step with the encrypted token store, which is the truth: a control message
from the API (login / disconnect) is only a wake-up, and a fixed re-check reads the store anyway, so a lost message is
rebuilt (AC-3). Stored session gone -> the socket stops and the status says ``stopped``; a different session -> the
old socket stops and one starts on the new session; the same session -> nothing. The token stays in memory (AC-7).

Part B: ``supervise_users`` holds ONE socket per user with an active stored session, each in its own task (one user's
failure never reaches another's, AC-9); Zerodha's caps are refused and logged, never cut to fit (AC-6); a session that
reaches its expiry is closed, announced as ended and not reconnected (AC-8). With no stored session the process idles
instead of exiting. Not in this part: the order-update stream (C).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ofo.broker import egress as _egress
from ofo.timeutil import IST_UNNAMED as IST
from redis.exceptions import RedisError

from ofo_app import event_loop, feed_bus, feed_mode

log = logging.getLogger("ofo_app.feed_main")

RECHECK_S = 5.0  # the store is re-read at least this often, whatever the control stream said
STOP_GRACE_S = 3.0  # a stopped socket is awaited this long (a backoff sleep cannot be interrupted), then cancelled
IDLE_WAIT_S = 0.2  # a failing control read waits this long before the next try
SESSION_ENDED_WORD = "session ended"  # what KiteSocket.run returns when Kite refuses the session


@dataclass(frozen=True)
class StoredSession:
    """What the token store answers: the Kite key, the token (memory only, never in repr or log) and its fingerprint."""
    api_key: str
    access_token: str = field(repr=False)
    fingerprint: bytes = field(repr=False)
    expires_at: datetime.datetime | None = None  # the session's expected expiry (06:00, ADR-053); None = not known


ReadSession = Callable[[], Awaitable["StoredSession | None"]]


def prepare_process() -> None:
    """The first thing the process does: install the egress gate (idempotent). From here this process connects only to
    loopback, the database and the Kite doors, and starts no process."""
    _egress.install()


def feed_settings():
    """The process settings, built as a LIVE run: refuses the test database or an unnamed one (ADR-078) and the real
    Kite address under APP_ENV=test, exactly like the API."""
    from ofo_app.config import Settings  # noqa: PLC0415

    return Settings(LIVE_MARKET=True)  # type: ignore[call-arg]


def build_socket(relay: feed_bus.FeedRelay, *, api_key: str, access_token: str, ws_url: str,  # noqa: PLR0913
                 clock: Callable[[], datetime.datetime], connect: Callable | None = None,
                 on_reconnect: Callable[[], Awaitable[None]] | None = None):
    """The real ``KiteSocket`` over the relay. Its address check refuses anything but ``wss://ws.kite.trade`` (loopback
    only in the test suites' mode); ``connect`` is a test seam it refuses outside them."""
    from ofo_app.kite_ws import KiteSocket  # noqa: PLC0415

    return KiteSocket(relay, api_key=api_key, access_token=access_token, clock=clock, base_url=ws_url,  # type: ignore[arg-type]
                      connect=connect, on_reconnect=on_reconnect)


def _now() -> datetime.datetime:
    return datetime.datetime.now(IST)


async def run_feed(*, user_ref: str, api_key: str, access_token: str, ws_url: str,  # noqa: PLR0913
                   redis_url: str | None = None, client: Any = None,
                   clock: Callable[[], datetime.datetime] = _now,
                   connect: Callable | None = None, stop: asyncio.Event | None = None) -> str:
    """Hold the user's Kite socket and relay it to the bus until it is stopped or the session ends. Returns the socket's
    result word. The token is passed in memory and is never put on the bus or in a log line. Setting ``stop`` closes
    the Kite socket (within its poll interval) and ends the run."""
    owned = client is None
    client = client or feed_bus.new_client(redis_url or feed_mode.redis_url())
    relay = feed_bus.FeedRelay(user_ref, clock)
    socket = build_socket(relay, api_key=api_key, access_token=access_token, ws_url=ws_url, clock=clock,
                          connect=connect, on_reconnect=relay.announce_reconnect)
    relay.bind(socket)
    jobs = [asyncio.create_task(job(client), name=name) for name, job in
            (("feed-publish", relay.publish_loop), ("feed-want", relay.want_loop), ("feed-status", relay.status_loop))]
    if stop is not None:
        jobs.append(asyncio.create_task(_stop_when_set(stop, socket), name="feed-stop"))
    try:
        result = await socket.run()
        await relay.flush(client)  # the last events (dropped / ended) go out before the status says so
        with contextlib.suppress(Exception):
            await relay.publish_status(client)
        return result
    finally:
        for job in jobs:
            job.cancel()
        for job in jobs:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await job
        if owned:
            with contextlib.suppress(Exception):
                await client.aclose()


async def _stop_when_set(stop: asyncio.Event, socket: Any) -> None:
    await stop.wait()
    socket.stop()


class _Running:
    """The one socket the supervisor holds for a user: its session's fingerprint, key and expiry, its task and stop."""

    def __init__(self, session: StoredSession, task: asyncio.Task, stop: asyncio.Event) -> None:
        self.fingerprint, self.api_key, self.expires_at = session.fingerprint, session.api_key, session.expires_at
        self.task, self.stop = task, stop

    def alive(self) -> bool:
        return not self.task.done()

    def ended(self) -> bool:
        """Kite refused this session (403): the same stored session is never tried again."""
        return self.task.done() and not self.task.cancelled() and self.task.exception() is None \
            and self.task.result() == SESSION_ENDED_WORD

    async def halt(self) -> None:
        self.stop.set()
        done, _ = await asyncio.wait({self.task}, timeout=STOP_GRACE_S)
        if not done:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task


ListUsers = Callable[[], Awaitable[list[str]]]
ReadUserSession = Callable[[str], Awaitable["StoredSession | None"]]


class _Hub:
    """REQ-113 AC-9: ONE socket per user, each in its own task with its own error handling. The map ``running`` is
    ``user_ref -> _Running``; nothing a user's socket does (an exception, a close, a reconnect, a refusal) touches
    another user's entry. ``expired`` remembers the session fingerprint whose expiry closed the socket (AC-8): the same
    session is never reconnected, a new login (a new fingerprint) starts afresh."""

    def __init__(self, *, list_users: ListUsers, read_session: ReadUserSession,  # noqa: PLR0913
                 ws_url: str | Callable[[str], str], client: Any, clock: Callable[[], datetime.datetime],
                 connect: Callable | None, max_connections: int, watch: Iterable[str]) -> None:
        self.list_users, self.read_session, self.client, self.clock = list_users, read_session, client, clock
        self.ws_url, self.connect, self.max_connections, self.watch = ws_url, connect, max_connections, tuple(watch)
        self.running: dict[str, _Running] = {}
        self.expired: dict[str, bytes] = {}
        self.known: set[str] = set()
        self.positions: dict[str, Any] = {}
        self.counters = {"bad_control": 0}

    # ---- the control streams (a wake-up only) ------------------------------------------------------------------
    async def _baseline(self, user: str) -> Any:
        try:
            newest = await self.client.xrevrange(feed_bus.control_key(user), count=1)
        except (RedisError, OSError, TimeoutError) as exc:  # Redis down at start: read from the beginning, keep going
            log.warning("control stream position unreadable: %s", type(exc).__name__)
            return "0-0"
        return newest[0][0] if newest else "0-0"

    async def read_controls(self) -> bool:
        """One short blocking read of every watched user's control stream: a valid message arrived."""
        users = sorted(set(self.running) | set(self.expired) | set(self.known) | set(self.watch))
        for user in users:
            if user not in self.positions:
                self.positions[user] = await self._baseline(user)
        keys = {feed_bus.control_key(user): user for user in users}
        if not keys:  # nobody to watch yet: wait one short block (the timed re-check still runs), never a bare read
            await asyncio.sleep(feed_bus.READ_BLOCK_MS / 1000)
            return False
        try:
            entries = await self.client.xread({key: self.positions[user] for key, user in keys.items()},
                                              count=feed_bus.PUBLISH_BATCH, block=feed_bus.READ_BLOCK_MS)
        except (RedisError, OSError, TimeoutError) as exc:
            log.warning("control stream unreadable: %s", type(exc).__name__)
            await asyncio.sleep(IDLE_WAIT_S)
            return False
        woken = False
        for stream, items in entries or []:
            name = stream.decode("ascii", "replace") if isinstance(stream, bytes) else stream
            user = keys.get(name)
            for entry_id, fields in items:
                if user is not None:
                    self.positions[user] = entry_id
                if user is not None and feed_bus.valid_control(user, fields):
                    woken = True
                else:
                    self.counters["bad_control"] += 1
        return woken

    # ---- reconciling the sockets with the store (the truth) ----------------------------------------------------
    async def reconcile(self) -> None:
        try:
            listed = await self.list_users()
        except Exception as exc:  # noqa: BLE001 - unreadable (database unreachable): keep what runs; class only
            log.warning("active users unreadable: %s", type(exc).__name__)
            listed = list(self.running)
        self.known = set(listed)
        for user in sorted(self.known | set(self.running) | set(self.expired) | set(self.watch)):
            try:
                await self._one(user)
            except Exception as exc:  # noqa: BLE001 - one user's failure never reaches another user (AC-9)
                log.warning("feed for one user failed: %s", type(exc).__name__)

    def _past(self, expires_at: datetime.datetime | None) -> bool:
        return expires_at is not None and self.clock() >= expires_at  # the injected clock, never a sleep

    async def _safely(self, what: str, call: Awaitable[None]) -> None:
        try:
            await call
        except (RedisError, OSError, TimeoutError) as exc:
            log.warning("%s not published: %s", what, type(exc).__name__)

    async def _one(self, user: str) -> None:
        run = self.running.get(user)
        try:
            session = await self.read_session(user)
        except Exception as exc:  # noqa: BLE001 - unreadable: keep what runs; never the message (could hold a token)
            log.warning("stored session unreadable: %s", type(exc).__name__)
            return
        if run is not None and self._past(run.expires_at):  # AC-8: the session's day is over
            await self._end_by_expiry(user, run)
            return
        if session is None:
            self.expired.pop(user, None)
            if run is not None:
                await run.halt()
                self.running.pop(user, None)
                log.info("no stored session: the Kite socket was stopped")
            await self._safely("stopped status", feed_bus.publish_stopped(self.client, user, self.clock))
            return
        if self.expired.get(user) == session.fingerprint:  # ended by expiry: no reconnect, the status stays "ended"
            await self._safely("ended status", feed_bus.publish_ended(self.client, user, self.clock, event=False))
            return
        if run is None and self._past(session.expires_at):
            self.expired[user] = session.fingerprint
            log.info("stored session already past its expiry: no socket")
            await self._safely("ended event", feed_bus.publish_ended(self.client, user, self.clock, event=True))
            return
        self.expired.pop(user, None)
        if run is not None and run.fingerprint == session.fingerprint:
            if not (run.task.done() and not run.ended()):
                return
            failure = None if run.task.cancelled() else run.task.exception()  # it crashed: try the same session again
            log.warning("the Kite socket task ended unexpectedly (%s); restarting",
                        type(failure).__name__ if failure else "stopped")
        elif run is not None:
            await run.halt()
            log.info("a different stored session: the Kite socket restarts on it")
        await self._start_user(user, session)

    async def _end_by_expiry(self, user: str, run: _Running) -> None:
        await run.halt()
        self.running.pop(user, None)
        self.expired[user] = run.fingerprint
        log.info("the session reached its expiry: the Kite socket was closed and is not reconnected")
        await self._safely("ended event", feed_bus.publish_ended(self.client, user, self.clock, event=True))

    async def _start_user(self, user: str, session: StoredSession) -> None:
        """AC-6: at most ``max_connections`` live sockets per API key; one more is REFUSED, logged, marked capped."""
        held = sum(1 for other, run in self.running.items()
                   if other != user and run.alive() and run.api_key == session.api_key)
        if held >= self.max_connections:
            self.running.pop(user, None)
            log.warning("connection cap: %d sockets already open on this key (cap %d); one more is refused",
                        held, self.max_connections)
            await self._safely("capped status", feed_bus.publish_capped(self.client, user, self.clock))
            return
        url = self.ws_url(user) if callable(self.ws_url) else self.ws_url
        self.running[user] = _start(session, user, self.client, url, self.clock, self.connect)

    async def close(self) -> None:
        await asyncio.gather(*(run.halt() for run in self.running.values()), return_exceptions=True)


async def supervise_users(*, list_users: ListUsers, read_session: ReadUserSession,  # noqa: PLR0913
                          ws_url: str | Callable[[str], str], redis_url: str | None = None, client: Any = None,
                          clock: Callable[[], datetime.datetime] = _now, connect: Callable | None = None,
                          recheck_s: float = RECHECK_S, quit_: asyncio.Event | None = None,
                          max_connections: int | None = None, watch: Iterable[str] = ()) -> None:
    """Keep ONE Kite socket per user with an active stored session until ``quit_`` is set (REQ-113 AC-1, AC-9).
    Answer states of the store, per user: a session -> run (or keep running) on it; absent -> stop that user's socket,
    status ``stopped``; past its expiry -> close, publish ``ended``, never reconnect that session (AC-8); unreadable
    (decrypt error, database unreachable) -> keep what is running, class only in the log. Per key: more sockets than
    the cap -> the extra user is refused and marked ``capped`` (AC-6). Redis: a failing control read changes nothing
    (the timed re-check still runs); at start it is read from the beginning and retried, the process never exits."""
    from ofo_app.kite_ws import MAX_CONNECTIONS_PER_KEY  # noqa: PLC0415 - after prepare_process installed the gate

    owned = client is None
    client = client or feed_bus.new_client(redis_url or feed_mode.redis_url())
    quit_ = quit_ or asyncio.Event()
    hub = _Hub(list_users=list_users, read_session=read_session, ws_url=ws_url, client=client, clock=clock,
               connect=connect, max_connections=MAX_CONNECTIONS_PER_KEY if max_connections is None else max_connections,
               watch=watch)
    next_check = 0.0
    try:
        while not quit_.is_set():
            woken = await hub.read_controls()
            if woken or time.monotonic() >= next_check:
                await hub.reconcile()
                next_check = time.monotonic() + recheck_s
    finally:
        await hub.close()
        if owned:
            with contextlib.suppress(Exception):
                await client.aclose()


async def supervise(*, user_ref: str, read_session: ReadSession, ws_url: str,  # noqa: PLR0913
                    redis_url: str | None = None, client: Any = None,
                    clock: Callable[[], datetime.datetime] = _now, connect: Callable | None = None,
                    recheck_s: float = RECHECK_S, quit_: asyncio.Event | None = None) -> None:
    """The one-user form of ``supervise_users`` (A1): the user's socket kept in step with the stored session."""
    async def users() -> list[str]:
        return [user_ref]

    async def read(_user: str) -> StoredSession | None:
        return await read_session()

    await supervise_users(list_users=users, read_session=read, ws_url=ws_url, redis_url=redis_url, client=client,
                          clock=clock, connect=connect, recheck_s=recheck_s, quit_=quit_, watch=(user_ref,))


def _start(session: StoredSession, user_ref: str, client: Any, ws_url: str,  # noqa: PLR0913
           clock: Callable[[], datetime.datetime], connect: Callable | None) -> _Running:
    stop = asyncio.Event()
    task = asyncio.get_running_loop().create_task(
        run_feed(user_ref=user_ref, api_key=session.api_key, access_token=session.access_token, ws_url=ws_url,
                 client=client, clock=clock, connect=connect, stop=stop), name=f"feed-run-{user_ref}")
    return _Running(session, task, stop)


async def _main() -> int:
    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.broker_config import load_broker_config  # noqa: PLC0415
    from ofo_app.broker_crypto import TokenCipher  # noqa: PLC0415
    from ofo_app.broker_token_store import access_token_for, active_user_refs, session_expiry  # noqa: PLC0415
    from ofo_app.config import app_env  # noqa: PLC0415
    from ofo_app.db import close_db, get_engine, verify_pool_budget  # noqa: PLC0415

    prepare_process()
    event_loop.require_selector_loop()  # a loop whose connects the egress gate cannot see is refused (W-080 r7)
    settings = feed_settings()
    live_market.require_safe(app_env() or "", settings.KITE_WS_URL)
    redis_url = feed_mode.redis_url()
    config = load_broker_config()
    await verify_pool_budget()
    cipher = TokenCipher(config.token_key)

    async def list_users() -> list[str]:
        async with get_engine().connect() as conn:
            return await active_user_refs(conn)

    async def read_session(user: str) -> StoredSession | None:
        async with get_engine().connect() as conn:
            stored = await access_token_for(conn, user, cipher)
        if stored is None:
            return None
        async with get_engine().connect() as conn:
            expiry = await session_expiry(conn, user)
        return StoredSession(config.api_key, stored, live_market.token_fingerprint(stored), expiry)

    try:
        # No stored session is a state, not an error: the process idles (egress gate already installed), waits for a
        # login message or the timed re-check, and a process manager never restarts it in a loop (row 9 part B, item 4).
        await supervise_users(list_users=list_users, read_session=read_session, ws_url=settings.KITE_WS_URL,
                              redis_url=redis_url, watch=(live_market.OWNER_REF,))
    finally:
        await close_db()
    log.warning("market-data process ended")
    return 0


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logging.basicConfig(level=logging.INFO)
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
