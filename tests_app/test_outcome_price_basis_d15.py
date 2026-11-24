"""GC-ICLIVE-B D-15 on the real route: the server DERIVES the price basis from the paper book; no client claim is read.

Core: the replay condor. With no paper strategy the summary says plan prices. With a paper strategy whose open positions
match every leg (contract, side, quantity, entry = the book's average) it says paper fill prices and carries the plan's
credit as one line (hand: two SELL legs planned 0.10 above their fills = +2 x 0.10 x 65 = +13.00). An edited leg at a
live price, a book that cannot be read, a plan with other lots and a client-sent basis are each their own answer.
"""
from __future__ import annotations

import json
import pathlib
import sys
from decimal import Decimal
from http import HTTPStatus

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from httpx import ASGITransport, AsyncClient  # noqa: E402
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo_app.main import create_app  # noqa: E402
from ofo_app.routes import outcome as outcome_route  # noqa: E402
from ofo_app.routes.outcome import MarketContext, get_market_context  # noqa: E402
from test_outcome_margin import RATE, VALUATION, Transport, _body, source  # noqa: E402


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


async def _post(provider, body, fills):
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    app.dependency_overrides[outcome_route.get_margin_source] = lambda: source(Transport())

    async def reader(_id):
        return fills

    app.dependency_overrides[outcome_route.get_fills_reader] = lambda: reader
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post("/api/strategies/outcome", json=body)


def _paper_body(provider, **extra):
    return {**_body(provider), "paper_strategy_id": 7, "include_booked": False, **extra}


async def _fills_of(provider):
    """The book's open positions equal to the legs the plain request prices (signed quantity, average)."""
    resp = await _post(provider, _body(provider), None)
    legs = json.loads(resp.text)["legs"]
    return {x["instrument_id"]: ((1 if x["action"] == "BUY" else -1) * x["quantity"], Decimal(x["planned_entry"]))
            for x in legs}


async def test_no_paper_strategy_says_plan_prices(replayed):
    s = json.loads((await _post(replayed, _body(replayed), None)).text)["summary"]
    assert (s["price_basis_text"], s["plan_line"]) == ("At plan prices", None)


async def test_a_client_sent_basis_is_refused_not_read(replayed):
    resp = await _post(replayed, {**_body(replayed), "price_basis": "paper_fills"}, None)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_every_leg_a_fill_says_paper_fill_prices_and_states_the_plan_credit(replayed):
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    base = json.loads((await _post(replayed, _body(replayed), None)).text)
    credit = Decimal(base["summary"]["net_premium"]["amount"])
    for leg in body["legs"]:
        fill = Decimal(leg["planned_entry"])
        leg["plan_entry"] = f"{fill + Decimal('0.10') if leg['action'] == 'SELL' else fill:f}"
        leg["plan_lots"] = 1
    s = json.loads((await _post(replayed, body, fills)).text)["summary"]
    assert s["price_basis_text"] == "At paper fill prices"
    assert s["plan_line"] == f"Plan: Get ₹{credit + Decimal('13.00'):,} at plan prices"


async def test_a_plan_with_other_lots_does_not_price_the_fill_quantity_at_plan_prices(replayed):
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    for leg in body["legs"]:
        leg["plan_entry"], leg["plan_lots"] = leg["planned_entry"], 2  # the plan was 2 lots, the position holds 1
    s = json.loads((await _post(replayed, body, fills)).text)["summary"]
    assert s["price_basis_text"] == "At paper fill prices"
    assert s["plan_line"] == "Plan credit not shown: the plan's lots differ from the paper position"


async def test_an_edited_leg_at_a_live_price_is_not_called_a_paper_fill(replayed):
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    first = body["legs"][0]
    first["planned_entry"] = f"{Decimal(first['planned_entry']) + Decimal('0.05'):f}"  # typed at a live price
    s = json.loads((await _post(replayed, body, fills)).text)["summary"]
    assert s["price_basis_text"] == "At paper fill prices for 3 of 4 legs; the rest at their entered prices"
    assert s["plan_line"] is None


async def test_no_leg_matching_the_book_says_so(replayed):
    s = json.loads((await _post(replayed, _paper_body(replayed), {"NSE_FO:1": (-65, Decimal("1.00"))})).text)["summary"]
    assert s["price_basis_text"] == "At their entered prices: none of 4 legs is a paper fill"


async def test_a_book_that_cannot_be_read_claims_no_basis(replayed):
    s = json.loads((await _post(replayed, _paper_body(replayed), None)).text)["summary"]
    assert s["price_basis_text"] == "At their entered prices (the paper book could not be read)"
    assert s["plan_line"] is None


async def test_the_leg_quotes_carry_each_legs_own_quote_time(replayed):
    out = json.loads((await _post(replayed, _body(replayed), None)).text)
    quotes = out["leg_quotes"]
    assert len(quotes) == len(_body(replayed)["legs"]) and all(isinstance(q["quote_at"], str) for q in quotes)
