"""ADR-330 (36), issue #752 (amends ADR-200 (2)): "Freeze at 15:30" through a real route. After the close
GET /paper/strategies/{id} shows the last price received up to the close, not a later frame (the after-close check of
26 Nov 2026: 99.75, then 99.60, then 100.10 under one "Prices are from 15:30:00" label). The sequence is fed to the
REAL KiteProvider as real frames; the clock is injected. Paper only: nothing is filled. Real PostgreSQL, rolled back."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.marketdata.kite_provider import IST
from ofo_app import paper_store
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context
from test_strategy_store import _client
from test_strategy_tracking import IDS, _frame, _setup

D = Decimal
AT = datetime.datetime(2026, 10, 1, 4, 0, tzinfo=datetime.UTC)


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _t(hh: int, mm: int, ss: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, 8, hh, mm, ss, tzinfo=IST)  # Thursday, a trading day


async def _read_at(db, frames: list[tuple[str, datetime.datetime]], read_at: datetime.datetime) -> dict:
    app, stored, provider, clock, _last = await _setup(db)
    cid = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id,
                            [paper_store.NewOrder(cid, "SELL", 65, D("100.00"), "open", AT)])
    provider.book.remove(IDS[0])  # the replay's own quote is not part of this sequence
    provider.subscribe([IDS[0]])
    for rupees, at in frames:
        clock.now = at
        provider.on_frame(_frame(provider, IDS[0], rupees), at)
    clock.now = read_at
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: read_at, D("0.065"))
    app.dependency_overrides[get_answer_clock] = lambda: lambda: read_at
    async with _client(app) as c:
        reply = await c.get(f"/paper/strategies/{stored.id}")
    assert reply.status_code == HTTPStatus.OK, reply.text
    return next(p for p in reply.json()["positions"] if p["contract_id"] == cid)


async def test_after_the_close_the_paper_book_shows_the_last_price_up_to_the_close_not_a_later_frame(db):
    position = await _read_at(db, [("99.75", _t(15, 29, 59)), ("99.60", _t(15, 31, 10)),
                                   ("100.10", _t(15, 33, 48))], _t(15, 34, 0))
    assert (position["ltp"], position["price_state"]) == ("99.75", "live")
    assert position["price_at"].startswith("2026-10-08T15:29:59")


async def test_in_hours_the_paper_book_still_shows_the_latest_frame(db):
    position = await _read_at(db, [("99.50", _t(15, 29, 0)), ("99.75", _t(15, 29, 59))], _t(15, 29, 59))
    assert (position["ltp"], position["price_state"]) == ("99.75", "live")


async def test_after_the_close_with_only_post_close_frames_shows_the_latest_as_before(db):
    position = await _read_at(db, [("99.60", _t(15, 31, 10)), ("100.10", _t(15, 33, 48))], _t(15, 34, 0))
    assert D(position["ltp"]) == D("100.10")
