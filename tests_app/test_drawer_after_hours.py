"""GC-BM F-18 / ADR-200 (1) "the Strategy Builder and its strike drawer use the last price": after the close the strike
drawer prices strikes nobody held before the drawer opened, from the snapshot the feed sends for a new subscription.

Measured live 2026-10-27 18:56 IST (no launcher): every drawer strike blank except the put the strategy already held;
Greeks all "-". Under the walkthrough launcher (market forced open) the same drawer priced every strike, so the feed
does deliver the after-hours snapshots.

Real rows: the recorded 2026-10-08 NIFTY session in the REAL KiteProvider. Only one contract is held during the session;
at 18:00 IST the drawer's window lease subscribes the rest and the feed delivers one snapshot per new subscription
(the recorded frames, arriving at 18:00). The clock is injected (``MarketContext.clock``), never the wall clock.
"""
from __future__ import annotations

import dataclasses
import datetime
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import new_provider, recorded_frames, replay  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo.marketdata.quote import planning_price_usable  # noqa: E402
from ofo.rules.inputs import DataHealth  # noqa: E402
from ofo_app.catalogue_picker import PickableContract  # noqa: E402
from ofo_app.chain_push import ChainCatalogue  # noqa: E402
from ofo_app.live_push import LiveFeed  # noqa: E402
from ofo_app.routes import leg_picker  # noqa: E402
from ofo_app.routes.outcome import MarketContext  # noqa: E402

RATE = Decimal("0.065")
EXPIRY = datetime.date(2026, 10, 13)
HELD = "NSE_FO:44624"  # the one contract a strategy held during the session
AFTER_CLOSE = datetime.datetime(2026, 10, 8, 18, 0, tzinfo=IST)
IN_HOURS_LATE = datetime.datetime(2026, 10, 8, 11, 0, tzinfo=IST)  # in hours, the snapshot frames 1.5 h old: stale


def _catalogue(items) -> ChainCatalogue:
    rows = []
    for n, lc in enumerate(items):
        c = lc.contract
        if c.name != "NIFTY" or c.expiry != EXPIRY or c.instrument_type not in ("CE", "PE"):
            continue
        rows.append(PickableContract(n + 1, f"{c.exchange_segment}:{c.exchange_token}", c.exchange_segment,
                                     c.exchange_token, c.instrument_type, c.expiry, c.strike, c.lot_size,
                                     lc.broker_refs[0].broker_symbol if lc.broker_refs else "X"))
    return ChainCatalogue(expiries=(EXPIRY,), contracts=tuple(rows))


def _drawer(at: datetime.datetime, *, snapshot_at: datetime.datetime | None = None):
    """The session with only HELD (and the index) subscribed; then, at ``at``, the drawer reads, its lease subscribes
    the window, the feed delivers the snapshot frames (arriving at ``snapshot_at``), and the drawer reads again."""
    provider, clock, items = new_provider()
    index_id = provider.index_id("NIFTY")
    provider.subscribe([HELD, index_id])
    replay(provider, clock)
    clock.now = at
    feed = LiveFeed(MarketContext(provider, clock, RATE), FanOut(provider))
    cat = _catalogue(items)
    try:
        first = leg_picker.strikes_answer(feed, "NIFTY", EXPIRY, 10, cat, clock)
        for _frame_at, frame in recorded_frames():  # one snapshot per new subscription, received now
            provider.on_frame(frame, snapshot_at or at)
        second = leg_picker.strikes_answer(feed, "NIFTY", EXPIRY, 10, cat, clock)
    finally:
        leg_picker.LEASE.release()
    return first, second


def _cells(out):
    return [c for r in out.rows for c in (r.ce, r.pe) if c is not None]


def test_after_close_the_drawer_prices_unheld_strikes_from_their_snapshot_with_iv_and_delta():
    _first, out = _drawer(AFTER_CLOSE)
    cells = _cells(out)
    priced = [c for c in cells if c.ltp is not None]
    assert out.market_closed is True
    assert len(priced) == len(cells), [(c.instrument_id, c.health) for c in cells if c.ltp is None]
    assert all(c.health == "stale" for c in priced)  # never shown as live (ADR-015)
    assert all(c.oi is not None for c in priced)
    with_greeks = [c for c in priced if c.iv_percent is not None and c.delta is not None]
    assert len(with_greeks) >= len(priced) // 2, "the engine's IV/delta from the index's last close"
    assert out.reason is None or out.reason == "SOME_PRICES_MISSING"


def test_in_hours_a_stale_drawer_still_prices_nothing():
    """Unchanged in market hours: frames that stopped 1.5 h ago are stale, never a price."""
    _first, out = _drawer(IN_HOURS_LATE, snapshot_at=datetime.datetime(2026, 10, 8, 9, 30, tzinfo=IST))
    assert out.market_closed is False
    assert all(c.ltp is None and c.iv_percent is None and c.oi is None for c in _cells(out))


@pytest.mark.parametrize("health", ["unhealthy"])
def test_an_unsound_quote_is_never_priced_after_close(health):
    """Fail closed: the planning rule refuses a quote with a validation error even after the close."""
    provider, clock, _items = new_provider()
    provider.subscribe([HELD])
    replay(provider, clock)
    q = provider.book.get(HELD, AFTER_CLOSE)
    assert planning_price_usable(q, market_closed=True)
    assert not planning_price_usable(dataclasses.replace(q, health=DataHealth(health)), market_closed=True)


# ---- the depth popup (REQ-080 AC-7, read-only): the last held depth and day values after the close -----------------

def _depth_at(at: datetime.datetime):
    provider, clock, _items = new_provider()
    provider.subscribe([HELD])
    replay(provider, clock)
    clock.now = at
    feed = LiveFeed(MarketContext(provider, clock, RATE), FanOut(provider))
    handle = feed.fanout.subscribe(lambda _q: None, [HELD], max_queue=1)  # the popup's own hold, as on the screen
    try:
        return leg_picker.depth_answer(feed, HELD, clock), provider
    finally:
        feed.fanout.unsubscribe(handle)


def test_after_close_the_depth_popup_shows_the_last_depth_and_day_values_under_market_closed():
    out, _provider = _depth_at(AFTER_CLOSE)
    assert (out.state, out.reason, out.market_closed) == ("AVAILABLE", None, True)  # never "not fresh"
    assert out.bids and out.asks
    assert out.day_open is not None and out.prev_close is not None


def test_in_hours_a_stale_depth_popup_still_says_feed_stale():
    out, _provider = _depth_at(IN_HOURS_LATE)
    assert (out.state, out.reason, out.market_closed) == ("NOT_AVAILABLE", "FEED_STALE", False)


def test_after_close_the_execute_depth_still_refuses():
    """The order path's depth (``latest_depth``, read by ``LiveDepthQuotes``) stays live-only after the close."""
    provider, clock, _items = new_provider()
    provider.subscribe([HELD])
    replay(provider, clock)
    assert provider.latest_depth(HELD, IN_HOURS_LATE.replace(hour=9, minute=20, second=9)) is not None
    assert provider.latest_depth(HELD, AFTER_CLOSE) is None
    assert provider.depth_after_close(HELD, AFTER_CLOSE) is not None
