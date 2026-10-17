"""W-097: the app's one depth reader, ofo_app.live_market.latest_depth (ADR-080 (3)); no network, no database."""
from __future__ import annotations

import datetime
import pathlib
from decimal import Decimal

import pytest
from ofo.engine.executable_price import Depth
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app import live_market
from ofo_app.routes.outcome import MarketContext

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
INSTRUMENT_ID = "NSE_FO:47189"
AT = datetime.datetime.fromtimestamp(1792143440, IST)  # the frame's exchange time, 15:07:20 IST


class _Market:
    def __init__(self, ctx):
        self._ctx = ctx

    def context(self):
        return self._ctx


@pytest.fixture
def provider():
    p = KiteProvider(list(parse_instruments_csv(FIXTURES / "instruments-2026-10-08-subscribed.csv")), clock=lambda: AT)
    p.subscribe([INSTRUMENT_ID])
    p.on_connected(AT)
    p.on_frame((FIXTURES / "full-frame-12080386-150720.bin").read_bytes(), AT)
    return p


def _install(provider, clock):
    live_market.set_current(_Market(MarketContext(provider, clock, Decimal("0.065"))))


def test_no_live_market_gives_no_depth():
    """AC-1: with no live market the reader answers None, never a stale or invented depth."""
    live_market.set_current(None)
    assert live_market.latest_depth(INSTRUMENT_ID) is None


def test_reader_returns_the_depth_then_none_when_the_feed_goes_stale(provider):
    """AC-1: the app reader returns the domain Depth (5+5) while the feed is fresh and None once it is not."""
    now = [AT]
    _install(provider, lambda: now[0])
    try:
        depth = live_market.latest_depth(INSTRUMENT_ID)
        assert isinstance(depth, Depth) and len(depth.bids) == 5 and len(depth.asks) == 5
        assert depth.asks[0].price == Decimal("3.35")
        now[0] = AT + datetime.timedelta(seconds=10)
        assert live_market.latest_depth(INSTRUMENT_ID) is None
    finally:
        live_market.set_current(None)


def test_provider_without_depth_gives_none():
    """AC-1: a provider that has no latest_depth (the test replay) reads no depth instead of raising."""
    class _Bare:
        pass
    live_market.set_current(_Market(MarketContext(_Bare(), lambda: AT, Decimal("0.065"))))
    try:
        assert live_market.latest_depth(INSTRUMENT_ID) is None
    finally:
        live_market.set_current(None)

