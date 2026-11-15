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
        app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE, feed_owner="owner")  # a real user has a feed owner (shared compute)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post("/api/strategies/outcome", json=body)


def _fix_deltas(monkeypatch, call, put):
    """A fixed sold-leg delta pair in place of the engine's (the route and the rule set stay real)."""
    monkeypatch.setattr("ofo.outcome.service._sold_deltas", lambda _model, _greeks: (("CE", call), ("PE", put)))


async def test_the_138_condor_breaks_with_delta_0_46_exactly(replayed, monkeypatch) -> None:
    _fix_deltas(monkeypatch, Decimal("0.46"), Decimal("0.44"))
    resp = await _post(replayed, CONDOR)
    assert resp.status_code == HTTP_OK, resp.text
    out = resp.json()
    assert out["entry_guide_state"] == "breaks"
    assert out["entry_guide_line"] == ("Sold put delta 0.44 and sold call delta 0.46; the entry guide of the default "
                                       "rule set (Iron condor: system default) is 0.15 to 0.20.")


async def test_the_condor_is_within_with_delta_0_18_exactly(replayed, monkeypatch) -> None:
    _fix_deltas(monkeypatch, Decimal("0.18"), Decimal("0.17"))
    out = (await _post(replayed, CONDOR)).json()
    assert out["entry_guide_state"] == "within" and out["entry_guide_line"] is None


async def test_a_missing_delta_cannot_tell(replayed, monkeypatch) -> None:
    _fix_deltas(monkeypatch, None, Decimal("0.17"))
    out = (await _post(replayed, CONDOR)).json()
    assert out["entry_guide_state"] == "cannot_tell"
    assert out["entry_guide_line"] == "Could not check against the entry guide."


@pytest.mark.parametrize("stype", ["straddle", "ifly", None])  # a shape the guide does not suit; an unknown shape
async def test_a_shape_the_guide_does_not_suit_carries_neither_field(replayed, monkeypatch, stype) -> None:
    _fix_deltas(monkeypatch, Decimal("0.50"), Decimal("0.50"))
    monkeypatch.setattr("ofo_app.routes.outcome.type_of", lambda *_a, **_k: stype)
    out = (await _post(replayed, CONDOR)).json()
    assert out["state"] == "COMPUTED" and "entry_guide_state" not in out and "entry_guide_line" not in out


async def test_the_real_replay_condor_resolves_to_the_iron_condor_rule_set(replayed) -> None:
    out = (await _post(replayed, CONDOR)).json()
    assert out["entry_guide_state"] in {"breaks", "within"}  # a real delta was read for the real shape
    if out["entry_guide_state"] == "breaks":
        assert "(Iron condor: system default)" in out["entry_guide_line"]


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
