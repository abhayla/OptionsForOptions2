"""W-068: the planned-entry price rule (ADR-068 item 1, ADR-020 Q185 "no fake prices"), on the real 2026-10-08 replay
and on single-field variations of a real quote."""
import dataclasses
from decimal import Decimal

import pytest

from ofo.outcome.planned_entry import PlannedEntry, planned_entry_of
from ofo.rules.inputs import DataHealth

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay

D = Decimal
LIVE_ID, NO_QUOTE_ID = "NSE_FO:44616", "NSE_FO:47455"


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    last = replay(provider, clock)
    return provider, last


def _quote(replayed, **changes):
    provider, last = replayed
    return dataclasses.replace(provider.book.get(LIVE_ID, last), **changes)


def test_a_real_live_quote_gives_its_ltp(replayed):
    provider, last = replayed
    quote = provider.book.get(LIVE_ID, last)
    assert quote.health is DataHealth.AVAILABLE and quote.ltp > 0
    assert planned_entry_of(quote) == PlannedEntry(quote.ltp.quantize(D("0.01")), "ltp")


def test_a_leg_with_no_quote_has_no_price(replayed):
    provider, last = replayed
    assert provider.book.get(NO_QUOTE_ID, last) is None or planned_entry_of(provider.book.get(NO_QUOTE_ID, last)) is None
    assert planned_entry_of(None) is None


def test_ltp_wins_over_the_mid(replayed):
    got = planned_entry_of(_quote(replayed, ltp=D("104.65"), bid=D("1.00"), ask=D("2.00")))
    assert got == PlannedEntry(D("104.65"), "ltp")


def test_mid_only_when_there_is_no_ltp(replayed):
    assert planned_entry_of(_quote(replayed, ltp=None, bid=D("100.00"), ask=D("100.05"))) == PlannedEntry(D("100.03"), "mid")
    assert planned_entry_of(_quote(replayed, ltp=None, bid=D("100.00"), ask=D("101.00"))) == PlannedEntry(D("100.50"), "mid")


@pytest.mark.parametrize("changes", [
    dict(ltp=None, bid=D("100.00"), ask=None),  # one side only
    dict(ltp=None, bid=None, ask=None),
    dict(ltp=D("0"), bid=D("100"), ask=D("101")),  # a zero LTP is not a price and does not fall back to a mid
    dict(ltp=None, bid=D("0"), ask=D("101")),
    dict(ltp=D("104.65"), health=DataHealth.STALE),
    dict(ltp=D("104.65"), health=DataHealth.DELAYED),
    dict(ltp=D("104.65"), health=DataHealth.UNHEALTHY),
    dict(ltp=D("104.65"), health=DataHealth.UNAVAILABLE),
])
def test_everything_else_gives_no_price(replayed, changes):
    assert planned_entry_of(_quote(replayed, **changes)) is None
