"""Order lifecycle state machine and the confirmed-fill position ledger (REQ-057, ADR-017).

Spec: REQ-057 AC-1 (the seven states and their transitions, below, as data, not scattered ifs),
AC-2 (a submitted order never changes strategy state or positions until the broker confirms
execution — Q195), AC-3 (strategy state/position is never derived only from order rows — Q194).
ADR-017: submission is not execution; no automatic retry (a Rejected order cannot go back to
Submitted — there is no resubmission transition and no resubmission API here).

Two objects do the work and stay separate on purpose:
- :class:`Order` is the state machine. Its own state transitions (even to ``EXECUTED``) never
  touch any position by themselves — that is the Core proof this module exists to make true.
- :class:`PositionLedger` is the only thing a strategy's confirmed position lives in, and the
  only way to change it is :meth:`PositionLedger.apply_fill` with a broker-confirmed
  :class:`FillEvent`. Nothing else may write to it.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Final, NoReturn

from ofo.engine.legs import Action, require_price


class OrderState(Enum):
    PREPARED = "Prepared"
    SUBMITTED = "Submitted"
    PENDING = "Pending"
    PARTIALLY_EXECUTED = "Partially Executed"
    EXECUTED = "Executed"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"


#: States from which no further transition is ever allowed (AC-1). A Rejected order has no
#: resubmission transition (ADR-017: no automatic retry, and no manual "resubmit" either — a new
#: order is a new Order).
TERMINAL_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.EXECUTED, OrderState.REJECTED, OrderState.CANCELLED}
)

#: The whole lifecycle as data (AC-1): allowed next states for every state. Any pair not listed
#: here is refused by :meth:`Order.transition`. ``PARTIALLY_EXECUTED`` allows a transition to
#: itself because further partial fills accumulate without changing the order's state.
ALLOWED_TRANSITIONS: Final[dict[OrderState, frozenset[OrderState]]] = {
    OrderState.PREPARED: frozenset({OrderState.SUBMITTED, OrderState.CANCELLED}),
    OrderState.SUBMITTED: frozenset({
        OrderState.PENDING,
        OrderState.PARTIALLY_EXECUTED,
        OrderState.EXECUTED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
    }),
    OrderState.PENDING: frozenset({
        OrderState.PARTIALLY_EXECUTED,
        OrderState.EXECUTED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
    }),
    OrderState.PARTIALLY_EXECUTED: frozenset({
        OrderState.PARTIALLY_EXECUTED,
        OrderState.EXECUTED,
        OrderState.CANCELLED,
    }),
    OrderState.EXECUTED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.CANCELLED: frozenset(),
}

_NON_FILLING_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.PREPARED, OrderState.SUBMITTED, OrderState.PENDING, OrderState.REJECTED, OrderState.CANCELLED}
)


def _non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer, got {value!r}")
    return value


@dataclass
class Order:
    """One order, always belonging to a strategy (CLAUDE.md: no standalone order entry).

    ``state`` is read-only from outside; the only way to move it is :meth:`transition`, so a raw
    state change that bypasses the proper method is rejected by Python itself (there is no
    setter). ``filled_quantity`` only grows, via ``transition(..., filled_delta=...)``, and can
    never exceed ``quantity``.
    """

    strategy_id: str
    leg_ref: str
    contract: str
    side: Action
    quantity: int
    price: Decimal
    broker_order_id: str | None = None
    _state: OrderState = field(default=OrderState.PREPARED, init=False, repr=False)
    _filled_quantity: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        _non_empty_str(self.strategy_id, "strategy_id")
        _non_empty_str(self.leg_ref, "leg_ref")
        _non_empty_str(self.contract, "contract")
        if not isinstance(self.side, Action):
            raise ValueError(f"side must be an Action, got {self.side!r}")
        _positive_int(self.quantity, "quantity")
        require_price(self.price, "price", allow_zero=False)
        if self.broker_order_id is not None:
            _non_empty_str(self.broker_order_id, "broker_order_id")

    @property
    def state(self) -> OrderState:
        return self._state

    @property
    def filled_quantity(self) -> int:
        return self._filled_quantity

    def transition(self, new_state: OrderState, *, filled_delta: int = 0) -> None:
        """Move to ``new_state`` if the transition table allows it; refuse everything else.

        ``filled_delta`` is the ordered-quantity units this transition itself confirms as filled
        (0 for every state that carries no fill). This method never touches a
        :class:`PositionLedger` — an order changing state, including to ``EXECUTED``, changes
        nothing about the strategy's position by itself (AC-2/AC-3); only
        :meth:`PositionLedger.apply_fill` does that, from a separate, explicit fill event.
        """
        if not isinstance(new_state, OrderState):
            raise ValueError(f"new_state must be an OrderState, got {new_state!r}")
        allowed = ALLOWED_TRANSITIONS.get(self._state, frozenset())
        if new_state not in allowed:
            raise ValueError(f"{self._state.value} -> {new_state.value} is not an allowed order transition")
        if isinstance(filled_delta, bool) or not isinstance(filled_delta, int) or filled_delta < 0:
            raise ValueError(f"filled_delta must be a non-negative integer, got {filled_delta!r}")
        if filled_delta and new_state in _NON_FILLING_STATES:
            raise ValueError(f"{new_state.value} carries no fill; filled_delta must be 0, got {filled_delta}")
        new_filled = self._filled_quantity + filled_delta
        if new_filled > self.quantity:
            raise ValueError(
                f"filled quantity {new_filled} would exceed ordered quantity {self.quantity}"
            )
        if new_state is OrderState.EXECUTED and new_filled != self.quantity:
            raise ValueError(
                f"cannot mark Executed with {new_filled} of {self.quantity} filled; use Partially Executed"
            )
        if new_state is OrderState.PARTIALLY_EXECUTED and new_filled == 0:
            raise ValueError("Partially Executed needs at least one filled unit (filled_delta must be > 0)")
        self._state = new_state
        self._filled_quantity = new_filled


@dataclass(frozen=True)
class FillEvent:
    """One broker-confirmed fill. This is the ONLY event that may change a strategy's position."""

    strategy_id: str
    contract: str
    side: Action
    quantity: int
    price: Decimal
    broker_order_id: str

    def __post_init__(self) -> None:
        _non_empty_str(self.strategy_id, "strategy_id")
        _non_empty_str(self.contract, "contract")
        if not isinstance(self.side, Action):
            raise ValueError(f"side must be an Action, got {self.side!r}")
        _positive_int(self.quantity, "quantity")
        require_price(self.price, "price", allow_zero=False)
        _non_empty_str(self.broker_order_id, "broker_order_id")


