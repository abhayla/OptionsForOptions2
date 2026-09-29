"""AC-3: strategy state/position is never derived only from order rows (Q194). The only
legitimate source is derive_strategy_position(book, ...) reading broker-confirmed fills via an
OrderBook; refuse_position_from_orders documents and enforces the forbidden shortcut.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action
from ofo.orders.model import (
    FillEvent,
    Order,
    OrderBook,
    OrderState,
    derive_strategy_position,
    refuse_position_from_orders,
)

UTC = datetime.timezone.utc
CONTRACT = "NIFTY26OCT23200CE"


def make_order() -> Order:
    return Order("STRAT-5", "leg-0", CONTRACT, Action.BUY, 75, D("91.50"), broker_order_id="BRK-5")


def test_executed_order_row_without_a_fill_event_changes_nothing() -> None:
    """AC-3: an Executed order row, on its own, is not a source of position. In ONE book holding a
    submitted order, every way of producing an "Executed" row without a fill is refused (book
    transition, order transition, a forged Executed row added to the book), and the derived position
    stays empty; only a confirmed FillEvent in that same book moves it (issue #29 item 4)."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-5", OrderState.SUBMITTED)
    assert derive_strategy_position(book, "STRAT-5") == {}

    with pytest.raises(ValueError):
        book.transition("BRK-5", OrderState.EXECUTED)
    with pytest.raises(ValueError):
        book.order_for("BRK-5").order.transition(OrderState.EXECUTED)
    forged = Order("STRAT-5", "leg-1", CONTRACT, Action.BUY, 75, D("91.50"), broker_order_id="BRK-6")
    object.__setattr__(forged, "_state", OrderState.EXECUTED)  # a raw state change bypassing every method
    with pytest.raises(ValueError):
        book.add(forged)
    assert book.order_for("BRK-5").state is OrderState.SUBMITTED
    assert derive_strategy_position(book, "STRAT-5") == {}

    view = book.apply_fill(
        FillEvent("T-1", "BRK-5", CONTRACT, Action.BUY, 75, D("91.50"),
                  datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC))
    )
    assert view.state is OrderState.EXECUTED
    assert derive_strategy_position(book, "STRAT-5") == {CONTRACT: 75}


def test_derived_position_matches_confirmed_fills_only() -> None:
    """AC-3 positive case: once a fill is confirmed in the book, derive_strategy_position
    reflects exactly that confirmed quantity, independent of any order's own state."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-5", OrderState.SUBMITTED)
    book.apply_fill(
        FillEvent("T-1", "BRK-5", CONTRACT, Action.BUY, 75, D("91.50"),
                  datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC))
    )
    assert derive_strategy_position(book, "STRAT-5") == {CONTRACT: 75}


def test_refuse_position_from_orders_always_raises() -> None:
    """AC-3: the forbidden shortcut (derive position/state from order rows alone) is refused,
    even when the orders are all Executed -- it is not a working code path under any input."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-5", OrderState.SUBMITTED)
    executed = book.apply_fill(
        FillEvent("T-1", "BRK-5", CONTRACT, Action.BUY, 75, D("91.50"),
                  datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC))
    )
    with pytest.raises(ValueError):
        refuse_position_from_orders([executed.order])
    with pytest.raises(ValueError):
        refuse_position_from_orders([])  # even the empty case is refused, not silently {}


def test_derive_strategy_position_rejects_a_non_book_source() -> None:
    """AC-3 negative case: derive_strategy_position refuses anything that is not the OrderBook
    itself (e.g. a plain list of order rows), so the "order rows alone" shortcut cannot be taken
    by accident by passing the wrong object."""
    with pytest.raises(ValueError):
        derive_strategy_position([make_order()], "STRAT-5")  # type: ignore[arg-type]
