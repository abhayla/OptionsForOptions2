"""Lane N B2 (ADR-330 (28), ADR-283 (1)): a paper entry saved while the index quote is not live. Without the user's
confirmed "prices are not live" line the save is refused as before; with it the last index value the app holds is the
rule starting point (its own time is read with it). Unit tests on the reader with fakes (no database)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo.rules.inputs import DataHealth
from ofo_app import adjustment_readers as readers
from ofo_app.routes import paper
from ofo_app.strategy_refused import StrategyRefused

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 11, 27, 15, 8, tzinfo=IST)
QUOTE_AT = datetime.datetime(2026, 11, 27, 14, 46, tzinfo=IST)


def _ctx(*, connected, quote, closed=False):
    provider = SimpleNamespace(status=lambda: SimpleNamespace(connected=connected),
                               underlying_quote=lambda _u: quote)
    return SimpleNamespace(provider=provider, clock=lambda: NOW, closed=closed)


def _quote(ltp, health=DataHealth.AVAILABLE):
    return SimpleNamespace(ltp=ltp, price_at=QUOTE_AT, timestamp=QUOTE_AT, health=health, validation_errors=())


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(readers, "_scenario", lambda: None)
    monkeypatch.setattr(readers, "market_state", lambda ctx, _now: SimpleNamespace(closed=ctx.closed))
    monkeypatch.setattr("ofo_app.chain_push.index_id_of", lambda _c, _u: None)


async def _spot(ctx, confirmed):
    return await readers._index_spot_held(ctx, None, "NIFTY", confirmed)


async def test_fresh_tick_is_unchanged_with_or_without_the_flag():
    ctx = _ctx(connected=True, quote=_quote(D("24100.55")))
    assert await _spot(ctx, False) == D("24100.55")
    assert await _spot(ctx, True) == D("24100.55")


async def test_not_connected_and_confirmed_uses_the_last_held_value_with_its_time():
    ctx = _ctx(connected=False, quote=_quote(D("24087.30")))
    assert readers._index_value_not_live(ctx, "NIFTY") == (D("24087.30"), QUOTE_AT)
    got = await _spot(ctx, True)
    assert got == D("24087.30")
    assert isinstance(got, D)


async def test_not_connected_and_not_confirmed_is_refused_as_before():
    ctx = _ctx(connected=False, quote=_quote(D("24087.30")))
    with pytest.raises(StrategyRefused) as e:
        await _spot(ctx, False)
    assert e.value.args[0] == "paper_index_price_unavailable"


async def test_no_index_value_ever_and_confirmed_is_refused_with_its_reason():
    with pytest.raises(StrategyRefused) as e:
        await _spot(_ctx(connected=False, quote=None), True)
    assert e.value.args[0] == "paper_index_price_unavailable"
    with pytest.raises(StrategyRefused):
        await _spot(_ctx(connected=False, quote=_quote(D("0"))), True)
    with pytest.raises(StrategyRefused):
        await _spot(None, True)


async def test_market_closed_and_confirmed_uses_the_last_close(monkeypatch):
    close_at = datetime.datetime(2026, 11, 26, 15, 30, tzinfo=IST)
    monkeypatch.setattr(readers, "read_last_close",
                        lambda _q, closed, _s, _n: SourceReading(SourceState.STATED, D("24010.10"), close_at)
                        if closed else SourceReading(SourceState.ABSENT))
    ctx = _ctx(connected=False, quote=None, closed=True)
    assert readers._index_value_not_live(ctx, "NIFTY") == (D("24010.10"), close_at)
    assert await _spot(ctx, True) == D("24010.10")
    with pytest.raises(StrategyRefused):
        await _spot(ctx, False)


def test_the_order_request_carries_the_flag_default_false_and_the_typed_price_is_an_exact_decimal():
    order = {"contract_id": 1, "side": "SELL", "quantity": 75, "price": "39.15", "kind": "open"}
    body = paper.PaperOrdersIn.model_validate({"orders": [order]})
    assert body.prices_not_live_confirmed is False
    assert body.orders[0].price == D("39.15")
    assert isinstance(body.orders[0].price, D)
    on = paper.PaperOrdersIn.model_validate({"orders": [order], "prices_not_live_confirmed": True})
    assert on.prices_not_live_confirmed is True
    assert on.orders[0].price == D("39.15")


async def test_connected_but_too_old_index_quote_needs_the_tick_adr330_39():
    ctx = _ctx(connected=True, quote=_quote(D("24087.30"), DataHealth.STALE))
    with pytest.raises(StrategyRefused) as e:
        await _spot(ctx, False)
    assert e.value.args[0] == "paper_index_price_unavailable"
    got = await _spot(ctx, True)
    assert got == D("24087.30")
    assert isinstance(got, D)
