"""W-078 / REQ-059 AC-3 (ADR-080): order product, product-aware reduce-only, and the circuit-band block.

Spec basis: ADR-080 "every entry and adjustment order is NRML (carry forward), with no product choice on screen";
"a price outside the day's circuit band blocks that leg with the reason, never a silent clamp"; REQ-059 AC-4
"Validation never silently changes the user's strategy".

UNPROVEN ON REAL DATA until the 4b order: the exit-product tests use Kite's DOCUMENTED position row shape
(``{"tradingsymbol", "product": "NRML"|"MIS", "quantity"}``); the owner's account holds no position, so no real
position reply exists yet. The circuit band numbers are the real 15:10 CE reply (0.05 .. 32.6).
"""
from __future__ import annotations

import dataclasses
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from execution_inputs import EXPIRY, all_true_context, check, closing_orders, condor_legs
from partial_inputs import CONTRACTS, STRATEGY_ID, book_with_three_filled
from test_sink_backup_checks import _CountingTransport, _sink

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.product import Product
from ofo.errors import LegValue, display_text
from ofo.execution import CheckCode, ExecutionAction
from ofo.execution.context import product_key
from ofo.execution.price_check import circuit_block
from ofo.orders import Order

REAL = Path(__file__).resolve().parents[2] / "docs/research/kite-proof-2026-10-07/rest-2026-10-15-order"
LEG = Leg(Action.BUY, Instrument.CE, D("23550"), EXPIRY, 65, D("3.95"))


# -- product on the order and the broker request -----------------------------------------------------------------

def test_order_defaults_to_nrml_and_refuses_a_non_product():
    base = dict(strategy_id="S-1", leg_ref="leg-1", contract="CONTRACT-1", side=Action.BUY, quantity=65,
                price=D("3.95"), version_id="v1")
    assert Order(**base).product is Product.NRML
    assert Order(**base, product=Product.MIS).product is Product.MIS
    with pytest.raises(ValueError):
        Order(**base, product="MIS")


def test_broker_request_carries_the_orders_product(catalogue):
    """The sink copies the order's product into the request (default NRML; an exit's MIS survives)."""
    book = book_with_three_filled()
    # #263 item 2: an entry is NRML only; MIS is carried by an EXIT (leg-2 is a held short, its exit a BUY)
    for product, choice, ref, contract, side in (
            (Product.NRML, "complete", "leg-4", CONTRACTS[3], Action.BUY),
            (Product.MIS, "close", "leg-2", CONTRACTS[1], Action.BUY)):
        order = Order(STRATEGY_ID, ref, contract, side, 65, D("44.00"), version_id="v1",
                      client_tag="OFO999999999", product=product)
        (request,) = _sink(book, catalogue, choice=choice, transport=_CountingTransport()).resolve_all((order,))
        assert request.product is product


# -- reduce-only compares product --------------------------------------------------------------------------------

def _exit(active_products, exit_products=None, legs=None):
    legs = legs or condor_legs()
    if exit_products is None:  # the exit orders carry NRML unless a test says otherwise
        exit_products = {product_key(leg): Product.NRML for leg in legs}
    ctx = all_true_context(action=ExecutionAction.EXIT, active_legs=legs, active_products=active_products,
                           exit_products=exit_products)
    return ctx, Strategy(closing_orders(legs))


def _held(product):
    return {product_key(leg): product for leg in condor_legs()}


def test_exit_in_the_positions_product_passes(catalogue, eligibility):
    ctx, strategy = _exit(_held(Product.NRML))
    assert check(strategy, ctx, catalogue, eligibility).failures == ()
    ctx, strategy = _exit(_held(Product.MIS), exit_products=_held(Product.MIS))
    assert check(strategy, ctx, catalogue, eligibility).failures == ()


@pytest.mark.parametrize("held, exits", [(Product.MIS, None), (Product.NRML, Product.MIS)], ids=["mis-held-nrml-exit",
                                                                                              "nrml-held-mis-exit"])
