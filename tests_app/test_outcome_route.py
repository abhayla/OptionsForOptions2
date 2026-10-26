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

from marketdata._kite_fixture import all_instrument_ids, new_provider, new_provider_with_futures, replay  # noqa: E402

from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo.outcome import read_snapshot  # noqa: E402

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


async def _post(body, provider=None, stored_lookup=None):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_contract_lookup, get_market_context

    app = create_app()
    if stored_lookup is not None:  # the stored catalogue answers for the legs, at the replay's clock
        app.dependency_overrides[get_contract_lookup] = lambda: stored_lookup
        app.dependency_overrides[get_answer_clock] = lambda: (lambda: VALUATION)
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
                        "table", "scenario", "payoff", "summary", "leg_quotes", "charges_breakdown"}
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


async def test_a_session_that_ended_is_from_your_prices_and_carries_no_leg_quotes():
    """REQ-049 AC-4/AC-5 / ADR-168 (5): leg_quotes only for a live computed answer. After the Kite session ends every
    leg is priced, so the answer is FROM_ENTRIES (REQ-077 AC-9) and the held bid/ask is not shown."""
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    live = (await _post(_body(provider), provider)).json()
    assert live["state"] == "COMPUTED" and len(live["leg_quotes"]) == len(CONDOR)
    provider.on_session_ended(VALUATION)
    out = (await _post(_body(provider), provider)).json()
    assert out["state"] == "FROM_ENTRIES" and out["output_label"] == LABEL_FROM_ENTRIES
    assert "leg_quotes" not in out


async def test_no_provider_has_no_leg_quotes(replayed):
    out = (await _post(_body(replayed))).json()
    assert out["state"] == "NOT_CONNECTED" and "leg_quotes" not in out


async def test_route_returns_the_scenario_heading_pair(replayed):
    """REQ-035 AC-7: the route's table carries the heading pair as two parts (no database needed)."""
    resp = await _post(_body(replayed), replayed)
    assert resp.is_success, resp.text
    assert resp.json()["table"]["scenario_heading"] == ["NIFTY at expiry", "You make/lose"]


# ---- REQ-077 AC-9 (row 21d): no live data, every leg priced -> At Expiry from the user's prices --------------------

LABEL_FROM_ENTRIES = "From your prices - no live data"
SPREAD = (("NSE_FO:44624", "BUY", "81.30"), ("NSE_FO:44632", "SELL", "30.00"))


def _spread_body(view="at_expiry", fallback=False):
    legs = [{"instrument_id": iid, "action": action, "lots": 1, "planned_entry": entry,
             "captured_at": VALUATION.isoformat()} for iid, action, entry in SPREAD]
    return {"underlying": "NIFTY", "legs": legs, "view": view, "fallback": fallback}


def provider_for_catalogue():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


async def _post_stored(body, provider=None):
    """Like _post, with the stored catalogue answering for the legs (the database read replaced by the replay's)."""
    snap = read_snapshot(provider_for_catalogue(), "NIFTY", [iid for iid, *_ in SPREAD], VALUATION, RATE)
    found = {iid: snap.legs[iid].contract for iid, *_ in SPREAD}

    async def lookup(ids):
        return {i: found[i] for i in ids if i in found}

    return await _post(body, provider, stored_lookup=lookup)


async def test_no_provider_every_leg_priced_shows_at_expiry_from_the_users_prices():
    resp = await _post_stored(_spread_body())
    assert resp.is_success, resp.text
    out = resp.json()
    assert out["state"] == "FROM_ENTRIES" and out["status_label"] == LABEL_FROM_ENTRIES
    assert out["output_label"] == LABEL_FROM_ENTRIES and "22,800" in out["centre_label"]
    assert out["spot_level"] is None and out["spot_at"] is None
    assert out["summary"]["max_loss"] == "3334.50" and out["summary"]["max_profit"] == "9665.50"
    assert "leg_quotes" not in out  # no Bid/Ask: nothing here is a live quote
    assert all(leg["ltp"] is None and leg["iv"] is None and leg["health"] is None for leg in out["legs"])
    assert out["table"]["spot_level"] is None and out["scenario"]["available"] is True
    assert not any(lv["current"] for lv in out["scenario"]["levels"])
    assert out["margin"]["state"] == "NOT_AVAILABLE_YET"
    _no_floats(out)


