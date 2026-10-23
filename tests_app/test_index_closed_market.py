"""REQ-114 AC-7 / ADR-015 on the index answer (chunk 1 Tier A review round 2, class live-wording-on-a-closed-market):
the REAL index answer (``indices_answer``, behind the REST read and the socket push) on the REAL KiteProvider fed the
recorded full frame and then a heartbeat every second is never ``LIVE`` while the market is closed, even when the
page's own socket holds the indices (``live=True``). The market state comes from the one market-state function
(``market_closed_for`` through ``market_state``); the expected open/closed answers come from the ADR-119 calendar:
Saturday 2026-10-24 and the 2026-10-20 holiday closed, Wednesday 2026-10-21 10:00 open, 2031 past the calendar's data
(fail closed). No database.

Answer states (standing item d): open -> LIVE with the quote's own health; closed (weekend, holiday, after hours) ->
NOT_CONNECTED, market_closed true, each row's last value and time kept, health stale (never available); not held
-> no value; date past the calendar -> as closed."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import pathlib
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.rules.inputs import DataHealth
from ofo_app.index_push import IndexPush, indices_answer
from ofo_app.live_push import ChannelClosed
from ofo_app.main import create_app
from ofo_app.replay_mode import _load_recording
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context, get_streaming

FIX = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
FRAME = (FIX / "full-frame-12080386-150720.bin").read_bytes()
LEG = "NSE_FO:47189"  # the contract in the recorded full frame
SATURDAY = datetime.datetime(2026, 10, 24, 10, 0, tzinfo=IST)
WEDNESDAY = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)
HOLIDAY = datetime.datetime(2026, 10, 20, 10, 0, tzinfo=IST)  # ADR-119 calendar: a trading holiday (Tuesday)
AFTER_HOURS = datetime.datetime(2026, 10, 21, 16, 0, tzinfo=IST)
PAST_CALENDAR = datetime.datetime(2031, 3, 5, 10, 0, tzinfo=IST)  # past the calendar's data: fail closed


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now


def _fed(start: datetime.datetime) -> tuple[KiteProvider, Clock]:
    clock = Clock(start)
    provider = KiteProvider(list(parse_instruments_csv(FIX / "instruments-2026-10-08-subscribed.csv")), clock=clock)
    provider.subscribe([LEG])
    provider.on_connected(start)
    provider.on_frame(FRAME, start + datetime.timedelta(seconds=1))
    for second in range(2, 300):  # heartbeats: the socket is up, no new price
        provider.on_frame(b"\x00", start + datetime.timedelta(seconds=second))
    clock.now = start + datetime.timedelta(seconds=299, milliseconds=500)
    return provider, clock


def _answer(start: datetime.datetime):
    provider, clock = _fed(start)
    return indices_answer(MarketContext(provider, clock, Decimal("0.065")), live=True, now=clock)


def _index_fed(start: datetime.datetime) -> tuple[KiteProvider, Clock]:
    """The REAL 2026-10-08 recording (NIFTY index token 256265 = NSE_INDEX:1001 among its frames), its receive times
    moved to ``start``, then a heartbeat a second for 5 minutes: the socket is up and no new price arrives."""
    items, frames = _load_recording()
    clock = Clock(start)
    provider = KiteProvider(items, clock=clock)
    provider.subscribe([i for i in (provider.index_id(u) for u in ("NIFTY", "SENSEX")) if i is not None])
    first = frames[0][0]
    provider.on_connected(start)
    for at, frame in frames:
        provider.on_frame(frame, start + (at - first))
    for second in range(11, 300):
        provider.on_frame(b"\x00", start + datetime.timedelta(seconds=second))
    clock.now = start + datetime.timedelta(seconds=299, milliseconds=500)
    return provider, clock


#: NIFTY's last price in the recording (its last frame, exchange time 2026-10-08 09:20:09 IST), read from the
#: recording itself, not from the answer under test
NIFTY_LAST = Decimal("22533.25")
NIFTY_AT = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)


@pytest.mark.parametrize("start", [SATURDAY, HOLIDAY, AFTER_HOURS, PAST_CALENDAR],
                         ids=["saturday", "holiday", "after-hours", "past-calendar"])
def test_closed_market_index_answer_is_never_live_and_keeps_the_last_value_as_stale(start):
    """AC-7 / REQ-072 AC-2: closed market, socket holding the indices (live=True), real index frames then heartbeats:
    state NOT_CONNECTED (never LIVE), market_closed true, NIFTY keeps its last value and time, labelled stale."""
    provider, clock = _index_fed(start)
    body = indices_answer(MarketContext(provider, clock, Decimal("0.065")), live=True, now=clock)
    assert (body.state, body.market_closed) == ("NOT_CONNECTED", True)
    nifty = body.indices[0]
    assert (nifty.underlying, nifty.value, nifty.at, nifty.health) == ("NIFTY", NIFTY_LAST, NIFTY_AT, "stale")


def test_open_market_index_answer_with_real_frames_is_live_and_available():
    """AC-7 negative case: Wednesday 10:00 IST, same real frames: LIVE, NIFTY's value available."""
    provider, clock = _index_fed(WEDNESDAY)
    body = indices_answer(MarketContext(provider, clock, Decimal("0.065")), live=True, now=clock)
    assert (body.state, body.market_closed) == ("LIVE", False)
    assert (body.indices[0].value, body.indices[0].health) == (NIFTY_LAST, "available")