class PositionLedger:
    """Confirmed positions, keyed by (strategy_id, contract). Changes ONLY via :meth:`apply_fill`.

    An order's own state (Submitted, Pending, even Executed) never reaches this class; only a
    :class:`FillEvent`, standing for the broker's confirmation, can move a position (AC-2, Q195).
    """

    def __init__(self) -> None:
        self._positions: dict[tuple[str, str], int] = {}
        self._fills: list[FillEvent] = []

    def apply_fill(self, fill: FillEvent) -> None:
        if not isinstance(fill, FillEvent):
            raise ValueError(f"apply_fill needs a FillEvent, got {fill!r}")
        key = (fill.strategy_id, fill.contract)
        delta = fill.quantity if fill.side is Action.BUY else -fill.quantity
        self._positions[key] = self._positions.get(key, 0) + delta
        self._fills.append(fill)

    def position(self, strategy_id: str, contract: str) -> int:
        """Net confirmed units for one contract of one strategy (0 if never filled)."""
        return self._positions.get((strategy_id, contract), 0)

    def positions_for(self, strategy_id: str) -> Mapping[str, int]:
        return {
            contract: qty
            for (sid, contract), qty in self._positions.items()
            if sid == strategy_id and qty != 0
        }

    @property
    def fills(self) -> tuple[FillEvent, ...]:
        return tuple(self._fills)


def derive_strategy_position(ledger: PositionLedger, strategy_id: str) -> Mapping[str, int]:
    """The one legitimate way to get a strategy's position (AC-3): read the ledger of confirmed
    fills. There is no other function in this module that returns a position, on purpose.
    """
    if not isinstance(ledger, PositionLedger):
        raise ValueError(f"derive_strategy_position needs a PositionLedger, got {ledger!r}")
    _non_empty_str(strategy_id, "strategy_id")
    return ledger.positions_for(strategy_id)


def refuse_position_from_orders(orders: Iterable[Order]) -> NoReturn:
    """Guard against AC-3's forbidden shortcut: deriving a strategy's position or state from order
    rows alone (an Executed order row is not a fill; reconciliation/the broker-confirmed
    :class:`PositionLedger` is the only source, Q194). Always raises; there is no code path here
    that reads ``Order.state`` and returns a position, so this cannot silently start working.
    """
    list(orders)  # touch the iterable so a caller cannot claim it was ignored unread
    raise ValueError(
        "a strategy's position/state must never be derived from order rows alone; "
        "use derive_strategy_position(ledger, strategy_id) against confirmed fills"
    )
