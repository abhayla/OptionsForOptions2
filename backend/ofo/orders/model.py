"""Order lifecycle state machine and the confirmed-fill position ledger (REQ-057, ADR-017).

Spec: REQ-057 AC-1 (the seven states and their transitions, below, as data, not scattered ifs),
AC-2 (a submitted order never changes strategy state or positions until the broker confirms
execution — Q195), AC-3 (strategy state/position is never derived only from order rows — Q194).
ADR-017: submission is not execution; no automatic retry (a Rejected order cannot go back to
Submitted — there is no resubmission transition and no resubmission API here).

W-019 fix round: a bare "apply this fill to the ledger" method accepted any fill message without
checking it against the order it claims to fill (replays, unknown orders, wrong contract/side,
over-fill), and the state machine let a fully filled order be recorded as Cancelled. The fix is
:class:`OrderBook`, which owns both the orders and the ledger and is the ONLY way a fill reaches
either of them:

- :class:`Order` is immutable (frozen); every field, including its private state fields, refuses
  a direct assignment, so the only way to move it is :meth:`Order.transition`, which returns a
  NEW ``Order`` and never touches a position by itself — not even a transition to ``EXECUTED``.
  That is the Core proof this module exists to make true.
- :class:`OrderBook.apply_fill` is the one place a :class:`FillEvent` is accepted: it checks the
  fill's ``broker_order_id`` against a REGISTERED order, that the contract and side match, that
  the order is open, that the cumulative filled quantity never exceeds the ordered quantity, and
  that a replayed ``event_id`` moves nothing a second time — then updates the order's state
  (auto-selecting ``Partially Executed`` or ``Executed``, never leaving a fully filled order
  short) and the ledger's position together, in the same call.
"""
from __future__ import annotations

import dataclasses
import datetime
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
#: itself because further partial fills accumulate without changing the order's state; a
#: transition to ``CANCELLED`` from there means "cancel the remaining, unfilled quantity" and is
#: refused once the order is already fully filled (see :meth:`Order.transition`).
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

_OPEN_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.SUBMITTED, OrderState.PENDING, OrderState.PARTIALLY_EXECUTED}
)
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


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer, got {value!r}")
    return value


