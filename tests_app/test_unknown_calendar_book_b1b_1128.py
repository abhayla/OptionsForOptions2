"""Lane B1b item 4 (Opus review of Lane RA2's branch, 28 Nov): when the trading calendar cannot answer for a date, the
market counts as closed (``feed_health.FeedState.market_closed``: "a date it cannot answer: fail closed"). Orders stay
blocked, but the paper book then read a stored close as LIVE during real market hours. Real case: Friday 9 Oct 2026,
11:00 IST, no session, a stored close of 9 Oct 15:29:58 in the book, the calendar patched to answer ``NO_CALENDAR``
(the data file holds no holiday table for the year). An unknown calendar answer reads NOT_CONNECTED with no figure.
(The backstop test, a no-session LIVE book always has a non-null as_of, is Lane RA2's.)"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo import market_calendar
from ofo.marketdata.kite_provider import IST
from ofo_app.routes.outcome import MarketContext, get_market_context
from test_paper_routes import _client, db  # noqa: F401 - db is the rollback fixture
from test_stored_close_paper_pnl_ra2_1128 import SATURDAY, _no_session_book

D = Decimal
FRIDAY_NOON = datetime.datetime(2026, 10, 9, 12, 0, tzinfo=IST)


def _calendar_cannot_answer(monkeypatch):
    unknown = market_calendar.MarketStatus.NO_CALENDAR
    monkeypatch.setattr(market_calendar, "market_status", lambda now, holidays=None: unknown)


async def test_core_a_calendar_that_cannot_answer_never_serves_the_stored_close_as_live(db, monkeypatch):  # noqa: F811
    app, stored = await _no_session_book(db)
    _calendar_cannot_answer(monkeypatch)
    provider = app.dependency_overrides[get_market_context]().provider
    context = MarketContext(provider, lambda: FRIDAY_NOON, D("0.065"), None)
    app.dependency_overrides[get_market_context] = lambda: context
    async with _client(app) as c:
        single = (await c.get(f"/paper/strategies/{stored.id}")).json()
        whole = (await c.get("/paper/strategies")).json()
    listed = next(s for s in whole["strategies"] if s["strategy_id"] == stored.id)
    for body in (single, listed):
        assert (body["state"], body["unbooked"], body["total"], body["as_of"]) == ("NOT_CONNECTED", None, None, None)


async def test_the_same_book_with_a_calendar_that_answers_closed_still_reads_live_with_its_time(db):  # noqa: F811
    app, stored = await _no_session_book(db)  # Saturday 10 Oct: the calendar answers CLOSED_WEEKEND
    assert market_calendar.market_status(SATURDAY) is market_calendar.MarketStatus.CLOSED_WEEKEND
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["state"], body["as_of"] is not None) == ("LIVE", True)
