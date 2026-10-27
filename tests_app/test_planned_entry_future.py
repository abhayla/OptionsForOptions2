"""I-12 (#583, REQ-077 AC-5, REQ-080 AC-9): a futures leg captures its planned entry from the futures LTP.

Root cause: ``ofo.outcome.snapshot.read_snapshot`` looked every leg's quote up in ``option_chain_snapshot`` (CE and PE
only), so a future's quote was always None and the route answered ``no_live_price`` however live the future was. The
fix reads a future through ``futures_quote``. Real rows: the recorded NIFTY instrument slice's own futures (REQ-135).
Answer states, one test each: future ticking -> LTP; future with only a bid/ask -> mid; no tick in time -> no_live_price
and nothing left held; a zero tick -> no_live_price (zero is not a price); a provider that offers no futures quote ->
no_live_price (never an error).
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import new_provider_with_futures  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.marketdata.provider import NotSupported  # noqa: E402
from ofo_app.live_push import LiveFeed  # noqa: E402
from ofo_app.main import create_app  # noqa: E402
from ofo_app.routes import planned_entry as route  # noqa: E402
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context  # noqa: E402

HTTP_OK = 200
ANSWER = datetime.datetime(2026, 10, 8, 3, 50, 5, tzinfo=datetime.UTC)


def _frame(provider, instrument_id: str, rupees: str) -> bytes:
    token = provider._token_of[instrument_id]
    paise = int(Decimal(rupees) * 100)
    return (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + token.to_bytes(4, "big") + paise.to_bytes(4, "big")


class Rig:
    def __init__(self) -> None:
        self.provider, self.clock, _items, futures = new_provider_with_futures("NIFTY")
        far = max(futures, key=lambda x: x.contract.expiry)  # a future still listed on the recorded day
        self.future_id = f"{far.contract.exchange_segment}:{far.contract.exchange_token}"
        self.provider.on_connected(self.clock.now)
        self.fanout = FanOut(self.provider)
        self.feed = LiveFeed(MarketContext(self.provider, lambda: self.clock.now, Decimal("0.065")), self.fanout)
        self.tick: str | None = None
        real = self.provider.subscribe

        def subscribe(ids):
            real(ids)
            if self.tick is not None and self.future_id in ids:
                asyncio.get_running_loop().call_later(0.1, lambda: self.provider.on_frame(
                    _frame(self.provider, self.future_id, self.tick), self.clock.now))
        self.provider.subscribe = subscribe

    def app(self):
        app = create_app()
        app.dependency_overrides[get_market_context] = lambda: self.feed.ctx
        app.dependency_overrides[route.get_live_feed] = lambda: self.feed
        app.dependency_overrides[get_answer_clock] = lambda: (lambda: ANSWER)
        return app

    async def post(self):
        async with AsyncClient(transport=ASGITransport(app=self.app()), base_url="http://t") as ac:
            resp = await ac.post("/api/strategies/planned-entry",
                                 json={"underlying": "NIFTY", "instrument_ids": [self.future_id]})
        assert resp.status_code == HTTP_OK, resp.text
        return resp.json()["entries"][0]


@pytest.fixture
def fast_wait(monkeypatch):
    monkeypatch.setattr(route, "PLANNED_ENTRY_WAIT_S", 0.4)


async def test_core_a_ticking_future_is_captured_at_its_ltp_and_released(fast_wait):
    rig = Rig()
    rig.tick = "22800.00"
    entry = await rig.post()
    assert (entry["planned_entry"], entry["source"], entry["reason_code"]) == ("22800.00", "ltp", None)
    assert entry["captured_at"] is not None
    assert rig.fanout.subscriber_count(rig.future_id) == 0  # the route's own hold ended


async def test_a_future_with_no_tick_in_time_is_no_live_price_and_nothing_stays_held(fast_wait):
    rig = Rig()
    entry = await rig.post()
    assert (entry["planned_entry"], entry["reason_code"]) == (None, "no_live_price")
    assert rig.fanout.subscriber_count(rig.future_id) == 0


async def test_a_zero_tick_on_a_future_is_not_a_price(fast_wait):
    rig = Rig()
    rig.tick = "0.00"
    entry = await rig.post()
    assert (entry["planned_entry"], entry["reason_code"]) == (None, "no_live_price")


async def test_a_provider_with_no_futures_quote_leaves_the_leg_unpriced_not_an_error(fast_wait, monkeypatch):
    rig = Rig()

    def refuse(_underlying, _expiry):
        raise NotSupported("no futures quotes")
    monkeypatch.setattr(rig.provider, "futures_quote", refuse)
    entry = await rig.post()
    assert (entry["planned_entry"], entry["reason_code"]) == (None, "no_live_price")
