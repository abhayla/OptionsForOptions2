"""Lane B1b item 5: routes/adjustment_history.py read "paused, prices not live" with no session while the paper
book showed a figure from the stored close (the book's rule since Lane RA2 item 1; ADR-330 (60), ADR-212).

Real case: the no-session book of test_stored_close_paper_pnl_ra2_1128.py (Saturday 10 Oct 2026, stored closes of
Friday 9 Oct 15:29:58: 45.15 / 14.95 / 70.75 / 30.80 on legs entered at 39.15 / 12.95 / 82.75 / 35.80, +195.00 before
charges). The history of that trade must read the same open figure; an unknown calendar must pause it like the
book."""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

from ofo import market_calendar
from ofo_app.routes.outcome import MarketContext, get_market_context
from test_paper_routes import _client, db  # noqa: F401 - db is the rollback fixture
from test_stored_close_paper_pnl_ra2_1128 import SATURDAY, _no_session_book

D = Decimal


async def _history(app, strategy_id: int) -> dict:
    async with _client(app) as c:
        reply = await c.get(f"/api/strategies/{strategy_id}/adjustment-history")
    assert reply.status_code == HTTPStatus.OK, reply.text[:300]
    return reply.json()


async def test_core_no_session_the_history_reads_the_stored_close_like_the_book(db):  # noqa: F811
    app, stored = await _no_session_book(db)
    async with _client(app) as c:
        book = (await c.get(f"/paper/strategies/{stored.id}")).json()
    totals = (await _history(app, stored.id))["totals"]
    assert D(book["unbooked"]) == D("195.00")
    assert totals["prices_reason"] is None and totals["open_reason"] is None
    assert D(totals["open_pnl"]) == D(book["unbooked"])


async def test_an_unknown_calendar_pauses_the_history_like_the_book(db, monkeypatch):  # noqa: F811
    app, stored = await _no_session_book(db)
    unknown = market_calendar.MarketStatus.NO_CALENDAR
    monkeypatch.setattr(market_calendar, "market_status", lambda now, holidays=None: unknown)
    totals = (await _history(app, stored.id))["totals"]
    assert totals["open_pnl"] is None and totals["open_reason"] is not None


async def test_no_stored_close_keeps_the_history_paused(db):  # noqa: F811
    from marketdata._kite_fixture import Clock, listed  # noqa: PLC0415
    from ofo.marketdata.kite_provider import KiteProvider  # noqa: PLC0415
    app, stored = await _no_session_book(db)
    provider = KiteProvider(listed(), clock=Clock(SATURDAY))  # holds nothing
    context = MarketContext(provider, lambda: SATURDAY, D("0.065"), None)
    app.dependency_overrides[get_market_context] = lambda: context
    totals = (await _history(app, stored.id))["totals"]
    assert totals["open_pnl"] is None
