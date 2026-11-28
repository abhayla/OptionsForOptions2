"""Lane RA2, coordinator's rule of 28 Nov (a stored close is not a live price; fail closed): with only a stored last
close in the book, what needs a live price does not unlock. Each guard is a named test:
(1) no fill, stop or exit price: ``paper.leg_price`` (the only price a fill or a trigger reads) is not live for a stored
    close, while ``paper.display_price`` (display only, ADR-212) is, with the close's own time;
(2) the monitor fires nothing from a stored close, even with an index exit crossed and a leg stop level passed;
(3) the market exit-state answer stays closed, so Exit Confirm stays greyed (ADR-330 (60)).
Real case: Friday 9 Oct 2026 close at 15:29:58, read on Saturday 10 Oct with no broker session (PC walk 28 Nov)."""
from __future__ import annotations

import datetime
import sys
from decimal import Decimal
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from httpx import ASGITransport, AsyncClient
from marketdata._kite_fixture import Clock, listed
from ofo.marketdata.feed_health import DataHealth
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.outcome.snapshot import read_snapshot
from ofo.tracking import paper
from ofo_app import last_close_store as lcs
from ofo_app.main import create_app
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context
from ofo_app.routes.outcome import MarketContext as _Ctx  # noqa: F401
from test_paper_monitor import INDEX, Market, _exit_below, _monitor, _stops, _strategy, _trigger_state, db  # noqa: F401
from test_strategy_tracking import IDS

D = Decimal
SATURDAY = datetime.datetime(2026, 10, 10, 11, 0, tzinfo=IST)
CLOSE_AT = datetime.datetime(2026, 10, 9, 15, 29, 58, tzinfo=IST)


class _Store:
    def __init__(self, latest) -> None:
        self.latest = latest

    def read_latest(self, ids=None):
        return dict(self.latest)


async def _seeded_provider() -> KiteProvider:
    provider = KiteProvider(listed(), clock=Clock(SATURDAY))
    latest = {iid: (D("45.15"), CLOSE_AT, datetime.date(2026, 10, 9)) for iid in IDS}
    assert await lcs.seed_once(provider, _Store(latest), SATURDAY) is not None
    return provider


async def test_guard_1_a_stored_close_is_never_a_fill_or_stop_price_but_is_a_display_price():
    provider = await _seeded_provider()
    ctx = MarketContext(provider, lambda: SATURDAY, D("0.065"), None)
    snapshot = read_snapshot(provider, "NIFTY", [IDS[0]], SATURDAY, ctx.rate, quality=ctx.forward_quality)
    assert snapshot.market_closed is True
    fill = paper.leg_price(snapshot, IDS[0])
    assert not paper.is_live(fill) and fill.price is None, fill  # what a fill, stop or exit reads: no price
    shown = paper.display_price(snapshot, IDS[0])
    assert paper.is_live(shown) and shown.price == D("45.15") and shown.at == CLOSE_AT, shown  # display only


async def test_guard_2_the_monitor_fires_nothing_from_a_stored_close(db):  # noqa: F811
    market = Market(at=SATURDAY)  # a closed day; the book holds only closes, which the feed marks stale
    stored, _ids, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    for key in keys:
        market.tick(key, "45.15", DataHealth.STALE)
    market.tick(INDEX, "22800.00", DataHealth.STALE)  # below the exit level 22,850.00
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False) and await _stops(db, stored.id) == []


async def test_guard_3_the_exit_state_stays_closed_with_only_a_stored_close():
    provider = await _seeded_provider()
    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: (lambda: SATURDAY)
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: SATURDAY, D("0.065"), None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        reply = await ac.get("/api/market/exit-state")
    assert reply.status_code == HTTPStatus.OK, reply.text
    sentence = reply.json()["sentence"]
    assert sentence.startswith("The market is closed. Exits can be placed from 09:15 on Monday 12 Oct"), sentence
