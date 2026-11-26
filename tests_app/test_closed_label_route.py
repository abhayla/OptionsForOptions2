"""ADR-330 (36) (LR-Q18) through the real outcome route: the banner sentence is the server's (``closed_prices_text``),
built by the one closed_label function. Replayed real recording; condor legs are removed from the book and first priced
after the close (15:33:48) by a real frame. Paper only; no database."""
from __future__ import annotations

import datetime

from httpx import ASGITransport, AsyncClient
from ofo.marketdata.kite_provider import IST
from test_builder_after_hours import AFTER_CLOSE, CONDOR, _app, _condor, _held_ltp, _replayed
from test_strategy_tracking import _frame

LATE = datetime.datetime(2026, 10, 8, 15, 33, 48, tzinfo=IST)
READ_AT = datetime.datetime(2026, 10, 8, 15, 34, 0, tzinfo=IST)
HTTP_OK = 200


def _hms(t: datetime.datetime) -> str:
    return t.astimezone(IST).strftime("%H:%M:%S")


async def _post(provider, clock, body: dict) -> dict:
    clock.now = READ_AT
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        resp = await ac.post("/api/strategies/outcome", json=body)
    assert resp.status_code == HTTP_OK, resp.text
    return resp.json()


def _first_price_after_close(provider, clock, instrument_ids: list[str]) -> None:
    for iid in instrument_ids:
        provider.book.remove(iid)
        provider.subscribe([iid])
        clock.now = LATE
        provider.on_frame(_frame(provider, iid, "50.00"), LATE)


async def test_outcome_with_one_leg_first_priced_after_the_close_reads_one_leg_as_of():
    provider, clock, _last = _replayed()
    body = _condor(provider, AFTER_CLOSE)
    frozen = [provider.book.get(iid, AFTER_CLOSE).timestamp for iid, _ in CONDOR[:3]]
    _first_price_after_close(provider, clock, [CONDOR[3][0]])
    out = await _post(provider, clock, body)
    assert out["market_closed"] is True
    assert out["closed_prices_text"].startswith("Market closed. Prices are from ")
    assert out["closed_prices_text"].endswith(f"; 1 leg as of {_hms(LATE)}.")
    assert datetime.datetime.fromisoformat(out["last_price_at"]) <= datetime.datetime(2026, 10, 8, 15, 30, tzinfo=IST)
    assert datetime.datetime.fromisoformat(out["last_price_at"]) >= max(frozen)
    print("ONE LEG:", out["closed_prices_text"])


async def test_outcome_with_two_legs_first_priced_after_the_close_reads_the_plural():
    provider, clock, _last = _replayed()
    body = _condor(provider, AFTER_CLOSE)
    _first_price_after_close(provider, clock, [CONDOR[2][0], CONDOR[3][0]])
    out = await _post(provider, clock, body)
    assert out["closed_prices_text"].endswith(f"; 2 legs as of {_hms(LATE)}.")


async def test_outcome_with_every_leg_frozen_carries_no_added_text():
    provider, clock, _last = _replayed()
    out = await _post(provider, clock, _condor(provider, AFTER_CLOSE))
    assert out["market_closed"] is True and out["closed_prices_text"] is None


async def test_outcome_with_every_leg_first_priced_after_the_close_is_as_built_today():
    provider, clock, _last = _replayed()
    body = _condor(provider, AFTER_CLOSE)
    _first_price_after_close(provider, clock, [iid for iid, _ in CONDOR])
    out = await _post(provider, clock, body)
    assert out["closed_prices_text"] is None
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == LATE  # the banner reads "Prices are from 15:33:48."


async def test_outcome_in_session_carries_no_added_text():
    provider, clock, _last = _replayed()
    at = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
    body = _condor(provider, at)
    clock.now = at
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        out = (await ac.post("/api/strategies/outcome", json=body)).json()
    assert out["market_closed"] is False and out["closed_prices_text"] is None
    assert _held_ltp(provider, CONDOR[0][0])  # the recording is still held
