"""REQ-113 AC-1, AC-7: the API process opens no Kite socket in ``bus`` mode; the feed mode is an allow-list; the
market-data process has the egress gate installed, refuses a loopback Kite address outside the test suites, and
puts no token on the bus or in a log line."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import subprocess
import sys
import types
import uuid

import pytest
from ofo.broker import egress
from ofo_app import catalogue_store, db, feed_bus, feed_main, feed_mode, kite_ws, live_market, main
from websockets.asyncio.server import serve

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests"))
from marketdata._kite_fixture import listed
from test_feed_restart_core import LoopingKite

BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
MIN_FRAMES = 5
MIN_IDLE_READS = 4  # the LATE_LOGIN_CHILD waits for this many store reads before it stores a session
TOKEN = "TOK-boundary-secret-not-real"  # noqa: S105 - a fixture value, not a credential


class _Conn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Engine:
    def connect(self):
        return _Conn()


@pytest.fixture
def api_world(monkeypatch):
    """A LiveMarket start with a stored session, a fixture catalogue and a Kite socket class that records its builds."""
    built: list[tuple] = []
    connects: list[str] = []

    class RecordingKiteSocket:
        def __init__(self, *a, **k):
            built.append((a, k))
            self.connections = 0

        async def run(self):
            await asyncio.sleep(3600)

        def stop(self):
            pass

    async def stored(self, config):
        return TOKEN

    async def no_catalogue(conn):
        return types.SimpleNamespace(all_entries=list)

    monkeypatch.setattr(kite_ws, "KiteSocket", RecordingKiteSocket)
    monkeypatch.setattr(kite_ws, "_ws_connect", lambda *a, **k: connects.append("connect"))
    monkeypatch.setattr(db, "get_engine", _Engine)
    monkeypatch.setattr(catalogue_store, "load_catalogue", no_catalogue)
    monkeypatch.setattr(live_market, "listed_for_kite", lambda entries: listed())
    monkeypatch.setattr(live_market.LiveMarket, "_stored_token", stored)
    monkeypatch.setattr(live_market, "get_settings", lambda: types.SimpleNamespace(KITE_WS_URL="ws://127.0.0.1:1"))
    return types.SimpleNamespace(built=built, connects=connects,
                                 config=types.SimpleNamespace(api_key="K-boundary", token_key=b"k"))


async def test_api_startup_in_bus_mode_opens_no_websocket_and_makes_no_kite_call(api_world, monkeypatch, redis_url):
    """AC-1: with FEED_MODE=bus the API's live start builds a BusSocket, never a KiteSocket, and opens no websocket."""
    monkeypatch.setenv("FEED_MODE", "bus")
    monkeypatch.setenv("REDIS_URL", redis_url)
    market = live_market.LiveMarket()
    await market.start(api_world.config)
    try:
        assert market.state == live_market.LIVE
        assert type(market._socket).__name__ == "BusSocket"
        assert api_world.built == [], "the API built a Kite socket in bus mode"
        assert api_world.connects == [], "the API opened a websocket in bus mode"
    finally:
        await market.stop()


async def test_the_same_start_in_inprocess_mode_builds_the_kite_socket(api_world, monkeypatch):
    """Control for the test above: the check discriminates, because in-process mode does build the Kite socket."""
    monkeypatch.delenv("FEED_MODE", raising=False)
    market = live_market.LiveMarket()
    await market.start(api_world.config)
    try:
        assert len(api_world.built) == 1
    finally:
        await market.stop()


@pytest.mark.parametrize("value", ["", "Bus", "BUS", " bus", "bus ", "redis", "none", "in-process", "inprocess\n"])
def test_an_unknown_feed_mode_refuses_start_up(monkeypatch, value):
    """Allow-list: only the exact words ``inprocess`` and ``bus`` start the app, in every environment."""
    monkeypatch.setenv("FEED_MODE", value)
    for env in ("production", "development", "test", ""):
        with pytest.raises(feed_mode.FeedModeRefused, match="FEED_MODE"):
            feed_mode.require_valid(env, True)
    with pytest.raises(feed_mode.FeedModeRefused):
        main.create_app()  # the app builder itself refuses, before anything is served