async def test_no_provider_estimated_now_is_unavailable_with_its_reason():
    out = (await _post_stored(_spread_body("estimated_now"))).json()
    assert out["state"] == "FROM_ENTRIES"
    assert out["scenario"]["available"] is False and out["scenario"]["totals"] is None
    assert "needs live prices" in out["scenario"]["unavailable_reason"]
    assert out["payoff"]["points"] == []


async def test_no_provider_and_no_stored_contract_keeps_the_not_connected_answer():
    out = (await _post(_spread_body())).json()  # no database in this process: the catalogue answers nothing
    assert out["state"] == "NOT_CONNECTED" and out["status_label"] == "Draft — Live data not connected"
    assert out["table"] is None and out["summary"] is None and "leg_quotes" not in out


async def test_a_dropped_socket_fallback_is_from_entries_with_no_leg_quotes(replayed):
    out = (await _post_stored(_spread_body(fallback=True), replayed)).json()
    assert out["state"] == "FROM_ENTRIES" and out["output_label"] == LABEL_FROM_ENTRIES  # REQ-077 AC-9 label
    assert out["status_label"].startswith("Live market data disconnected. Last updated: ")  # REQ-049 AC-5 message
    assert "leg_quotes" not in out and out["spot_level"] is None
    assert all(leg["ltp"] is None for leg in out["legs"])
    assert out["summary"]["max_loss"] == "3334.50"


async def test_an_ended_kite_session_every_leg_priced_is_from_entries_not_the_old_not_connected():
    """REQ-077 AC-9 "with no live data" includes a session that ended while the provider is up (the fallback flag is
    not even needed): At Expiry from the user's prices, no leg_quotes, no live value."""
    provider = provider_for_catalogue()
    provider.on_session_ended(VALUATION)
    assert provider.status().session_ended is True
    out = (await _post_stored(_spread_body(), provider)).json()
    assert out["state"] == "FROM_ENTRIES", out
    assert out["output_label"] == LABEL_FROM_ENTRIES and out["table"]["output_label"] == LABEL_FROM_ENTRIES
    assert out["status_label"].startswith("Live market data disconnected. Last updated: ")
    assert "leg_quotes" not in out and out["spot_level"] is None
    assert all(leg["ltp"] is None for leg in out["legs"])
    assert out["summary"]["max_loss"] == "3334.50" and out["summary"]["max_profit"] == "9665.50"


# ---- W-155 / REQ-135 AC-4: a strategy of one futures leg, on the recorded 2026-10-08 frames ----------------------
def provider_with_nifty_futures():
    """The replay provider with the real NIFTY futures rows of the instrument-list slice added (the recorded frames
    carry options only, so a futures leg has a listed contract but no quote of its own)."""
    provider, clock, items, futures = new_provider_with_futures("NIFTY")
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider, futures


def _future_body(futures, action):
    c = futures[1].contract  # NIFTY 27 Oct 2026 futures
    return {"underlying": "NIFTY", "legs": [{
        "instrument_id": f"{c.exchange_segment}:{c.exchange_token}", "action": action, "lots": 1,
        "planned_entry": "24000", "captured_at": VALUATION.isoformat()}]}


@pytest.mark.parametrize(("action", "unlimited_side", "finite_side"),
                         [("BUY", "max_profit", "max_loss"), ("SELL", "max_loss", "max_profit")])
