"""#263 items 1-2: broker positions are keyed by (contract, product); the sink refuses a non-NRML entry/adjustment.

Class: (1) code reading Zerodha's position rows into a contract-keyed map, while Zerodha keys them by (contract,
product); (2) ADR-080's "every entry and adjustment order is NRML" enforced only by a default, not at the one path every
order passes. Spec basis: ADR-080 "an exit takes the product of the position it reduces"; REQ-059.

UNPROVEN ON REAL DATA until the 4b order: rows follow Kite's DOCUMENTED shape; the owner's account holds no position.

Guards and the mutation that kills each:
- G1 (``assess`` duplicate check keyed by (contract, product)): mutant ``(p.contract,)`` -> the core test raises.
- G2 (``_strategy_position_lines`` picks the ledger's product row): mutant "keep the first row" -> the MIS-first order
  test exits with MIS.
- G3 (ambiguity refusal): mutant "keep held[0]" -> the ambiguous test is ready instead of refused.
- G4 (``allowed_or_refuse`` NRML-entry check): mutant deleting the ``if not reducing ...`` line -> the sink tests pass an
  MIS entry through.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import pytest
from partial_inputs import (
    BROKER_IDS, CONTRACTS, FILL_AT, STRATEGY_ID, FakeBroker, FakePlanner, LOT, book_with_three_filled, entry_context,
    new_book, record_for_legs,
)
from partial_inputs import STORED_FREEZE
from test_close_slices import SELL_PE, _state, big_plan
from test_sink_backup_checks import _CountingTransport, _sink, _tagged

from ofo.engine import Action
from ofo.engine.product import Product
from ofo.errors import display_text
from ofo.execution.partial import (
    BrokerPositionLine, ExecutionStatus, assess, close_partial_strategy,
)
from ofo.execution.send_guard import SendRefused
from ofo.orders import FillEvent, Order, OrderState

SHORT = CONTRACTS[1]  # the planned SELL leg used for the second row


def _with_second_row(broker: FakeBroker, product: Product, qty: int, *, nrml_first: bool = True) -> FakeBroker:
    base = next(p for p in broker.positions if p.contract == SHORT)
    extra = dataclasses.replace(base, net_quantity=qty, product=product)
    rows = []
    for p in broker.positions:
        rows.append(p)
        if p is base and nrml_first:
            rows.append(extra)
    if not nrml_first:
        rows.insert(0, extra)
    return FakeBroker(rows, broker.order_statuses)


def _state_two_products(qty: int = LOT, *, nrml_first: bool = True):  # noqa: ANN202
    book, broker = _state((qty, qty, qty, 0), qty)
    return book, _with_second_row(broker, Product.MIS, -qty, nrml_first=nrml_first)


# -- item 1 ---------------------------------------------------------------------------------------------------------

def test_core_nrml_and_mis_rows_of_one_contract_no_longer_break_the_exit(catalogue, eligibility) -> None:  # noqa: ANN001
    """The issue's case: NIFTY SELL leg held -65 NRML (the strategy's own fill) and -65 MIS (the user's own). assess
    used to raise 'duplicate contract'; the exit now reduces the NRML row only, with product NRML."""
    book, broker = _state_two_products()
    prep = close_partial_strategy(big_plan(LOT), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, stored_freeze=STORED_FREEZE)
    assert prep.ready, prep.reason
    sells = [o for o in prep.orders if o.leg_ref == SELL_PE]
    assert [(o.quantity, o.product) for o in sells] == [(LOT, Product.NRML)]


@pytest.mark.parametrize("nrml_first", [True, False])
def test_row_order_never_decides_which_product_is_exited(catalogue, eligibility, nrml_first) -> None:  # noqa: ANN001
    book, broker = _state_two_products(nrml_first=nrml_first)
    prep = close_partial_strategy(big_plan(LOT), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, stored_freeze=STORED_FREEZE)
    assert prep.ready and {o.product for o in prep.orders if o.leg_ref == SELL_PE} == {Product.NRML}


def test_the_strategy_whose_fills_are_mis_exits_the_mis_row(catalogue, eligibility) -> None:  # noqa: ANN001
    """The ledger, not a default, names the product: when the strategy's own fill on the contract was MIS, the MIS row is
    the one reduced and the NRML row (someone else's) is left alone."""
    book, broker = _state((LOT, LOT, LOT, 0), LOT)
    book._orders[next(k for k, o in book._orders.items() if o.contract == SHORT)] = dataclasses.replace(
        next(o for o in book._orders.values() if o.contract == SHORT), product=Product.MIS)
    rows = [dataclasses.replace(p, product=Product.MIS) if p.contract == SHORT else p for p in broker.positions]
    broker = _with_second_row(FakeBroker(rows, broker.order_statuses), Product.NRML, -LOT)
    prep = close_partial_strategy(big_plan(LOT), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, stored_freeze=STORED_FREEZE)
    assert prep.ready, prep.reason
    assert {o.product for o in prep.orders if o.leg_ref == SELL_PE} == {Product.MIS}


def test_two_products_the_ledger_cannot_separate_is_refused_with_four_parts(catalogue, eligibility) -> None:  # noqa: ANN001
    """The strategy's own fills on the contract are in BOTH products: the platform does not guess."""
    book, broker = _state((LOT, LOT, LOT, 0), LOT)
    book.add(Order(STRATEGY_ID, SELL_PE, SHORT, Action.SELL, LOT, D("80.00"), broker_order_id="BRK-9",
                   version_id="v1", product=Product.MIS))
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.apply_fill(FillEvent("T-9", "BRK-9", SHORT, Action.SELL, LOT, D("80.00"), FILL_AT))
    broker = _with_second_row(broker, Product.MIS, -LOT)
    a = assess(big_plan(LOT), broker.positions, broker.order_statuses, book, FakePlanner(), read_at=broker.read_at)
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED
    text = [m for m in a.mismatches if SHORT in m and "more than one product" in m]
    assert len(text) == 1 and "Exit the position in Zerodha yourself" in text[0]
    prep = close_partial_strategy(big_plan(LOT), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, stored_freeze=STORED_FREEZE)
    assert not prep.ready and prep.orders == ()


def test_two_held_rows_and_no_ledger_fill_on_the_contract_is_refused() -> None:
    """The ledger has no fill for the contract (so it names no product) while Zerodha shows it in two products."""
    book, broker = _state((LOT, 0, LOT, 0), LOT)
    base = _state((LOT, LOT, LOT, 0), LOT)[1].positions[1]
    rows = [p for p in broker.positions] + [dataclasses.replace(base, product=Product.NRML),
                                           dataclasses.replace(base, product=Product.MIS)]
    a = assess(big_plan(LOT), rows, broker.order_statuses, book, FakePlanner(), read_at=broker.read_at)
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert any(SHORT in m and "more than one product" in m for m in a.mismatches)


def test_a_true_duplicate_contract_and_product_is_still_refused() -> None:
    book, broker = _state((LOT, LOT, LOT, 0), LOT)
    with pytest.raises(ValueError, match="duplicate position contract and product"):
        assess(big_plan(LOT), broker.positions + [broker.positions[0]], broker.order_statuses, book, FakePlanner(),
               read_at=broker.read_at)


# -- item 2 ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("choice", ["complete", "retry"])
def test_the_sink_refuses_a_non_nrml_entry_order(catalogue, choice) -> None:  # noqa: ANN001
    book = book_with_three_filled()
    transport = _CountingTransport()
    order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1",
                  product=Product.MIS)
    with pytest.raises(SendRefused) as err:
        _sink(book, catalogue, choice=choice, transport=transport).resolve_all((_tagged(order),))
    assert "other than NRML" in err.value.reason and "Prepare the orders again" in display_text(err.value.message)
    assert transport.calls == []


def test_the_sink_still_passes_an_nrml_entry_order(catalogue) -> None:  # noqa: ANN001
    order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    (request,) = _sink(book_with_three_filled(), catalogue).resolve_all((_tagged(order),))
    assert request.product is Product.NRML


def test_a_close_exit_keeps_its_positions_product_through_the_sink(catalogue) -> None:  # noqa: ANN001
    book = book_with_three_filled()
    order = Order(STRATEGY_ID, "leg-2", CONTRACTS[1], Action.BUY, LOT, D("80.00"), version_id="v1",
                  product=Product.MIS)
    (request,) = _sink(book, catalogue, choice="close").resolve_all((_tagged(order),))
    assert request.product is Product.MIS


# -- round 2: a single held row is checked against the ledger's product too ---------------------------------------

def _one_short_row(rows_for_short):  # noqa: ANN001, ANN202
    book, broker = _state((LOT, LOT, LOT, 0), LOT)
    base = next(p for p in broker.positions if p.contract == SHORT)
    rows = [p for p in broker.positions if p.contract != SHORT] + [
        dataclasses.replace(base, net_quantity=q, product=prod) for q, prod in rows_for_short]
    return book, FakeBroker(rows, broker.order_statuses)


def test_round2_flat_nrml_row_and_an_unrelated_mis_row_is_refused_not_exited(catalogue, eligibility) -> None:  # noqa: ANN001
    """Probe: the strategy's fill is NRML; the user exited it in Kite (NRML row 0) and holds an unrelated MIS -65 on the
    same contract. The platform must not close that MIS position as the strategy's exit."""
    book, broker = _one_short_row([(0, Product.NRML), (-LOT, Product.MIS)])
    a = assess(big_plan(LOT), broker.positions, broker.order_statuses, book, FakePlanner(), read_at=broker.read_at)
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert any(SHORT in m and "did not place" in m for m in a.mismatches)
    prep = close_partial_strategy(big_plan(LOT), broker, book, FakePlanner(), entry_context(), catalogue, eligibility, stored_freeze=STORED_FREEZE)
    assert not prep.ready and prep.orders == ()


def test_round2_a_single_row_in_another_product_than_the_fills_is_refused() -> None:
    """A possible Kite MIS->NRML conversion: not guessed; the owner decides conversions later."""
    book, broker = _one_short_row([(-LOT, Product.MIS)])
    a = assess(big_plan(LOT), broker.positions, broker.order_statuses, book, FakePlanner(), read_at=broker.read_at)
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert any(SHORT in m and "did not place" in m for m in a.mismatches)


def test_round3_unread_product_row_is_refused_when_the_own_product_row_exists_but_is_flat() -> None:
    book, broker = _one_short_row([(0, Product.NRML), (-LOT, None)])
    rows = [dataclasses.replace(r, product=None) if (r.contract == SHORT and r.net_quantity) else r
            for r in broker.positions]
    a = assess(big_plan(LOT), rows, broker.order_statuses, book, FakePlanner(), read_at=broker.read_at)
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert any(SHORT in m and "did not place" in m and "will not close the other position" in m
               for m in a.mismatches)


def test_round2_all_zero_rows_outside_the_plan_are_listed_once() -> None:
    book, broker = _state((LOT, LOT, LOT, 0), LOT)
    stray = BrokerPositionLine("NIFTY26O06" + "99999CE", 0, D("1.00"), product=Product.NRML)
    rows = broker.positions + [stray, dataclasses.replace(stray, product=Product.MIS)]
    a = assess(big_plan(LOT), rows, broker.order_statuses, book, FakePlanner(), read_at=broker.read_at)
    assert sum("99999CE" in m for m in a.mismatches) == 1
