"""ADR-300 (GC-ICFIX P2): POST /api/strategies/outcome carries the entry-guide state and line for a strategy with a sold
option leg: the sold legs' delta comes from the outcome's own model (no second pricing pass), the guide from the default
rule set of the strategy's shape. The real 2026-10-08 replay (as test_outcome_route.py). No database is needed."""
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
HTTP_OK = 200
BOUGHT_ONLY = (("NSE_FO:44632", "BUY"), ("NSE_FO:44595", "BUY"))


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


async def _post(provider, legs):
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.outcome import MarketContext, get_market_context  # noqa: PLC0415

    body = {"underlying": "NIFTY", "legs": [
        {"instrument_id": iid, "action": action, "lots": 1,
         "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
        for iid, action in legs]}
    app = create_app()
    if provider is not None:
        app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post("/api/strategies/outcome", json=body)


async def test_a_condor_answers_with_a_state_and_the_default_rule_sets_name(replayed) -> None:
    resp = await _post(replayed, CONDOR)
    assert resp.status_code == HTTP_OK, resp.text
    out = resp.json()
    assert out["entry_guide_state"] in {"breaks", "within"}, out["entry_guide_state"]  # a real delta was read
    if out["entry_guide_state"] == "breaks":
        line = out["entry_guide_line"]
        assert "the entry guide of the default rule set (" in line and line.endswith("is 0.15 to 0.20.")
        assert line.startswith(("Sold call delta 0.", "Sold put delta 0."))
    else:
        assert out["entry_guide_line"] is None  # within the guide: no line


async def test_a_strategy_with_no_sold_leg_carries_neither_field(replayed) -> None:
    out = (await _post(replayed, BOUGHT_ONLY)).json()
    assert out["state"] == "COMPUTED" and "entry_guide_state" not in out and "entry_guide_line" not in out


async def test_an_answer_that_is_not_computed_carries_neither_field() -> None:
    from ofo_app.main import create_app  # noqa: PLC0415

    body = {"underlying": "NIFTY", "legs": [{"instrument_id": "NSE_FO:44624", "action": "SELL", "lots": 1,
                                             "planned_entry": "80.00", "captured_at": VALUATION.isoformat()}]}
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as ac:
        out = (await ac.post("/api/strategies/outcome", json=body)).json()
    assert out["state"] != "COMPUTED" and "entry_guide_state" not in out


def test_the_outcome_model_carries_the_sold_legs_deltas() -> None:
    from ofo.outcome.service import Outcome  # noqa: PLC0415

    assert "sold_deltas" in Outcome.__dataclass_fields__
