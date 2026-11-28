"""Lane N round 3 defects 1 and 2 (ADR-330 (28), (39), ADR-200 (4)): one price-state rule decides whether the index
value may be held. RCA 1: ``_index_value_not_live`` checked only ``ltp > 0``, so a confirmed save took a crossed quote.
RCA 2: ``entry_facts_now`` had no health check, so a STALE index quote was stored as entry_spot with no tick.
Unit tests with fakes (no database)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.rules.inputs import DataHealth
from ofo_app import adjustment_readers as readers
from ofo_app.strategy_refused import StrategyRefused

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 11, 27, 15, 8, tzinfo=IST)
AT = datetime.datetime(2026, 11, 27, 14, 46, tzinfo=IST)


def _quote(ltp, health=DataHealth.AVAILABLE, errors=()):
    return SimpleNamespace(ltp=ltp, price_at=AT, timestamp=AT, health=health, validation_errors=errors)


def _ctx(quote):
    provider = SimpleNamespace(status=lambda: SimpleNamespace(connected=True), underlying_quote=lambda _u: quote)
    return SimpleNamespace(provider=provider, clock=lambda: NOW)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(readers, "_scenario", lambda: None)
    monkeypatch.setattr(readers, "market_state", lambda ctx, _now: SimpleNamespace(closed=False))
    monkeypatch.setattr("ofo_app.chain_push.index_id_of", lambda _c, _u: None)


CROSSED = _quote(D("24000.05"), DataHealth.UNHEALTHY, ("crossed_quote",))
OLD = _quote(D("24087.30"), DataHealth.STALE)


async def test_confirmed_save_refuses_a_crossed_quote_with_its_reason():
    ctx = _ctx(CROSSED)
    assert readers._index_value_not_live(ctx, "NIFTY") is None
    with pytest.raises(StrategyRefused) as e:
        await readers._index_spot_held(ctx, None, "NIFTY", True)
    assert e.value.args[0] == "paper_index_price_unavailable" and e.value.reason == "crossed_quote"


async def test_confirmed_save_still_takes_a_merely_old_valid_quote():
    assert await readers._index_spot_held(_ctx(OLD), None, "NIFTY", True) == D("24087.30")


async def test_entry_facts_refuse_a_stale_index_quote_unless_confirmed():
    sold = [SimpleNamespace(instrument_type="CE", strike=D("24100"), expiry=None)]
    assert await readers.entry_facts_now(_ctx(OLD), "NIFTY", sold) is None
    facts = await readers.entry_facts_now(_ctx(OLD), "NIFTY", sold, confirmed=True)
    assert facts is not None and facts.entry_spot == D("24087.30")


async def test_entry_facts_refuse_a_crossed_quote_even_when_confirmed():
    sold = [SimpleNamespace(instrument_type="CE", strike=D("24100"), expiry=None)]
    assert await readers.entry_facts_now(_ctx(CROSSED), "NIFTY", sold, confirmed=True) is None


async def test_entry_facts_take_a_live_quote_without_confirmation():
    sold = [SimpleNamespace(instrument_type="CE", strike=D("24100"), expiry=None)]
    facts = await readers.entry_facts_now(_ctx(_quote(D("24100.55"))), "NIFTY", sold)
    assert facts is not None and facts.entry_spot == D("24100.55")


# ---- Lane FR item 6 (K2 finding F1): a ticked first fill with the feed down still stores its entry facts ---------------
def _down(quote):
    ctx = _ctx(quote)
    ctx.provider.status = lambda: SimpleNamespace(connected=False)
    return ctx


async def test_a_ticked_first_fill_with_the_feed_down_stores_the_held_index_value():
    sold = [SimpleNamespace(instrument_type="CE", strike=D("24100"), expiry=None)]
    facts = await readers.entry_facts_now(_down(OLD), "NIFTY", sold, confirmed=True)
    print("FEED DOWN, TICKED", facts)
    assert facts is not None and facts.entry_spot == D("24087.30")


async def test_with_the_feed_down_and_no_tick_nothing_is_stored_and_a_flagged_quote_never_is():
    sold = [SimpleNamespace(instrument_type="CE", strike=D("24100"), expiry=None)]
    assert await readers.entry_facts_now(_down(OLD), "NIFTY", sold) is None
    assert await readers.entry_facts_now(_down(CROSSED), "NIFTY", sold, confirmed=True) is None
    assert await readers.entry_facts_now(None, "NIFTY", sold, confirmed=True) is None


async def test_the_first_fill_reader_holds_an_index_nobody_subscribed_yet(monkeypatch):
    """The index not yet on the book (quote None) is held on the shared fan-out, as ``_index_spot_held`` does."""
    sold = [SimpleNamespace(instrument_type="CE", strike=D("24100"), expiry=None)]
    book: list = []
    provider = SimpleNamespace(status=lambda: SimpleNamespace(connected=True),
                               underlying_quote=lambda _u: book[0] if book else None)
    ctx = SimpleNamespace(provider=provider, clock=lambda: NOW)
    monkeypatch.setattr("ofo_app.chain_push.index_id_of", lambda _c, _u: "256265")
    held: list = []

    async def read_quotes(feed, ids, read, ready, connected, wait, poll):
        held.append(ids)
        book.append(_quote(D("24100.55")))
        return read()
    monkeypatch.setattr(readers, "read_quotes", read_quotes)
    facts = await readers.entry_facts_now(ctx, "NIFTY", sold, feed=object())
    assert held == [["256265"]] and facts is not None and facts.entry_spot == D("24100.55")
