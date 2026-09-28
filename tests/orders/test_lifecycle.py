"""AC-1: exactly seven order states, an explicit allowed-transition table, every other transition
refused; partial fills accumulate filled quantity and never exceed the ordered quantity. Also the
work item's Core/Proof: a submitted order leaves the strategy's positions unchanged until a
broker fill confirmation arrives, and then only the confirmed quantity changes.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action
from ofo.orders.model import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    FillEvent,
    Order,
    OrderState,
    PositionLedger,
)


def make_order(**overrides: object) -> Order:
    fields = dict(
        strategy_id="STRAT-1", leg_ref="leg-0", contract="NIFTY26OCT23000CE",
        side=Action.BUY, quantity=75, price=D("120.50"),
    )
    fields.update(overrides)
    return Order(**fields)  # type: ignore[arg-type]


def test_exactly_seven_states() -> None:
    """AC-1: the state set is exactly these seven, no more, no fewer."""
    names = {s.value for s in OrderState}
    assert names == {
        "Prepared", "Submitted", "Pending", "Partially Executed", "Executed", "Rejected", "Cancelled",
    }
    assert len(OrderState) == 7


def test_transition_table_covers_every_state_and_terminals_have_no_exits() -> None:
    """AC-1: every state has an entry in the table; Executed/Rejected/Cancelled allow nothing."""
    assert set(ALLOWED_TRANSITIONS) == set(OrderState)
    for terminal in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()
    assert TERMINAL_STATES == {OrderState.EXECUTED, OrderState.REJECTED, OrderState.CANCELLED}


def test_full_happy_path_submitted_to_executed_via_partial_fills() -> None:
    """AC-1 + Core: drive one order through every allowed transition; positions move only on
    confirmed fills, and only by the confirmed quantity, never by the order's own state change.
    """
    order = make_order(quantity=100)
    ledger = PositionLedger()

    assert order.state is OrderState.PREPARED
    order.transition(OrderState.SUBMITTED)
    assert order.state is OrderState.SUBMITTED
    assert ledger.position("STRAT-1", "NIFTY26OCT23000CE") == 0  # Core: submission changes nothing

    order.transition(OrderState.PENDING)
    assert order.state is OrderState.PENDING
    assert ledger.position("STRAT-1", "NIFTY26OCT23000CE") == 0

    # First partial fill: broker confirms 40 of 100.
    order.transition(OrderState.PARTIALLY_EXECUTED, filled_delta=40)
    assert order.filled_quantity == 40
    assert ledger.position("STRAT-1", "NIFTY26OCT23000CE") == 0  # order state alone still changes nothing
    ledger.apply_fill(FillEvent("STRAT-1", "NIFTY26OCT23000CE", Action.BUY, 40, D("120.50"), "BRK-1"))
    assert ledger.position("STRAT-1", "NIFTY26OCT23000CE") == 40  # Core: only the confirmed quantity changes

    # Second partial fill accumulates (self-transition), never exceeding ordered quantity.
    order.transition(OrderState.PARTIALLY_EXECUTED, filled_delta=35)
    assert order.filled_quantity == 75
    ledger.apply_fill(FillEvent("STRAT-1", "NIFTY26OCT23000CE", Action.BUY, 35, D("120.60"), "BRK-2"))
    assert ledger.position("STRAT-1", "NIFTY26OCT23000CE") == 75

    # Final fill completes the order.
    order.transition(OrderState.EXECUTED, filled_delta=25)
    assert order.state is OrderState.EXECUTED
    assert order.filled_quantity == 100
    ledger.apply_fill(FillEvent("STRAT-1", "NIFTY26OCT23000CE", Action.BUY, 25, D("120.70"), "BRK-3"))
    assert ledger.position("STRAT-1", "NIFTY26OCT23000CE") == 100


@pytest.mark.parametrize(
    "start,target",
    [
        (OrderState.PREPARED, OrderState.PENDING),
        (OrderState.PREPARED, OrderState.EXECUTED),
        (OrderState.SUBMITTED, OrderState.PREPARED),
        (OrderState.PENDING, OrderState.PREPARED),
        (OrderState.EXECUTED, OrderState.SUBMITTED),
        (OrderState.REJECTED, OrderState.SUBMITTED),  # ADR-017: no automatic/manual resubmission
        (OrderState.CANCELLED, OrderState.SUBMITTED),
    ],
)
def test_disallowed_transitions_are_refused(start: OrderState, target: OrderState) -> None:
    """AC-1: any transition not in the table is refused, including Rejected -> Submitted."""
    order = make_order()
    order._state = start  # test-only seed of the starting state, not a production code path
    with pytest.raises(ValueError):
        order.transition(target)
    assert order.state is start  # refused transition leaves state unchanged


def test_partial_fill_cannot_exceed_ordered_quantity() -> None:
    """AC-1: filled quantity accumulates but never above the ordered quantity."""
    order = make_order(quantity=50)
    order.transition(OrderState.SUBMITTED)
    order.transition(OrderState.PARTIALLY_EXECUTED, filled_delta=40)
    with pytest.raises(ValueError):
        order.transition(OrderState.PARTIALLY_EXECUTED, filled_delta=20)  # 40 + 20 > 50
    assert order.filled_quantity == 40


def test_executed_requires_full_fill() -> None:
    """AC-1: an order cannot be marked Executed while units remain unfilled."""
    order = make_order(quantity=50)
    order.transition(OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        order.transition(OrderState.EXECUTED, filled_delta=30)  # only 30 of 50


def test_order_requires_a_strategy() -> None:
    """CLAUDE.md: every order belongs to a strategy; an order without one is refused."""
    with pytest.raises(ValueError):
        make_order(strategy_id="")
    with pytest.raises(ValueError):
        make_order(strategy_id=None)


def test_price_goes_through_the_engine_money_guard() -> None:
    """Price is a Decimal via the engine's money guard: a float-derived value is refused."""
    with pytest.raises(ValueError):
        make_order(price=D(0.1))  # Decimal built from a float, not a clean 2dp value
    with pytest.raises(ValueError):
        make_order(price=D("0"))  # allow_zero=False


def test_state_has_no_public_setter() -> None:
    """Input-domain checklist: a raw state change that bypasses transition() is rejected."""
    order = make_order()
    with pytest.raises(AttributeError):
        order.state = OrderState.EXECUTED  # type: ignore[misc]
