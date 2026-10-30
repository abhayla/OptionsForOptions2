"""W-114 (REQ-072 AC-2; REQ-049 AC-2/AC-4; ADR-077): the read-only index push and the index REST read.

The push-class and REST-function tests run on a fake provider behind the REAL shared ``FanOut`` and a fake channel
minted by the door's ``socket_body``: no database, no server, no Kite. The app-route test at the end uses the real app
on the test replay (APP_ENV=test, OUTCOME_REPLAY) in-process, with no lifespan and so no database.

Expected values come from the inputs the tests write (the fake quote's price, time and health), never from the code's
own output: a pushed ``value`` is the quote's price as a 2-decimal string, ``at`` its time, ``health`` its health.
"""
from __future__ import annotations

import asyncio
import datetime
import json
from decimal import Decimal

import pytest
from ofo.errors import render
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app.errors import socket_body
from ofo_app.index_push import IndexPush, IndicesOut
from ofo_app.live_push import ChannelClosed, LiveFeed
from ofo_app.main import create_app
from ofo_app.routes import indices
from ofo_app.routes.indices import indices_read
from ofo_app.routes.outcome import MarketContext
from starlette.testclient import TestClient

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 19, 9, 20, 0, tzinfo=IST)
NIFTY_ID, SENSEX_ID = "NSE_INDEX:256265", "BSE_INDEX:265"
ONE, TWO = 1, 2  # push counts
HTTP_OK = 200
ERROR = render("user_input_request_invalid").as_dict()


def quote(instrument_id: str, underlying: str, ltp: str, at: datetime.datetime,
          health: DataHealth = DataHealth.AVAILABLE) -> NormalizedQuote:
    exchange = instrument_id.split("_", maxsplit=1)[0]
    return NormalizedQuote(instrument_id, underlying, exchange, "INDICES", None, None, None, Decimal(ltp),
                           None, None, None, None, None, None, None, None, None, None, at,
                           SourceMetadata("fake", "fake-feed"), health)


class FakeProvider:
    """The provider methods the fan-out and the push use; records every vendor subscribe / unsubscribe."""

    def __init__(self, ids: dict[str, str | None]) -> None:
        self.ids = ids
        self.quotes: dict[str, NormalizedQuote] = {}
        self.vendor_subscribed: set[str] = set()
        self.subscribe_calls = 0
        self._listener = None

    def live_quote_stream(self, listener) -> None:
        self._listener = listener

    def subscribe(self, ids) -> None:
        self.subscribe_calls += 1
        self.vendor_subscribed.update(ids)

    def unsubscribe(self, ids) -> None:
        self.vendor_subscribed.difference_update(ids)

    def index_id(self, underlying: str) -> str | None:
        return self.ids.get(underlying)

    def underlying_quote(self, underlying: str) -> NormalizedQuote | None:
        instrument_id = self.ids.get(underlying)
        return None if instrument_id is None else self.quotes.get(instrument_id)

    def tick(self, q: NormalizedQuote) -> None:
        self.quotes[q.instrument_id] = q
        if self._listener is not None:
            self._listener(q)


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
        """Minted exactly as the app's door socket mints it, then read back as JSON."""
        self.sent.append(json.loads(bytes(socket_body(source, (IndicesOut,)))))


class Mono:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Wall:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime.datetime:
        return self.now


def make_rig(ids: dict[str, str | None] | None = None):
    provider = FakeProvider({"NIFTY": NIFTY_ID, "SENSEX": SENSEX_ID} if ids is None else ids)
    wall = Wall()
    feed = LiveFeed(MarketContext(provider, wall, Decimal("0.065")), FanOut(provider))
    channel, mono = FakeChannel(), Mono()
    push = IndexPush(channel, feed, monotonic=mono, now=wall, poll=0.005)
    return provider, feed, channel, mono, push


async def settle(n: int = 6) -> None:
    for _ in range(n):
        await asyncio.sleep(0.01)


def both(provider, nifty: str, sensex: str, at: datetime.datetime, health: DataHealth = DataHealth.AVAILABLE) -> None:
    provider.tick(quote(NIFTY_ID, "NIFTY", nifty, at, health))
    provider.tick(quote(SENSEX_ID, "SENSEX", sensex, at, health))


