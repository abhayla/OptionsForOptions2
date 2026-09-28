"""AC-1: exactly seven order states, an explicit allowed-transition table, every other transition
refused; partial fills accumulate filled quantity and never exceed the ordered quantity. Also the
work item's Core/Proof: a submitted order leaves the strategy's positions unchanged until a
broker fill confirmation arrives, and then only the confirmed quantity changes.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action
from ofo.orders.model import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    FillEvent,
    Order,
    OrderBook,
    OrderState,
)

UTC = datetime.timezone.utc
CONTRACT = "NIFTY26OCT23000CE"


def make_order(**overrides: object) -> Order:
    fields = dict(
        strategy_id="STRAT-1", leg_ref="leg-0", contract=CONTRACT,
        side=Action.BUY, quantity=75, price=D("120.50"), broker_order_id="BRK-1",
    )
    fields.update(overrides)
    return Order(**fields)  # type: ignore[arg-type]


def make_fill(event_id: str, quantity: int, *, broker_order_id: str = "BRK-1") -> FillEvent:
    return FillEvent(
        event_id, broker_order_id, CONTRACT, Action.BUY, quantity, D("120.50"),
        datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )


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
    """AC-1 + Core: drive one order through every allowed transition via the OrderBook; positions
    move only on confirmed fills, and only by the confirmed quantity, never by the order's own
    state change.
    """
    book = OrderBook()
    order = make_order(quantity=100)
    book.add(order)

    order = book.transition("BRK-1", OrderState.SUBMITTED)
    assert order.state is OrderState.SUBMITTED
    assert book.position("STRAT-1", CONTRACT) == 0  # Core: submission changes nothing

    order = book.transition("BRK-1", OrderState.PENDING)
    assert order.state is OrderState.PENDING
    assert book.position("STRAT-1", CONTRACT) == 0

    # First confirmed fill: broker confirms 40 of 100.
    order = book.apply_fill(make_fill("EVT-1", 40))
    assert order.state is OrderState.PARTIALLY_EXECUTED
    assert order.filled_quantity == 40
    assert book.position("STRAT-1", CONTRACT) == 40  # Core: only the confirmed quantity changes

    # Second partial fill accumulates.
    order = book.apply_fill(make_fill("EVT-2", 35))
    assert order.filled_quantity == 75
    assert book.position("STRAT-1", CONTRACT) == 75

    # Final fill completes the order: state moves to Executed automatically.
    order = book.apply_fill(make_fill("EVT-3", 25))
    assert order.state is OrderState.EXECUTED
    assert order.filled_quantity == 100
    assert book.position("STRAT-1", CONTRACT) == 100


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
    seeded = order._copy_with(state=start, filled_quantity=0)  # test-only seed, not a public path
    with pytest.raises(ValueError):
        seeded.transition(target)
    assert seeded.state is start  # refused transition leaves the (already-returned) state unchanged


def test_partial_fill_cannot_exceed_ordered_quantity() -> None:
    """AC-1: filled quantity accumulates but never above the ordered quantity."""
    book = OrderBook()
    book.add(make_order(quantity=50))
    book.transition("BRK-1", OrderState.SUBMITTED)
    order = book.apply_fill(make_fill("EVT-1", 40))
    assert order.filled_quantity == 40
    with pytest.raises(ValueError):
        book.apply_fill(make_fill("EVT-2", 20))  # 40 + 20 > 50
    assert book.order_for("BRK-1").filled_quantity == 40  # rejected fill changed nothing


def test_executed_requires_full_fill() -> None:
    """AC-1: an order's own transition() cannot be marked Executed while units remain unfilled."""
    order = make_order(quantity=50)
    submitted = order.transition(OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        submitted.transition(OrderState.EXECUTED, filled_delta=30)  # only 30 of 50


def test_a_fully_filled_order_cannot_be_cancelled() -> None:
    """AC-1 fix-round negative case: an order fully filled via a confirmed fill is Executed, and
    Executed is terminal -- it can never be recorded as Cancelled.
    """
    book = OrderBook()
    book.add(make_order(quantity=25))
    book.transition("BRK-1", OrderState.SUBMITTED)
    order = book.apply_fill(make_fill("EVT-1", 25))
    assert order.state is OrderState.EXECUTED
    with pytest.raises(ValueError):
        book.transition("BRK-1", OrderState.CANCELLED)


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


def test_order_fields_have_no_public_setter() -> None:
    """Input-domain checklist / W-019 fix round: a raw state change that bypasses transition()
    (including quantity, state or filled_quantity) is rejected -- Order is frozen.
    """
    order = make_order()
    with pytest.raises(AttributeError):
        order.state = OrderState.EXECUTED  # type: ignore[misc]
    with pytest.raises(AttributeError):
        order._state = OrderState.EXECUTED  # type: ignore[misc]
    with pytest.raises(AttributeError):
        order._filled_quantity = 999  # type: ignore[misc]
    with pytest.raises(AttributeError):
        order.quantity = 999  # type: ignore[misc]
