"""W-125 (REQ-079 AC-1..AC-9, AC-11): POST /api/strategies/load-template and /quick-pick, over the real app door.

No database, no Kite: the stored-catalogue reader and the market context are overridden seams (like test_chain_live.py).
Hand-computed expectations: grid 22000..23500 step 50, spot 22810 -> ATM 22800 (10 away; 22850 is 40 away).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app.catalogue_picker import PickableContract
from ofo_app.chain_push import ChainCatalogue
from ofo_app.routes import chain, outcome
from ofo_app.routes.outcome import MarketContext
from starlette.testclient import TestClient

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 22, 10, 0, 0, tzinfo=IST)
NEAR, NEXT = datetime.date(2026, 10, 27), datetime.date(2026, 11, 3)
GRID = [Decimal(22000 + 50 * i) for i in range(31)]  # 22000 .. 23500
NIFTY_ID = "NSE_INDEX:256265"
LABEL = "Strikes placed by a fixed rule - change them"
LOAD, PICK = "/api/strategies/load-template", "/api/strategies/quick-pick"
HTTP_OK, HTTP_CONFLICT, HTTP_UNPROCESSABLE, HTTP_UNAVAILABLE = 200, 409, 422, 503
HELD_SENTENCE = "Ready-made shapes and quick picks are not available yet."


def _contracts(expiry, base):
    out = []
    for i, strike in enumerate(GRID):
        for j, side in enumerate(("CE", "PE")):
            token = base + 2 * i + j
            out.append(PickableContract(token, f"NSE_FO:{token}", "NSE_FO", token, side, expiry, strike, 75,
                                        f"NIFTY{expiry:%y%m%d}{strike}{side}"))
    return tuple(out)


CATALOGUES = {NEAR: ChainCatalogue(expiries=(NEAR, NEXT), contracts=_contracts(NEAR, 40000)),
              NEXT: ChainCatalogue(expiries=(NEAR, NEXT), contracts=_contracts(NEXT, 50000))}


class Reader:
    def __init__(self) -> None:
        self.calls: list[datetime.date] = []

    async def __call__(self, underlying, expiry):
        self.calls.append(expiry)
        return CATALOGUES.get(expiry, ChainCatalogue(expiries=(NEAR, NEXT), contracts=()))


class Provider:
    def __init__(self, ltp, health=DataHealth.AVAILABLE) -> None:
        self.quote = NormalizedQuote(NIFTY_ID, "NIFTY", "NSE", "INDICES", None, None, None, Decimal(ltp), None, None,
                                     None, None, None, None, None, None, None, None, T0,
                                     SourceMetadata("fake", "fake-feed"), health)

    def index_id(self, underlying):
        return NIFTY_ID

    def underlying_quote(self, underlying):
        return self.quote


def _client(monkeypatch, tmp_path, *, env="development", ctx=None, reader=None):
    from ofo_app.main import create_app  # noqa: PLC0415

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", env)
    app = create_app()
    reader = reader or Reader()
    app.dependency_overrides[outcome.get_market_context] = lambda: ctx
    app.dependency_overrides[chain.get_chain_reader] = lambda: reader
    return TestClient(app), reader


def _ctx(ltp="22810", health=DataHealth.AVAILABLE):
    return MarketContext(Provider(ltp, health), lambda: T0, Decimal("0.065"))


def _legs(body):
    return [(leg["action"], leg["instrument"], leg["strike"], leg["expiry"]) for leg in body["legs"]]


def test_core_ac3_bull_call_spread_and_strangle_over_the_door(monkeypatch, tmp_path):
    """Core / AC-3 / AC-7 / AC-4: NIFTY 22,810 -> BUY 22800 CE / SELL 23000 CE; strangle 100 SELL -> SELL 22700 PE /
    SELL 22900 CE; every leg is a listed contract with the verbatim label."""
    client, _ = _client(monkeypatch, tmp_path, ctx=_ctx())
    r = client.post(LOAD, json={"underlying": "NIFTY", "template_id": "bull_call_spread", "expiry": NEAR.isoformat()})
    assert r.status_code == HTTP_OK, r.text
    n = NEAR.isoformat()
    assert _legs(r.json()) == [("BUY", "CE", "22800.00", n), ("SELL", "CE", "23000.00", n)]
    assert {leg["label"] for leg in r.json()["legs"]} == {LABEL}
    ids = {c.instrument_id for c in CATALOGUES[NEAR].contracts}
    assert all(leg["instrument_id"] in ids for leg in r.json()["legs"])
    q = client.post(PICK, json={"underlying": "NIFTY", "kind": "strangle", "distance": 100, "side": "SELL",
                                "expiry": n})
    assert _legs(q.json()) == [("SELL", "PE", "22700.00", n), ("SELL", "CE", "22900.00", n)]


def test_ac1_switch_off_refuses_before_any_read_and_places_nothing(monkeypatch, tmp_path):
    """AC-1 / AC-11: production without a reference -> 409 with the held sentence, zero catalogue reads."""
    client, reader = _client(monkeypatch, tmp_path, env="production", ctx=_ctx())
    for path, body in ((LOAD, {"underlying": "NIFTY", "template_id": "bull_call_spread", "expiry": NEAR.isoformat()}),
                       (PICK, {"underlying": "NIFTY", "kind": "straddle", "distance": 0, "side": "BUY",
                               "expiry": NEAR.isoformat()})):
        r = client.post(path, json=body)
        assert r.status_code == HTTP_CONFLICT and HELD_SENTENCE in r.text, (path, r.text)
    assert reader.calls == []


def test_ac11_a_request_cannot_turn_the_switch_on(monkeypatch, tmp_path):
    """Attack case: body field, header, query and cookie naming the switch change nothing (body field is refused)."""
    client, reader = _client(monkeypatch, tmp_path, env="production", ctx=_ctx())
    body = {"underlying": "NIFTY", "template_id": "bull_call_spread", "expiry": NEAR.isoformat()}
    r = client.post(LOAD + "?OFO_HELD_PLATFORM_STRIKES=on", json=body, headers={"OFO_HELD_PLATFORM_STRIKES": "on"},
                    cookies={"OFO_HELD_PLATFORM_STRIKES": "on"})
    assert r.status_code == HTTP_CONFLICT and reader.calls == []
    r2 = client.post(LOAD, json={**body, "platform_strikes": True})
    assert r2.status_code in (HTTP_CONFLICT, HTTP_UNPROCESSABLE) and "legs" not in r2.text


def test_ac3_and_ac6_calendar_spread_places_both_expiries_and_is_refused_without_a_next_one(monkeypatch, tmp_path):
    """AC-6 / ADR-157: calendar spread on NEAR uses NEXT for the far leg; on NEXT (no later expiry) it is a catalogue
    message with a 4xx status, never a 500."""
    client, _ = _client(monkeypatch, tmp_path, ctx=_ctx())
    ok = client.post(LOAD, json={"underlying": "NIFTY", "template_id": "calendar_spread", "expiry": NEAR.isoformat()})
    assert _legs(ok.json()) == [("SELL", "CE", "22800.00", NEAR.isoformat()),
                                ("BUY", "CE", "22800.00", NEXT.isoformat())]
    refused = client.post(LOAD, json={"underlying": "NIFTY", "template_id": "calendar_spread",
                                      "expiry": NEXT.isoformat()})
    assert refused.status_code == HTTP_UNPROCESSABLE and "does not have in the instrument list" in refused.text


@pytest.mark.parametrize("ctx", [None, _ctx(health=DataHealth.UNHEALTHY), _ctx(health=DataHealth.UNAVAILABLE)])
def test_ac8_missing_or_stale_spot_is_refused_with_the_reason(monkeypatch, tmp_path, ctx):
    """AC-8: no live feed, or an unhealthy / unavailable index value -> the spot message, nothing placed."""
    client, _ = _client(monkeypatch, tmp_path, ctx=ctx)
    r = client.post(LOAD, json={"underlying": "NIFTY", "template_id": "bull_call_spread", "expiry": NEAR.isoformat()})
    assert r.status_code == HTTP_UNAVAILABLE and "missing or out of date" in r.text and "legs" not in r.text


def test_ac7_a_distance_not_offered_and_an_unknown_template_are_refused(monkeypatch, tmp_path):
    """AC-7: distance 75 is refused; an unknown template id is the fixed input message."""
    client, _ = _client(monkeypatch, tmp_path, ctx=_ctx())
    bad = client.post(PICK, json={"underlying": "NIFTY", "kind": "strangle", "distance": 75, "side": "SELL",
                                  "expiry": NEAR.isoformat()})
    assert bad.status_code == HTTP_UNPROCESSABLE and "not one of the distances offered" in bad.text
    unknown = client.post(LOAD, json={"underlying": "NIFTY", "template_id": "no_such", "expiry": NEAR.isoformat()})
    assert unknown.status_code == HTTP_UNPROCESSABLE and "legs" not in unknown.text


def test_ac6_an_expiry_the_stored_list_does_not_hold_is_refused(monkeypatch, tmp_path):
    """AC-6: an expiry outside the underlying's listed expiries -> catalogue message, not a server error."""
    client, _ = _client(monkeypatch, tmp_path, ctx=_ctx())
    r = client.post(LOAD, json={"underlying": "NIFTY", "template_id": "bull_call_spread", "expiry": "2026-12-29"})
    assert r.status_code == HTTP_UNPROCESSABLE and "does not have" in r.text


def test_ac4_futures_templates_are_refused_not_half_loaded(monkeypatch, tmp_path):
    """The stored option list has no future for a covered call: the whole load is refused (strike-not-listed)."""
    client, _ = _client(monkeypatch, tmp_path, ctx=_ctx())
    r = client.post(LOAD, json={"underlying": "NIFTY", "template_id": "covered_call", "expiry": NEAR.isoformat()})
    assert r.status_code == HTTP_UNPROCESSABLE and "legs" not in r.text