def rows(message: dict) -> dict[str, dict]:
    return {r["underlying"]: r for r in message["indices"]}


async def close(channel, task) -> None:
    await channel.inbound.put(ChannelClosed)
    await task


async def test_ac2_core_two_pushes_with_changing_timestamps_for_both_indices():
    """AC-2 (core proof): two index quote changes for both indices, one second apart, reach the channel as two pushes,
    each with the quotes' own values, times and health, NIFTY then SENSEX, state LIVE."""
    provider, _feed, channel, mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(push.run())
    await settle()
    t1 = T0 + datetime.timedelta(seconds=1)
    both(provider, "25146.00", "82012.75", t1)
    mono.now += 1.0
    await settle()
    await close(channel, task)
    assert len(channel.sent) == TWO
    first, second = channel.sent
    assert [r["underlying"] for r in first["indices"]] == ["NIFTY", "SENSEX"]
    assert first["state"] == second["state"] == "LIVE"
    assert rows(first)["NIFTY"] == {"underlying": "NIFTY", "instrument_id": NIFTY_ID, "value": "25145.50",
                                    "at": T0.isoformat(), "health": "available"}
    assert rows(first)["SENSEX"]["value"] == "82010.25" and rows(first)["SENSEX"]["at"] == T0.isoformat()
    assert rows(second)["NIFTY"]["value"] == "25146.00" and rows(second)["NIFTY"]["at"] == t1.isoformat()
    assert rows(second)["SENSEX"]["value"] == "82012.75" and rows(second)["SENSEX"]["at"] == t1.isoformat()


@pytest.mark.parametrize("health", list(DataHealth))
async def test_ac2_each_row_carries_the_quotes_own_health(health):
    """AC-2: each of the five health states (available, stale, delayed, unhealthy, unavailable) reaches the row as the
    quote gave it, never upgraded."""
    provider, _feed, channel, _mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0, health)
    task = asyncio.create_task(push.run())
    await settle()
    await close(channel, task)
    assert [r["health"] for r in channel.sent[0]["indices"]] == [health.value, health.value]


async def test_ac2_a_health_change_alone_is_pushed():
    """AC-2: the feed going stale with no new tick (same price, same time) still changes the row: pushed after 1 s."""
    provider, _feed, channel, mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(push.run())
    await settle()
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, "NIFTY", "25145.50", T0, DataHealth.STALE)  # no tick
    mono.now += 1.0
    await settle()
    await close(channel, task)
    assert len(channel.sent) == TWO
    assert rows(channel.sent[1])["NIFTY"]["health"] == "stale" and rows(channel.sent[1])["NIFTY"]["value"] == "25145.50"


async def test_ac2_at_most_one_push_a_second():
    """AC-2: two changes 0.2 s apart give one push (the first, at once); after 1 s the second change goes out."""
    provider, _feed, channel, mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(push.run())
    await settle()
    assert len(channel.sent) == ONE
    mono.now += 0.2
    both(provider, "25150.00", "82020.00", T0 + datetime.timedelta(milliseconds=200))
    await settle()
    assert len(channel.sent) == ONE
    mono.now += 0.8
    await settle()
    await close(channel, task)
    assert len(channel.sent) == TWO and rows(channel.sent[1])["NIFTY"]["value"] == "25150.00"


async def test_ac2_no_change_no_push():
    """AC-2: with nothing changed, 30 s of polling sends nothing after the first push."""
    provider, _feed, channel, mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(push.run())
    await settle()
    mono.now += 30
    await settle()
    await close(channel, task)
    assert len(channel.sent) == ONE


async def test_ac2_the_subscription_is_released_on_close():
    """AC-2: while open, the socket holds both index ids on the ONE shared fan-out (one vendor subscribe); after the
    connection ends the subscriber count is 0 for both and the vendor subscription is gone."""
    provider, feed, channel, _mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(push.run())
    await settle()
    assert feed.fanout.subscriber_count(NIFTY_ID) == ONE and feed.fanout.subscriber_count(SENSEX_ID) == ONE
    assert provider.subscribe_calls == ONE
    await close(channel, task)
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0 and feed.fanout.subscriber_count(SENSEX_ID) == 0
    assert provider.vendor_subscribed == set()


