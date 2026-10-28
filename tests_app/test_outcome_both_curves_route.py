"""GC-UI step 4 server through POST /api/strategies/outcome (REQ-083 AC-1/AC-4, REQ-137 AC-1/AC-3): the new request
options and their reply blocks on the real 2026-10-08 replay (strategy 54's shape: BUY 22600 CE / SELL 22800 CE
13-Oct). Absent options keep today's reply keys exactly. No database is needed."""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider_with_futures, replay  # noqa: E402

from ofo.marketdata.kite_provider import IST  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
S54 = (("NSE_FO:44616", "BUY"), ("NSE_FO:44624", "SELL"))


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items, _futures = new_provider_with_futures("NIFTY")
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _body(provider, **extra):
    legs = [{"instrument_id": iid, "action": action, "lots": 1,
             "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
            for iid, action in S54]
    return {"underlying": "NIFTY", "legs": legs, **extra}


async def _post(body, provider):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import MarketContext, get_market_context

    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post("/api/strategies/outcome", json=body)


async def test_both_views_flag_off_keeps_todays_keys_and_on_adds_curves(replayed):
    off = (await _post(_body(replayed), replayed)).json()
    on = (await _post(_body(replayed, both_views=True), replayed)).json()
    assert "curves" not in off and "other" not in off["scenario"]
    assert set(on) - set(off) == {"curves", "payoff_table"}  # both views also brings the two-column table
    assert on["curves"]["at_expiry"]["points"] == off["payoff"]["points"]
    est = (await _post(_body(replayed, view="estimated_now"), replayed)).json()
    assert on["curves"]["estimated_now"]["points"] == est["payoff"]["points"]
    assert on["scenario"]["other"]["totals"] == est["scenario"]["totals"]


@pytest.mark.parametrize("bad", [1, "true", None])
async def test_both_views_is_strict(replayed, bad):
    assert (await _post(_body(replayed, both_views=bad), replayed)).status_code == 422


@pytest.mark.parametrize("bad", [30, 0, -50, 300, 50.0, "50", True])
async def test_payoff_step_outside_the_four_is_refused(replayed, bad):
    assert (await _post(_body(replayed, payoff_step=bad), replayed)).status_code == 422


@pytest.mark.parametrize("step", [10, 25, 50, 100])
async def test_payoff_step_and_sd_through_the_route(replayed, step):
    off = (await _post(_body(replayed), replayed)).json()
    on = (await _post(_body(replayed, payoff_step=step, sd_bands=True), replayed)).json()
    assert set(on) - set(off) == {"payoff_table", "standard_deviation"}
    assert on["payoff_table"]["step"] == str(step) and on["payoff_table"]["rows"]
    assert on["standard_deviation"]["available"] is True and on["standard_deviation"]["horizon_days"] == 5
    assert len(on["standard_deviation"]["bands"]) == 4
