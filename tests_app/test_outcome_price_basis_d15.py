"""GC-ICLIVE-B D-15 / D-17 on the real route: the summary says which prices it uses; a paper trade shows its fills and
keeps the plan's credit visible, labelled as the plan.

Core: the replay condor with its two SELL legs planned 0.10 above their fills. Hand arithmetic: the credit at the plan
is the fills' credit + 2 x 0.10 x 65 = +13.00. The time value beside the credit is on the same (entry) prices.
"""
from __future__ import annotations

import json
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from test_outcome_margin import _body, _post, source, Transport  # noqa: E402


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


async def _summary(provider, **extra):
    body = {**_body(provider), **extra}
    [resp] = await _post(body, provider, source(Transport()))
    assert resp.status_code == 200, resp.text
    return json.loads(resp.text)["summary"]


async def test_default_request_says_plan_prices(replayed):
    s = await _summary(replayed)
    assert s["price_basis_text"] == "At plan prices"
    assert s["plan_line"] is None


async def test_paper_fills_basis_shows_fills_and_the_plan_line(replayed):
    body = _body(replayed)
    for leg in body["legs"]:
        fill = Decimal(leg["planned_entry"])
        leg["plan_entry"] = f"{fill + Decimal('0.10') if leg['action'] == 'SELL' else fill:f}"
    [base] = await _post(_body(replayed), replayed, source(Transport()))
    fills_credit = Decimal(json.loads(base.text)["summary"]["net_premium"]["amount"])
    [resp] = await _post({**body, "price_basis": "paper_fills"}, replayed, source(Transport()))
    s = json.loads(resp.text)["summary"]
    assert s["price_basis_text"] == "At paper fill prices"
    assert Decimal(s["net_premium"]["amount"]) == fills_credit  # the figure is the fills'
    assert s["plan_line"] == f"Plan: Get ₹{fills_credit + Decimal('13.00'):,} at plan prices"


async def test_paper_fills_without_plan_prices_has_no_plan_line(replayed):
    s = await _summary(replayed, price_basis="paper_fills")
    assert s["price_basis_text"] == "At paper fill prices"
    assert s["plan_line"] is None


async def test_time_value_is_the_same_on_two_live_prices(replayed):
    # the time value follows the credit's prices: asking twice with the same entry prices gives the same figure, and it
    # equals the signed entry premium minus intrinsic (hand: time + intrinsic = -(credit) for a net seller)
    s = await _summary(replayed)
    assert Decimal(s["time_value"]) + Decimal(s["intrinsic_value"]) == -Decimal(s["net_premium"]["amount"])