async def test_ac2_the_subscription_is_released_when_the_send_fails():
    """AC-2: a send that fails (the browser went away mid-send) still releases the subscription."""
    provider, feed, channel, _mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)

    async def broken(_source) -> None:
        raise ChannelClosed()

    channel.send = broken
    with pytest.raises(ChannelClosed):
        await push.run()
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0 and feed.fanout.subscriber_count(SENSEX_ID) == 0


async def test_ac2_a_client_message_gets_the_catalogue_error_and_changes_nothing():
    """AC-2: anything the client sends is answered with the one catalogue message; the subscription and the pushes are
    unchanged (no extra push, still one holder per index)."""
    provider, feed, channel, _mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(push.run())
    await settle()
    for message in ({"underlying": "SENSEX"}, {"fallback": True}, "x"):
        await channel.inbound.put(message)
        await settle()
    assert channel.sent[1:] == [ERROR, ERROR, ERROR]
    assert push.pushes == ONE and provider.subscribe_calls == ONE
    assert feed.fanout.subscriber_count(NIFTY_ID) == ONE and feed.fanout.subscriber_count(SENSEX_ID) == ONE
    await close(channel, task)


async def test_ac2_sensex_unknown_to_the_catalogue_is_unavailable_and_nifty_stays_live():
    """AC-2: index_id('SENSEX') is None: the SENSEX row is unavailable with no number; NIFTY is live and only NIFTY is
    subscribed."""
    provider, _feed, channel, _mono, push = make_rig({"NIFTY": NIFTY_ID, "SENSEX": None})
    provider.tick(quote(NIFTY_ID, "NIFTY", "25145.50", T0))
    task = asyncio.create_task(push.run())
    await settle()
    assert provider.vendor_subscribed == {NIFTY_ID}
    await close(channel, task)
    message = channel.sent[0]
    assert message["state"] == "LIVE"
    assert rows(message)["SENSEX"] == {"underlying": "SENSEX", "instrument_id": None, "value": None, "at": None,
                                       "health": "unavailable"}
    assert rows(message)["NIFTY"]["value"] == "25145.50" and rows(message)["NIFTY"]["health"] == "available"


async def test_ac2_no_feed_socket_says_not_connected_with_null_values():
    """AC-2 / REQ-049 AC-4: no live feed: one NOT_CONNECTED message, every value, time and health null."""
    channel, mono, wall = FakeChannel(), Mono(), Wall()
    push = IndexPush(channel, None, monotonic=mono, now=wall, poll=0.005)
    task = asyncio.create_task(push.run())
    await settle()
    mono.now += 5
    await settle()
    await close(channel, task)
    assert len(channel.sent) == ONE
    assert channel.sent[0]["state"] == "NOT_CONNECTED"
    assert all(r["value"] is None and r["at"] is None and r["health"] is None for r in channel.sent[0]["indices"])


# ---- the REST read (the function the route returns), no server -------------------------------------------------------

class Held:
    """The live market's streaming predicate (subscriber on the shared fan-out), owned by the rig's context."""

    def __init__(self, feed: LiveFeed) -> None:
        self.ctx = feed.ctx
        self._fanout = feed.fanout

    def __call__(self, instrument_id: str) -> bool:
        return self._fanout.subscriber_count(instrument_id) > 0


async def test_ac2_fallback_is_not_live_while_another_socket_holds_the_indices():
    """AC-2 / ADR-077 (finding liveness-from-shared-subscribers): a SECOND socket holds both indices on the shared
    fan-out; this page's fallback read answers NOT_CONNECTED with each index's last value time and no number. The
    control (no fallback) on the same state is LIVE, so the flag, not the holder count, decides."""
    provider, feed, channel, _mono, other = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(other.run())
    await settle()
    assert feed.fanout.subscriber_count(NIFTY_ID) == ONE
    down = indices_read(feed.ctx, Held(feed), fallback=True, now=Wall())
    control = indices_read(feed.ctx, Held(feed), fallback=False, now=Wall())
    await close(channel, task)
    assert down.state == "NOT_CONNECTED"
    assert [(r.value, r.at, r.health) for r in down.indices] == [(None, T0, None), (None, T0, None)]
    assert control.state == "LIVE" and [r.value for r in control.indices] == [Decimal("25145.50"), Decimal("82010.25")]


