"""Lane K2 item 1 (ADR-330 (28), (39)): the order door passes the trader's "prices are not live" tick to the first-fill
entry-facts reader. Without it a ticked first fill on a STALE index stored no entry facts, for good (one row per
strategy, never rewritten). Unit tests with fakes (no database)."""
from __future__ import annotations

import datetime
import inspect
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.rules.inputs import DataHealth
from ofo_app import adjustment_readers as readers
from ofo_app.routes import paper

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
AT = datetime.datetime(2026, 11, 27, 14, 46, tzinfo=IST)
EXPIRY = datetime.date(2026, 12, 1)


def _quote(ltp, health=DataHealth.AVAILABLE, errors=()):
    return SimpleNamespace(ltp=ltp, price_at=AT, timestamp=AT, health=health, validation_errors=errors)


def _ctx(quote):
    provider = SimpleNamespace(status=lambda: SimpleNamespace(connected=True), underlying_quote=lambda _u: quote)
    return SimpleNamespace(provider=provider, clock=lambda: AT, closed=False)


def _legs():
    contract = SimpleNamespace(instrument_type="CE", strike=D("24200"), expiry=EXPIRY)
    state = {1: SimpleNamespace(stored=SimpleNamespace(listed=SimpleNamespace(contract=contract)))}
    return [SimpleNamespace(contract_id=1, side="SELL", kind="open")], state


@pytest.fixture(autouse=True)
def _no_iv(monkeypatch):
    async def none_iv(*_a, **_k):
        return None
    monkeypatch.setattr(readers, "atm_iv_now", none_iv)


async def _facts(quote, confirmed):
    orders, state = _legs()
    return await paper.entry_facts(_ctx(quote), "NIFTY", orders, state, confirmed=confirmed)


async def test_ticked_first_fill_on_a_stale_index_stores_the_entry_facts():
    facts = await _facts(_quote(D("24087.30"), DataHealth.STALE), True)
    assert facts is not None
    assert facts.entry_spot == D("24087.30")


async def test_unticked_first_fill_on_a_stale_index_stores_nothing():
    assert await _facts(_quote(D("24087.30"), DataHealth.STALE), False) is None


async def test_live_index_stores_the_facts_with_or_without_the_tick():
    for confirmed in (False, True):
        facts = await _facts(_quote(D("24100.55")), confirmed)
        assert facts is not None
        assert facts.entry_spot == D("24100.55")


@pytest.mark.parametrize("quote", [
    _quote(D("24087.30"), DataHealth.UNHEALTHY),
    _quote(D("24087.30"), DataHealth.STALE, ("crossed_quote",)),
    _quote(D("0"), DataHealth.STALE),
])
async def test_flagged_crossed_or_unpriced_index_is_refused_even_when_ticked(quote):
    assert await _facts(quote, True) is None


def test_the_door_passes_the_tick_to_the_entry_facts_call():
    src = inspect.getsource(paper._place_orders)  # FD2: the door body moved behind place_paper_orders
    assert "confirmed=body.prices_not_live_confirmed" in src.split("entry_facts(", 1)[1].split("if first", 1)[0]
