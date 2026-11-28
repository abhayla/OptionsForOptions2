"""Lane FD2 item 3 (Lane TC defects D-1, D-2 of the PC walk of 28 Nov; ADR-330 (63), ADR-212): with no stored Zerodha
session the stored last close is still read into the book while the market is closed, and every read shows it with
its own date and time. Fakes only (no database): the catalogue provider and the close store are the same ones the
last-close tests use."""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from marketdata._kite_fixture import Clock, all_instrument_ids, listed
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app import last_close_store as lcs
from ofo_app import live_market
from ofo_app.routes.indices import indices_read

FRIDAY = datetime.date(2026, 11, 27)
NOW = datetime.datetime(2026, 11, 28, 6, 0, tzinfo=IST)  # a Saturday: the market is closed
CLOSE_AT = datetime.datetime(2026, 11, 27, 15, 29, 58, tzinfo=IST)
ROWS = 17


class _Store:
    def __init__(self, latest) -> None:
        self.latest, self.reads = latest, 0

    def read_latest(self, ids=None):
        self.reads += 1
        return dict(self.latest)

    def write_closes(self, rows):
        return len(list(rows))


def _seventeen(provider) -> dict:
    """Seventeen stored closes: the NIFTY 50 and SENSEX indexes and fifteen contracts of the recorded catalogue."""
    nifty, sensex = provider.index_id("NIFTY"), provider.index_id("SENSEX")
    others = [i for i in all_instrument_ids(listed()) if i not in (nifty, sensex)][:ROWS - 2]
    latest = {nifty: (Decimal("24187.35"), CLOSE_AT, FRIDAY), sensex: (Decimal("79000.10"), CLOSE_AT, FRIDAY)}
    latest |= {iid: (Decimal("10.05"), CLOSE_AT, FRIDAY) for iid in others}
    assert len(latest) == ROWS
    return latest


async def _market_with_no_session(monkeypatch) -> live_market.LiveMarket:
    market = live_market.LiveMarket()
    provider = KiteProvider(listed(), clock=Clock(NOW))
    market._clock = lambda: NOW  # the closed day, pinned: no wall clock in a test

    async def no_token(_config):
        return None

    async def catalogue_provider():
        return provider

    monkeypatch.setattr(market, "_stored_token", no_token)
    monkeypatch.setattr(market, "_catalogue_provider", catalogue_provider)
    await market.start(object())
    return market


async def test_core_d1_with_no_session_the_indices_answer_the_stored_close_with_its_own_time(monkeypatch):
    market = await _market_with_no_session(monkeypatch)
    ctx = market.context()
    assert ctx is not None, "no session must still leave a book for the stored close"
    store = _Store(_seventeen(ctx.provider))
    assert await lcs.seed_once(ctx.provider, store, NOW) == ROWS
    answer = indices_read(ctx, None, fallback=False, now=lambda: NOW)
    nifty = next(r for r in answer.indices if r.underlying == "NIFTY")
    assert (nifty.value, nifty.at) == (Decimal("24187.35"), CLOSE_AT)
    assert answer.state == "NOT_CONNECTED" and answer.market_closed is True
    assert market.state == live_market.NOT_CONNECTED
    assert ctx.provider.status().connected is False  # no socket was made: nothing was asked of Zerodha


async def test_d1_the_state_is_not_connected_and_the_task_seeds_the_book_with_no_session(monkeypatch):
    market = await _market_with_no_session(monkeypatch)
    ctx = market.context()
    store = _Store(_seventeen(ctx.provider))

    async def sleep(_):
        raise asyncio.CancelledError

    with contextlib.suppress(asyncio.CancelledError):
        await lcs.run_forever(market, store, sleep=sleep)  # the lifespan's one task, one turn
    assert store.reads == 1
    nifty = ctx.provider.book.get(ctx.provider.index_id("NIFTY"), NOW)
    assert nifty is not None and nifty.ltp == Decimal("24187.35")


async def test_d1_no_stored_close_leaves_the_prices_not_available(monkeypatch):
    market = await _market_with_no_session(monkeypatch)
    ctx = market.context()
    assert await lcs.seed_once(ctx.provider, _Store({}), NOW) == 0
    answer = indices_read(ctx, None, fallback=False, now=lambda: NOW)
    assert [(r.value, r.at) for r in answer.indices] == [(None, None), (None, None)]


async def test_d1_a_catalogue_that_cannot_be_read_leaves_no_book_and_the_start_does_not_fail(monkeypatch):
    market = live_market.LiveMarket()

    async def no_token(_config):
        return None

    async def broken():
        raise OSError("database down")

    monkeypatch.setattr(market, "_stored_token", no_token)
    monkeypatch.setattr(market, "_catalogue_provider", broken)
    await market.start(object())
    assert market.context() is None and market.state == live_market.NOT_CONNECTED


async def test_d1_a_disconnect_keeps_the_stored_close_on_the_screens(monkeypatch):
    market = await _market_with_no_session(monkeypatch)
    live_market.set_current(market)
    try:
        market.feed = None  # as the disconnect clears it
        await live_market.stop_current()
        assert market.context() is not None and market.state == live_market.NOT_CONNECTED
    finally:
        live_market.set_current(None)
