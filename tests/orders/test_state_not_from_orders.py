"""AC-3: strategy state/position is never derived only from order rows (Q194). The only
legitimate source is derive_strategy_position(ledger, ...) reading broker-confirmed fills;
refuse_position_from_orders documents and enforces the forbidden shortcut.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action
from ofo.orders.model import (
    FillEvent,
    Order,
    OrderState,
    PositionLedger,
    derive_strategy_position,
    refuse_position_from_orders,
)

CONTRACT = "NIFTY26OCT23200CE"


def test_executed_order_row_without_a_fill_event_changes_nothing() -> None:
    """AC-3: an Executed order row, on its own, is not a source of position -- the derived
    position for the strategy stays empty until a confirmed FillEvent lands in the ledger.
    """
    order = Order("STRAT-5", "leg-0", CONTRACT, Action.BUY, 75, D("91.50"))
    order.transition(OrderState.SUBMITTED)
    order.transition(OrderState.EXECUTED, filled_delta=75)
    assert order.state is OrderState.EXECUTED

    ledger = PositionLedger()  # never told about the order above
    assert derive_strategy_position(ledger, "STRAT-5") == {}


def test_derived_position_matches_confirmed_fills_only() -> None:
    """AC-3 positive case: once a fill is confirmed in the ledger, derive_strategy_position
    reflects exactly that confirmed quantity, independent of any order's own state."""
    order = Order("STRAT-5", "leg-0", CONTRACT, Action.BUY, 75, D("91.50"))
    order.transition(OrderState.SUBMITTED)
    order.transition(OrderState.EXECUTED, filled_delta=75)

    ledger = PositionLedger()
    ledger.apply_fill(FillEvent("STRAT-5", CONTRACT, Action.BUY, 75, D("91.50"), "BRK-1"))
    assert derive_strategy_position(ledger, "STRAT-5") == {CONTRACT: 75}


def test_refuse_position_from_orders_always_raises() -> None:
    """AC-3: the forbidden shortcut (derive position/state from order rows alone) is refused,
    even when the orders are all Executed -- it is not a working code path under any input.
    """
    orders = [
        Order("STRAT-5", "leg-0", CONTRACT, Action.BUY, 75, D("91.50")),
    ]
    orders[0].transition(OrderState.SUBMITTED)
    orders[0].transition(OrderState.EXECUTED, filled_delta=75)
    with pytest.raises(ValueError):
        refuse_position_from_orders(orders)
    with pytest.raises(ValueError):
        refuse_position_from_orders([])  # even the empty case is refused, not silently {}


def test_derive_strategy_position_rejects_a_non_ledger_source() -> None:
    """AC-3 negative case: derive_strategy_position refuses anything that is not the ledger
    itself (e.g. a plain list of order rows), so the "order rows alone" shortcut cannot be taken
    by accident by passing the wrong object.
    """
    with pytest.raises(ValueError):
        derive_strategy_position([Order("STRAT-5", "leg-0", CONTRACT, Action.BUY, 75, D("91.50"))], "STRAT-5")  # type: ignore[arg-type]