def test_exit_in_another_product_is_refused(held, exits, catalogue, eligibility):
    ctx, strategy = _exit(_held(held), exit_products=_held(exits) if exits else None)
    result = check(strategy, ctx, catalogue, eligibility)
    assert result.failed_codes == {CheckCode.EXIT_NOT_REDUCE_ONLY}
    assert "differs from the product of the position it closes" in result.failures[0].reason


def test_exit_with_an_unread_position_product_is_refused(catalogue, eligibility):
    """A position whose product Zerodha did not report is unknown, never assumed NRML."""
    partial = _held(Product.NRML)
    partial.pop(product_key(condor_legs()[0]))
    ctx, strategy = _exit(partial)
    assert check(strategy, ctx, catalogue, eligibility).failed_codes == {CheckCode.EXIT_NOT_REDUCE_ONLY}


def test_context_refuses_a_non_product_mapping():
    with pytest.raises(ValueError):
        all_true_context(active_products={product_key(LEG): "NRML"})


@pytest.mark.parametrize("missing", ["active_products", "exit_products", "both"])
def test_exit_with_products_missing_is_blocked_like_missing_active_legs(missing, catalogue, eligibility):
    """Round 2 MAJOR 1: missing products never skip the check; the exit is blocked as unverified."""
    held = {product_key(leg): Product.NRML for leg in condor_legs()}
    fields = {"active_products": held, "exit_products": held}
    for name in fields:
        if missing in (name, "both"):
            fields[name] = None
    ctx = all_true_context(action=ExecutionAction.EXIT, active_legs=condor_legs(), **fields)
    result = check(Strategy(closing_orders(condor_legs())), ctx, catalogue, eligibility)
    assert result.failed_codes == {CheckCode.EXIT_NOT_REDUCE_ONLY}
    assert "could not compare this exit" in result.failures[0].reason


def test_exit_leg_the_orders_do_not_name_is_blocked_not_assumed_nrml(catalogue, eligibility):
    held = _held(Product.NRML)
    unnamed = dict(held)
    unnamed.pop(product_key(condor_legs()[1]))
    ctx, strategy = _exit(held, exit_products=unnamed)
    assert check(strategy, ctx, catalogue, eligibility).failed_codes == {CheckCode.EXIT_NOT_REDUCE_ONLY}


# -- circuit band ------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def band():
    (quote,) = json.loads((REAL / "quote_CE.json").read_text(), parse_float=D)["data"].values()
    return quote["lower_circuit_limit"], quote["upper_circuit_limit"]


def test_circuit_band_blocks_one_paisa_outside_and_passes_on_the_band(band):
    lower, upper = D(str(band[0])), D(str(band[1]))
    assert (lower, upper) == (D("0.05"), D("32.6"))
    value = LegValue(1, LEG, "NIFTY")
    assert circuit_block(upper, lower, upper, value) is None
    assert circuit_block(lower, lower, upper, value) is None
    over = circuit_block(upper + D("0.01"), lower, upper, value)
    under = circuit_block(lower - D("0.01"), lower, upper, value)
    for blocked in (over, under):
        assert blocked is not None
        text = display_text(blocked)
        assert "0.05" in text and ("32.60" in text or "32.6" in text)
        assert "has not been changed" in text


def test_circuit_block_accepts_int_bands_as_kite_prints_them_and_refuses_floats(band):
    """Kite prints a whole-number price as a JSON integer; an int is exact, a float is not."""
    value = LegValue(1, LEG, "NIFTY")
    assert circuit_block(D("30"), 1, 32, value) is None
    assert circuit_block(D("33"), 1, 32, value) is not None
    with pytest.raises(ValueError):
        circuit_block(D("4"), 0.05, D("32.6"), value)


def test_circuit_block_refuses_floats_and_a_crossed_band(band):
    value = LegValue(1, LEG, "NIFTY")
    with pytest.raises(ValueError):
        circuit_block(4.0, D("0.05"), D("32.6"), value)
    with pytest.raises(ValueError):
        circuit_block(D("4"), D("32.6"), D("0.05"), value)


def test_dataclass_replace_keeps_product():
    order = Order("S-1", "leg-1", "X", Action.SELL, 65, D("3.95"), version_id="v1", product=Product.MIS)
    assert dataclasses.replace(order, client_tag="OFO1").product is Product.MIS
