# ruff: noqa: PLR2004
"""REQ-113 AC-9, AC-1, AC-7 (row 9 part B): one Kite socket per user in the market-data process, each isolated.

Core (step 1): killing user A's Kite socket leaves user B's ticks flowing and no frame of A's reaches B. User A and
user B each have a stored session (files, the stand-in of the token store, as in part A) and their own looping fake
Kite on loopback replaying the REAL recorded frames (``frames-2026-10-08-092000-10s.bin.gz``); the REAL
``feed_main.supervise_users`` runs as an OS process through the test-only launcher. The in-process tests below run the
same function with an injected clock.

Answer states listed (standing item d). Token store, per user: session present -> run | none -> stop, status
``stopped`` | past its expiry -> see test_feed_session_expiry | undecryptable -> the store answers none (see
test_broker_token_store) -> stop | database unreachable (the read raises) -> keep the running socket, class only in the
log (test_an_unreadable_store_keeps_the_running_socket). Active-users read: user refs only
(test_active_user_refs_is_an_allow_list_of_one_column). Kite's socket: accepted -> frames flow | refused (403) -> that
user's session ended, no retry, the other user unaffected (test_kite_403_for_one_user_ends_only_that_user) | dropped or
closed -> reconnect with backoff, the other user unaffected (the core).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import os
import pathlib
import uuid
from collections import Counter
from http import HTTPStatus

import pytest
import redis.asyncio as aioredis
from ofo.marketdata.kite_provider import IST
from ofo_app import broker_token_store as store
from ofo_app import feed_bus, feed_main, live_market
from ofo_app.broker_crypto import TokenCipher
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_feed_control import CountingKite
from test_feed_restart_core import _start, until
from websockets.asyncio.server import serve

LAUNCHER_ROLE = "feedmulti"
KEY = "KEY-isolation"
T0 = datetime.datetime(2026, 10, 23, 9, 20, tzinfo=IST)


def new_ref(tag: str) -> str:
    return f"{tag}{uuid.uuid4().hex[:10]}"


class TwoKites:
    """The recorded frames in two byte-disjoint halves: a frame in a stream proves WHOSE Kite sent it."""

    def __init__(self) -> None:
        every = CountingKite().frames
        even, odd = {every[i] for i in range(0, len(every), 2)}, {every[i] for i in range(1, len(every), 2)}
        self.a_only, self.b_only = even - odd - {b"\x00"}, odd - even - {b"\x00"}
        assert self.a_only and self.b_only
        self.a_frames = [f for f in every if f in self.a_only]
        self.b_frames = [f for f in every if f in self.b_only]


def kite_with(frames: list[bytes]) -> CountingKite:
    kite = CountingKite()
    kite.frames = frames
    return kite


async def stream_entries(bus, user: str, after: str = "-") -> list[tuple[str, feed_bus.BusMessage]]:
    out = []
    for entry_id, fields in await bus.xrange(feed_bus.ticks_key(user), min=after):
        message, reason = feed_bus.decode_message(user, fields)  # a foreign-user entry would be refused here
        assert message is not None, reason
        out.append((entry_id.decode() if isinstance(entry_id, bytes) else entry_id, message))
    return out


async def user_status(bus, user: str) -> dict | None:
    raw = await bus.get(feed_bus.status_key(user))
    return None if raw is None else feed_bus.decode_status(user, raw)


async def clean(bus, *users: str) -> None:
    for user in users:
        await bus.delete(*(k(user) for k in (feed_bus.ticks_key, feed_bus.want_key, feed_bus.status_key,
                                              feed_bus.control_key)))


# ------------------------------------------------------------------------------------------------------------------
# The core, as OS processes
# ------------------------------------------------------------------------------------------------------------------
async def test_killing_one_users_socket_leaves_the_other_users_ticks_flowing(  # noqa: C901
    redis_url, tmp_path):
    """AC-9 core: two users, two fake Kites; A's server is killed. B keeps receiving frames newer than the kill, B's
    Kite never saw a second connection, the feed process is still running, and B's stream holds only B's Kite's frames
    (A's frames are byte-disjoint from B's), under B's user ref."""
    user_a, user_b = new_ref("ua"), new_ref("ub")
    halves = TwoKites()
    kite_a, kite_b = kite_with(halves.a_frames), kite_with(halves.b_frames)
    server_a, server_b = await serve(kite_a.handler, "127.0.0.1", 0), await serve(kite_b.handler, "127.0.0.1", 0)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / f"{user_a}.txt").write_text("TOK-user-a-not-a-real-token")
    (sessions / f"{user_b}.txt").write_text("TOK-user-b-not-a-real-token")
    cfg = {"redis_url": redis_url, "session_dir": str(sessions), "recheck_s": 0.5, "users": {
        user_a: {"ws_url": f"ws://127.0.0.1:{server_a.sockets[0].getsockname()[1]}"},
        user_b: {"ws_url": f"ws://127.0.0.1:{server_b.sockets[0].getsockname()[1]}"}}}
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg))
    bus = aioredis.Redis.from_url(redis_url)
    children = {LAUNCHER_ROLE: _start(LAUNCHER_ROLE, cfg_path, {**os.environ, "OFO_TEST_KITE_TOKEN": "unused"})}

    async def both_live():
        sa, sb = await user_status(bus, user_a), await user_status(bus, user_b)
        return sa and sb and sa["connected"] and sb["connected"] and sa["phase"] == sb["phase"] == "live"

    try:
        await until(both_live, "both users' sockets to connect", children)
        await until(lambda: _count_at_least(bus, user_b, 5), "user B's first frames", children)
        await until(lambda: _count_at_least(bus, user_a, 5), "user A's first frames", children)
        kill_id = (await bus.xrevrange(feed_bus.ticks_key(user_b), count=1))[0][0].decode()
        kill_us = (await user_status(bus, user_b))["last_frame_us"]  # the feed's receive time of B's newest frame
        server_a.close()  # user A's Kite socket dies (the server and its open connection)
        await server_a.wait_closed()

        async def a_dropped():
            status = await user_status(bus, user_a)
            return status and not status["connected"]

        await until(a_dropped, "user A's socket to be seen dropped", children)
        before = len(await stream_entries(bus, user_b, kill_id))

        async def b_flows():
            status = await user_status(bus, user_b)
            grown = len(await stream_entries(bus, user_b, kill_id)) >= before + 20
            return status and status["connected"] and (status["last_frame_us"] or 0) > kill_us and grown

        await until(b_flows, "user B's frames newer than the kill", children)
        assert children[LAUNCHER_ROLE].poll() is None, "the feed process stopped when one user's socket died"
        assert kite_b.accepted == 1, f"user B's Kite saw {kite_b.accepted} connections; A's failure reconnected B"
        for _id, message in await stream_entries(bus, user_b):
            if message.kind == feed_bus.KIND_FRAME:
                assert message.data in halves.b_only, "a frame that is not B's Kite's reached B's stream"
        for _id, message in await stream_entries(bus, user_a):
            if message.kind == feed_bus.KIND_FRAME:
                assert message.data in halves.a_only, "a frame that is not A's Kite's reached A's stream"
        assert (await user_status(bus, user_a))["connections"] == 1  # A's own count: its one connection, now gone
    finally:
        for child in children.values():
            if child.poll() is None:
                child.kill()
        for child in children.values():
            child.wait(timeout=30)
        server_b.close()
        await server_b.wait_closed()
        await clean(bus, user_a, user_b)
        await bus.aclose()


