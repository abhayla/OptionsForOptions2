"""W-078 round 2 (Tier A review REVISE): the product and circuit rules sit in the path EVERY order passes.

Class: a safety check that silently passes when its input is missing, or checks a declared list instead of the
actual order. Spec basis: ADR-080 "an exit takes the product of the position it reduces"; "a price outside the
day's circuit band blocks that leg with the reason, never a silent clamp".

UNPROVEN ON REAL DATA until the 4b order: the position rows are Kite's DOCUMENTED shape (``tradingsymbol``,
``product``, ``quantity``, ``average_price``, ``last_price``); the owner's account holds no position yet.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import pytest
from execution_inputs import all_true_context, check, condor_legs
from partial_inputs import FakeBroker, FakePlanner, entry_context
from partial_inputs import STORED_FREEZE
from test_close_slices import BUY_PE, QTY, SELL_CE, SELL_PE, _state, big_plan

from ofo.engine import Action, Strategy
from ofo.engine.product import Product
from ofo.execution import CheckCode, ExecutionAction, VersionState
from ofo.execution.safety import FlagCode
from ofo.execution.context import product_key
from ofo.execution.partial import close_partial_strategy
from ofo.execution.partial import position_line_from_kite_row


# -- parser for Kite's documented position row ---------------------------------------------------------------------

def test_kite_position_row_parses_product_quantity_and_prices():
    row = {"tradingsymbol": "ANY-CONTRACT", "product": "MIS", "quantity": -65, "average_price": D("3.95"),
           "last_price": 4}
    line = position_line_from_kite_row(row)
    assert (line.contract, line.net_quantity, line.product) == ("ANY-CONTRACT", -65, Product.MIS)
    assert (line.average_price, line.ltp) == (D("3.95"), D("4"))


def test_kite_position_row_unknown_product_is_unread_not_assumed():
    row = {"tradingsymbol": "X", "product": "CNC", "quantity": 65, "average_price": D("3.95"), "last_price": D("4")}
    assert position_line_from_kite_row(row).product is None
    assert position_line_from_kite_row({**row, "product": None}).product is None


def test_kite_position_row_refuses_floats():
    with pytest.raises(ValueError):
        position_line_from_kite_row({"tradingsymbol": "X", "product": "NRML", "quantity": 65,
                                     "average_price": 3.95, "last_price": D("4")})


# -- the exit orders take the position's product, and the gate checks the orders ----------------------------------

def _close_with(catalogue, eligibility, *, short_product, default_product=Product.NRML, context=None):
    book, broker = _state((QTY, QTY, QTY, 0))
    lines = [dataclasses.replace(p, product=short_product if p.net_quantity < 0 else Product.NRML)
             for p in broker.positions]
    broker = FakeBroker(lines, broker.order_statuses, default_product=default_product)
    # #263 round 2: the position's product must be the one the strategy's own fills carry (a lone row in another
    # product is refused, not exited), so the ledger's orders take each held line's product here.
    held_product = {p.contract: p.product for p in lines}
    for key, order in list(book._orders.items()):
        if held_product.get(order.contract) is not None:
            book._orders[key] = dataclasses.replace(order, product=held_product[order.contract])
    return close_partial_strategy(big_plan(), broker, book, FakePlanner(), context or entry_context(), catalogue,
                                  eligibility, stored_freeze=STORED_FREEZE)


def test_core_mis_short_positions_are_closed_with_orders_carrying_mis(catalogue, eligibility):
    prep = _close_with(catalogue, eligibility, short_product=Product.MIS)
    assert prep.ready, prep.reason
    by_ref = {o.leg_ref: o.product for o in prep.orders}
    assert by_ref == {SELL_PE: Product.MIS, SELL_CE: Product.MIS, BUY_PE: Product.NRML}


def test_nrml_positions_are_closed_with_nrml(catalogue, eligibility):
    prep = _close_with(catalogue, eligibility, short_product=Product.NRML)
    assert prep.ready and {o.product for o in prep.orders} == {Product.NRML}


def test_a_position_whose_product_was_not_read_blocks_the_exit(catalogue, eligibility):
    book, broker = _state((QTY, QTY, QTY, 0))
    unread = [dataclasses.replace(p, product=None) for p in broker.positions]  # Zerodha never reported a product
    broker = FakeBroker(unread, broker.order_statuses, default_product=None)
    prep = close_partial_strategy(big_plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, stored_freeze=STORED_FREEZE)
    assert not prep.ready and prep.orders == ()


def test_the_gate_checks_the_orders_not_a_callers_declared_exit_products(catalogue, eligibility):
    """A caller declaring every exit NRML cannot hide an MIS exit order: the declared list is replaced by the orders'
    own products, so the exit still matches its MIS position and passes (a gate that trusted the declared list would
    see MIS held vs NRML declared and block)."""
    declared = {product_key(leg): Product.NRML for leg in condor_legs()}
    prep = _close_with(catalogue, eligibility, short_product=Product.MIS,
                       context=entry_context(exit_products=declared))
    assert prep.ready, prep.reason
    assert {o.product for o in prep.orders} == {Product.MIS, Product.NRML}


# -- circuit band in the gate, every action -----------------------------------------------------------------------

def _band_ctx(action, bands, **extra):
    return all_true_context(action=action, price_bands=bands, **extra)


def _bands(lower, upper, legs=None):
    return {product_key(leg): (lower, upper) for leg in (legs or condor_legs())}


@pytest.mark.parametrize("action", [ExecutionAction.NEW_ENTRY, ExecutionAction.ADJUSTMENT])
def test_price_inside_the_band_passes_and_on_the_band_passes(action, condor, catalogue, eligibility):
    prices = [leg.entry_price for leg in condor.legs]
    ctx = _band_ctx(action, _bands(min(prices), max(prices)))
    assert CheckCode.PRICE_OUTSIDE_BAND not in check(condor, ctx, catalogue, eligibility).failed_codes


@pytest.mark.parametrize("action", [ExecutionAction.NEW_ENTRY, ExecutionAction.ADJUSTMENT])
def test_price_one_paisa_outside_the_band_blocks_that_leg(action, condor, catalogue, eligibility):
    leg = condor.legs[0]
    bands = _bands(D("0.05"), D("1000"))
    bands[product_key(leg)] = (D("0.05"), leg.entry_price - D("0.01"))
    result = check(condor, _band_ctx(action, bands), catalogue, eligibility)
    band_failures = [f for f in result.failures if f.code is CheckCode.PRICE_OUTSIDE_BAND]
    assert [f.leg_number for f in band_failures] == [1]
    assert "outside today's price band" in band_failures[0].reason


@pytest.mark.parametrize("bands", [None, {}], ids=["no-bands", "leg-without-band"])
def test_a_missing_band_blocks_never_passes(bands, condor, catalogue, eligibility):
    result = check(condor, _band_ctx(ExecutionAction.NEW_ENTRY, bands), catalogue, eligibility)
    assert result.failed_codes == {CheckCode.PRICE_OUTSIDE_BAND}
    assert "price band" in result.failures[0].reason and "could not read" in result.failures[0].reason


def _exit_inputs(price=None, bands="missing"):
    legs = condor_legs()
    flip = {Action.BUY: Action.SELL, Action.SELL: Action.BUY}
    exit_legs = tuple(dataclasses.replace(l, action=flip[l.action], **({} if price is None else {"entry_price": price}))
                      for l in legs)
    products = {product_key(l): Product.NRML for l in legs}
    kw = {} if bands == "missing" else {"price_bands": bands}
    if bands == "missing":
        kw["price_bands"] = None
    ctx = all_true_context(action=ExecutionAction.EXIT, active_legs=legs, active_products=products,
                           exit_products=products, **kw)
    return Strategy(exit_legs), ctx


def test_exit_with_a_missing_band_is_a_warning_the_user_confirms_not_a_block(catalogue, eligibility):
    """REQ-059 exit carve-out + Q239: an exit is never stopped by a band that could not be read."""
    strategy, ctx = _exit_inputs()
    result = check(strategy, ctx, catalogue, eligibility)
    assert result.failures == () and result.blocked is False
    warned = [f for f in result.flags if f.code is FlagCode.PRICE_BAND_UNKNOWN_ON_EXIT]
    assert len(warned) == 1 and "price band" in warned[0].message
    assert result.requires_confirmation is True


def test_exit_leg_with_a_zero_price_is_never_compared_to_a_band(catalogue, eligibility):
    """A stored leg carries entry price 0 = unknown: not 'outside 0.05..', but a missing price -> warning."""
    strategy, ctx = _exit_inputs(price=D("0"), bands=_bands(D("0.05"), D("1000")))
    result = check(strategy, ctx, catalogue, eligibility)
    assert result.failures == ()
    assert any(f.code is FlagCode.PRICE_BAND_UNKNOWN_ON_EXIT for f in result.flags)


def test_exit_priced_outside_a_known_band_still_blocks(catalogue, eligibility):
    strategy, ctx = _exit_inputs(bands=_bands(D("0.05"), D("1")))
    result = check(strategy, ctx, catalogue, eligibility)
    assert result.failed_codes == {CheckCode.PRICE_OUTSIDE_BAND}
    assert "outside today's price band" in result.failures[0].reason


def test_exit_inside_a_known_band_has_no_warning(catalogue, eligibility):
    strategy, ctx = _exit_inputs(bands=_bands(D("0.05"), D("1000")))
    result = check(strategy, ctx, catalogue, eligibility)
    assert result.failures == () and not any(f.code is FlagCode.PRICE_BAND_UNKNOWN_ON_EXIT for f in result.flags)
    assert result.requires_confirmation is False


# -- round 4: the band is compared with the price the ORDER will carry, never a leg placeholder -------------------

def _adjust(order_prices, bands=None):
    bands = bands if bands is not None else _bands(D("0.05"), D("500"))
    placeholder = tuple(dataclasses.replace(l, entry_price=D("0")) for l in condor_legs())  # as modification.py builds
    ctx = all_true_context(action=ExecutionAction.ADJUSTMENT, version_state=VersionState.PROPOSED, price_bands=bands,
                           order_prices=order_prices)
    return Strategy(placeholder), ctx


def _prices(value, legs=None):
    return {product_key(l): value for l in (legs or condor_legs())}


def test_adjustment_with_real_order_prices_inside_a_real_band_passes(catalogue, eligibility):
    strategy, ctx = _adjust(_prices(D("42.50")))
    assert check(strategy, ctx, catalogue, eligibility).failures == ()


def test_adjustment_with_an_order_price_outside_the_band_blocks_that_leg(catalogue, eligibility):
    prices = _prices(D("42.50"))
    prices[product_key(condor_legs()[2])] = D("500.01")
    result = check(*_adjust(prices)[:1], _adjust(prices)[1], catalogue, eligibility)
    assert [(f.code, f.leg_number) for f in result.failures] == [(CheckCode.PRICE_OUTSIDE_BAND, 3)]


@pytest.mark.parametrize("prices", [None, {}], ids=["no-prices", "leg-without-price"])
def test_adjustment_with_no_order_price_yet_blocks_not_known_yet(prices, catalogue, eligibility):
    result = check(*_adjust(prices)[:1], _adjust(prices)[1], catalogue, eligibility)
    assert result.failed_codes == {CheckCode.PRICE_OUTSIDE_BAND}
    assert "not known yet" in result.failures[0].reason


def test_exit_with_no_band_is_not_checked_rather_than_passed(catalogue, eligibility):
    strategy, ctx = _exit_inputs()
    result = check(strategy, ctx, catalogue, eligibility)
    assert CheckCode.PRICE_OUTSIDE_BAND in result.not_checked
    assert CheckCode.PRICE_OUTSIDE_BAND not in result.passed


def test_confirmation_text_names_the_unknown_band_when_it_is_the_only_warning(catalogue, eligibility):
    strategy, ctx = _exit_inputs()
    result = check(strategy, ctx, catalogue, eligibility)
    assert result.confirmation_text == "We could not check this exit's price against today's price band — confirm to continue."
    assert "stale" not in result.confirmation_text
