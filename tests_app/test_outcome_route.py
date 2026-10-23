"""REQ-034 AC-1 (W-063): the NIFTY 13-Oct iron condor through POST /api/strategies/outcome on the real 2026-10-08
replay. Every part AC-1 names is present (P&L, max profit/loss, breakevens, payoff, scenario behaviour, margin as
NOT_AVAILABLE_YET, risk), every money/points value is a JSON string, and with no provider the route answers the
"Draft — Live data not connected" state. No database is needed."""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402

from ofo.marketdata.kite_provider import IST  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
CONDOR = (("NSE_FO:44624", "SELL"), ("NSE_FO:44632", "BUY"), ("NSE_FO:44604", "SELL"), ("NSE_FO:44595", "BUY"))
NUMBER_KEYS = {"value", "per_unit", "vendor", "strike", "planned_entry", "ltp", "iv", "spot_level", "level", "pnl",
               "max_profit", "max_loss", "lower_be", "upper_be", "step", "start", "end"}


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _body(provider):
    legs = [{"instrument_id": iid, "action": action, "lots": 1,
             "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
            for iid, action in CONDOR]
    return {"underlying": "NIFTY", "legs": legs}


async def _post(body, provider=None):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import MarketContext, get_market_context

    app = create_app()
    if provider is not None:
        app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post("/api/strategies/outcome", json=body)


def _no_floats(node, path="$"):
    """Every JSON number in the response is a bool/int count, never a float; named number keys are strings."""
    if isinstance(node, float):
        raise AssertionError(f"float at {path}")
    if isinstance(node, dict):
        for k, v in node.items():
            if k in NUMBER_KEYS and v is not None and not isinstance(v, (str, dict)):
                raise AssertionError(f"{path}.{k} is {type(v).__name__}, not a string")
            _no_floats(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _no_floats(v, f"{path}[{i}]")


async def test_condor_outcome_has_every_ac1_part(replayed):
    resp = await _post(_body(replayed), replayed)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert set(out) == {"state", "underlying", "status_label", "reason", "output_label", "valuation",
                        "answered_at", "market_closed", "last_price_at", "spot_level", "spot_at", "legs", "margin",
                        "table", "scenario", "payoff", "summary", "leg_quotes"}
    assert (out["state"], out["underlying"]) == ("COMPUTED", "NIFTY")
    assert out["spot_level"] == "22533.25"
    assert out["margin"]["state"] == "NOT_AVAILABLE_YET" and isinstance(out["margin"]["reason"], str)
    s = out["summary"]
    for key in ("what_can_i_lose", "what_can_i_make", "where_do_i_start_losing"):
        assert isinstance(s[key], str) and s[key]
    assert isinstance(s["max_profit"], str) and isinstance(s["max_loss"], str)
    assert len(s["breakevens"]) == 2 and all(isinstance(b, str) for b in s["breakevens"])
    assert s["risk_boundaries"] == ["22200", "23000"]  # risk: where the max loss is reached
    sc = out["scenario"]
    assert (sc["view"], sc["kind"], sc["available"]) == ("at_expiry", "exact", True)
    assert [lv["level"] for lv in sc["levels"] if lv["current"]] == ["22533.25"]
    pts = out["payoff"]["points"]
    assert [p["level"] for p in pts] == [lv["level"] for lv in sc["levels"]]
    assert [p["pnl"] for p in pts] == sc["totals"]
    total = next(r for r in out["table"]["rows"] if r["row_id"] == "TOTAL")
    assert [total["cells"][p["level"]]["value"] for p in pts] == [p["pnl"] for p in pts]
    assert isinstance(total["cells"]["unrealized_pnl"]["value"], str)  # P&L since the planned entry
    assert len(out["legs"]) == 4 and all(isinstance(leg["planned_entry"], str) for leg in out["legs"])
    assert [leg["quantity"] for leg in out["legs"]] == [65, 65, 65, 65]
    _no_floats(out)


async def test_a_request_carrying_the_retired_level_is_ignored(replayed):
    """REQ-006 / ADR-168 (4): `ux_level` is ignored: the same outcome, Bid/Ask present, no level key in the answer."""
    plain = (await _post(_body(replayed), replayed)).json()
    for level in ("guided", "advanced"):
        resp = await _post({**_body(replayed), "ux_level": level}, replayed)
        assert resp.is_success, resp.text
        out = resp.json()
        assert "ux_level" not in out
        assert out["table"] == plain["table"] and out["payoff"] == plain["payoff"]
        assert out["leg_quotes"] == plain["leg_quotes"] and len(out["leg_quotes"]) == len(CONDOR)
    resp = await _post({**_body(replayed), "nonsense": 1}, replayed)
    assert resp.is_client_error  # only the retired key is dropped; any other unknown key is still refused


async def test_no_provider_returns_not_connected_state(replayed):
    resp = await _post(_body(replayed))
    assert resp.status_code == 200
    out = resp.json()
    assert out["state"] == "NOT_CONNECTED"
    assert out["status_label"] == "Draft — Live data not connected"
    assert out["margin"]["state"] == "NOT_AVAILABLE_YET"
    assert out["table"] is None and out["payoff"] is None and out["summary"] is None
    assert [leg["planned_entry"] for leg in out["legs"]] == [leg["planned_entry"] for leg in _body(replayed)["legs"]]
    _no_floats(out)


async def test_float_planned_entry_is_refused(replayed):
    body = _body(replayed)
    body["legs"][0]["planned_entry"] = 104.65
    resp = await _post(body, replayed)
    assert resp.status_code == 422


def test_committed_openapi_schema_matches_the_route():
    from fastapi import FastAPI

    from ofo_app.routes import outcome

    app = FastAPI(title="OptionsForOptions2 API - outcome", version="0.1.0")
    app.include_router(outcome.router)
    committed = json.loads((ROOT / "docs" / "api" / "outcome.openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(app.openapi()))


async def test_leg_quotes_carry_bid_ask_for_everyone(replayed):
    """REQ-035 AC-5 / ADR-168 (5): bid/ask come in the leg_quotes block for every request, taken from the same
    snapshot as the table; the table's locked columns do not change."""
    out = (await _post(_body(replayed), replayed)).json()
    assert not any(c["id"] in ("bid", "ask") for c in out["table"]["columns"])
    assert all(c["visible"] for c in out["table"]["columns"])  # one column set: nothing hidden
    rows = out["leg_quotes"]
    assert [r["instrument_id"] for r in rows] == [iid for iid, _ in CONDOR]
    for r in rows:
        q = replayed.book.get(r["instrument_id"], VALUATION)
        assert r["bid"] == (None if q.bid is None else f"{q.bid:f}")
        assert r["ask"] == (None if q.ask is None else f"{q.ask:f}")
        assert isinstance(r["health"], str) and r["symbol"]
    assert any(r["bid"] is not None and r["ask"] is not None for r in rows)  # the recording carries depth
    _no_floats(out)


async def test_a_session_that_ended_is_not_connected_and_carries_no_leg_quotes():
    """REQ-049 AC-4/AC-5 / ADR-168 (5): leg_quotes only for a live computed answer. After the Kite session ends the
    answer is NOT_CONNECTED and the held bid/ask is not shown (class: every state other than COMPUTED)."""
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    live = (await _post(_body(provider), provider)).json()
    assert live["state"] == "COMPUTED" and len(live["leg_quotes"]) == len(CONDOR)
    provider.on_session_ended(VALUATION)
    out = (await _post(_body(provider), provider)).json()
    assert out["state"] == "NOT_CONNECTED" and out["status_label"] == "Draft — Live data not connected"
    assert "leg_quotes" not in out


async def test_no_provider_has_no_leg_quotes(replayed):
    out = (await _post(_body(replayed))).json()
    assert out["state"] == "NOT_CONNECTED" and "leg_quotes" not in out


async def test_route_returns_the_scenario_heading_pair(replayed):
    """REQ-035 AC-7: the route's table carries the heading pair as two parts (no database needed)."""
    resp = await _post(_body(replayed), replayed)
    assert resp.is_success, resp.text
    assert resp.json()["table"]["scenario_heading"] == ["NIFTY at expiry", "You make/lose"]