def test_closed_market_not_held_shows_no_value():
    """REQ-049 AC-4: closed market and the page's socket not holding the indices: no value, last value time only."""
    provider, clock = _index_fed(SATURDAY)
    body = indices_answer(MarketContext(provider, clock, Decimal("0.065")), live=False, now=clock)
    assert body.state == "NOT_CONNECTED"
    assert (body.indices[0].value, body.indices[0].at, body.indices[0].health) == (None, NIFTY_AT, None)


class _NoFeedProvider:
    """A provider with no feed state whose quote reads available (a fake, the bus relay): the calendar decides."""

    def __init__(self, provider: KiteProvider) -> None:
        self._p = provider

    def index_id(self, underlying: str):
        return self._p.index_id(underlying)

    def underlying_quote(self, underlying: str):
        quote = self._p.underlying_quote(underlying)
        return None if quote is None else dataclasses.replace(quote, health=DataHealth.AVAILABLE)


def test_closed_market_never_labels_a_value_available():
    """AC-7 fail closed: on a closed market a quote that reads available is labelled stale, never available."""
    provider, clock = _index_fed(SATURDAY)
    body = indices_answer(MarketContext(_NoFeedProvider(provider), clock, Decimal("0.065")), live=True, now=clock)
    assert (body.state, body.market_closed) == ("NOT_CONNECTED", True)
    assert (body.indices[0].value, body.indices[0].health) == (NIFTY_LAST, "stale")


def test_open_market_index_answer_stays_live():
    """AC-7 negative case: Wednesday 10:00 IST, same frames, live=True: LIVE, market_closed false."""
    body = _answer(WEDNESDAY)
    assert body.market_closed is False
    assert body.state == "LIVE"


def test_open_market_not_held_is_not_live():
    """AC-7: an open market whose page socket does not hold the indices stays NOT_CONNECTED (unchanged)."""
    provider, clock = _fed(WEDNESDAY)
    body = indices_answer(MarketContext(provider, clock, Decimal("0.065")), live=False, now=clock)
    assert (body.state, body.market_closed) == ("NOT_CONNECTED", False)


async def _rest(start: datetime.datetime) -> dict:
    provider, clock = _fed(start)
    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: clock
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, clock, Decimal("0.065"))
    app.dependency_overrides[get_streaming] = lambda: None  # a test's own context: held (live) on an open market
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/market/indices")
    assert r.status_code == HTTPStatus.OK, r.text
    return r.json()


@pytest.mark.asyncio
async def test_rest_route_on_saturday_is_not_live_and_on_wednesday_is_live():
    """AC-7 through the route: Saturday NOT_CONNECTED + market_closed; Wednesday LIVE."""
    sat = await _rest(SATURDAY)
    assert (sat["state"], sat["market_closed"]) == ("NOT_CONNECTED", True)
    wed = await _rest(WEDNESDAY)
    assert (wed["state"], wed["market_closed"]) == ("LIVE", False)


class _Channel:
    """One socket: records what is sent, closes after the first push."""

    def __init__(self) -> None:
        self.sent: list = []
        self._closed = asyncio.Event()

    async def send(self, body) -> None:
        self.sent.append(body)
        self._closed.set()

    async def receive(self):
        await self._closed.wait()
        raise ChannelClosed()


class _Fanout:
    def subscribe(self, _listener, _ids) -> int:
        return 1

    def unsubscribe(self, _handle) -> None:
        pass

    def pump_one(self, _handle) -> None:
        pass


class _Feed:
    def __init__(self, ctx: MarketContext) -> None:
        self.ctx = ctx
        self.fanout = _Fanout()


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "state"), [(SATURDAY, "NOT_CONNECTED"), (WEDNESDAY, "LIVE")],
                         ids=["saturday", "wednesday"])
async def test_socket_push_follows_the_market_state(start, state):
    """AC-7 through the socket: the subscribed push on Saturday is NOT_CONNECTED, on Wednesday LIVE."""
    provider, clock = _fed(start)
    channel = _Channel()
    push = IndexPush(channel, _Feed(MarketContext(provider, clock, Decimal("0.065"))), monotonic=lambda: 0.0,
                     now=clock, poll=0.01)
    await asyncio.wait_for(push.run(), timeout=5)
    assert [b.state for b in channel.sent] == [state]
