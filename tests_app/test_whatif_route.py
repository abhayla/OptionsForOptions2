"""W-127 (REQ-084 AC-4, AC-6; REQ-034 AC-6): the what-if inputs through POST /api/strategies/outcome on the real
2026-10-08 replay. The browser sends only inputs; every figure in the reply is a string from the engine."""
from __future__ import annotations

import datetime
import importlib
import pathlib
import sys

import pytest
from ofo_app.routes import strategies

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
route = importlib.import_module("test_outcome_route")  # the replay helpers of the outcome route tests
kite = importlib.import_module("marketdata._kite_fixture")

HTTP_OK = 200
HTTP_UNPROCESSABLE = 422


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = kite.new_provider()
    provider.subscribe(kite.all_instrument_ids(items))
    kite.replay(provider, clock)
    return provider


async def test_req084_ac4_inputs_in_the_request_give_the_target_figures_in_the_reply(replayed):
    """REQ-084 AC-4: target level, target date and IV offset in; the reply carries the target level and date used, the
    IV offset, both P&L figures and the Estimated curve, all as strings."""
    body = route._body(replayed, "advanced")
    body.update(target_level="22600", target_time=(route.VALUATION + datetime.timedelta(days=2)).isoformat(),
                iv_offset="2.0")
    resp = await route._post(body, replayed)
    assert resp.status_code == HTTP_OK
    w = resp.json()["whatif"]
    assert (w["target_level"], w["iv_offset"], w["estimated_available"]) == ("22600.00", "2.0", True)
    assert w["target_time"].startswith("2026-10-10T09:20:09")
    assert isinstance(w["target_estimated_pnl"], str) and isinstance(w["target_expiry_pnl"], str)
    assert len(w["estimated_points"]) == len(resp.json()["payoff"]["points"])
    assert w["greeks"]["examples"][0]["greek"] == "delta"
    route._no_floats(resp.json())


async def test_req084_ac3_an_offset_off_the_tenth_grid_or_a_float_is_refused(replayed):
    """REQ-084 AC-3 (red cases): 2.05 is not a step of 0.1; a JSON number is not a decimal string; both are 422."""
    for bad in ("2.05", "abc", 2.0):
        body = route._body(replayed)
        body["iv_offset"] = bad
        assert (await route._post(body, replayed)).status_code == HTTP_UNPROCESSABLE, bad


async def test_req084_ac6_the_same_request_without_inputs_has_the_same_expiry_curve(replayed):
    """REQ-084 AC-6: what-if inputs never change the At Expiry payoff, the table or the legs of the reply."""
    plain = (await route._post(route._body(replayed), replayed)).json()
    body = route._body(replayed)
    body.update(target_level="22800", iv_offset="-3.0")
    moved = (await route._post(body, replayed)).json()
    for key in ("payoff", "table", "legs", "summary", "scenario"):
        assert plain[key] == moved[key]
    assert plain["whatif"] != moved["whatif"]


@pytest.mark.parametrize("field", ["target_level", "target_time", "iv_offset"])
async def test_req034_ac6_the_inputs_are_not_in_the_stored_definition_fields(field):
    """REQ-034 AC-6: the strategy definition model (what is saved) has no what-if field."""
    names = {n for model in vars(strategies).values() if hasattr(model, "model_fields") for n in model.model_fields}
    assert field not in names
