"""Lane RA2 item 1 (Lane TG D-TG-1; ADR-330 (60), ADR-212, ADR-008): with NO broker session and a stored close in the
book, a running paper trade shows its P&L from the stored close with the close's own time, on every paper read.

Real case (Lane TG, PC walk 28 Nov, no session): the Live card LTP column read 147.50 (as of 15:29:58) while every
running paper row stayed "P&L - / Paper P&L paused - prices not live" and Home read "4 strategies left out: their prices
are not live." Cause: ``_figures`` got ``connected=False`` and the book state was NOT_CONNECTED, figures null.
Hand arithmetic: the saved legs entered at 39.15 / 12.95 / 82.75 / 35.80 (test_strategy_tracking) and the stored closes
are 45.15 / 14.95 / 70.75 / 30.80 -> +195.00 before charges (the same sum as AC-1 of that file: -390 + 130 + 780 - 325).
"""
from __future__ import annotations

import datetime
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from marketdata._kite_fixture import Clock, listed
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app import last_close_store as lcs
from ofo_app import paper_store
from ofo_app.routes.outcome import MarketContext, get_market_context, load_charge_rates
from test_paper_routes import _client, _new, db  # noqa: F401 - db is the rollback fixture
from test_strategy_tracking import ENTRY_PRICES, IDS, _setup

D = Decimal
SATURDAY = datetime.datetime(2026, 10, 10, 11, 0, tzinfo=IST)  # the market is closed
CLOSE_AT = datetime.datetime(2026, 10, 9, 15, 29, 58, tzinfo=IST)
FRIDAY = datetime.date(2026, 10, 9)
CLOSES = ["45.15", "14.95", "70.75", "30.80"]


class _Store:
    def __init__(self, latest) -> None:
        self.latest = latest

    def read_latest(self, ids=None):
        return dict(self.latest)

    def write_closes(self, rows):
        return len(list(rows))


async def _no_session_book(db):  # noqa: F811
    """The saved four-leg strategy with paper orders, and a context with NO session: a disconnected provider whose book
    holds only the stored closes of Friday 9 Oct (``seed_once``, the same call the app makes at start)."""
    app, stored, *_ = await _setup(db)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [
        _new(cid, leg.action.value, leg.quantity, price)
        for cid, leg, price in zip(ids, stored.saved.definition.legs, ENTRY_PRICES, strict=True)])
    provider = KiteProvider(listed(), clock=Clock(SATURDAY))
    store = _Store({iid: (D(close), CLOSE_AT, FRIDAY) for iid, close in zip(IDS, CLOSES, strict=True)})
    assert await lcs.seed_once(provider, store, SATURDAY) is not None
    assert provider.status().connected is False
    context = MarketContext(provider, lambda: SATURDAY, D("0.065"), None)
    app.dependency_overrides[get_market_context] = lambda: context
    app.dependency_overrides[load_charge_rates] = lambda: None
    return app, stored


async def test_core_no_session_a_running_paper_trade_reads_its_pnl_from_the_stored_close_with_its_time(db):  # noqa: F811
    app, stored = await _no_session_book(db)
    async with _client(app) as c:
        single = (await c.get(f"/paper/strategies/{stored.id}")).json()
        whole = (await c.get("/paper/strategies")).json()
    listed_ = next(s for s in whole["strategies"] if s["strategy_id"] == stored.id)
    for body in (single, listed_):
        assert (body["state"], body["pause_reason"]) == ("LIVE", None)
        assert D(body["unbooked"]) == D("195.00") and D(body["total"]) == D("195.00")
        assert body["as_of"] is not None and datetime.datetime.fromisoformat(body["as_of"]) == CLOSE_AT
        assert {p["ltp"] for p in body["positions"]} == set(CLOSES)
    assert whole["totals"]["left_out_count"] == 0


async def test_no_session_and_no_stored_close_stays_not_connected_with_no_figure(db):  # noqa: F811
    app, stored = await _no_session_book(db)
    provider = KiteProvider(listed(), clock=Clock(SATURDAY))  # a book that holds nothing
    context = MarketContext(provider, lambda: SATURDAY, D("0.065"), None)
    app.dependency_overrides[get_market_context] = lambda: context
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["state"], body["unbooked"], body["total"]) == ("NOT_CONNECTED", None, None)


async def test_no_session_with_the_market_open_never_serves_a_stored_figure(db):  # noqa: F811
    app, stored = await _no_session_book(db)
    open_at = datetime.datetime(2026, 10, 9, 11, 0, tzinfo=IST)  # Friday, market open: the held close is not read
    context = MarketContext(app.dependency_overrides[get_market_context]().provider, lambda: open_at, D("0.065"), None)
    app.dependency_overrides[get_market_context] = lambda: context
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["state"], body["unbooked"]) == ("NOT_CONNECTED", None)
