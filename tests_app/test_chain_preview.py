"""W-124 (REQ-031 AC-1/AC-2/AC-3, REQ-030 AC-14): POST /api/market/chain/preview on the recorded 2026-10-08 replay.

Core: the NIFTY 13-Oct iron condor (the same four legs as tests_app/test_outcome_route.py) previewed from the chain
carries exactly the outcome route's own net premium, max profit, max loss, breakevens and payoff points - the one engine,
no second call path. Expected values are READ from the outcome route's reply for the same legs (two doors, one engine),
and the fixed ones (4 legs) are the recorded replay's. The full table, Greeks and scenarios are NOT in the reply
(REQ-031 AC-3). No database, no network.
"""
from __future__ import annotations

import datetime
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
SHORT_CALL = (("NSE_FO:44624", "SELL"),)
PATH = "/api/market/chain/preview"
OUTCOME_PATH = "/api/strategies/outcome"
FOUR = 4


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _legs(provider, picks):
    return [{"instrument_id": iid, "action": action, "lots": 1,
             "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
            for iid, action in picks]


async def _post(path, body, provider=None):
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.outcome import MarketContext, get_market_context  # noqa: PLC0415

    app = create_app()
    if provider is not None:
        app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(path, json=body)


async def test_core_condor_preview_equals_the_outcome_routes_own_numbers(replayed):
    legs = _legs(replayed, CONDOR)
    prev = await _post(PATH, {"underlying": "NIFTY", "legs": legs}, replayed)
    full = await _post(OUTCOME_PATH, {"underlying": "NIFTY", "legs": legs}, replayed)
    assert prev.status_code == full.status_code == 200, (prev.text, full.text)
    p, f = prev.json(), full.json()
    assert p["state"] == "COMPUTED" and len(f["legs"]) == FOUR
    summary = f["summary"]
    assert (p["max_profit"], p["max_loss"], p["breakevens"]) == (summary["max_profit"], summary["max_loss"],
                                                                 summary["breakevens"])
    assert (p["max_profit_unlimited"], p["max_loss_unlimited"]) == (False, False)
    total = next(r for r in f["table"]["rows"] if r["row_id"] == "TOTAL")["cells"]["entry_value"]
    assert (p["net_premium"], p["net_side"]) == (total["value"], total["side"])
    assert p["net_side"] in ("Cr", "Dr") and p["payoff"] == f["payoff"]["points"] and p["payoff"]
    # REQ-031 AC-3: nothing of the full analysis is carried
    assert not {"table", "scenario", "legs", "margin", "advanced_details"} & set(p)
    assert Decimal(p["max_profit"]) > 0 and Decimal(p["max_loss"]) > 0  # a defined-risk condor: both numbers, no word


async def test_ac14_the_matched_template_name_is_shown_and_nothing_is_converted(replayed):
    p = (await _post(PATH, {"underlying": "NIFTY", "legs": _legs(replayed, CONDOR)}, replayed)).json()
    assert p["matched_template"] == "Iron Condor"
    assert not {"execute", "order", "basket", "converted"} & set(p)


async def test_one_naked_short_call_reads_unlimited_loss_not_a_number(replayed):
    p = (await _post(PATH, {"underlying": "NIFTY", "legs": _legs(replayed, SHORT_CALL)}, replayed)).json()
    assert (p["max_loss_unlimited"], p["max_loss"]) == (True, None)


async def test_no_feed_is_not_connected_with_no_number(replayed):
    p = (await _post(PATH, {"underlying": "NIFTY", "legs": _legs(replayed, CONDOR)})).json()
    assert p["state"] == "NOT_CONNECTED"
    assert (p["net_premium"], p["max_profit"], p["max_loss"], p["breakevens"], p["payoff"],
            p["matched_template"]) == (None, None, None, [], [], None)


async def test_socket_down_fallback_is_not_live_whatever_else_streams(replayed):
    body = {"underlying": "NIFTY", "legs": _legs(replayed, CONDOR), "fallback": True}
    p = (await _post(PATH, body, replayed)).json()
    assert p["state"] != "COMPUTED" and p["net_premium"] is None and p["payoff"] == []


@pytest.mark.parametrize("bad", [{"underlying": "NIFTY", "legs": []}, {"underlying": "BANKNIFTY", "legs": [1]},
                                 {"underlying": "NIFTY", "legs": [], "ux_level": "advanced"}])
async def test_a_bad_body_is_refused_422(replayed, bad):
    assert (await _post(PATH, bad, replayed)).status_code == 422
