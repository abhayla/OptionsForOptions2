"""REQ-114 AC-7 through the ROUTES (chunk 1 Tier A review F1, class market-state-decided-per-surface; finding
verified-on-a-module-the-product-does-not-call): the outcome, chain and index REST routes, on the REAL KiteProvider fed
the recorded full frame and then a heartbeat every second, answer ``market_closed`` with the last price time on Saturday
2026-10-24 10:00 IST, and not on Wednesday 2026-10-21 10:00 IST. The socket pushes send the same answer functions
(``chain_answer`` / ``indices_answer`` / ``outcome_response``). No database: every dependency with a store is overridden.

Answer states (standing item d): open -> market_closed false, quotes as the feed says; closed (weekend) -> true, every
quote health "stale" (never "available"); no context at all -> the calendar's own answer."""
# ruff: noqa: PLR2004
from __future__ import annotations

import datetime
import pathlib
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_provider import IST, KiteProvider

FIX = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
FRAME = (FIX / "full-frame-12080386-150720.bin").read_bytes()
LEG = "NSE_FO:47189"  # the contract in the recorded full frame
SATURDAY = datetime.datetime(2026, 10, 24, 10, 0, tzinfo=IST)
WEDNESDAY = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now


def _fed(start: datetime.datetime) -> tuple[KiteProvider, Clock, datetime.datetime]:
    clock = Clock(start)
    provider = KiteProvider(list(parse_instruments_csv(FIX / "instruments-2026-10-08-subscribed.csv")), clock=clock)
    provider.subscribe([LEG])
    provider.on_connected(start)
    frame_at = start + datetime.timedelta(seconds=1)
    provider.on_frame(FRAME, frame_at)
    for second in range(2, 300):
        provider.on_frame(b"\x00", start + datetime.timedelta(seconds=second))
    clock.now = start + datetime.timedelta(seconds=299, milliseconds=500)
    return provider, clock, frame_at


def _app(provider, clock):
    from ofo_app.chain_push import ChainCatalogue
    from ofo_app.main import create_app
    from ofo_app.routes.chain import get_chain_reader
    from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context, get_streaming

    async def reader(_underlying, _expiry):
        return ChainCatalogue(expiries=(), contracts=())

    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: clock
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, clock, Decimal("0.065"))
    app.dependency_overrides[get_streaming] = lambda: None
    app.dependency_overrides[get_chain_reader] = lambda: reader
    return app


async def _answers(start: datetime.datetime):
    provider, clock, frame_at = _fed(start)
    price = f"{provider.book.get(LEG, clock.now).ltp:f}"
    body = {"underlying": "NIFTY", "fallback": False,
            "legs": [{"instrument_id": LEG, "action": "SELL", "lots": 1, "planned_entry": price,
                      "captured_at": clock.now.isoformat()}]}
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        outcome = await ac.post("/api/strategies/outcome", json=body)
        chain = await ac.get("/api/market/chain", params={"underlying": "NIFTY", "expiry": "2026-10-27"})
        indices = await ac.get("/api/market/indices")
    for r in (outcome, chain, indices):
        assert r.status_code == 200, r.text
    healths = sorted({q.health.value for q in provider.book.quotes(clock.now)})
    return outcome.json(), chain.json(), indices.json(), frame_at, healths


def _instant(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_saturday_with_heartbeats_every_route_answers_market_closed_with_the_last_price_time():
    """AC-7: Saturday 10:00 IST, one frame then heartbeats: outcome, chain and index answer market_closed true and
    the last price time is the frame's arrival; no quote reads available."""
    outcome, chain, indices, frame_at, healths = await _answers(SATURDAY)
    for answer in (outcome, chain, indices):
        assert answer["market_closed"] is True
        assert _instant(answer["last_price_at"]) == frame_at
    assert healths == ["stale"]  # the quotes those answers read (the recorded contract has expired: outcome REFUSED)


@pytest.mark.asyncio
async def test_wednesday_with_the_same_frames_every_route_answers_open():
    """AC-7 negative case: Wednesday 10:00 IST, same frames: market_closed false, the leg's quote available."""
    outcome, chain, indices, frame_at, healths = await _answers(WEDNESDAY)
    for answer in (outcome, chain, indices):
        assert answer["market_closed"] is False
        assert _instant(answer["last_price_at"]) == frame_at
    assert healths == ["available"]


def test_with_no_context_the_answers_read_the_calendar():
    """AC-7: no live context (not connected): the calendar's answer, with no last price time."""
    from ofo_app.index_push import indices_answer
    from ofo_app.routes.outcome import market_state

    assert indices_answer(None, live=False, now=lambda: SATURDAY).market_closed is True
    assert indices_answer(None, live=False, now=lambda: WEDNESDAY).market_closed is False
    assert market_state(None, datetime.datetime(2031, 3, 5, 10, 0, tzinfo=IST)).closed is True  # past its data
    assert market_state(None, SATURDAY).last_price_at is None