async def test_a_lone_future_summary_body_carries_the_ac4_answers(action, unlimited_side, finite_side):
    """AC-4 on the real route: the unlimited side is null + its flag, the other side is finite, Reward/Risk is null
    with the reason 'No fixed maximum', Time value and Intrinsic value are 0.00 (a string, never a float)."""
    provider, futures = provider_with_nifty_futures()
    resp = await _post(_future_body(futures, action), provider)
    assert resp.is_success, resp.text
    out = resp.json()
    s = out["summary"]
    assert out["state"] == "COMPUTED"
    assert s[unlimited_side] is None and s[f"{unlimited_side}_unlimited"] is True
    assert s[finite_side] == "1560000" and s[f"{finite_side}_unlimited"] is False
    assert (s["reward_risk"], s["reward_risk_reason"]) == (None, "No fixed maximum")
    assert (s["time_value"], s["intrinsic_value"]) == ("0.00", "0.00")
    _no_floats(out)


async def test_a_bounded_strategy_summary_carries_the_money_figures_as_strings(replayed):
    """No rate table on this route: no ratio, since REQ-081 AC-4 wants both maximums including charges; the time and
    intrinsic value (AC-3) stay money strings."""
    s = (await _post(_body(replayed), replayed)).json()["summary"]
    assert (s["reward_risk"], s["risk_reward"]) == (None, None)
    assert s["reward_risk_reason"] == "the charges could not be priced, so the ratio is not shown"
    assert all(isinstance(s[k], str) for k in ("time_value", "intrinsic_value"))


async def test_every_outcome_leg_carries_days_to_expiry_counted_from_the_answers_ist_date(replayed):
    """AC-2: the condor legs expire 13 Oct, the answer is 8 Oct 09:20 IST -> 5 days; a futures leg 27 Oct -> 19."""
    legs = (await _post(_body(replayed), replayed)).json()["legs"]
    assert {leg["expiry"] for leg in legs} == {"2026-10-13"}
    assert [leg["days_to_expiry"] for leg in legs] == [5] * 4
    provider, futures = provider_with_nifty_futures()
    future_leg = (await _post(_future_body(futures, "BUY"), provider)).json()["legs"][0]
    assert (future_leg["expiry"], future_leg["days_to_expiry"]) == ("2026-10-27", 19)


async def test_the_day_count_follows_the_answers_ist_date_not_the_utc_date(replayed):
    """Off-by-one guard: 00:30 IST on 13 Oct is 19:00 UTC on 12 Oct; the legs expiring 13 Oct read 0, not 1."""
    from ofo_app.routes.outcome import MarketContext, OutcomeRequest, outcome_response

    utc_instant = datetime.datetime(2026, 10, 12, 19, 0, tzinfo=datetime.UTC)
    req = OutcomeRequest.model_validate(_body(replayed))
    legs = outcome_response(req, MarketContext(replayed, lambda: utc_instant, RATE)).model_dump(mode="json")["legs"]
    assert [leg["expiry"] for leg in legs] == ["2026-10-13"] * 4
    assert [leg["days_to_expiry"] for leg in legs] == [0] * 4


async def test_last_price_at_is_null_before_the_first_frame_and_an_aware_time_after_in_rest_and_push(replayed):
    """AC-3: the stamp reads the feed's own last price time. REST and the live push build the body with the same
    function (outcome_response), so they carry the same value; before any frame it is null."""
    from ofo_app.live_push import outcome_response as pushed  # the push loop's own import
    from ofo_app.routes.outcome import MarketContext, OutcomeRequest, outcome_response

    assert pushed is outcome_response
    after = (await _post(_body(replayed), replayed)).json()
    stamp = datetime.datetime.fromisoformat(after["last_price_at"])
    assert stamp.utcoffset() is not None
    req = OutcomeRequest.model_validate(_body(replayed))
    push = outcome_response(req, MarketContext(replayed, lambda: VALUATION, RATE)).model_dump(mode="json")
    assert datetime.datetime.fromisoformat(push["last_price_at"]) == stamp

    fresh, _clock, _items = new_provider()  # connected to nothing: no frame has arrived
    before = outcome_response(req, MarketContext(fresh, lambda: VALUATION, RATE)).model_dump(mode="json")
    assert before["last_price_at"] is None
