"""REQ-114 AC-7 / ADR-015 on the index answer (chunk 1 Tier A review round 2, class live-wording-on-a-closed-market):
the REAL index answer (``indices_answer``, behind the REST read and the socket push) on the REAL KiteProvider fed the
recorded full frame and then a heartbeat every second is never ``LIVE`` while the market is closed, even when the
page's own socket holds the indices (``live=True``). The market state comes from the one market-state function
(``market_closed_for`` through ``market_state``); the expected open/closed answers come from the ADR-119 calendar:
Saturday 2026-10-24 and the 2026-10-20 holiday closed, Wednesday 2026-10-21 10:00 open, 2031 past the calendar's data
(fail closed). No database.

Answer states (standing item d): open -> LIVE with the quote's own health; closed (weekend, holiday, after hours) ->
NOT_CONNECTED, market_closed true, no value, each row's last value time kept; date past the calendar -> as closed."""
from __future__ import annotations

import asyncio
import datetime
import pathlib
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app.index_push import IndexPush, indices_answer
from ofo_app.live_push import ChannelClosed
from ofo_app.main import create_app
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


@pytest.mark.parametrize("start", [SATURDAY, HOLIDAY, AFTER_HOURS, PAST_CALENDAR],
                         ids=["saturday", "holiday", "after-hours", "past-calendar"])
def test_closed_market_index_answer_is_never_live(start):
    """AC-7: closed market, socket holding the indices (live=True), heartbeats: state NOT_CONNECTED, market_closed
    true, no value shown, no health word."""
    body = _answer(start)
    assert body.market_closed is True
    assert body.state == "NOT_CONNECTED"
    assert [r.value for r in body.indices] == [None, None]
    assert [r.health for r in body.indices] == [None, None]


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
