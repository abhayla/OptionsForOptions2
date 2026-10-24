"""REQ-077 AC-8 (W-149, row 21b): a typed price is a planning number only.

"A typed price is a planning number only: the order's limit price on Execute still comes from market depth and the
user's tolerance (ADR-080, ADR-095), and the Execute review shows both ... The basket never uses a typed price as its
limit."

No database, no order sent: ``price_legs`` runs on the real catalogue row and the real recorded NIFTY depth quote
(``execute_replay.live_quote``, 2026-10-16 15:07 IST). ``executable_limit`` takes the limit from the walked depth levels;
the planned entry is only the slippage reference, so the three planned-entry cases below must give one limit.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import pytest
from ofo.engine import Action
from ofo.execution.basket import make_tag
from ofo.instruments import Catalogue
from ofo_app import execute_plan as ep
from ofo_app.execute_replay import CORE_ID, listed_contract, live_quote
from ofo_app.routes import execute as route

QUANTITY = 65


def _catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load([listed_contract()])
    return cat


def _quote() -> ep.LegQuote:
    quote = ep.quote_from_kite(live_quote())
    assert quote is not None
    return quote


def _price(entry: D | None, quote: ep.LegQuote | None = None, action: Action = Action.BUY) -> ep.PricedPlan:
    q = quote if quote is not None else _quote()
    return ep.price_legs("1", "NIFTY", [ep.LegToPrice(CORE_ID, action, QUANTITY, entry)], _catalogue(), lambda i, t: q)


def _limit(priced: ep.PricedPlan) -> D:
    return priced.plan.legs[0].leg.entry_price


@pytest.mark.parametrize("action", [Action.BUY, Action.SELL])
def test_ac8_typed_entry_30_percent_above_or_below_gives_the_same_limit_as_no_entry(action):
    """AC-8 core proof: the limit is identical for no planned entry, 30% above and 30% below the market."""
    quote = _quote()
    market = quote.last_price
    assert market is not None and market > 0
    none_case = _limit(_price(None, quote, action))
    above = _limit(_price(market * D("1.3"), quote, action))
    below = _limit(_price(market * D("0.7"), quote, action))
    assert above == none_case == below
    # the limit is the worst walked depth level (ADR-080 (3)), not a function of the typed price
    levels = quote.depth.asks if action is Action.BUY else quote.depth.bids
    assert none_case in {level.price for level in levels}


def test_ac8_basket_leg_price_is_the_depth_limit_never_the_typed_price():
    """AC-8: the plan leg the basket is built from carries the depth limit; a typed price differing from it never
    appears as any leg's price."""
    quote = _quote()
    typed = quote.last_price * D("1.3")
    priced = _price(typed, quote)
    limit = _limit(priced)
    assert limit == _limit(_price(None, quote))
    assert limit != typed
    assert all(p.leg.entry_price != typed for p in priced.plan.legs)


def test_ac8_the_planned_entry_is_carried_for_the_review_and_none_when_absent():
    """AC-8: the review's 'planned price' is the leg's planned entry, unchanged; no entry -> None."""
    assert _price(D("81.30")).planned_prices == (D("81.30"),)
    assert _price(None).planned_prices == (None,)


def test_ac8_review_orders_carry_both_numbers_per_leg():
    """AC-8: the review order shows planned price (2 decimals) next to the limit, matched by the tag's leg index."""
    priced = _price(D("81.3"))
    tag = make_tag(1, 1, 0)
    assert route._planned_price(priced.planned_prices, tag) == D("81.30")
    assert route._planned_price((None,), tag) is None
    assert route._planned_price((), tag) is None  # a leg index beyond the carried prices: no planned price, no crash
    assert route._planned_price((D("1"), D("2.005")), make_tag(1, 1, 1)) == D("2.01")


def test_ac8_the_answer_puts_the_planned_price_into_each_review_order_by_tag():
    """AC-8: ``_answer`` (the route's one reply builder) carries the planned entry on the order whose tag names that
    leg, next to the depth limit, and None where the leg had no planned entry. Database-free: a real sealed basket."""
    from ofo.execution.basket import build_basket  # noqa: PLC0415
    from ofo.execution.freeze import FreezeCheck  # noqa: PLC0415
    from ofo_app.execute_replay import AT  # noqa: PLC0415

    class _Funds:
        def available_funds(self):
            return D("1003")

        def zerodha_required(self, orders):
            return D("354.25")

    def answer(entry: D | None):
        priced = _price(entry)
        basket = build_basket(priced.plan, _catalogue(), 1, freeze_check=lambda p: FreezeCheck((), ()),
                              margin_source=_Funds())
        cost = route.cost_out(basket.orders, None, route.Figures(D("1003"), D("354.25"), AT))
        return basket, route._answer(1, basket, "kitekey", cost, priced.planned_prices)

    basket, planned = answer(D("81.3"))
    assert [o.tag for o in planned.orders] == [o.tag for o in basket.orders] == [make_tag(1, 1, 0)]
    assert planned.orders[0].planned_price == D("81.30")
    assert planned.orders[0].price == basket.orders[0].price  # the depth limit stays beside it, untouched
    _, unplanned = answer(None)
    assert unplanned.orders[0].planned_price is None


def test_ac8_no_depth_refuses_the_leg_and_never_prices_from_the_typed_price():
    """AC-8 / standing (d): thin depth, a missing quote and an absent depth refuse with gate_price_not_known."""
    quote = _quote()
    empty = dataclasses.replace(quote, depth=dataclasses.replace(quote.depth, asks=(), bids=()))
    for q in (empty, None):
        with pytest.raises(ep.LegRefused) as refused:
            ep.price_legs("1", "NIFTY", [ep.LegToPrice(CORE_ID, Action.BUY, QUANTITY, D("81.30"))], _catalogue(),
                          lambda i, t, q=q: q)
        assert str(refused.value)  # the catalogue text, not a bare error


def test_ac8_thin_depth_is_refused_not_priced_from_the_typed_price():
    """AC-8: a quantity the 5 levels cannot cover is refused, whatever the typed price."""
    with pytest.raises(ep.LegRefused):
        ep.price_legs("1", "NIFTY", [ep.LegToPrice(CORE_ID, Action.BUY, 10**9, D("81.30"))], _catalogue(),
                      lambda i, t: _quote())


def test_ac8_circuit_band_still_checks_the_limit_not_the_typed_price():
    """AC-8: a band that excludes the depth limit refuses the leg; a typed price inside the band does not rescue it."""
    quote = _quote()
    limit = _limit(_price(None, quote))
    outside = dataclasses.replace(quote, band=(limit + D("100"), limit + D("200")))
    with pytest.raises(ep.LegRefused):
        _price(limit + D("150"), outside)  # typed price inside the band, limit outside it
    inside = dataclasses.replace(quote, band=(limit - D("1"), limit + D("1")))
    assert _limit(_price(limit + D("50"), inside)) == limit  # typed price outside the band is not checked
