"""W-065 (REQ-035 AC-4; ADR-068; REQ-048 AC-4): the live strategy push and the live market context, on the W-064 replay
provider and a fake clock. No Kite connection, no database. Most tests drive :class:`StrategyPush` through its
two-method channel (minted by the door's ``socket_body``); the phase-2 tests at the end drive the real app's door socket
route /api/strategies/live on the replay, and the REST route's not-live answer (issue #206).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402

from ofo.errors import render  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo_app import live_market  # noqa: E402
from ofo_app.config import Settings  # noqa: E402
from ofo_app.live_push import ChannelClosed, LiveFeed, StrategyPush  # noqa: E402
from ofo_app.routes.outcome import MarketContext, get_market_context  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
SELL_CE, BUY_CE, SELL_PE, BUY_PE = "NSE_FO:44624", "NSE_FO:44632", "NSE_FO:44604", "NSE_FO:44595"
DB = "postgresql+asyncpg://example@127.0.0.1:5432/x"
ERROR = render("user_input_request_invalid").as_dict()


class FakeChannel:
    def __init__(self) -> None:
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []

    async def receive(self):
        item = await self.inbound.get()
        if item is ChannelClosed:
            raise ChannelClosed()
        return item

    async def send(self, source) -> None:
        """Minted exactly as the app's door socket mints it (ofo_app.errors.socket_body), then read back as JSON."""
        from ofo_app.errors import socket_body
        from ofo_app.routes.outcome import OutcomeResponse

        self.sent.append(json.loads(bytes(socket_body(source, (OutcomeResponse,)))))


