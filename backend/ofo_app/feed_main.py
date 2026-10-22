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

Not in this part (B/C): the per-user socket map, the cap refuse-and-log, the 06:00 session end, and the order-update
stream.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ofo.broker import egress as _egress
from ofo.timeutil import IST_UNNAMED as IST
from redis.exceptions import RedisError

from ofo_app import event_loop, feed_bus, feed_mode

log = logging.getLogger("ofo_app.feed_main")

EXIT_NO_SESSION = 3
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
    """The one socket the supervisor holds: its session's fingerprint, its task and its stop switch."""

    def __init__(self, fingerprint: bytes, task: asyncio.Task, stop: asyncio.Event) -> None:
        self.fingerprint, self.task, self.stop = fingerprint, task, stop

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


async def supervise(*, user_ref: str, read_session: ReadSession, ws_url: str,  # noqa: PLR0913
                    redis_url: str | None = None, client: Any = None,
                    clock: Callable[[], datetime.datetime] = _now, connect: Callable | None = None,
                    recheck_s: float = RECHECK_S, quit_: asyncio.Event | None = None) -> None:
    """Keep the user's Kite socket in step with the stored session until ``quit_`` is set. Answer states of the store:
    a session -> run (or keep running) on it; absent -> stop the socket, status ``stopped``, no reconnect; unreadable
    (decrypt error, database unreachable) -> keep what is running and log the class only. Redis states: an empty
    or failing control read changes nothing (the timed re-check still runs); a malformed message is counted, skipped."""
    owned = client is None
    client = client or feed_bus.new_client(redis_url or feed_mode.redis_url())
    quit_ = quit_ or asyncio.Event()
    running: _Running | None = None
    last_id: Any = "$"
    counters = {"bad_control": 0}
    next_check = 0.0
    try:
        newest = await client.xrevrange(feed_bus.control_key(user_ref), count=1)
        last_id = newest[0][0] if newest else "0-0"
        while not quit_.is_set():
            woken, last_id = await _read_control(client, user_ref, last_id, counters)
            if woken or time.monotonic() >= next_check:
                running = await _reconcile(running, user_ref=user_ref, read_session=read_session, client=client,
                                           ws_url=ws_url, clock=clock, connect=connect)
                next_check = time.monotonic() + recheck_s
    finally:
        if running is not None:
            await running.halt()
        if owned:
            with contextlib.suppress(Exception):
                await client.aclose()


async def _read_control(client: Any, user_ref: str, last_id: Any, counters: dict) -> tuple[bool, Any]:
    """One short blocking read of the control stream: (a valid message arrived, the new read position)."""
    try:
        entries = await client.xread({feed_bus.control_key(user_ref): last_id}, count=feed_bus.PUBLISH_BATCH,
                                     block=feed_bus.READ_BLOCK_MS)
    except (RedisError, OSError, TimeoutError) as exc:
        log.warning("control stream unreadable: %s", type(exc).__name__)
        await asyncio.sleep(IDLE_WAIT_S)
        return False, last_id
    woken = False
    for _stream, items in entries or []:
        for entry_id, fields in items:
            last_id = entry_id
            if feed_bus.valid_control(user_ref, fields):
                woken = True
            else:
                counters["bad_control"] += 1
    return woken, last_id


async def _reconcile(running: _Running | None, *, user_ref: str, read_session: ReadSession, client: Any,  # noqa: PLR0913
                     ws_url: str, clock: Callable[[], datetime.datetime],
                     connect: Callable | None) -> _Running | None:
    """Read the stored session and make the socket match it. Returns what is running afterwards."""
    try:
        session = await read_session()
    except Exception as exc:  # noqa: BLE001 - unreadable: keep what runs; never the message (it could hold a token)
        log.warning("stored session unreadable: %s", type(exc).__name__)
        return running
    if session is None:
        if running is not None:
            await running.halt()
            log.info("no stored session: the Kite socket was stopped")
        await _publish_stopped(client, user_ref, clock)
        return None
    if running is not None and running.fingerprint == session.fingerprint:
        if running.task.done() and not running.ended():  # it crashed: the same session may be tried again
            return _start(session, user_ref, client, ws_url, clock, connect)
        return running
    if running is not None:
        await running.halt()
        log.info("a different stored session: the Kite socket restarts on it")
    return _start(session, user_ref, client, ws_url, clock, connect)


def _start(session: StoredSession, user_ref: str, client: Any, ws_url: str,  # noqa: PLR0913
           clock: Callable[[], datetime.datetime], connect: Callable | None) -> _Running:
    stop = asyncio.Event()
    task = asyncio.get_running_loop().create_task(
        run_feed(user_ref=user_ref, api_key=session.api_key, access_token=session.access_token, ws_url=ws_url,
                 client=client, clock=clock, connect=connect, stop=stop), name="feed-run")
    return _Running(session.fingerprint, task, stop)


async def _publish_stopped(client: Any, user_ref: str, clock: Callable[[], datetime.datetime]) -> None:
    try:
        await feed_bus.publish_stopped(client, user_ref, clock)
    except (RedisError, OSError, TimeoutError) as exc:
        log.warning("stopped status not published: %s", type(exc).__name__)


async def _main() -> int:
    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.broker_config import load_broker_config  # noqa: PLC0415
    from ofo_app.broker_crypto import TokenCipher  # noqa: PLC0415
    from ofo_app.broker_token_store import access_token_for  # noqa: PLC0415
    from ofo_app.config import app_env  # noqa: PLC0415
    from ofo_app.db import close_db, get_engine, verify_pool_budget  # noqa: PLC0415

    prepare_process()
    event_loop.require_selector_loop()  # a loop whose connects the egress gate cannot see is refused (W-080 r7)
    settings = feed_settings()
    live_market.require_safe(app_env() or "", settings.KITE_WS_URL)
    redis_url = feed_mode.redis_url()
    config = load_broker_config()
    await verify_pool_budget()
    try:
        async with get_engine().connect() as conn:
            token = await access_token_for(conn, live_market.OWNER_REF, TokenCipher(config.token_key))
    except BaseException:
        await close_db()
        raise
    if token is None:
        await close_db()
        log.error("market-data process: no active Kite session; connect through the login first")
        return EXIT_NO_SESSION
    del token
    cipher = TokenCipher(config.token_key)

    async def read_session() -> StoredSession | None:
        async with get_engine().connect() as conn:
            stored = await access_token_for(conn, live_market.OWNER_REF, cipher)
        return None if stored is None else StoredSession(config.api_key, stored, live_market.token_fingerprint(stored))

    try:
        await supervise(user_ref=live_market.OWNER_REF, read_session=read_session, ws_url=settings.KITE_WS_URL,
                        redis_url=redis_url)
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
