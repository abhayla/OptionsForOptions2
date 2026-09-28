"""AC-2: a submitted order never changes strategy state or positions until the broker confirms
execution (Q195). Every state a submitted order can reach on its own -- Pending, Partially
Executed, Executed, Rejected, Cancelled -- is exercised here without ever calling
PositionLedger.apply_fill, and the ledger must stay empty throughout.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action
from ofo.orders.model import FillEvent, Order, OrderState, PositionLedger


CONTRACT = "NIFTY26OCT23000PE"


def make_order(quantity: int = 75) -> Order:
    return Order("STRAT-9", "leg-0", CONTRACT, Action.SELL, quantity, D("86.00"))


def test_submitted_and_pending_change_nothing() -> None:
    """AC-2: moving to Submitted, then Pending, leaves the ledger untouched."""
    order = make_order()
    ledger = PositionLedger()
    order.transition(OrderState.SUBMITTED)
    assert ledger.position("STRAT-9", CONTRACT) == 0
    order.transition(OrderState.PENDING)
    assert ledger.position("STRAT-9", CONTRACT) == 0
    assert ledger.fills == ()


def test_order_marked_executed_without_a_fill_event_leaves_the_ledger_empty() -> None:
    """AC-2/Core: even reaching Executed, by state transition alone, changes no position -- only
    an explicit, broker-confirmed FillEvent applied to the ledger can.
    """
    order = make_order(quantity=75)
    ledger = PositionLedger()
    order.transition(OrderState.SUBMITTED)
    order.transition(OrderState.EXECUTED, filled_delta=75)
    assert order.state is OrderState.EXECUTED
    assert order.filled_quantity == 75
    assert ledger.position("STRAT-9", CONTRACT) == 0  # no apply_fill was ever called
    assert ledger.fills == ()


def test_partially_executed_without_a_fill_event_leaves_the_ledger_empty() -> None:
    """AC-2: a Partially Executed order (broker says "some units confirmed") is still not a
    position change on its own; only apply_fill moves the ledger.
    """
    order = make_order(quantity=75)
    ledger = PositionLedger()
    order.transition(OrderState.SUBMITTED)
    order.transition(OrderState.PARTIALLY_EXECUTED, filled_delta=30)
    assert ledger.position("STRAT-9", CONTRACT) == 0


def test_rejected_and_cancelled_never_touch_the_ledger() -> None:
    """AC-2 negative case: a rejected/cancelled order (no fill ever confirmed) never moves the
    ledger, and cannot be resubmitted (ADR-017: no automatic or manual retry).
    """
    rejected = make_order()
    ledger = PositionLedger()
    rejected.transition(OrderState.SUBMITTED)
    rejected.transition(OrderState.REJECTED)
    assert ledger.position("STRAT-9", CONTRACT) == 0
    with pytest.raises(ValueError):
        rejected.transition(OrderState.SUBMITTED)  # no resubmission transition exists

    cancelled = Order("STRAT-9", "leg-1", CONTRACT, Action.SELL, 20, D("86.00"))
    cancelled.transition(OrderState.CANCELLED)
    assert ledger.position("STRAT-9", CONTRACT) == 0


def test_the_ledger_only_moves_by_the_confirmed_quantity_of_an_explicit_fill() -> None:
    """AC-2/Core, positive case: applying the fill event is what moves the ledger, by exactly the
    confirmed quantity -- not the ordered quantity, not the order's filled_quantity bookkeeping.
    """
    order = make_order(quantity=75)
    ledger = PositionLedger()
    order.transition(OrderState.SUBMITTED)
    order.transition(OrderState.PARTIALLY_EXECUTED, filled_delta=50)
    assert ledger.position("STRAT-9", CONTRACT) == 0
    ledger.apply_fill(FillEvent("STRAT-9", CONTRACT, Action.SELL, 50, D("86.00"), "BRK-1"))
    assert ledger.position("STRAT-9", CONTRACT) == -50  # SELL reduces net position
