"""REQ-001 AC-1/AC-4 (W-129): every route and socket that takes an underlying refuses a value outside the supported set
with the same catalogue message (gate_underlying_unsupported, USER_INPUT_101), wrong case included. No database."""
from __future__ import annotations

import datetime
from typing import get_args

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
from ofo_app.db import get_db
from ofo_app.main import create_app
from ofo_app.routes.catalogue import get_today
from ofo_app.routes.chain import REST_PATH
from ofo_app.routes.ready_made import LoadTemplateIn, QuickPickIn
from ofo_app.underlying import Underlying, refusal_of
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _unused_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validation answers before any query; the settings still need a URL, which is never connected to."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")


CODE = "USER_INPUT_101"
INVALID = "USER_INPUT_002"
SERVER_ERROR = 500
REFUSED = 422
LEG = {"contract_id": 1, "action": "BUY", "quantity": 75}


def _calls(value: str) -> list[tuple[str, str, dict]]:
    return [
        ("POST", "/api/strategies/outcome", {"underlying": value, "legs": []}),
        ("POST", "/strategies", {"underlying": value, "legs": [LEG]}),
        ("PUT", "/strategies/1", {"underlying": value, "legs": [LEG], "expected_revision": 1}),
        ("POST", "/api/strategies/planned-entry", {"underlying": value, "instrument_ids": ["NSE_FO:1"]}),
        ("GET", f"{REST_PATH}?underlying={value}&expiry=2026-10-29", {}),
        ("GET", f"/api/catalogue/{value}/expiries", {}),
        ("GET", f"/api/catalogue/{value}/contracts?expiry=2026-10-29", {}),
    ]


async def _send(method: str, path: str, body: dict):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: None  # the refusal comes before any read
    app.dependency_overrides[get_today] = lambda: datetime.date(2026, 10, 22)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.request(method, path, json=body or None)


@pytest.mark.parametrize("value", ["BANKNIFTY", "nifty", "Sensex"])
@pytest.mark.parametrize("index", range(7))
async def test_every_route_refuses_an_unsupported_underlying_the_same_way(value: str, index: int) -> None:
    method, path, body = _calls(value)[index]
    resp = await _send(method, path, body)
    assert resp.status_code == REFUSED, (path, resp.text)
    assert CODE in resp.text, (path, resp.text)
    assert "Supported underlyings: " + ", ".join(SUPPORTED_UNDERLYINGS) in resp.text
    assert INVALID not in resp.text
    assert f"{value} is not supported." in resp.text  # echoed as typed, never rewritten


@pytest.mark.parametrize("value", ["BANK-NIFTY", "x" * 30, "N I"])
async def test_a_non_symbol_is_the_fixed_input_error_and_never_echoed(value: str) -> None:
    resp = await _send("POST", "/api/strategies/outcome", {"underlying": value, "legs": []})
    assert resp.status_code == REFUSED
    assert INVALID in resp.text and value not in resp.text


async def test_a_supported_underlying_is_not_refused_by_the_type() -> None:
    resp = await _send("POST", "/api/strategies/outcome", {"underlying": "NIFTY", "legs": []})
    assert CODE not in resp.text


def test_refusal_of_ignores_other_problems() -> None:
    assert refusal_of([{"type": "missing", "loc": ("body", "underlying"), "input": None}]) is None
    assert refusal_of([{"type": "literal_error", "loc": ("body", "kind"), "input": "x"}]) is None


def test_the_type_is_built_from_the_home_set() -> None:
    assert set(get_args(Underlying)) == set(SUPPORTED_UNDERLYINGS)


@pytest.mark.parametrize("value", ["BANKNIFTY", "nifty"])
@pytest.mark.parametrize("model,body", [
    (LoadTemplateIn, {"template_id": "x", "expiry": "2026-10-29"}),
    (QuickPickIn, {"kind": "straddle", "distance": 0, "side": "BUY"}),
])
def test_the_held_ready_made_bodies_refuse_it_too(value: str, model: type, body: dict) -> None:
    """The ready-made routes answer 'held' before reading a body (Q211); the body models carry the same type."""
    with pytest.raises(ValidationError) as caught:
        model.model_validate({"underlying": value, **body})
    message = refusal_of(caught.value.errors())
    assert message is not None and message.code == CODE


async def test_an_index_row_as_a_leg_is_refused_not_a_500() -> None:
    resp = await _send("POST", "/api/strategies/outcome", {
        "underlying": "NIFTY", "legs": [{"instrument_id": "NSE_INDEX:256265", "action": "BUY", "lots": 1,
                                         "planned_entry": "100.00", "captured_at": "2026-10-22T09:20:00+05:30"}]})
    assert resp.status_code < SERVER_ERROR, resp.text


async def test_an_index_row_as_a_leg_with_a_provider_is_refused_with_a_catalogue_message() -> None:
    """AC-2: the catalogue's INDEX row (NSE_INDEX:1001) is not a CE/PE/FUT leg; with a live provider the outcome route
    must answer a catalogue refusal, not a 500."""
    import pathlib
    import sys
    from decimal import Decimal

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests"))
    from marketdata._kite_fixture import all_instrument_ids, new_provider, replay

    from ofo.marketdata.kite_provider import IST
    from ofo_app.routes.outcome import MarketContext, get_market_context

    valuation = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: valuation, Decimal("0.065"))
    leg = {"instrument_id": provider.index_id("NIFTY"), "action": "BUY", "lots": 1, "planned_entry": "100.00",
           "captured_at": valuation.isoformat()}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/strategies/outcome", json={"underlying": "NIFTY", "legs": [leg]})
    assert resp.status_code < SERVER_ERROR, resp.text
    assert "unknown instrument" in resp.text, resp.text  # the leg is named unvalued by the catalogue explanation