async def test_ac2_rest_is_not_live_when_no_socket_holds_the_indices():
    """AC-2 / issue #206: on the live feed with no holder, the first-paint read is NOT_CONNECTED (no number as live)."""
    provider, feed, _channel, _mono, _push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    answer = indices_read(feed.ctx, Held(feed), fallback=False, now=Wall())
    assert answer.state == "NOT_CONNECTED" and all(r.value is None for r in answer.indices)


def test_ac2_rest_with_no_feed_is_not_connected_with_null_values():
    """AC-2: no live feed at all: NOT_CONNECTED, values and times null, answered at the server clock."""
    wall = Wall()
    answer = indices_read(None, None, fallback=False, now=wall)
    assert answer.state == "NOT_CONNECTED" and answer.answered_at == T0
    assert [(r.underlying, r.value, r.at, r.health) for r in answer.indices] == [
        ("NIFTY", None, None, None), ("SENSEX", None, None, None)]


# ---- the plain first-paint read on a COLD feed (issue #612): the read holds the index ids itself ---------------------

class ColdProvider(FakeProvider):
    """Quotes exist at the vendor but only arrive once the ids are subscribed (the live cold case, 30 Oct 12:20)."""

    def __init__(self, ids, pending: list[NormalizedQuote], connected: bool = True) -> None:
        super().__init__(ids)
        self.pending = pending
        self.connected = connected

    def status(self):
        return type("Status", (), {"connected": self.connected})()

    def subscribe(self, ids) -> None:
        super().subscribe(ids)
        for q in self.pending:
            if q.instrument_id in ids:
                self.tick(q)


def cold_rig(pending_ids=(NIFTY_ID, SENSEX_ID), connected: bool = True, ids=None):
    quotes = {NIFTY_ID: quote(NIFTY_ID, "NIFTY", "25145.50", T0), SENSEX_ID: quote(SENSEX_ID, "SENSEX", "82010.25", T0)}
    provider = ColdProvider({"NIFTY": NIFTY_ID, "SENSEX": SENSEX_ID} if ids is None else ids,
                            [quotes[i] for i in pending_ids], connected)
    wall = Wall()
    feed = LiveFeed(MarketContext(provider, wall, Decimal("0.065")), FanOut(provider))
    return provider, feed, wall


async def first_paint(feed, wall, *, fallback=False, wait=0.3):
    return await indices.indices_first_paint(feed.ctx, Held(feed), feed, fallback=fallback, now=wall, wait=wait)


async def test_cold_plain_read_holds_the_index_ids_and_answers_live_with_both_values():
    """#612 core: no socket holds the indices, quotes only arrive once subscribed: the plain read is LIVE with both
    values, and the hold is released after the answer."""
    provider, feed, wall = cold_rig()
    answer = await first_paint(feed, wall)
    assert answer.state == "LIVE"
    assert [r.value for r in answer.indices] == [Decimal("25145.50"), Decimal("82010.25")]
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0 and provider.vendor_subscribed == set()


async def test_cold_plain_read_with_one_index_priced_by_the_deadline_is_live_with_the_other_unavailable():
    """Only NIFTY arrives: the read waits out the deadline, then answers what it has (LIVE, SENSEX unavailable, null)."""
    provider, feed, wall = cold_rig(pending_ids=(NIFTY_ID,))
    answer = await first_paint(feed, wall, wait=0.1)
    assert answer.state == "LIVE"
    assert [(r.underlying, r.value, r.health) for r in answer.indices] == [
        ("NIFTY", Decimal("25145.50"), "available"), ("SENSEX", None, "unavailable")]
    assert provider.vendor_subscribed == set()