async def _count_at_least(bus, user: str, n: int):
    return await bus.xlen(feed_bus.ticks_key(user)) >= n or None


# ------------------------------------------------------------------------------------------------------------------
# In-process rig: the same supervise_users with an injected clock and an in-memory token store
# ------------------------------------------------------------------------------------------------------------------
class FakeClock:
    def __init__(self, now: datetime.datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += datetime.timedelta(**kw)


class MemoryStore:
    """The stand-in for the encrypted token store: ``set`` a user's session, ``fail`` a user's read, count the reads."""

    def __init__(self) -> None:
        self.sessions: dict[str, tuple[str, datetime.datetime | None]] = {}
        self.failing: set[str] = set()
        self.reads: Counter = Counter()

    def set(self, user: str, token: str, expires_at: datetime.datetime | None = None) -> None:
        self.sessions[user] = (token, expires_at)

    async def list_users(self) -> list[str]:
        return sorted(self.sessions)

    async def read(self, user: str):
        self.reads[user] += 1
        if user in self.failing:
            raise OSError("database unreachable: postgresql://secret@host")  # the message must never be logged
        found = self.sessions.get(user)
        if found is None:
            return None
        token, expires_at = found
        return feed_main.StoredSession(KEY, token, live_market.token_fingerprint(token), expires_at)


class Rig:
    """Runs ``supervise_users`` in this process against the real Redis stand-in and one fake Kite server per user."""

    def __init__(self, redis_url: str, clock: FakeClock | None = None) -> None:
        self.redis_url, self.clock = redis_url, clock or FakeClock()
        self.store, self.kites, self.servers, self.urls = MemoryStore(), {}, {}, {}
        self.bus = aioredis.Redis.from_url(redis_url)
        self.quit = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.users: list[str] = []

    async def kite(self, user: str, kite: CountingKite | None = None, **serve_kw) -> CountingKite:
        self.kites[user] = kite or CountingKite()
        self.servers[user] = await serve(self.kites[user].handler, "127.0.0.1", 0, **serve_kw)
        self.urls[user] = f"ws://127.0.0.1:{self.servers[user].sockets[0].getsockname()[1]}"
        self.users.append(user)
        return self.kites[user]

    def start(self, *, client=None, max_connections: int | None = None, recheck_s: float = 0.1,
              watch: tuple[str, ...] = ()) -> None:
        self.task = asyncio.ensure_future(feed_main.supervise_users(
            list_users=self.store.list_users, read_session=self.store.read, ws_url=lambda user: self.urls[user],
            redis_url=self.redis_url, client=client, clock=self.clock, recheck_s=recheck_s, quit_=self.quit,
            max_connections=max_connections, watch=watch))

    async def until(self, predicate, what: str, limit: float = 30.0):
        async def checked():
            if self.task.done():
                pytest.fail(f"the feed task ended while waiting for {what}: {self.task.exception()!r}")
            return await predicate()
        return await until(checked, what, {}, limit)

    async def close(self) -> None:
        self.quit.set()
        if self.task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.task, 30)
        for server in self.servers.values():
            server.close()
            await server.wait_closed()
        await clean(self.bus, *self.users)
        await self.bus.aclose()

    async def live(self, user: str):
        status = await user_status(self.bus, user)
        return status if status and status["connected"] and status["phase"] == "live" else None


