"""Clock boundary 15:30 (live test day 27 Nov 2026; Lane Q2 gap 3; ADR-330 (36), ADR-212, REQ-049 AC-4).

One QuoteBook lives ACROSS the close, as the API process does on a real day: quotes keep arriving after 15:30 (the
26 Nov case: 99.75, 99.60, 100.10 read under one label). The read at each moment of the walk must give the figure of
the rule: live in session (the latest tick), the last price made up to the close afterwards, with its own time, and
never a later frame. The clock is injected and passed to every read; nothing here reads the wall clock.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.engine.legs import Instrument
from ofo.marketdata.feed_health import FeedState, QuoteBook
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo.settings import calc, defaults

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
TUE = datetime.date(2026, 12, 1)
SRC = SourceMetadata(provider="kite", feed_id="x")
OPTION = "NSE_FO:44614"


def at(h: int, m: int, s: int = 0) -> datetime.datetime:
    return datetime.datetime(TUE.year, TUE.month, TUE.day, h, m, s, tzinfo=IST)


def _quote(ltp: str, ts: datetime.datetime) -> NormalizedQuote:
    return NormalizedQuote(OPTION, "NIFTY", "NFO", "NFO-OPT", Instrument.PE, datetime.date(2026, 12, 8), D("25750"),
                           D(ltp), D(ltp) - D("0.05"), D(ltp) + D("0.05"), 10, 10, None, None, None, None, None, None,
                           ts, SRC, DataHealth.AVAILABLE)


@pytest.fixture
def book():
    feed = FeedState(windows=calc.feed_windows(dict(defaults())))  # the real calendar decides open / closed
    feed.on_connected(at(9, 15))
    return QuoteBook(feed)


def _tick(book: QuoteBook, ltp: str, ts: datetime.datetime) -> None:
    book.update(_quote(ltp, ts))
    book.feed.on_data(ts)


def test_the_figure_walks_across_the_close_and_never_takes_a_later_frame(book):
    _tick(book, "99.75", at(15, 29, 59))
    assert book.get(OPTION, at(15, 29, 59)).ltp == D("99.75")  # in session: the latest tick
    _tick(book, "99.60", at(15, 31, 10))  # after the close
    _tick(book, "100.10", at(15, 33, 48))
    for now in (at(15, 31, 11), at(15, 33, 49), at(15, 37, 0), at(18, 0, 0)):
        quote = book.get(OPTION, now)
        assert (quote.ltp, quote.price_at) == (D("99.75"), at(15, 29, 59)), now  # label and figure agree


def test_a_tick_exactly_at_the_close_is_the_last_close(book):
    _tick(book, "100.00", at(15, 30, 0))
    _tick(book, "101.00", at(15, 30, 1))
    quote = book.get(OPTION, at(15, 36, 0))
    assert (quote.ltp, quote.price_at) == (D("100.00"), at(15, 30, 0))


def test_in_session_the_latest_tick_is_served_until_the_close(book):
    for ltp, ts in (("98.00", at(15, 28, 0)), ("98.50", at(15, 29, 0)), ("99.00", at(15, 29, 55))):
        _tick(book, ltp, ts)
        assert book.get(OPTION, ts + datetime.timedelta(seconds=1)).ltp == D(ltp)
