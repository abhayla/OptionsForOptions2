"""W-065 (REQ-035 AC-4; ADR-068; REQ-048 AC-4): the live strategy push and the live market context, on the W-064 replay
provider and a fake clock. No Kite connection, no database. The platform WebSocket route itself is NOT registered by
this item (the W-024 guard tests refuse a websocket route outside the error boundary; see the work item's next_action),
so these tests drive :class:`StrategyPush` through its two-method channel.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import new_provider, replay  # noqa: E402

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

    async def send(self, body: dict) -> None:
        self.sent.append(body)


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


@pytest.fixture
def rig():
    provider, clock, _items = new_provider()
    replay(provider, clock)  # the recorded 2026-10-08 frames; nothing subscribed yet
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
    assert len(channel.sent) == 2 and len(channel.sent[1]["legs"]) == 1  # answered at once, not after a second
    assert feed.fanout.subscriber_count(BUY_PE) == 0 and feed.fanout.subscriber_count(SELL_CE) == 1
    await channel.inbound.put(ChannelClosed)
    await task


async def test_everything_is_unsubscribed_when_the_connection_closes(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    index_id = provider.index_id("NIFTY")
    ids = [SELL_CE, BUY_CE, SELL_PE, BUY_PE, index_id]
    assert all(feed.fanout.subscriber_count(i) == 1 for i in ids) and len(provider.subscribed_tokens()) == 5
    await channel.inbound.put(ChannelClosed)
    await task
    assert all(feed.fanout.subscriber_count(i) == 0 for i in ids)
    assert provider.subscribed_tokens() == []  # the vendor subscription is released with the last watcher


async def test_a_task_cancelled_mid_run_also_unsubscribes(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.subscribed_tokens() == []


async def test_bad_input_gets_the_one_catalogue_message_and_the_connection_goes_on(rig):
    provider, feed, channel, mono, push = rig
    good = request(provider)  # built first: the failed subscribe un-subscribes (and so forgets) the replayed quotes
    task = asyncio.create_task(push.run())
    await channel.inbound.put({"underlying": "NIFTY", "legs": []})
    unknown = {**good, "legs": [{**good["legs"][0], "instrument_id": "NSE_FO:1"}] + good["legs"][1:]}  # not in the catalogue
    await channel.inbound.put(unknown)
    await settle()
    assert channel.sent == [ERROR, ERROR] and provider.subscribed_tokens() == []
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
    provider, clock, _ = new_provider()
    replay(provider, clock)
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
        def __init__(self, prov, *, api_key, access_token, clock, base_url):
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
    assert provider.subscribed_tokens() == []  # the proof releases everything it subscribed