@dataclass(frozen=True)
class Order:
    """One order, always belonging to a strategy (CLAUDE.md: no standalone order entry).

    Frozen: every field, public or private, refuses a direct assignment (``order.quantity = 5``,
    ``order._state = ...`` and ``order._filled_quantity = ...`` all raise). The only way to move
    an order is :meth:`transition`, which returns a NEW ``Order`` — the caller must keep the
    returned value (an :class:`OrderBook` does this for you).
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

    def _copy_with(self, *, state: OrderState, filled_quantity: int) -> Order:
        """Build a new ``Order`` sharing every other field. Bypasses ``__init__``/validation on
        purpose (the fields were already validated once, at original construction) and is the
        only place outside a fresh ``Order(...)`` call that ever sets ``_state``/``_filled_quantity``.
        """
        clone = object.__new__(Order)
        for f in dataclasses.fields(self):
            object.__setattr__(clone, f.name, getattr(self, f.name))
        object.__setattr__(clone, "_state", state)
        object.__setattr__(clone, "_filled_quantity", filled_quantity)
        return clone

    def transition(self, new_state: OrderState, *, filled_delta: int = 0) -> Order:
        """Return a NEW ``Order`` in ``new_state`` if the transition table allows it; refuse
        everything else, including: over-filling, marking ``Executed`` while short of the ordered
        quantity, ``Partially Executed`` with no fill at all, and cancelling an order that is
        already fully filled (a fully filled order is ``Executed`` and terminal — see
        ``ALLOWED_TRANSITIONS``).

        ``filled_delta`` is the ordered-quantity units this transition itself confirms as filled
        (0 for every state that carries no fill). This method never touches a position — an order
        changing state, including to ``EXECUTED``, changes nothing about the strategy's position
        by itself (AC-2/AC-3); only :meth:`OrderBook.apply_fill` can move a position, from a
        separate, explicit, checked fill event.
        """
        if not isinstance(new_state, OrderState):
            raise ValueError(f"new_state must be an OrderState, got {new_state!r}")
        allowed = ALLOWED_TRANSITIONS.get(self._state, frozenset())
        if new_state not in allowed:
            raise ValueError(f"{self._state.value} -> {new_state.value} is not an allowed order transition")
        filled_delta = _non_negative_int(filled_delta, "filled_delta")
        if filled_delta and new_state in _NON_FILLING_STATES:
            raise ValueError(f"{new_state.value} carries no fill; filled_delta must be 0, got {filled_delta}")
        new_filled = self._filled_quantity + filled_delta
        if new_filled > self.quantity:
            raise ValueError(f"filled quantity {new_filled} would exceed ordered quantity {self.quantity}")
        if new_state is OrderState.EXECUTED and new_filled != self.quantity:
            raise ValueError(
                f"cannot mark Executed with {new_filled} of {self.quantity} filled; use Partially Executed"
            )
        if new_state is OrderState.PARTIALLY_EXECUTED and new_filled == 0:
            raise ValueError("Partially Executed needs at least one filled unit (filled_delta must be > 0)")
        if new_state is OrderState.CANCELLED and self._filled_quantity >= self.quantity:
            raise ValueError("a fully filled order cannot be Cancelled; it is Executed and terminal")
        return self._copy_with(state=new_state, filled_quantity=new_filled)


@dataclass(frozen=True)
class FillEvent:
    """One broker-confirmed fill message, as received. On its own it changes nothing — only
    :meth:`OrderBook.apply_fill` may turn it into a state/position change, and only after
    checking it against the exact order it claims to fill.
    """

    event_id: str
    broker_order_id: str
    contract: str
    side: Action
    quantity: int
    price: Decimal
    timestamp: datetime.datetime

    def __post_init__(self) -> None:
        _non_empty_str(self.event_id, "event_id")
        _non_empty_str(self.broker_order_id, "broker_order_id")
        _non_empty_str(self.contract, "contract")
        if not isinstance(self.side, Action):
            raise ValueError(f"side must be an Action, got {self.side!r}")
        _positive_int(self.quantity, "quantity")
        require_price(self.price, "price", allow_zero=False)
        if not isinstance(self.timestamp, datetime.datetime) or self.timestamp.tzinfo is None:
            raise ValueError(f"timestamp must be a timezone-aware datetime.datetime, got {self.timestamp!r}")


class PositionLedger:
    """Confirmed net units per (strategy_id, contract). Internal bookkeeping for
    :class:`OrderBook` only — nothing outside this module calls :meth:`_record`; the checked,
    public entry point for a fill is always :meth:`OrderBook.apply_fill`.
    """

    def __init__(self) -> None:
        self._positions: dict[tuple[str, str], int] = {}
        self._seen_event_ids: set[str] = set()
        self._fills: list[FillEvent] = []

    def has_seen(self, event_id: str) -> bool:
        return event_id in self._seen_event_ids

    def _record(self, strategy_id: str, fill: FillEvent) -> None:
        """Move the position by one confirmed fill. Idempotent: a repeated ``event_id`` is a
        documented no-op, so the same fill applied twice moves the position once.
        """
        if fill.event_id in self._seen_event_ids:
            return
        key = (strategy_id, fill.contract)
        delta = fill.quantity if fill.side is Action.BUY else -fill.quantity
        self._positions[key] = self._positions.get(key, 0) + delta
        self._seen_event_ids.add(fill.event_id)
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


class OrderBook:
    """Owns a set of registered orders and their :class:`PositionLedger` together (W-019 fix
    round). A fill is applied ONLY through the order it claims to fill: ``broker_order_id``,
    contract and side must match a REGISTERED order, the order must be open (Submitted / Pending
    / Partially Executed), the cumulative filled quantity must never exceed the ordered quantity,
    and a replayed ``event_id`` is a no-op, never a second move. The order's own state (partial
    fill, or auto-selected ``Executed`` once fully filled) and the ledger's position update
    together in :meth:`apply_fill`; nothing here can update one without the other.
    """

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._ledger = PositionLedger()

    def add(self, order: Order) -> None:
        """Register an order so it can later receive fills. Requires a ``broker_order_id`` —
        without one, no fill could ever be matched to it.
        """
        if not isinstance(order, Order):
            raise ValueError(f"add needs an Order, got {order!r}")
        if order.broker_order_id is None:
            raise ValueError("an order needs a broker_order_id before it can be added to the book")
        if order.broker_order_id in self._orders:
            raise ValueError(f"broker_order_id {order.broker_order_id!r} is already registered")
        self._orders[order.broker_order_id] = order

    def order_for(self, broker_order_id: str) -> Order:
        try:
            return self._orders[broker_order_id]
        except KeyError:
            raise ValueError(f"unknown broker order id {broker_order_id!r}") from None

    def transition(self, broker_order_id: str, new_state: OrderState) -> Order:
        """A non-fill transition (Submitted, Pending, Rejected, a manual Cancel)."""
        order = self.order_for(broker_order_id)
        updated = order.transition(new_state)
        self._orders[broker_order_id] = updated
        return updated

    def apply_fill(self, fill: FillEvent) -> Order:
        """The one checked entry point for a broker-confirmed fill (AC-2, AC-3, W-019 fix round).

        Refuses: an unknown ``broker_order_id`` (b); a contract or side that does not match the
        registered order (c); an order that is not open; a cumulative fill above the ordered
        quantity (d). A replayed ``event_id`` (a) is a documented no-op: the order and the ledger
        are both returned/left exactly as they were. A fill that completes the order always moves
        it to ``Executed`` (e) — the caller never chooses the resulting state.
        """
        if not isinstance(fill, FillEvent):
            raise ValueError(f"apply_fill needs a FillEvent, got {fill!r}")
        order = self.order_for(fill.broker_order_id)  # unknown order id -> ValueError
        if self._ledger.has_seen(fill.event_id):
            return order  # idempotent replay: no second move of the order or the position
        if fill.contract != order.contract:
            raise ValueError(
                f"fill is for contract {fill.contract!r}, order {order.broker_order_id} is for {order.contract!r}"
            )
        if fill.side is not order.side:
            raise ValueError(f"fill side {fill.side} does not match order side {order.side}")
        if order.state not in _OPEN_STATES:
            raise ValueError(f"order {order.broker_order_id} is {order.state.value}; it cannot accept a fill")
        new_filled = order.filled_quantity + fill.quantity
        if new_filled > order.quantity:
            raise ValueError(
                f"fill would take filled quantity to {new_filled}, above ordered quantity {order.quantity}"
            )
        new_state = OrderState.EXECUTED if new_filled == order.quantity else OrderState.PARTIALLY_EXECUTED
        updated = order.transition(new_state, filled_delta=fill.quantity)
        self._ledger._record(order.strategy_id, fill)
        self._orders[fill.broker_order_id] = updated
        return updated

    def position(self, strategy_id: str, contract: str) -> int:
        return self._ledger.position(strategy_id, contract)

    def positions_for(self, strategy_id: str) -> Mapping[str, int]:
        return self._ledger.positions_for(strategy_id)

    @property
    def fills(self) -> tuple[FillEvent, ...]:
        return self._ledger.fills


def derive_strategy_position(book: OrderBook, strategy_id: str) -> Mapping[str, int]:
    """The one legitimate way to get a strategy's position (AC-3): read the book's ledger of
    confirmed fills. There is no other function in this module that returns a position.
    """
    if not isinstance(book, OrderBook):
        raise ValueError(f"derive_strategy_position needs an OrderBook, got {book!r}")
    _non_empty_str(strategy_id, "strategy_id")
    return book.positions_for(strategy_id)


def refuse_position_from_orders(orders: Iterable[Order]) -> NoReturn:
    """Guard against AC-3's forbidden shortcut: deriving a strategy's position or state from order
    rows alone (an Executed order row is not a fill; reconciliation/the broker-confirmed
    :class:`OrderBook` ledger is the only source, Q194). Always raises; there is no code path here
    that reads ``Order.state`` and returns a position, so this cannot silently start working.
    """
    list(orders)  # touch the iterable so a caller cannot claim it was ignored unread
    raise ValueError(
        "a strategy's position/state must never be derived from order rows alone; "
        "use derive_strategy_position(book, strategy_id) against confirmed fills"
    )