def test_inprocess_with_a_live_market_is_refused_in_production_and_only_there(monkeypatch):
    """The one-process case is for development and test: a production deploy would cut the socket (AC-2)."""
    monkeypatch.delenv("FEED_MODE", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    with pytest.raises(feed_mode.FeedModeRefused, match="production"):
        feed_mode.require_valid("production", True)
    assert feed_mode.require_valid("production", False) == feed_mode.INPROCESS  # no live market: no socket exists
    for env in ("development", "test", ""):
        assert feed_mode.require_valid(env, True) == feed_mode.INPROCESS
    monkeypatch.setenv("FEED_MODE", "bus")
    assert feed_mode.require_valid("production", True) == feed_mode.BUS
    monkeypatch.delenv("REDIS_URL")
    with pytest.raises(feed_mode.FeedModeRefused, match="REDIS_URL"):
        feed_mode.require_valid("production", True)


def test_the_market_data_process_has_the_egress_gate_and_refuses_a_loopback_kite_address():
    """AC-7: a fresh process that is NOT the test launcher: ``prepare_process`` installs the egress gate, test mode is
    off, a loopback Kite address is refused before anything opens, and an injected connect is refused too."""
    code = (
        "import json, datetime\n"
        "from ofo.broker import egress\n"
        "from ofo_app import feed_main, feed_bus\n"
        "feed_main.prepare_process()\n"
        "out = {'installed': egress.installed(), 'test_mode': egress._test_mode()}\n"
        "relay = feed_bus.FeedRelay('u1', lambda: datetime.datetime.now())\n"
        "for name, kw in (('loopback', {}), ('seam', {'connect': lambda *a, **k: None})):\n"
        "    try:\n"
        "        url = 'ws://127.0.0.1:9' if name == 'loopback' else 'wss://ws.kite.trade'\n"
        "        feed_main.build_socket(relay, api_key='k', access_token='t', ws_url=url,\n"
        "                               clock=datetime.datetime.now, **kw)\n"
        "        out[name] = 'BUILT'\n"
        "    except Exception as exc:\n"
        "        out[name] = type(exc).__name__\n"
        "print(json.dumps(out))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    run = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,  # noqa: S603
                         timeout=120, check=False)
    assert run.returncode == 0, run.stderr[-1500:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out == {"installed": True, "test_mode": False, "loopback": "KiteCallRefused", "seam": "EgressRefused"}


IDLE_CHILD = r"""import asyncio, json, sys, types
from ofo.broker import egress
from ofo_app import broker_config, broker_crypto, broker_token_store, db, event_loop, feed_main, feed_mode
from ofo_app import live_market
seen = {'prepared': False, 'built': 0}
real_prepare = feed_main.prepare_process
def prepare():
    seen['prepared'] = True
    real_prepare()
real_loop_check = event_loop.require_selector_loop
def first_step():
    seen['prepared_first'] = seen['prepared']
    seen['at_first_step'] = egress.installed()
    real_loop_check()
class Conn:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
class Engine:
    def connect(self): return Conn()
async def noop(*a, **k): return None
async def nobody(*a, **k): return []
def built(*a, **k):
    seen['built'] += 1
feed_main.prepare_process = prepare
event_loop.require_selector_loop = first_step
feed_main.feed_settings = lambda: types.SimpleNamespace(KITE_WS_URL='wss://ws.kite.trade')
live_market.require_safe = lambda *a: None
feed_mode.redis_url = lambda: 'redis://127.0.0.1:1/0'
broker_config.load_broker_config = lambda: types.SimpleNamespace(token_key=b'k', api_key='K')
broker_crypto.TokenCipher = lambda key: None
broker_token_store.access_session_for = noop
broker_token_store.active_user_refs = nobody
db.verify_pool_budget, db.close_db, db.get_engine = noop, noop, Engine
feed_main.build_socket = built
feed_main.run_feed = built
async def go():
    try:
        seen['code'] = await asyncio.wait_for(feed_main._main(), 3)
    except TimeoutError:
        seen['code'] = 'still running'
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(go())
print(json.dumps({**seen, 'installed_after': egress.installed()}))
"""


def test_the_market_data_process_installs_the_egress_gate_then_idles_for_want_of_a_session():
    """Attack 5 (row 9 part B, item 4): ``feed_main._main`` with no stored session installs the egress gate first, makes
    no Kite socket, and does NOT exit (a process manager would restart an exiting feed in a loop until a login): it is
    still running after 3 s. Only the database, config and token-store reads are stood in; the order of start-up
    steps is the real ``_main``."""
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    with subprocess.Popen([sys.executable, "-c", IDLE_CHILD], env=env, stdout=subprocess.PIPE,  # noqa: S603
                          stderr=subprocess.PIPE, text=True) as child:
        stdout, stderr = child.communicate(timeout=120)
    assert child.returncode == 0, stderr[-1500:]
    out = json.loads(stdout.strip().splitlines()[-1])
    assert out == {"prepared": True, "prepared_first": True, "built": 0, "at_first_step": True,
                   "code": "still running", "installed_after": True}


LATE_LOGIN_CHILD = r"""import asyncio, json, pathlib, sys, types
from ofo_app import broker_config, broker_crypto, broker_token_store, db, event_loop, feed_main, feed_mode
from ofo_app import live_market
redis_url, session_file = sys.argv[1], pathlib.Path(sys.argv[2])
seen = {'reads': 0, 'started': 0, 'exit': None}
class Conn:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
class Engine:
    def connect(self): return Conn()
async def noop(*a, **k): return None
async def nobody(*a, **k): return []
async def session(conn, user, cipher):
    seen['reads'] += 1
    return ('TOK-late-login', None) if session_file.exists() else None
async def fake_run(**kw):
    seen['started'] += 1
    await kw['stop'].wait()
feed_main.feed_settings = lambda: types.SimpleNamespace(KITE_WS_URL='wss://ws.kite.trade')
live_market.require_safe = lambda *a: None
feed_mode.redis_url = lambda: redis_url
broker_config.load_broker_config = lambda: types.SimpleNamespace(token_key=b'k', api_key='K')
broker_crypto.TokenCipher = lambda key: None
broker_token_store.access_session_for = session
broker_token_store.active_user_refs = nobody
db.verify_pool_budget, db.close_db, db.get_engine = noop, noop, Engine
feed_main.run_feed = fake_run
feed_main.supervise_users.__kwdefaults__['recheck_s'] = 0.2
async def waited(predicate, limit=20.0):
    for _ in range(int(limit / 0.05)):
        if predicate() or main.done():
            return
        await asyncio.sleep(0.05)
async def go():
    global main
    main = asyncio.ensure_future(feed_main._main())
    await waited(lambda: seen['reads'] >= 4)
    seen['idle_reads'], seen['up_while_idle'] = seen['reads'], not main.done()
    session_file.write_text('stored')
    await waited(lambda: seen['started'] >= 1)
    seen['up_at_start'] = not main.done()
    main.cancel()
    await asyncio.gather(main, return_exceptions=True)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(go())
print(json.dumps(seen))
"""


def test_the_market_data_process_stays_up_without_a_session_and_starts_a_socket_after_a_login(redis_url, tmp_path):
    """Attack 3 (AC-1): the real ``feed_main._main`` with no stored session is still running after several timed
    re-checks of the store (it never exits: a process manager would restart it in a loop), and a session stored later
    starts that user's socket. Every wait is bounded (20 s in the child, 90 s for the process), so a crash or a hang
    FAILS the test instead of stalling it."""
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    session_file = tmp_path / "stored-session"
    with subprocess.Popen([sys.executable, "-c", LATE_LOGIN_CHILD, redis_url, str(session_file)], env=env,  # noqa: S603
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
        try:
            stdout, stderr = child.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            pytest.fail("the market-data process hung")
    assert child.returncode == 0, f"the process exited instead of idling: {stderr[-1500:]}"
    out = json.loads(stdout.strip().splitlines()[-1])
    assert out["up_while_idle"] and out["idle_reads"] >= MIN_IDLE_READS, out
    assert out["started"] == 1 and out["up_at_start"], out


async def test_no_token_appears_in_any_bus_value_or_log_line(redis_url, caplog):
    """AC-7: the REAL feed code over the real KiteSocket (loopback, test mode): after frames flowed, no key the
    feed wrote (stream entries, status, wanted snapshot) and no log line contains the Kite token."""
    caplog.set_level(logging.DEBUG)
    user = f"t{uuid.uuid4().hex[:12]}"
    kite = LoopingKite()
    server = await serve(kite.handler, "127.0.0.1", 0)
    bus = feed_bus.new_client(redis_url)
    await bus.set(feed_bus.want_key(user), feed_bus.encode_want(user, [1, 2, 3]), px=60_000)
    task = asyncio.ensure_future(feed_main.run_feed(
        user_ref=user, api_key="KEY-boundary", access_token=TOKEN, redis_url=redis_url,
        ws_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"))
    try:
        for _ in range(500):
            if await bus.xlen(feed_bus.ticks_key(user)) >= MIN_FRAMES and await bus.exists(feed_bus.status_key(user)):
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("the feed published nothing")
        entries = await bus.xrange(feed_bus.ticks_key(user))
        dump = [json.dumps([[str(k), str(v)] for k, v in f.items()]) for _i, f in entries]
        keys = (feed_bus.status_key(user), feed_bus.want_key(user))
        dump += [(await bus.get(k)).decode("ascii", "replace") for k in keys]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        server.close()
        await server.wait_closed()
        await bus.aclose()
    assert not any(TOKEN in d or "KEY-boundary" in d for d in dump)
    assert not any(TOKEN in r.getMessage() or TOKEN in str(r.args) for r in caplog.records)
    assert kite.accepted == 1
    assert egress.installed()
