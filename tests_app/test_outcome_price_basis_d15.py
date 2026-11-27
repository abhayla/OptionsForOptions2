"""GC-ICLIVE-B D-15 on the real route: the server DERIVES the price basis from the paper book; no client claim is read.

Core: the replay condor. With no paper strategy the summary says plan prices. With a paper strategy whose open positions
match every leg (contract, side, quantity, entry = the book's average) it says paper fill prices and carries the plan's
credit as one line (hand: two SELL legs planned 0.10 above their fills = +2 x 0.10 x 65 = +13.00). An edited leg at a
live price, a book that cannot be read, a plan with other lots and a client-sent basis are each their own answer.
"""
from __future__ import annotations

import datetime
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
from ofo.marketdata import quote as quote_module  # noqa: E402
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


async def _post(provider, body, fills, plan=None):
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    app.dependency_overrides[outcome_route.get_margin_source] = lambda: source(Transport())

    async def reader(_id):
        return fills

    app.dependency_overrides[outcome_route.get_fills_reader] = lambda: reader

    async def plan_reader(_id):  # D-15 round 3: the plan the SERVER stored for that paper strategy (owner-checked read)
        return plan

    app.dependency_overrides[outcome_route.get_plan_reader] = lambda: plan_reader
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


async def _units_of(provider):
    resp = await _post(provider, _body(provider), None)
    return {x["instrument_id"]: x["quantity"] for x in json.loads(resp.text)["legs"]}


async def _plan_of(provider, body, bump="0.10"):
    units = await _units_of(provider)
    return {x["instrument_id"]: (x["action"], units[x["instrument_id"]],
                                 Decimal(x["planned_entry"]) + (Decimal(bump) if x["action"] == "SELL" else 0))
            for x in body["legs"]}


async def test_every_leg_a_fill_says_paper_fill_prices_and_serves_the_plan_line(replayed):
    """ADR-321 (8): the plan line shows only when every leg is a fill. Hand: the two SELL legs were planned 0.10 above
    their fills, so the plan's Get is the fill Get + 2 x 0.10 x 65 = +13.00."""
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    plan = await _plan_of(replayed, body)
    out = json.loads((await _post(replayed, body, fills, plan)).text)["summary"]
    assert out["price_basis_text"] == "At paper fill prices"
    net = out["net_premium"]
    assert net["side"] == "get"
    expected = Decimal(net["amount"]) + Decimal("13.00")
    assert out["plan_line"] == f"Plan: Get \u20b9{expected:,.2f} at plan prices"  # the figure is under a lakh
    assert out["plan_line"].startswith("Plan: Get ")


async def test_a_partly_exited_leg_serves_no_plan_line(replayed):
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    plan = await _plan_of(replayed, body)
    iid = body["legs"][0]["instrument_id"]
    net, avg = fills[iid]
    half = abs(net) // 2
    fills[iid] = ((half if net > 0 else -half), avg)  # the book holds half the planned quantity
    s = json.loads((await _post(replayed, body, fills, plan)).text)["summary"]
    assert s["plan_line"] is None


async def test_a_fully_exited_leg_serves_no_plan_line_the_23_nov_c11_shape(replayed):
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    plan = await _plan_of(replayed, body)
    gone = body["legs"].pop()["instrument_id"]
    fills.pop(gone)  # out of the book and out of the request; the stored plan still names it
    s = json.loads((await _post(replayed, body, fills, plan)).text)["summary"]
    assert s["price_basis_text"] == "At paper fill prices"
    assert s["plan_line"] is None


async def test_an_edited_leg_not_a_fill_serves_no_plan_line(replayed):
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    plan = await _plan_of(replayed, body)
    first = body["legs"][0]
    first["planned_entry"] = f"{Decimal(first['planned_entry']) + Decimal('0.05'):f}"
    s = json.loads((await _post(replayed, body, fills, plan)).text)["summary"]
    assert s["price_basis_text"].startswith("At paper fill prices for 3 of 4")
    assert s["plan_line"] is None


async def test_an_unplaced_plan_is_the_plan_itself_and_serves_no_plan_line(replayed):
    s = json.loads((await _post(replayed, _body(replayed), None)).text)["summary"]
    assert s["price_basis_text"] == "At plan prices" and s["plan_line"] is None


async def test_an_unreadable_book_serves_no_plan_line_even_with_a_stored_plan(replayed):
    body = _paper_body(replayed)
    plan = await _plan_of(replayed, body)
    s = json.loads((await _post(replayed, body, None, plan)).text)["summary"]
    assert s["plan_line"] is None


async def test_an_exited_plan_leg_never_prices_the_held_subset_as_the_plan_credit(replayed):
    """The plan has one more leg than the book holds (a planned leg no longer on the book): no plan line."""
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    plan = await _plan_of(replayed, body, "0")
    plan_all = {**plan, "NSE_FO:EXITED-WING": ("BUY", 65, Decimal("1.00"))}
    s = json.loads((await _post(replayed, body, fills, plan_all)).text)["summary"]
    assert s["plan_line"] is None


async def test_a_client_sent_plan_figure_is_refused_not_read(replayed):
    body = _paper_body(replayed)
    body["legs"][0]["plan_entry"] = "9.99"
    assert (await _post(replayed, body, await _fills_of(replayed))).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    body = _paper_body(replayed)
    body["legs"][0]["plan_lots"] = 1
    assert (await _post(replayed, body, await _fills_of(replayed))).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_no_stored_plan_gives_no_plan_line(replayed):
    s = json.loads((await _post(replayed, _paper_body(replayed), await _fills_of(replayed), None)).text)["summary"]
    assert s["price_basis_text"] == "At paper fill prices" and s["plan_line"] is None


async def test_uneven_fills_average_is_compared_as_the_paper_reply_rounds_it(replayed):
    """Fills 23.85 and 23.86 average 23.855; the paper reply shows 23.86 (half up) and the client sends that: still
    the book's fill. Hand: (23.85 + 23.86) / 2 = 23.855 -> 23.86."""
    fills = await _fills_of(replayed)
    body = _paper_body(replayed)
    first = body["legs"][0]
    net, _ = fills[first["instrument_id"]]
    first["planned_entry"] = "23.86"
    fills[first["instrument_id"]] = (net, (Decimal("23.85") + Decimal("23.86")) / 2)
    s = json.loads((await _post(replayed, body, fills)).text)["summary"]
    assert s["price_basis_text"] == "At paper fill prices"


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


async def test_the_reply_serves_the_oldest_leg_quote_time_so_the_screen_does_no_date_arithmetic(replayed):
    out = json.loads((await _post(replayed, _body(replayed), None)).text)
    times = [q["quote_at"] for q in out["leg_quotes"]]
    assert all(times) and out["oldest_quote_at"] is not None
    parsed = [datetime.datetime.fromisoformat(t) for t in times]
    assert datetime.datetime.fromisoformat(out["oldest_quote_at"]) == min(parsed)


async def test_a_leg_quote_without_a_time_leaves_the_oldest_time_empty(replayed, monkeypatch):
    monkeypatch.setattr(quote_module, "price_time", lambda _ts: None)  # a calendar with no data for the date
    out = json.loads((await _post(replayed, _body(replayed), None)).text)
    assert out["leg_quotes"] and all(q["quote_at"] is None for q in out["leg_quotes"])
    assert out["oldest_quote_at"] is None