@pytest.fixture
async def rig(redis_url):
    made = Rig(redis_url)
    yield made
    await made.close()


# ------------------------------------------------------------------------------------------------------------------
# Attack 2 and 6 (bus and log half)
# ------------------------------------------------------------------------------------------------------------------
async def test_an_exception_in_one_users_frame_handling_never_touches_the_other(rig, monkeypatch, caplog):
    """AC-9 attack 2 and AC-7 attack 6: A's frame handler raises on every frame; A's socket treats it as a drop and
    reconnects (it is disturbed), B's socket and Kite connection are untouched and B's frames keep arriving. No token
    appears in any stream entry, status or log line of either user."""
    caplog.set_level(logging.DEBUG)
    user_a, user_b = new_ref("ua"), new_ref("ub")
    token_a, token_b = "TOK-A-isolation-secret-1", "TOK-B-isolation-secret-2"
    kite_a, kite_b = await rig.kite(user_a), await rig.kite(user_b)
    rig.store.set(user_a, token_a)
    rig.store.set(user_b, token_b)
    real = feed_bus.FeedRelay.on_frame

    def on_frame(self, data, received_at):
        if self._user == user_a:
            raise RuntimeError(f"boom with {token_a}")  # the message holds a token: it must not be logged
        return real(self, data, received_at)

    monkeypatch.setattr(feed_bus.FeedRelay, "on_frame", on_frame)
    rig.start()
    await rig.until(lambda: _count_at_least(rig.bus, user_b, 10), "user B's frames")
    await rig.until(lambda: _is_true(kite_a.accepted >= 2), "user A's socket to drop and reconnect")
    mark = (await rig.bus.xrevrange(feed_bus.ticks_key(user_b), count=1))[0][0].decode()
    await rig.until(lambda: _count_more(rig.bus, user_b, mark, 10), "user B's frames after A's exceptions")
    assert kite_b.accepted == 1, "user B's socket reconnected because of user A's exception"
    assert (await rig.live(user_b)) is not None
    assert not rig.task.done()
    assert await rig.bus.xlen(feed_bus.ticks_key(user_a)) >= 1  # A's connected / dropped events still flow, no frame
    assert all(m.kind != feed_bus.KIND_FRAME for _i, m in await stream_entries(rig.bus, user_a))
    dump = []
    for user in (user_a, user_b):
        dump += [json.dumps([[str(k), str(v)] for k, v in f.items()]) for _i, f in
                 await rig.bus.xrange(feed_bus.ticks_key(user))]
        dump.append(str(await rig.bus.get(feed_bus.status_key(user))))
    assert not any(t in d for d in dump for t in (token_a, token_b, KEY))
    assert not any(t in r.getMessage() + str(r.args) + (r.exc_text or "") for r in caplog.records
                   for t in (token_a, token_b, "secret@host"))
    assert any(r.name == "ofo_app.kite_ws" for r in caplog.records)


