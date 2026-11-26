"""ADR-330 (39) / D-69 / F-32: in market hours an INDEX quote older than ``detection.index_quote_max_age_seconds`` is
not live, even while option frames keep the feed healthy. One rule: ``FeedState.quote_health`` read by ``QuoteBook``.

Pure: times passed in, settings are plain mappings.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.engine.legs import Instrument
from ofo.marketdata.feed_health import FeedState, QuoteBook
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata, planning_price_usable, priced
from ofo.rules.inputs import DataHealth
from ofo.settings import calc, defaults

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
SEC = datetime.timedelta(seconds=1)
SRC = SourceMetadata(provider="kite", feed_id="x")


def _at(h, m, s=0):
    return datetime.datetime(2026, 11, 25, h, m, s, tzinfo=IST)  # a Wednesday


def _index(ts):
    return NormalizedQuote("NIFTY-IDX", "NIFTY", "NSE", "INDICES", None, None, None, D("24000"), None, None, None,
                           None, None, None, None, None, None, None, ts, SRC, DataHealth.AVAILABLE)


def _option(ts):
    return NormalizedQuote("NIFTY-OPT", "NIFTY", "NFO", "NFO-OPT", Instrument.CE, datetime.date(2026, 12, 1),
                           D("24000"),
                           D("100"), D("99"), D("101"), 10, 10, None, None, None, None, None, None, ts, SRC,
                           DataHealth.AVAILABLE)


def _book(max_age="60", open_=True):
    values = dict(defaults())
    values["detection.index_quote_max_age_seconds"] = D(max_age)
    values["detection.feed_stale_seconds"] = D("30")
    feed = FeedState(windows=calc.feed_windows(values), market_open=lambda _t: open_)
    feed.on_connected(_at(9, 15))
    return QuoteBook(feed)


def test_default_is_sixty_seconds():
    assert calc.feed_windows(defaults()).index_quote_max_age == 60 * SEC


def test_real_case_index_silent_since_151518_while_option_frames_run_on():
    """NIFTY's last tick 15:15:18; option frames keep arriving (whole-feed health says live). At 15:16:30 (72 s after
    the index tick) the index is not live; the option on the same live feed still is."""
    book = _book()
    book.update(_index(_at(15, 15, 18)))
    book.update(_option(_at(15, 16, 29)))
    book.feed.on_data(_at(15, 16, 29))
    now = _at(15, 16, 30)
    assert book.feed.health(now) is DataHealth.AVAILABLE  # the whole feed says live
    idx = book.get("NIFTY-IDX", now)
    assert idx.health is DataHealth.STALE and not priced(idx)
    assert idx.timestamp == _at(15, 15, 18)  # shown with its own time
    assert not planning_price_usable(idx, market_closed=False)
    assert book.get("NIFTY-OPT", now).health is DataHealth.AVAILABLE
    assert {q.instrument_id: q.health for q in book.quotes(now)} == {
        "NIFTY-IDX": DataHealth.STALE, "NIFTY-OPT": DataHealth.AVAILABLE}


def test_59_seconds_old_is_live_60_still_live_61_is_not():
    book = _book()
    t = _at(10, 0, 0)
    book.update(_index(t))
    for age, expected in ((59, DataHealth.AVAILABLE), (60, DataHealth.AVAILABLE), (61, DataHealth.STALE)):
        book.feed.on_data(t + age * SEC)
        assert book.get("NIFTY-IDX", t + age * SEC).health is expected, age


def test_the_setting_changes_the_threshold():
    t = _at(10, 0, 0)
    now = t + 45 * SEC
    for max_age, expected in (("60", DataHealth.AVAILABLE), ("30", DataHealth.STALE)):
        book = _book(max_age)
        book.update(_index(t))
        book.feed.on_data(now)
        assert book.get("NIFTY-IDX", now).health is expected, max_age


def test_after_the_close_the_close_rule_applies_unchanged():
    """ADR-330 (36): closed market, the at-close quote is served and the feed's STALE (market closed) stands; the
    index age rule adds nothing (health is STALE either way, planning use allowed by market_closed)."""
    book = _book(open_=False)
    book.update(_index(_at(15, 30, 0)))
    q = book.get("NIFTY-IDX", _at(18, 0, 0))
    assert q.health is DataHealth.STALE and q.timestamp == _at(15, 30, 0)
    assert planning_price_usable(q, market_closed=True)
