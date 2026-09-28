"""AC-2: a submitted order never changes strategy state or positions until the broker confirms
execution (Q195). Every state a submitted order can reach on its own -- Pending, Rejected,
Cancelled -- is exercised here without ever calling OrderBook.apply_fill, and the ledger must
stay empty throughout. Also proves the fix-round guard: a fill is refused unless it matches the
exact order it claims to fill (unknown order, wrong contract, wrong side, an order that is not
open), and a completing fill always drives the order to Executed, never leaving it short.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action
from ofo.orders.model import FillEvent, Order, OrderBook, OrderState


UTC = datetime.timezone.utc
CONTRACT = "NIFTY26OCT23000PE"


def make_order(**overrides: object) -> Order:
    fields = dict(
        strategy_id="STRAT-9", leg_ref="leg-0", contract=CONTRACT,
        side=Action.SELL, quantity=75, price=D("86.00"), broker_order_id="BRK-9",
    )
    fields.update(overrides)
    return Order(**fields)  # type: ignore[arg-type]


def fill(event_id: str, quantity: int, *, broker_order_id: str = "BRK-9", contract: str = CONTRACT,
         side: Action = Action.SELL) -> FillEvent:
    return FillEvent(
        event_id, broker_order_id, contract, side, quantity, D("86.00"),
        datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )


def test_submitted_and_pending_change_nothing() -> None:
    """AC-2: moving to Submitted, then Pending, leaves the ledger untouched."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    assert book.position("STRAT-9", CONTRACT) == 0
    book.transition("BRK-9", OrderState.PENDING)
    assert book.position("STRAT-9", CONTRACT) == 0
    assert book.fills == ()


def test_rejected_and_cancelled_never_touch_the_ledger() -> None:
    """AC-2 negative case: a rejected/cancelled order (no fill ever confirmed) never moves the
    ledger, and cannot be resubmitted (ADR-017: no automatic or manual retry).
    """
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.transition("BRK-9", OrderState.REJECTED)
    assert book.position("STRAT-9", CONTRACT) == 0
    with pytest.raises(ValueError):
        book.transition("BRK-9", OrderState.SUBMITTED)  # no resubmission transition exists

    book.add(make_order(leg_ref="leg-1", quantity=20, broker_order_id="BRK-9B"))
    book.transition("BRK-9B", OrderState.CANCELLED)
    assert book.position("STRAT-9", CONTRACT) == 0


def test_a_completing_fill_always_moves_to_executed() -> None:
    """AC-2/Core positive case: a fill that fully covers the order drives it straight to
    Executed -- the caller cannot leave it at Partially Executed, and the position moves by
    exactly the confirmed quantity.
    """
    book = OrderBook()
    book.add(make_order(quantity=75))
    book.transition("BRK-9", OrderState.SUBMITTED)
    order = book.apply_fill(fill("EVT-1", 75))
    assert order.state is OrderState.EXECUTED
    assert book.position("STRAT-9", CONTRACT) == -75  # SELL reduces net position


def test_fill_for_an_unknown_broker_order_id_is_refused() -> None:
    """W-019 fix round (b): a fill naming a broker_order_id that was never registered is refused,
    not silently ignored or matched to the wrong order.
    """
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("EVT-1", 10, broker_order_id="BRK-DOES-NOT-EXIST"))
    assert book.position("STRAT-9", CONTRACT) == 0


def test_fill_for_the_wrong_contract_is_refused() -> None:
    """W-019 fix round (c): a fill's contract must match the order it claims to fill."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("EVT-1", 10, contract="NIFTY26OCT23400CE"))
    assert book.position("STRAT-9", CONTRACT) == 0


def test_fill_for_the_wrong_side_is_refused() -> None:
    """W-019 fix round (c): a fill's side must match the order it claims to fill."""
    book = OrderBook()
    book.add(make_order(side=Action.SELL))
    book.transition("BRK-9", OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("EVT-1", 10, side=Action.BUY))
    assert book.position("STRAT-9", CONTRACT) == 0


def test_fill_for_a_closed_order_is_refused() -> None:
    """W-019 fix round: a fill against an order that is not open (Rejected here) is refused."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.transition("BRK-9", OrderState.REJECTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("EVT-1", 10))
    assert book.position("STRAT-9", CONTRACT) == 0


def test_a_replayed_fill_moves_the_position_only_once() -> None:
    """W-019 fix round (a): the same fill message applied twice (same event_id) is an idempotent
    no-op the second time -- the position moves once, not twice.
    """
    book = OrderBook()
    book.add(make_order(quantity=75))
    book.transition("BRK-9", OrderState.SUBMITTED)
    duplicate = fill("EVT-1", 30)
    book.apply_fill(duplicate)
    assert book.position("STRAT-9", CONTRACT) == -30
    order_after_replay = book.apply_fill(duplicate)  # exact same event_id, replayed
    assert book.position("STRAT-9", CONTRACT) == -30  # unchanged
    assert order_after_replay.filled_quantity == 30  # order also unchanged, not double-counted


def test_fill_needs_a_timezone_aware_timestamp() -> None:
    """FillEvent construction refuses a naive datetime (W-019 fix round item 1)."""
    with pytest.raises(ValueError):
        FillEvent("EVT-1", "BRK-9", CONTRACT, Action.SELL, 10, D("86.00"), datetime.datetime(2026, 9, 29, 10, 0))


def test_fill_needs_an_event_id() -> None:
    """FillEvent construction refuses a missing/blank event_id (broker trade id)."""
    with pytest.raises(ValueError):
        FillEvent("", "BRK-9", CONTRACT, Action.SELL, 10, D("86.00"), datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC))