async def _is_true(value: bool):
    return value or None


async def _count_more(bus, user: str, after: str, n: int):
    return len(await bus.xrange(feed_bus.ticks_key(user), min=f"({after}")) >= n or None


# ------------------------------------------------------------------------------------------------------------------
# Token store answer states, per user
# ------------------------------------------------------------------------------------------------------------------
async def test_an_unreadable_store_keeps_the_running_socket_and_a_missing_session_stops_only_that_user(rig, caplog):
    """AC-9 / standing item (d): the read of A raises (database unreachable) -> A's socket is kept and only the class is
    logged; the read of A answers none -> only A is stopped (status stopped); B is never touched."""
    caplog.set_level(logging.INFO)
    user_a, user_b = new_ref("ua"), new_ref("ub")
    kite_a, kite_b = await rig.kite(user_a), await rig.kite(user_b)
    rig.store.set(user_a, "TOK-A-states")
    rig.store.set(user_b, "TOK-B-states")
    rig.start()
    await rig.until(lambda: _both_live(rig, user_a, user_b), "both live")
    rig.store.failing.add(user_a)
    reads = rig.store.reads[user_a]
    await rig.until(lambda: _is_true(rig.store.reads[user_a] >= reads + 3), "three failing re-checks of A")
    assert kite_a.active == 1 and kite_a.accepted == 1, "an unreadable store must keep A's running socket"
    assert any("stored session unreadable: OSError" in r.getMessage() for r in caplog.records)
    assert not any("secret@host" in r.getMessage() for r in caplog.records)
    rig.store.failing.clear()
    del rig.store.sessions[user_a]
    stopped = await rig.until(lambda: _phase(rig, user_a, "stopped"), "A stopped")
    assert stopped["connected"] is False
    assert kite_a.active == 0 and kite_b.active == 1 and kite_b.accepted == 1
    assert (await rig.live(user_b)) is not None


async def _both_live(rig, a, b):
    return (await rig.live(a) and await rig.live(b)) or None


async def _phase(rig, user, phase):
    status = await user_status(rig.bus, user)
    return status if status and status["phase"] == phase else None


async def test_kite_403_for_one_user_ends_only_that_user(rig):
    """AC-9 / standing item (d), Kite refuses (403): A's session ends (status ended, one ``ended`` event, no retry), B's
    socket flows and is not reconnected."""
    user_a, user_b = new_ref("ua"), new_ref("ub")
    await rig.kite(user_a, process_request=lambda connection, request: connection.respond(HTTPStatus.FORBIDDEN, "no\n"))
    kite_b = await rig.kite(user_b)
    rig.store.set(user_a, "TOK-A-403")
    rig.store.set(user_b, "TOK-B-403")
    rig.start()

    async def a_ended():
        status = await user_status(rig.bus, user_a)
        return status if status and status["ended"] else None

    await rig.until(a_ended, "A's session to end")
    await rig.until(lambda: rig.live(user_b), "B live")
    reads = rig.store.reads[user_a]
    await rig.until(lambda: _is_true(rig.store.reads[user_a] >= reads + 3), "three re-checks after A ended")
    ended = [m for _i, m in await stream_entries(rig.bus, user_a) if m.kind == feed_bus.KIND_ENDED]
    assert len(ended) == 1, "the same ended session must not be tried again"
    assert kite_b.accepted == 1 and (await rig.live(user_b)) is not None


