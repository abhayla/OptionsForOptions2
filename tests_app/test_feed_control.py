# ruff: noqa: PLR2004
"""REQ-113 AC-3, AC-7 (row 9 part A1): the API's Disconnect and login reach the market-data process.

The encrypted token store is the truth; a control message is only a wake-up. The feed process (the REAL
``feed_main.supervise`` over the REAL ``KiteSocket``) and the API (the REAL ``LiveMarket`` in ``bus`` mode, whose
``stop_current`` / ``pick_up_login`` are what the Disconnect and login routes call) run as OS processes through the
test-only launcher; Kite is a looping fake replaying the REAL recorded frames. The stored session is a file the test
writes or removes (the stand-in for the token store). Readiness is polled, never slept.

Every answer state of the token store: session present -> run on it | same session -> nothing | different session ->
restart on it | absent -> stop, status ``stopped`` | unreadable (decrypt error, database unreachable) -> keep the
running socket, log the class only. Redis: control stream empty -> nothing | malformed message -> counted, no wake |
connection refused / dropped -> no wake, the timed re-check still runs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import pathlib
import types

import pytest
import redis.asyncio as aioredis
from ofo_app import feed_bus, feed_main, live_market
from redis.exceptions import ConnectionError as RedisConnectionError
from test_feed_restart_core import TOKEN, LoopingKite, _is, _start, until
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

TOKEN_B = "TOK-second-login-not-a-real-token"  # noqa: S105 - a fixture value, not a credential
USER = live_market.OWNER_REF
RECHECK_S = 0.5
QUIET_S = 1.5  # longer than the re-check interval and the socket's 0.5 s poll: nothing new may arrive in it


class CountingKite(LoopingKite):
    """The looping fake Kite, also counting the connections that are open right now."""

    def __init__(self) -> None:
        super().__init__()
        self.active = 0

    async def handler(self, ws) -> None:
        self.active += 1
        try:
            await super().handler(ws)
        except ConnectionClosed:  # the feed closed its socket: the expected end of a connection
            pass
        finally:
            self.active -= 1


class Rig:
    def __init__(self, redis_url: str, tmp_path: pathlib.Path) -> None:
        self.kite = CountingKite()
        self.dir = tmp_path
        self.session = tmp_path / "session.txt"
        self.cfg = {"user": USER, "redis_url": redis_url, "state_file": str(tmp_path / "api.json"),
                    "session_file": str(self.session), "disconnect_file": str(tmp_path / "disconnect.flag"),
                    "login_file": str(tmp_path / "login.flag"), "recheck_s": RECHECK_S}
        self.cfg_path = tmp_path / "cfg.json"
        self.env = {**os.environ, "OFO_TEST_KITE_TOKEN": TOKEN, "FEED_MODE": "bus", "REDIS_URL": redis_url,
                    "LIVE_MARKET": "1"}
        self.bus = aioredis.Redis.from_url(redis_url)
        self.children: dict[str, object] = {}
        self.server = None

    async def open(self) -> None:
        self.server = await serve(self.kite.handler, "127.0.0.1", 0)
        self.cfg["ws_url"] = f"ws://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"
        self.cfg_path.write_text(json.dumps(self.cfg))
        self.session.write_text(TOKEN)

    def launch(self, role: str, name: str | None = None) -> None:
        env = self.env if role != "feed" else {**self.env, "FEED_MODE": "bus"}
        self.children[name or role] = _start(role, self.cfg_path, env)

    async def status(self) -> dict | None:
        raw = await self.bus.get(feed_bus.status_key(USER))
        return None if raw is None else feed_bus.decode_status(USER, raw)

    async def api_state(self) -> dict | None:
        try:
            return json.loads(pathlib.Path(self.cfg["state_file"]).read_text())  # noqa: ASYNC240 - a tiny file
        except (OSError, ValueError):
            return None

    async def stream_end(self) -> str | None:
        newest = await self.bus.xrevrange(feed_bus.ticks_key(USER), count=1)
        return newest[0][0].decode() if newest else None

    async def until(self, predicate, what: str, limit: float = 30.0):
        return await until(predicate, what, self.children, limit)

    async def feed_streaming(self, accepted: int | None = None) -> dict | None:
        status = await self.status()
        ok = status is not None and status["connected"] and status["phase"] == "live"
        return status if ok and (accepted is None or self.kite.accepted == accepted) and self.kite.active == 1 else None

    async def feed_stopped(self) -> dict | None:
        status = await self.status()
        return status if status and status["phase"] == "stopped" and self.kite.active == 0 else None

    async def close(self) -> None:
        for child in self.children.values():
            if child.poll() is None:
                child.kill()
        for child in self.children.values():
            child.wait(timeout=30)
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        await self.bus.delete(*(k(USER) for k in (feed_bus.ticks_key, feed_bus.want_key, feed_bus.status_key,
                                                   feed_bus.control_key)))
        await self.bus.aclose()


def _write_session(rig: Rig, token: str) -> None:
    rig.session.write_text(token)


def _remove_session(rig: Rig) -> None:
    rig.session.unlink()


def _flag(rig: Rig, name: str) -> None:
    """Ask the API launcher to run the real Disconnect / login hook (it deletes the flag file when it has)."""
    pathlib.Path(rig.cfg[name]).write_text("go")


@pytest.fixture
async def rig(redis_url, tmp_path):
    r = Rig(redis_url, tmp_path)
    await r.open()
    try:
        yield r
    finally:
        await r.close()


async def test_disconnect_in_bus_mode_stops_the_feed_process_kite_socket(rig):
    """AC-3 (core, attack 1): Disconnect in ``bus`` mode closes the FEED process's Kite socket - the status shows
    stopped, 0 connections, not connected - and no frame newer than the Disconnect reaches the stream the API reads.
    The feed process stays alive. (Role ``feed`` = the A0 process with no supervisor: that is the red run.)"""
    role = os.environ.get("OFO_TEST_FEED_ROLE", "feedsup")
    rig.launch(role, "feed")
    await rig.until(lambda: rig.feed_streaming(1), "the feed to hold one Kite connection")
    rig.launch("api")
    await rig.until(lambda: _is(rig.api_state, lambda s: s["ticks"] > 0), "the API to receive price ticks")
    # the Disconnect route's two steps: the stored session ends, then stop_current runs
    _remove_session(rig)
    _flag(rig, "disconnect_file")
    await rig.until(lambda: _is(rig.api_state, lambda s: s["state"] == "not_connected"),
                    "the API to read not connected")
    stopped = await rig.until(rig.feed_stopped, "the feed to stop its Kite socket (0 live connections)", 20.0)
    assert stopped["connected"] is False and stopped["connections"] == 0
    after = await rig.stream_end()
    await asyncio.sleep(QUIET_S)  # the absence of a frame is what is asserted: a clock-bounded quiet window
    assert await rig.stream_end() == after, "a frame was published after the Disconnect"
    assert rig.kite.active == 0
    assert rig.children["feed"].poll() is None, "the feed process itself must stay up"


async def test_a_lost_control_message_is_rebuilt_by_the_timed_recheck(rig):
    """AC-3 (attack 2): the session is removed and NO control message is ever published; the feed's fixed re-check
    still stops its socket, within a few intervals."""
    rig.launch("feedsup", "feed")
    await rig.until(lambda: rig.feed_streaming(1), "the feed to hold one Kite connection")
    assert await rig.bus.xlen(feed_bus.control_key(USER)) == 0
    _remove_session(rig)
    await rig.until(rig.feed_stopped, "the re-check to stop the socket with no message", 20.0)


async def test_a_new_login_restarts_the_feed_on_it_and_the_same_session_again_does_not(rig):
    """AC-3, AC-7 (attack 3): a different stored session -> the old socket closes and exactly one new one opens; the
    same session announced again (a login message) -> no restart."""
    rig.launch("feedsup", "feed")
    await rig.until(lambda: rig.feed_streaming(1), "the first connection")
    _write_session(rig, TOKEN_B)
    await rig.until(lambda: rig.feed_streaming(2), "the restart on the new session (2 accepted, 1 open)")
    client = feed_bus.new_client(rig.cfg["redis_url"])
    try:
        for _ in range(3):
            await feed_bus.publish_control(client, USER, feed_bus.CONTROL_LOGIN, live_market.datetime.datetime.now(
                live_market.IST))
    finally:
        await client.aclose()
    await asyncio.sleep(QUIET_S)  # three wake-ups and several re-checks later: the absence of a restart is asserted
    assert rig.kite.accepted == 2 and rig.kite.active == 1


async def test_no_token_or_fingerprint_is_on_the_bus_or_in_any_log_line(rig):
    """AC-7 (attack 4): after a login, a restart and a Disconnect through both processes, no key on the bus (ticks,
    control, status, wanted) and no log file holds a token, its sha256 digest or its hex."""
    rig.launch("feedsup", "feed")
    await rig.until(lambda: rig.feed_streaming(1), "the first connection")
    rig.launch("api")
    await rig.until(lambda: _is(rig.api_state, lambda s: s["ticks"] > 0), "the API to receive ticks")
    _write_session(rig, TOKEN_B)
    _flag(rig, "login_file")
    await rig.until(lambda: rig.feed_streaming(2), "the restart on the new session")
    _remove_session(rig)
    _flag(rig, "disconnect_file")
    await rig.until(rig.feed_stopped, "the feed to stop", 20.0)
    secrets = []
    for token in (TOKEN, TOKEN_B):
        digest = hashlib.sha256(token.encode()).digest()
        secrets += [token.encode(), digest, digest.hex().encode(), token.encode().hex().encode()]
    assert await rig.bus.xlen(feed_bus.control_key(USER)) >= 2, "the login and the Disconnect were not published"
    blobs = []
    for key in (feed_bus.ticks_key, feed_bus.control_key):
        blobs += [repr(item).encode() for item in await rig.bus.xrange(key(USER))]
    for key in (feed_bus.status_key, feed_bus.want_key):
        blobs.append(await rig.bus.get(key(USER)) or b"")
    for name in ("feedsup", "api"):
        blobs.append(rig.dir.joinpath(f"{name}.log").read_bytes())
    for blob in blobs:
        for secret in secrets:
            assert secret not in blob


# ---- the answer states, one test each, on the real reconcile / control read --------------------------------------

class _Task:
    def __init__(self, done: bool = False, result: str | None = None) -> None:
        self._done, self._result = done, result

    def done(self) -> bool:
        return self._done

    def cancelled(self) -> bool:
        return False

    def exception(self):
        return None

    def result(self):
        return self._result


class _Fake:
    def __init__(self) -> None:
        self.started: list[bytes] = []
        self.halted = 0
        self.stopped_status = 0


def _session(token: str) -> feed_main.StoredSession:
    return feed_main.StoredSession("K", token, hashlib.sha256(token.encode()).digest())


@pytest.fixture
def fake(monkeypatch):
    f = _Fake()

    def start(session, *args):
        f.started.append(session.fingerprint)
        return feed_main._Running(session, _Task(), types.SimpleNamespace(set=lambda: None))

    async def halt(self):
        f.halted += 1

    async def stopped(*args):
        f.stopped_status += 1

    monkeypatch.setattr(feed_main, "_start", start)
    monkeypatch.setattr(feed_main._Running, "halt", halt)
    monkeypatch.setattr(feed_bus, "publish_stopped", stopped)
    return f


def _hub(read_session, client=None):
    async def users():
        return [USER]

    async def read(_user):
        return await read_session()

    return feed_main._Hub(list_users=users, read_session=read, ws_url="ws://x", client=client, clock=lambda: None,
                          connect=None, max_connections=3, watch=(USER,))


async def _reconcile(running, read_session):
    hub = _hub(read_session)
    if running is not None:
        hub.running[USER] = running
    await hub.reconcile()
    return hub.running.get(USER)


async def test_store_present_starts_the_socket_and_the_same_session_changes_nothing(fake):
    """(d) session present -> run on it; the same session again -> nothing."""
    async def read():
        return _session(TOKEN)

    running = await _reconcile(None, read)
    assert running is not None and len(fake.started) == 1
    assert await _reconcile(running, read) is running
    assert len(fake.started) == 1 and fake.halted == 0


async def test_store_different_session_halts_the_old_socket_and_starts_the_new(fake):
    """(d) a different session -> the old socket stops, one new starts."""
    running = await _reconcile(None, _answer(_session(TOKEN)))
    after = await _reconcile(running, _answer(_session(TOKEN_B)))
    assert fake.halted == 1 and len(fake.started) == 2 and after.fingerprint == _session(TOKEN_B).fingerprint


async def test_store_absent_halts_the_socket_publishes_stopped_and_does_not_restart(fake):
    """(d) no stored session -> stop, status stopped, nothing running; it stays so on the next check."""
    running = await _reconcile(None, _answer(_session(TOKEN)))
    assert await _reconcile(running, _answer(None)) is None
    assert fake.halted == 1 and fake.stopped_status == 1
    assert await _reconcile(None, _answer(None)) is None
    assert len(fake.started) == 1 and fake.stopped_status == 2


@pytest.mark.parametrize("error", [ValueError(f"cannot decrypt {TOKEN}"), OSError(f"db unreachable {TOKEN}")])
async def test_store_unreadable_keeps_the_running_socket_and_logs_the_class_only(fake, caplog, error):
    """(d) decrypt error or database unreachable -> keep the current socket; the log names the class, never the text."""
    running = await _reconcile(None, _answer(_session(TOKEN)))
    caplog.set_level(logging.DEBUG)

    async def read():
        raise error

    assert await _reconcile(running, read) is running
    assert fake.halted == 0 and fake.stopped_status == 0
    assert type(error).__name__ in caplog.text and TOKEN not in caplog.text


async def test_a_socket_whose_session_kite_refused_is_not_restarted_on_the_same_session(fake):
    """(d) Kite said 'session ended' for this stored session: the same session is not tried again; a crash is."""
    ended = feed_main._Running(_session(TOKEN), _Task(True, feed_main.SESSION_ENDED_WORD), None)
    assert await _reconcile(ended, _answer(_session(TOKEN))) is ended
    crashed = feed_main._Running(_session(TOKEN), _Task(True, "stopped"), None)
    assert await _reconcile(crashed, _answer(_session(TOKEN))) is not crashed
    assert len(fake.started) == 1


def _answer(value):
    async def read():
        return value

    return read


async def test_control_stream_states(redis_url):
    """(d) Redis: empty -> no wake | valid -> wake | malformed or foreign -> counted, no wake | refused -> no wake."""
    user = f"c{os.urandom(5).hex()}"
    bus = feed_bus.new_client(redis_url)
    hub = _hub(None, bus)
    hub.positions[user] = "0-0"
    hub.watch = (user,)
    try:
        assert await hub.read_controls() is False
        await bus.xadd(feed_bus.control_key(user), {"u": user, "k": "login", "t": "5", "token": "x"})  # extra key
        await bus.xadd(feed_bus.control_key(user), {"u": "other", "k": "login", "t": "5"})
        await bus.xadd(feed_bus.control_key(user), {"u": user, "k": "mystery", "t": "5"})
        assert await hub.read_controls() is False and hub.counters["bad_control"] == 3
        await feed_bus.publish_control(bus, user, "disconnect", live_market.datetime.datetime.now(live_market.IST))
        assert await hub.read_controls() is True
    finally:
        await bus.delete(feed_bus.control_key(user))
        await bus.aclose()

    class Refused:
        async def xread(self, *a, **k):
            raise RedisConnectionError("refused")

    refused = _hub(None, Refused())
    refused.positions[user] = "7-0"
    refused.watch = (user,)
    assert await refused.read_controls() is False and refused.positions[user] == "7-0"


async def test_lost_wake_up_publish_never_raises(monkeypatch, caplog):
    """(d) Redis refused while the API wakes the feed: the login/Disconnect still stands, a warning names the class."""
    monkeypatch.setenv("FEED_MODE", "bus")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    caplog.set_level(logging.WARNING)
    await live_market.LiveMarket().tell_feed(feed_bus.CONTROL_DISCONNECT)
    assert "market-data process not woken" in caplog.text


async def test_inprocess_mode_publishes_nothing_to_the_bus(redis_url, monkeypatch):
    """Attack 7 (unit): outside ``bus`` mode neither login pick-up nor Disconnect touches Redis."""
    monkeypatch.setenv("FEED_MODE", "inprocess")
    monkeypatch.setenv("REDIS_URL", redis_url)
    bus = feed_bus.new_client(redis_url)
    try:
        market = live_market.LiveMarket()
        await market.tell_feed(feed_bus.CONTROL_LOGIN)
        await market.tell_feed(feed_bus.CONTROL_DISCONNECT)
        assert await bus.exists(feed_bus.control_key(USER)) == 0
    finally:
        await bus.aclose()


def test_the_control_message_allows_only_a_kind_and_a_time():
    """AC-7: ``publish_control`` refuses any kind but login / disconnect; ``valid_control`` is an allow-list."""
    assert feed_bus.valid_control("u1", {"u": "u1", "k": "login", "t": "123"})
    assert not feed_bus.valid_control("u1", {"u": "u1", "k": "login", "t": "123", "fp": "abc"})
    assert not feed_bus.valid_control("u1", {"u": "u1", "k": "login", "t": "1" * 19})
    with pytest.raises(ValueError, match="login / disconnect"):
        asyncio.run(feed_bus.publish_control(None, "u1", "token", live_market.datetime.datetime.now()))


async def test_module_login_hook_and_stop_current_wake_the_feed_in_bus_mode_only(redis_url, monkeypatch):
    """Callers ``routes/broker.py`` (login callback -> ``live_market.pick_up_login``) and ``routes/broker_status.py``
    (Disconnect -> ``live_market.stop_current``): in ``bus`` mode each publishes its one control message; with
    LIVE_MARKET off, or no registered market, nothing is published."""
    market = live_market.LiveMarket()

    async def no_restart(self, *a, **k):
        return None

    monkeypatch.setattr(live_market.LiveMarket, "_restart_if_new", no_restart)
    monkeypatch.setattr(live_market, "_current", market)
    monkeypatch.setenv("FEED_MODE", "bus")
    monkeypatch.setenv("REDIS_URL", redis_url)
    bus = feed_bus.new_client(redis_url)
    kinds = []

    async def sent() -> list[bytes]:
        return [fields[b"k"] for _id, fields in await bus.xrange(feed_bus.control_key(USER))]

    try:
        await bus.delete(feed_bus.control_key(USER))
        monkeypatch.delenv("LIVE_MARKET", raising=False)
        await live_market.pick_up_login(types.SimpleNamespace())
        assert await sent() == []  # LIVE_MARKET off: the hook does nothing
        monkeypatch.setenv("LIVE_MARKET", "1")
        await live_market.pick_up_login(types.SimpleNamespace())
        await live_market.stop_current()
        kinds = await sent()
        assert kinds == [b"login", b"disconnect"]
        monkeypatch.setattr(live_market, "_current", None)
        await live_market.stop_current()
        assert await sent() == kinds  # no registered market: nothing more
    finally:
        await bus.delete(feed_bus.control_key(USER))
        await bus.aclose()


async def test_the_status_phase_in_bus_mode_follows_the_feed_status_key(redis_url):
    """Caller ``routes/broker_status.py`` -> ``live_market.feed_phase``: in ``bus`` mode the phase comes from the
    provider the BusSocket drives, so a ``stopped`` feed status leaves it not healthy."""
    from ofo.rules.inputs import DataHealth  # noqa: PLC0415
    from test_bus_socket import PRICE_FRAME, T0, World, go_live, poll  # noqa: PLC0415

    w = World(redis_url)
    try:
        await go_live(w)
        await w.publish("frame", T0, PRICE_FRAME)
        assert w.provider.feed.health(T0) is DataHealth.AVAILABLE
        body = {"u": w.user, "connected": False, "ended": False, "connections": 0, "last_frame_us": None,
                "phase": "stopped"}
        await w.bus.set(feed_bus.status_key(w.user), json.dumps(body), px=60_000)
        await poll(lambda: w.provider.feed.connected is False, "the stopped status to read as not connected")
        assert w.provider.feed.health(T0) is not DataHealth.AVAILABLE
    finally:
        await w.stop()