class Mono:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def ltp_frame(provider, instrument_id: str, rupees: str) -> bytes:
    token = provider._token_of[instrument_id]
    paise = int(Decimal(rupees) * 100)
    return (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + token.to_bytes(4, "big") + paise.to_bytes(4, "big")


def request(provider, ids=((SELL_CE, "SELL"), (BUY_CE, "BUY"), (SELL_PE, "SELL"), (BUY_PE, "BUY"))) -> dict:
    return {"underlying": "NIFTY", "legs": [
        {"instrument_id": i, "action": a, "lots": 1, "planned_entry": f"{provider.book.get(i, VALUATION).ltp:f}",
         "captured_at": VALUATION.isoformat()} for i, a in ids]}


def held_replay(provider, clock, items):
    """Replay the recording into a provider that holds every recorded instrument: since gate 4a D-1 a tick for a token
    nobody holds never reaches the book, so the rig holds them the way the app's replay provider does."""
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    return replay(provider, clock)


def none_held(provider, ids) -> bool:
    """No vendor subscription is left for any of ``ids`` (the rig's other recorded instruments stay held)."""
    wanted = set(provider.subscribed_tokens())
    return all(provider._token_of[i] not in wanted for i in ids)


def strategy_ids(provider) -> list:
    return [SELL_CE, BUY_CE, SELL_PE, BUY_PE, provider.index_id("NIFTY")]


@pytest.fixture
def rig():
    provider, clock, items = new_provider()
    held_replay(provider, clock, items)  # the recorded 2026-10-08 frames; no strategy subscribed yet
    ctx = MarketContext(provider, lambda: VALUATION, RATE)
    feed = LiveFeed(ctx, FanOut(provider))
    channel, mono = FakeChannel(), Mono()
    push = StrategyPush(channel, feed, monotonic=mono, poll=0.005)
    return provider, feed, channel, mono, push


async def settle(n: int = 6) -> None:
    for _ in range(n):
        await asyncio.sleep(0.01)


def tick(provider, instrument_id: str, rupees: str) -> None:
    provider.on_frame(ltp_frame(provider, instrument_id, rupees), VALUATION)


async def test_at_most_one_push_a_second_when_ticks_arrive_faster(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    assert len(channel.sent) == 1  # the baseline answer
    for n in range(20):  # twenty changed ticks inside one second of the monotonic clock
        tick(provider, SELL_CE, f"{100 + n}.05")
        await settle(2)
    assert len(channel.sent) == 1
    mono.now += 1.0
    await settle()
    assert len(channel.sent) == 2  # exactly one catch-up push, not twenty
    assert channel.sent[1]["legs"][0]["ltp"] == "119.05"
    await channel.inbound.put(ChannelClosed)
    await task


async def test_no_push_when_no_input_changed(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    mono.now += 30
    await settle()
    assert len(channel.sent) == 1  # time passing alone is not a change
    tick(provider, SELL_CE, "111.10")
    mono.now += 1
    await settle()
    assert len(channel.sent) == 2
    tick(provider, SELL_CE, "111.10")  # the same quote again
    mono.now += 5
    await settle()
    assert len(channel.sent) == 2
    await channel.inbound.put(ChannelClosed)
    await task


async def test_the_push_equals_the_rest_outcome_for_the_same_snapshot(rig):
    provider, feed, channel, mono, push = rig
    from ofo_app.main import create_app

    body = request(provider)
    task = asyncio.create_task(push.run())
    await channel.inbound.put(body)
    await settle()
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: feed.ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        rest = (await ac.post("/api/strategies/outcome", json=body)).json()
    assert channel.sent[0] == rest
    assert rest["state"] == "COMPUTED"
    await channel.inbound.put(ChannelClosed)
    await task


async def test_a_new_client_message_replaces_the_strategy(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    assert feed.fanout.subscriber_count(BUY_PE) == 1
    await channel.inbound.put(request(provider, ids=((SELL_CE, "SELL"),)))
    await settle()
    assert feed.fanout.subscriber_count(BUY_PE) == 0 and feed.fanout.subscriber_count(SELL_CE) == 1
    assert len(channel.sent) == 1  # round 2: the 1 s gate since the last push holds for a changed strategy too
    mono.now += 1.0
    await settle()
    assert len(channel.sent) == 2 and len(channel.sent[1]["legs"]) == 1  # the new strategy, one second later
    await channel.inbound.put(ChannelClosed)
    await task


async def test_ac4_an_identical_strategy_resent_10_times_pushes_nothing_more(rig):
    """AC-4 / ADR-068 (2) "at most once a second per strategy, and only when an input changed": the same strategy sent
    10 more times with a frozen clock and no tick yields no push beyond the first, and no re-subscription; even after
    the clock moves on, with no input changed, nothing more is pushed."""
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    body = request(provider)
    await channel.inbound.put(body)
    await settle()
    handle = push._handle
    for _ in range(10):
        await channel.inbound.put(dict(body))
    await settle(12)
    assert len(channel.sent) == 1 and push._handle == handle and feed.fanout.subscriber_count(SELL_CE) == 1
    mono.now += 5
    await settle()
    assert len(channel.sent) == 1
    await channel.inbound.put(ChannelClosed)
    await task


async def test_ac4_a_burst_of_10_changed_strategies_within_a_second_pushes_at_most_twice(rig):
    """AC-4 / ADR-068 (2): 10 DIFFERENT strategies within one second (frozen clock, then +1 s) -> the first push at once,
    at most one more after the second has passed, and that one is the LAST strategy sent; nothing else."""
    provider, feed, channel, mono, push = rig
    legs = ((SELL_CE, "SELL"), (BUY_CE, "BUY"), (SELL_PE, "SELL"), (BUY_PE, "BUY"))
    bodies = [request(provider, ids=legs[:1 + n % 4]) | {"ux_level": ("guided", "standard", "advanced")[n % 3]}
              for n in range(10)]  # built first: a released instrument leaves the provider's book
    task = asyncio.create_task(push.run())
    for body in bodies:
        await channel.inbound.put(body)
        await settle(2)
    await settle(6)
    assert len(channel.sent) == 1
    mono.now += 1.0
    await settle()
    mono.now += 10
    await settle()
    assert len(channel.sent) == 2
    assert len(channel.sent[1]["legs"]) == 1 + 9 % 4 and channel.sent[1]["ux_level"] == "guided"  # n=9
    await channel.inbound.put(ChannelClosed)
    await task


async def test_everything_is_unsubscribed_when_the_connection_closes(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    index_id = provider.index_id("NIFTY")
    ids = [SELL_CE, BUY_CE, SELL_PE, BUY_PE, index_id]
    assert all(feed.fanout.subscriber_count(i) == 1 for i in ids) and not none_held(provider, ids)
    await channel.inbound.put(ChannelClosed)
    await task
    assert all(feed.fanout.subscriber_count(i) == 0 for i in ids)
    assert none_held(provider, ids)  # the vendor subscription is released with the last watcher


async def test_a_task_cancelled_mid_run_also_unsubscribes(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert none_held(provider, strategy_ids(provider))


async def test_an_unsupported_underlying_gets_the_unsupported_underlying_message(rig):
    """W-129 (REQ-001 AC-1): the strategy socket answers the same catalogue message as the routes, as typed."""
    _provider, _feed, channel, _mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put({"underlying": "BANKNIFTY", "legs": []})
    await channel.inbound.put({"underlying": "nifty", "legs": []})
    await settle()
    assert channel.sent == [render("gate_underlying_unsupported", symbol="BANKNIFTY").as_dict(),
                            render("gate_underlying_unsupported", symbol="nifty").as_dict()]
    await channel.inbound.put(ChannelClosed)
    await task


async def test_bad_input_gets_the_one_catalogue_message_and_the_connection_goes_on(rig):
    provider, feed, channel, mono, push = rig
    good = request(provider)  # built first: the failed subscribe un-subscribes (and so forgets) the replayed quotes
    task = asyncio.create_task(push.run())
    await channel.inbound.put({"underlying": "NIFTY", "legs": []})
    unknown = {**good, "legs": [{**good["legs"][0], "instrument_id": "NSE_FO:1"}] + good["legs"][1:]}  # not in the catalogue
    await channel.inbound.put(unknown)
    await settle()
    assert channel.sent == [ERROR, ERROR] and all(feed.fanout.subscriber_count(i) == 0 for i in strategy_ids(provider))
    await channel.inbound.put(good)
    await settle()
    assert len(channel.sent) == 3 and channel.sent[2] != ERROR and "state" in channel.sent[2]  # answered normally
    await channel.inbound.put(ChannelClosed)
    await task


async def test_no_session_answers_not_connected_once(rig):
    provider, feed, channel, mono, _ = rig
    push = StrategyPush(channel, None, monotonic=mono, poll=0.005)  # get_market_context() is None: no session
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    mono.now += 10
    await settle()
    assert [m["state"] for m in channel.sent] == ["NOT_CONNECTED"]
    await channel.inbound.put(ChannelClosed)
    await task


class FakeSocket:
    def __init__(self, provider, result="session ended", error=None) -> None:
        self.provider, self.result, self.error = provider, result, error
        self.stopped = False

    async def run(self):
        if self.error:
            raise self.error
        if self.result == "session ended":
            self.provider.on_session_ended(VALUATION)
        else:
            while not self.stopped:
                await asyncio.sleep(0.005)
        return self.result

    def stop(self):
        self.stopped = True


async def test_session_ended_makes_the_context_not_live():
    provider, clock, items = new_provider()
    held_replay(provider, clock, items)
    market = live_market.LiveMarket()
    market.attach(provider, FakeSocket(provider), lambda: VALUATION)
    await settle()
    assert market.state == live_market.SESSION_ENDED
    assert provider.status().session_ended is True
    leg = provider.book.get(SELL_CE, VALUATION)
    assert leg.health.value != "available"  # every quote now shows a not-live health (REQ-049 AC-5)
    await market.stop()


async def test_the_live_context_runs_and_stops_with_the_socket():
    provider, clock, _ = new_provider()
    market = live_market.LiveMarket()
    sock = FakeSocket(provider, result="stopped")
    market.attach(provider, sock, lambda: VALUATION)
    live_market.set_current(market)
    try:
        assert market.state == live_market.LIVE and live_market.current_context() is market.feed.ctx
        await market.stop()
        assert sock.stopped is True
    finally:
        live_market.set_current(None)
    assert live_market.current_context() is None and get_market_context() is None


async def test_a_socket_failure_is_logged_by_class_name_only(caplog):
    provider, clock, _ = new_provider()
    market = live_market.LiveMarket()
    market.attach(provider, FakeSocket(provider, error=RuntimeError("wss://x?access_token=SECRET-TOKEN-123")),
                  lambda: VALUATION)
    with caplog.at_level(logging.DEBUG):
        await settle()
    assert market.state == live_market.SESSION_ENDED
    assert "RuntimeError" in caplog.text and "SECRET-TOKEN-123" not in caplog.text
    await market.stop()


class _Conn:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


class _Engine:
    def connect(self):
        return _Conn()


class _Cfg:
    token_key = b"k" * 32
    api_key = "key123"


async def test_start_without_a_stored_session_stays_not_connected(monkeypatch):
    from ofo_app import broker_token_store, db

    async def none(*a, **k):
        return None

    monkeypatch.setattr(db, "get_engine", lambda: _Engine())
    monkeypatch.setattr(broker_token_store, "access_token_for", none)
    market = live_market.LiveMarket()
    await market.start(_Cfg())
    assert market.state == live_market.NOT_CONNECTED and market.context() is None


async def test_start_with_a_session_builds_the_socket_without_logging_the_token(monkeypatch, caplog):
    from ofo_app import broker_token_store, catalogue_store, db, kite_ws

    provider, clock, items = new_provider()
    seen = {}

    async def token(*a, **k):
        return "TOKEN-VALUE-987"

    class Catalogue:
        def all_entries(self):
            from ofo.instruments.catalogue import Catalogue as C
            c = C()
            c.load(items)
            return c.all_entries()

    async def load(conn):
        return Catalogue()

    class Sock(FakeSocket):
        def __init__(self, prov, *, api_key, access_token, clock, base_url, on_reconnect=None):  # noqa: PLR0913 - KiteSocket's keywords
            super().__init__(prov, result="stopped")
            seen.update(api_key=api_key, base_url=base_url, token_given=access_token == "TOKEN-VALUE-987")

    monkeypatch.setattr(db, "get_engine", lambda: _Engine())
    monkeypatch.setattr(broker_token_store, "access_token_for", token)
    monkeypatch.setattr(catalogue_store, "load_catalogue", load)
    monkeypatch.setattr(kite_ws, "KiteSocket", Sock)
    monkeypatch.setenv("DATABASE_URL", DB)
    from ofo_app.config import get_settings
    get_settings.cache_clear()
    market = live_market.LiveMarket()
    with caplog.at_level(logging.DEBUG):
        await market.start(_Cfg())
    assert market.state == live_market.LIVE and seen["token_given"] and seen["api_key"] == "key123"
    assert market.feed.ctx.provider.index_id("NIFTY") is not None
    assert "TOKEN-VALUE-987" not in caplog.text
    await market.stop()
    get_settings.cache_clear()


def test_live_market_is_off_by_default_and_never_on_in_test_with_the_real_kite():
    assert Settings(DATABASE_URL=DB, _env_file=None).LIVE_MARKET is False
    assert not live_market.live_requested()
    with pytest.raises(ValueError, match="not the real Kite"):
        Settings(DATABASE_URL=DB, APP_ENV="test", LIVE_MARKET=True, _env_file=None)
    assert Settings(DATABASE_URL=DB, APP_ENV="test", LIVE_MARKET=True, KITE_WS_URL="ws://127.0.0.1:9",
                    _env_file=None).LIVE_MARKET is True
    assert Settings(DATABASE_URL=DB, APP_ENV="development", LIVE_MARKET=True, _env_file=None).LIVE_MARKET is True
    assert live_market.REAL_KITE_WS == "wss://ws.kite.trade"
    with pytest.raises(live_market.LiveRefused):
        live_market.require_safe("test", "wss://ws.kite.trade")
    live_market.require_safe("test", "ws://127.0.0.1:9")


def test_create_app_refuses_live_market_in_test_env_with_the_real_kite(monkeypatch):
    from ofo_app.main import create_app

    monkeypatch.setenv("LIVE_MARKET", "1")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("KITE_WS_URL", raising=False)
    with pytest.raises(live_market.LiveRefused):
        create_app()


def _load_proof():
    import importlib.util

    path = ROOT / "docs" / "research" / "kite-proof-2026-10-07" / "w065_live_push_proof.py"
    loader_spec = importlib.util.spec_from_file_location("w065_live_push_proof", path)
    mod = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(mod)
    return mod


async def test_the_in_process_proof_code_path_passes_on_the_replay_provider(rig):
    """The orchestrator's live proof script runs this same function (run_core) against the real Kite feed; here it
    runs on the W-064 replay provider and a fake clock, with a tick injected every 0.25 s of fake time."""
    proof = _load_proof()
    provider, feed, _channel, mono, _push = rig
    body = request(provider)
    steps = {"n": 0}

    async def sleep(seconds: float) -> None:
        mono.now += seconds
        steps["n"] += 1
        tick(provider, SELL_CE, f"{100 + steps['n'] % 40}.05")
        await asyncio.sleep(0.03)

    summary = await proof.run_core(feed, lambda _spot: body, monotonic=mono, sleep=sleep, seconds=30,
                                   min_pushes=20, poll=0.005)
    assert summary["pushes"] >= 20, summary
    assert summary["min_gap_s"] >= 1.0, summary  # the 1 s gate holds with a changed tick every 0.25 s
    assert max(summary["distinct_ltp_per_leg"]) > 1 and summary["distinct_unrealized_pnl"] > 1, summary
    assert summary["passed"] is True, summary
    assert none_held(provider, strategy_ids(provider))  # the proof releases everything it subscribed


# ---- phase 2: the door socket route and issue #206 (REST not live when the live inputs are not streaming) ---------------

def _replay_app(monkeypatch):
    from ofo_app.main import create_app

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OUTCOME_REPLAY", "1")
    monkeypatch.delenv("LIVE_MARKET", raising=False)
    return create_app()


def _replay_request() -> dict:
    return {"underlying": "NIFTY", "legs": [
        {"instrument_id": i, "action": a, "lots": 1, "planned_entry": "100.00", "captured_at": VALUATION.isoformat()}
        for i, a in ((SELL_CE, "SELL"), (BUY_CE, "BUY"), (SELL_PE, "SELL"), (BUY_PE, "BUY"))]}


def test_ac4_the_socket_route_pushes_exactly_the_rest_outcome_on_the_replay(monkeypatch):
    """AC-4: a client of the REAL app's /api/strategies/live (APP_ENV=test, OUTCOME_REPLAY) receives, as its first
    push, byte-for-byte the JSON the REST outcome route returns for the same body and the same replay snapshot (one
    engine: both are outcome_response). Bad input on the socket gets the one catalogue message, and the socket goes on."""
    from starlette.testclient import TestClient

    from ofo_app.routes import live

    client = TestClient(_replay_app(monkeypatch))
    body = _replay_request()
    rest = client.post("/api/strategies/outcome", json=body)
    assert rest.status_code == 200 and rest.json()["state"] == "COMPUTED"
    with client.websocket_connect(live.PATH) as ws:
        ws.send_text("not json")
        assert ws.receive_json() == ERROR
        ws.send_json(body)
        pushed = ws.receive_text()
    assert pushed == rest.text  # the same door-minted bytes, not only the same values
    assert len(rest.json()["legs"]) == 4 and all(leg["ltp"] is not None for leg in rest.json()["legs"])


def test_ac4_the_socket_takes_no_credential_in_its_url(monkeypatch):
    """AC-4 / REQ-048 AC-5: the route's path has no parameter and the endpoint never sees the query string; a token
    appended to the URL changes nothing (the same first push) and is never echoed."""
    from starlette.testclient import TestClient

    from ofo_app.routes import live

    client = TestClient(_replay_app(monkeypatch))
    route = next(r for r in client.app.routes if getattr(r, "path", "") == live.PATH)
    assert route.param_convertors == {}
    with client.websocket_connect(live.PATH) as ws:
        ws.send_json(_replay_request())
        plain = ws.receive_text()
    client = TestClient(_replay_app(monkeypatch))  # a fresh replay: the frames do not refill after the first release
    with client.websocket_connect(live.PATH + "?token=SECRETVALUE123") as ws:
        ws.send_json(_replay_request())
        with_token = ws.receive_text()
    assert with_token == plain and "SECRETVALUE123" not in with_token


def test_ac4_the_door_socket_mints_only_its_models_or_a_catalogue_message():
    """AC-4 (door, W-066/W-069): a socket message is EXACTLY a declared ApiModel (emit) or a catalogue message; a dict
    (even a catalogue message's dict), an ApiModel the route did not declare, a free string and bytes are refused."""
    from ofo_app.api_models import DoorRefused
    from ofo_app.errors import ClosedWebSocketRoute, socket_body
    from ofo_app.routes.broker import RefusalOut
    from ofo_app.routes.outcome import OutcomeResponse

    models = (OutcomeResponse,)
    undeclared = RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))
    assert json.loads(bytes(socket_body(render("user_input_request_invalid"), models))) == ERROR
    for bad in ({"state": "COMPUTED"}, "free text", b"{}", undeclared, render("user_input_request_invalid").as_dict()):
        with pytest.raises(DoorRefused):
            socket_body(bad, models)
    with pytest.raises(TypeError):  # a socket route must declare closed message models
        ClosedWebSocketRoute("/x", lambda s: None, message_models=())
    with pytest.raises(TypeError):
        ClosedWebSocketRoute("/x", lambda s: None, message_models=(dict,))


@pytest.fixture
def live_rig():
    """A running-app live market whose feed is the replay provider (no Kite, no database)."""
    provider, clock, items = new_provider()
    held_replay(provider, clock, items)
    market = live_market.LiveMarket()
    market.feed = LiveFeed(MarketContext(provider, lambda: VALUATION, RATE), FanOut(provider))
    live_market.set_current(market)
    yield provider, market.feed
    live_market.set_current(None)


async def _post(body: dict) -> dict:
    from ofo_app.main import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as ac:
        resp = await ac.post("/api/strategies/outcome", json=body)
    assert resp.status_code == 200
    return resp.json()


async def test_206_rest_answers_not_live_while_the_inputs_are_not_streaming(live_rig):
    """AC-4 / issue #206: with live market data on, the REST outcome for a strategy nobody streams (the socket is down)
    is the not-live state: NOT_CONNECTED with REQ-049 AC-5's message (ADR-068 (2) "labelled as not live"), no LTP, no
    table, no frozen bid/ask - never the old missing-index-spot refusal. While a subscriber streams the legs and the
    index the same call is COMPUTED and equals outcome_response; dropping one leg, or the index, makes it not live."""
    from ofo_app.routes.outcome import OutcomeRequest, outcome_response

    provider, feed = live_rig
    body = request(provider)
    ids = [leg["instrument_id"] for leg in body["legs"]]
    index_id = provider.index_id("NIFTY")
    for ux in ("standard", "advanced"):
        out = await _post({**body, "ux_level": ux})
        label = out["status_label"]
        assert out["state"] == "NOT_CONNECTED", out
        assert label.startswith("Live market data disconnected. Last updated: ") and label.endswith(
            ". Live strategy monitoring is paused."), label
        assert [leg["ltp"] for leg in out["legs"]] == [None] * 4 and [leg["label"] for leg in out["legs"]] == [label] * 4
        assert out["table"] is None and out["summary"] is None and "advanced_details" not in out
    handle = feed.fanout.subscribe(lambda _q: None, ids + [index_id])
    try:
        streamed = await _post(body)
        assert streamed["state"] == "COMPUTED"
        assert streamed == outcome_response(OutcomeRequest.model_validate(body), feed.ctx).model_dump(
            mode="json", exclude_unset=True)
    finally:
        feed.fanout.unsubscribe(handle)
    for subset in (ids[:3] + [index_id], ids):  # one leg not streaming; the index not streaming
        partial = feed.fanout.subscribe(lambda _q: None, subset)
        try:
            assert (await _post(body))["state"] == "NOT_CONNECTED"
        finally:
            feed.fanout.unsubscribe(partial)


async def test_206_without_a_live_market_the_rest_route_is_unchanged(rig):
    """AC-4 / #206 negative: no live market running (the replay or a test's own context) -> the provider's quotes are
    used as they are and the answer is COMPUTED; the streaming check applies only to the live market's own context."""
    from ofo_app.main import create_app

    provider, feed, *_ = rig
    assert live_market.current_feed() is None
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: feed.ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        out = (await ac.post("/api/strategies/outcome", json=request(provider))).json()
    assert out["state"] == "COMPUTED"


async def test_206_the_streaming_check_applies_only_to_the_live_markets_own_context(rig, live_rig):
    """AC-4 / #206 negative: a live market IS running with nothing streaming, but the route's context is another one
    (a test's or the replay's own provider) -> that context's quotes are used as they are: COMPUTED, not the not-live
    state. Only the live market's own context is judged by its fan-out's subscriptions."""
    from ofo_app.main import create_app

    provider, feed, *_ = rig
    assert live_market.current_feed() is not None and live_market.current_context() is not feed.ctx
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: feed.ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        out = (await ac.post("/api/strategies/outcome", json=request(provider))).json()
    assert out["state"] == "COMPUTED"



# ---- phase 3: the replay serves every connection, and REST is not live after a socket drop (W-065 frontend) ----------

LIVE_SELL, LIVE_BUY = "NSE_FO:44626", "NSE_FO:44630"  # NIFTY 13-Oct 22850 CE / 22950 CE: used by no other replay test
#: REQ-049 AC-5's text; 09:20:09 is the last recorded frame (09:20:09.879 IST, frames-2026-10-08-092000-10s.bin.gz)
AC5_AFTER_DROP = "Live market data disconnected. Last updated: 09:20:09 AM. Live strategy monitoring is paused."


def _spread_request() -> dict:
    return {"underlying": "NIFTY", "legs": [
        {"instrument_id": i, "action": a, "lots": 1, "planned_entry": "100.00", "captured_at": VALUATION.isoformat()}
        for i, a in ((LIVE_SELL, "SELL"), (LIVE_BUY, "BUY"))]}


def _pnl_cell(push: dict, row_id: str) -> str:
    row = next(r for r in push["table"]["rows"] if r["row_id"] == row_id)
    return row["cells"]["unrealized_pnl"]["display"]


def test_ac4_the_replay_serves_every_connection_and_its_pushes_change(monkeypatch):
    """AC-4 (W-065 phase 3): on the replay, a second connection after the first closed gets prices again (the frames
    used to be spent by the first release), and on each connection the recording plays on, so LTP and Unrealized P&L
    change across pushes, at most one push a second (ADR-068 (2)). The SELL leg's P&L is checked by hand:
    (planned entry 100.00 - LTP) x 65 units (one NIFTY lot)."""
    import time

    from starlette.testclient import TestClient

    from ofo_app.routes import live

    client = TestClient(_replay_app(monkeypatch))
    for _ in range(2):
        pushes, times = [], []
        with client.websocket_connect(live.PATH) as ws:
            ws.send_json(_spread_request())
            for _ in range(4):
                pushes.append(json.loads(ws.receive_text()))
                times.append(time.monotonic())
        assert all(p["state"] == "COMPUTED" and p["output_label"] is None for p in pushes)
        ltps = [p["legs"][0]["ltp"] for p in pushes]
        assert len(set(ltps)) >= 3, ltps  # the recording moves this leg 14 times in 10 s
        assert len({_pnl_cell(p, "1") for p in pushes}) >= 3
        assert all(b - a >= 0.9 for a, b in zip(times, times[1:], strict=False))  # receive-side gap; the server gate is 1.0 s
        for p in pushes:
            expected = (Decimal("100.00") - Decimal(p["legs"][0]["ltp"])) * 65
            assert _pnl_cell(p, "1") == f"₹{expected:,.2f}"


def test_ac4_replay_rest_is_not_live_after_the_socket_drops_and_live_again_while_held(monkeypatch):
    """AC-4 / ADR-077 / REQ-049 AC-5 on the replay: before any socket the REST answer has numbers (REST-only screens keep
    working); after the socket that held the legs closes, REST answers NOT_CONNECTED with AC-5's message and the newest
    price time the replay held (the last recorded frame, 09:20:09), and no numbers; while a socket holds the legs again,
    REST computes. A strategy whose legs no socket ever held is unaffected by another strategy's drop."""
    from starlette.testclient import TestClient

    from ofo_app.routes import live

    client = TestClient(_replay_app(monkeypatch))
    body = _spread_request()
    before = client.post("/api/strategies/outcome", json=body).json()
    assert before["state"] == "COMPUTED" and before["status_label"] is None
    with client.websocket_connect(live.PATH) as ws:
        ws.send_json(body)
        ws.receive_text()
    after = client.post("/api/strategies/outcome", json=body).json()
    assert after["state"] == "NOT_CONNECTED"
    assert after["status_label"] == AC5_AFTER_DROP
    assert after.get("table") is None and after.get("summary") is None
    assert all(leg["ltp"] is None for leg in after["legs"])
    other = client.post("/api/strategies/outcome", json=_replay_request()).json()  # the condor: never held
    assert other["state"] == "COMPUTED"
    with client.websocket_connect(live.PATH) as ws:
        ws.send_json(body)
        ws.receive_text()
        held = client.post("/api/strategies/outcome", json=body).json()
    assert held["state"] == "COMPUTED"


def test_ac4_replay_streaming_counts_holders_and_never_drops_the_index():
    """AC-4 (replay rule, unit): a leg is not streaming only when a socket held it, released it, and none holds it now;
    two holders need two releases; the index always reads as streaming."""
    from ofo_app.replay_mode import ReplayStreaming

    s = ReplayStreaming(ctx=None, index_ids=frozenset({"NSE_INDEX:1001"}))
    assert s("NSE_FO:1") is True  # never held
    s.hold(["NSE_FO:1", "NSE_INDEX:1001"])
    s.hold(["NSE_FO:1"])
    s.release(["NSE_FO:1", "NSE_INDEX:1001"])
    assert s("NSE_FO:1") is True  # one holder left
    s.release(["NSE_FO:1"])
    assert s("NSE_FO:1") is False
    assert s("NSE_INDEX:1001") is True
    s.hold(["NSE_FO:1"])
    assert s("NSE_FO:1") is True


def test_ac5_two_holders_this_pages_socket_dropped_the_fallback_is_not_live(monkeypatch):
    """REQ-049 AC-5 / ADR-077 (W-065 p3 r2): a second socket (another tab, another user) holds the same legs while THIS
    page's socket drops. The REST refresh the page sends as its fallback (fallback=true) is the not-live answer: AC-5's
    exact text with the newest price time kept (09:20:09), no table, no summary, no leg numbers. The same request without
    the flag (or false) is unchanged (COMPUTED)."""
    from starlette.testclient import TestClient

    from ofo_app.routes import live

    client = TestClient(_replay_app(monkeypatch))
    body = _spread_request()
    with client.websocket_connect(live.PATH) as other:
        other.send_json(body)
        other.receive_text()
        with client.websocket_connect(live.PATH) as mine:
            mine.send_json(body)
            mine.receive_text()
        fallback = client.post("/api/strategies/outcome", json={**body, "fallback": True}).json()
        assert fallback["state"] == "NOT_CONNECTED"
        assert fallback["status_label"] == AC5_AFTER_DROP
        assert fallback.get("table") is None and fallback.get("summary") is None
        assert all(leg["ltp"] is None and leg["label"] == AC5_AFTER_DROP for leg in fallback["legs"])
        plain = client.post("/api/strategies/outcome", json=body).json()
        assert plain["state"] == "COMPUTED" and plain["table"] is not None
        assert client.post("/api/strategies/outcome", json={**body, "fallback": False}).json()["state"] == "COMPUTED"
    refused = client.post("/api/strategies/outcome", json={**body, "fallback": "maybe"}).json()
    assert refused.get("state") != "COMPUTED"  # a non-boolean flag never yields numbers (fail closed)


def test_ac5_fallback_without_a_market_context_is_the_draft_answer_not_numbers():
    from ofo_app.routes.outcome import OutcomeRequest, outcome_response

    import datetime

    fixed = lambda: datetime.datetime(2026, 10, 16, 3, 50, 5, tzinfo=datetime.timezone.utc)  # noqa: E731 - the answer clock
    plain = outcome_response(OutcomeRequest.model_validate(_spread_request()), None, now=fixed).model_dump(
        mode="json", exclude_unset=True)
    flagged = outcome_response(OutcomeRequest.model_validate({**_spread_request(), "fallback": True}), None,
                               now=fixed).model_dump(mode="json", exclude_unset=True)
    assert flagged == plain and flagged["state"] != "COMPUTED"