# ------------------------------------------------------------------------------------------------------------------
# Item 4 and item 5
# ------------------------------------------------------------------------------------------------------------------
async def test_a_feed_with_no_stored_session_idles_and_starts_a_socket_when_one_appears(rig):
    """Item 4: no stored session is a state, not an exit: the feed stays up, opens no Kite connection, and a session
    stored later starts that user's socket."""
    user = new_ref("ua")
    kite = await rig.kite(user)
    rig.start(watch=(user,))
    status = await rig.until(lambda: _phase(rig, user, "stopped"), "the idle status of a watched user")
    assert status["connected"] is False and not rig.task.done()
    assert kite.accepted == 0
    rig.store.set(user, "TOK-late-login")
    await rig.until(lambda: rig.live(user), "the late session's socket")
    assert kite.accepted == 1


class FlakyRedis:
    """The real client, but the first ``xrevrange`` and every ``xread`` fail until ``heal`` is called."""

    def __init__(self, real) -> None:
        self.real, self.down, self.failed_first = real, True, 0

    def heal(self) -> None:
        self.down = False

    async def xrevrange(self, *a, **kw):
        if self.down:
            self.failed_first += 1
            raise RedisConnectionError("refused")
        return await self.real.xrevrange(*a, **kw)

    async def xread(self, *a, **kw):
        if self.down:
            raise RedisConnectionError("refused")
        return await self.real.xread(*a, **kw)

    def __getattr__(self, name):
        return getattr(self.real, name)


async def test_redis_refused_at_feed_start_keeps_the_process_up_and_starts_once_redis_answers(rig, caplog):
    """Item 5: the control stream's first position read fails -> the process stays up (class only in the log), keeps
    retrying on the re-check, and starts the user's socket once Redis answers."""
    caplog.set_level(logging.INFO)
    user = new_ref("ua")
    kite = await rig.kite(user)
    rig.store.set(user, "TOK-redis-late")
    flaky = FlakyRedis(aioredis.Redis.from_url(rig.redis_url))
    rig.start(client=flaky)
    await rig.until(lambda: _is_true(flaky.failed_first >= 1), "the first failing position read")
    await rig.until(lambda: _is_true(rig.store.reads[user] >= 3), "re-checks while Redis is down")
    assert not rig.task.done(), "the feed exited because Redis was down at start"
    assert any("control stream position unreadable: ConnectionError" in r.getMessage() for r in caplog.records)
    flaky.heal()
    await rig.until(lambda: rig.live(user), "the socket once Redis answers")
    assert kite.accepted == 1


# ------------------------------------------------------------------------------------------------------------------
# Attack 6, the database half (CI: real PostgreSQL)
# ------------------------------------------------------------------------------------------------------------------
async def test_active_user_refs_is_an_allow_list_of_one_column(app_engine):
    """Attack 6: the active-users read returns user refs and nothing else: its result has exactly one column named
    ``user_ref``, every item is a plain str, an ended session's user is not listed, and no token (the plaintext or
    the ciphertext) appears in anything it returns. Standing item (d), store answers: a session present -> listed |
    none -> not listed | ended -> not listed."""
    cipher = TokenCipher(os.urandom(32))
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    live_a, live_b, gone = f"test-{uuid.uuid4().hex}", f"test-{uuid.uuid4().hex}", f"test-{uuid.uuid4().hex}"
    secrets = {live_a: "TOK-db-a-secret", live_b: "TOK-db-b-secret", gone: "TOK-db-gone-secret"}
    async with maker() as session:
        for user, token in secrets.items():
            await store.store_session(session, user, token, cipher)
        await store.end_session(session, gone, store.EndReason.DISCONNECTED)
        await session.commit()
    async with maker() as session:
        raw = await session.execute(store._ACTIVE_REFS, {"broker": "zerodha"})
        assert list(raw.keys()) == ["user_ref"]
    async with maker() as session:
        refs = await store.active_user_refs(session)
        expiry = await store.session_expiry(session, live_a)
        none = await store.session_expiry(session, gone)
    assert all(type(r) is str for r in refs)
    assert live_a in refs and live_b in refs and gone not in refs
    assert not any(s in " ".join(refs) for s in secrets.values())
    assert expiry is not None and none is None


async def test_the_hub_lists_users_through_the_allow_list_only():
    """Attack 6, mutation anchor: ``_main`` reads users with ``active_user_refs`` (user refs) and tokens only per user
    through ``access_token_for``; the source names no other column read."""
    source = pathlib.Path(feed_main.__file__).read_text(encoding="utf-8")  # noqa: ASYNC240
    assert "active_user_refs" in source and "token_ciphertext" not in source