async def test_cold_plain_read_with_the_provider_disconnected_stays_not_connected():
    provider, feed, wall = cold_rig(pending_ids=(), connected=False)
    answer = await first_paint(feed, wall)
    assert answer.state == "NOT_CONNECTED" and all(r.value is None for r in answer.indices)
    assert provider.vendor_subscribed == set()


async def test_cold_read_without_a_feed_is_unchanged_not_connected():
    wall = Wall()
    answer = await indices.indices_first_paint(None, None, None, fallback=False, now=wall)
    assert answer.state == "NOT_CONNECTED" and all(r.value is None for r in answer.indices)


async def test_a_streaming_socket_means_no_extra_hold():
    """A socket already holds the indices: LIVE as today, and the read subscribes nothing itself."""
    provider, feed, channel, _mono, push = make_rig()
    both(provider, "25145.50", "82010.25", T0)
    task = asyncio.create_task(push.run())
    await settle()
    calls = provider.subscribe_calls
    answer = await first_paint(feed, Wall())
    await close(channel, task)
    assert answer.state == "LIVE" and provider.subscribe_calls == calls


async def test_cold_plain_read_in_a_closed_market_holds_nothing():
    provider, feed, wall = cold_rig()
    wall.now = datetime.datetime(2026, 10, 17, 11, 0, tzinfo=IST)  # a Saturday
    answer = await first_paint(feed, wall)
    assert answer.state == "NOT_CONNECTED" and answer.market_closed is True
    assert provider.subscribe_calls == 0


async def test_cold_fallback_read_stays_not_connected_and_holds_nothing():
    """ADR-077: fallback=true is never live, and the read does not hold the indices for it."""
    provider, feed, wall = cold_rig()
    answer = await first_paint(feed, wall, fallback=True)
    assert answer.state == "NOT_CONNECTED" and all(r.value is None for r in answer.indices)
    assert provider.subscribe_calls == 0


async def test_cold_plain_read_with_an_unknown_index_id_answers_as_today():
    """The catalogue does not know SENSEX: nothing to subscribe for it; NIFTY is held and LIVE, SENSEX unavailable."""
    provider, feed, wall = cold_rig(ids={"NIFTY": NIFTY_ID, "SENSEX": None})
    answer = await first_paint(feed, wall, wait=0.1)
    assert answer.state == "LIVE"
    assert [(r.underlying, r.value) for r in answer.indices] == [("NIFTY", Decimal("25145.50")), ("SENSEX", None)]


async def test_cold_plain_read_when_the_fanout_refuses_the_ids_answers_as_today():
    provider, feed, wall = cold_rig()

    def refuse(*_a, **_k):
        raise KeyError("no token")
    feed.fanout.subscribe = refuse
    answer = await first_paint(feed, wall)
    assert answer.state == "NOT_CONNECTED" and all(r.value is None for r in answer.indices)


# ---- the real app on the test replay (in-process, no lifespan, no database) ------------------------------------------

def _replay_app(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OUTCOME_REPLAY", "1")
    monkeypatch.delenv("LIVE_MARKET", raising=False)
    return create_app()


def test_ac2_the_app_socket_and_rest_serve_the_replay_indices(monkeypatch):
    """AC-2: the real app's door socket /api/market/indices/live on the replay pushes LIVE rows for NIFTY and SENSEX
    with the recording's health and an aware time; a client message gets the catalogue error; REST with fallback=true
    is NOT_CONNECTED with no number."""
    client = TestClient(_replay_app(monkeypatch))
    with client.websocket_connect(indices.PATH) as ws:
        first = ws.receive_json()
        ws.send_json({"x": 1})
        assert ws.receive_json() == ERROR
    assert first["state"] == "LIVE" and [r["underlying"] for r in first["indices"]] == ["NIFTY", "SENSEX"]
    for row in first["indices"]:
        assert row["instrument_id"] is not None and row["health"] in {h.value for h in DataHealth}
        assert row["at"] is not None and datetime.datetime.fromisoformat(row["at"]).tzinfo is not None
    down = client.get(indices.REST_PATH, params={"fallback": "true"})
    assert down.status_code == HTTP_OK and down.json()["state"] == "NOT_CONNECTED"
    assert all(r["value"] is None for r in down.json()["indices"])
