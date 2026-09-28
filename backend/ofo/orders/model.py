"""Order lifecycle state machine and the append-only fill ledger (REQ-057, ADR-016, ADR-018).

Spec: REQ-057 AC-1 (the seven states and their transitions, as data), AC-2 (a submitted order
never changes strategy state or positions until the broker confirms execution -- Q195), AC-3
(strategy state/position is never derived only from order rows -- Q194). ADR-016/ADR-018:
submission is not execution; an unresolved reconciliation mismatch blocks execution.

W-019 round 3 (independent review; `knowledge/findings/fill-not-exactly-once.json`): rounds 1-2
guarded the *doors* into two separate stores (the order's own ``_filled_quantity`` and the
ledger's ``_positions``) that had nothing tying them together, so a bug in either write path
silently diverged them (a reused trade id for a second order dropped that order's fill; a replay
with a different quantity was accepted; ``Order.transition(filled_delta=...)`` plus
``OrderBook.add`` could mark an order Executed with 10 filled while the ledger held 0).

The fix removes the duplication instead of re-guarding it:

- :class:`FillLedger` is the ONLY store of fill facts: append-only, keyed by
  ``(broker_order_id, trade_id)``, one full copy of each :class:`FillEvent` per key.
- :class:`Order` stores no filled quantity and no fill-implied state. Its own ``_state`` only
  ever holds Prepared / Submitted / Pending / Rejected / Cancelled -- states reached by explicit,
  non-fill business action. ``transition()`` refuses ``Partially Executed`` and ``Executed``
  outright: those are never something anyone "sets".
- :class:`OrderBook` is the only place a :class:`FillEvent` is accepted (:meth:`apply_fill`), and
  the only place ``filled_quantity`` and the effective state (Partially Executed / Executed) are
  computed -- always freshly, from the ledger, never cached. :meth:`OrderBook.position` is
  likewise always computed from the ledger, never stored.

NOTE (unverified): the shape of Kite's real fields -- ``order_id``, ``trade_id``, and the
cumulative ``filled_quantity`` carried in a postback -- is taken from the ADR/spec text, not from
a real Kite Connect response. Verify against an actual response as part of W-017's core proof
before this module is wired to a live feed.
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Final, Literal, NoReturn

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
#: resubmission transition (ADR-017: no automatic retry, and no manual "resubmit" either).
TERMINAL_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.EXECUTED, OrderState.REJECTED, OrderState.CANCELLED}
)

#: The whole lifecycle as data (AC-1): allowed next EFFECTIVE state for every EFFECTIVE state.
#: ``OrderBook`` evaluates this against the computed (ledger-derived) state, never the order's raw
#: base state alone -- that is what makes "cancel a fully filled order" impossible even though the
#: order's own base state (Submitted) would otherwise still show an open Cancel transition.
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

#: Effective states in which a fill may still legally arrive.
_OPEN_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.SUBMITTED, OrderState.PENDING, OrderState.PARTIALLY_EXECUTED}
)
#: States a fill-implying transition can never target directly (AC-1/round-3 item 2).
_FILL_IMPLIED_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.PARTIALLY_EXECUTED, OrderState.EXECUTED}
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


class FillConflictError(ValueError):
    """Raised when a (broker_order_id, trade_id) key is reused with a different fill, or the
    broker's reconciled cumulative quantity is LOWER than what is already recorded locally --
    both are irreconcilable, and neither moves anything.
    """


@dataclass(frozen=True)
class Order:
    """One order, always belonging to a strategy (CLAUDE.md: no standalone order entry).

    Frozen: every field, public or private, refuses a direct assignment. Stores NO filled
    quantity (round-3 item 2) -- ``OrderBook`` computes that from the ledger. Its own ``_state``
    only ever holds a non-fill-implied value (Prepared / Submitted / Pending / Rejected /
    Cancelled); :meth:`transition` refuses Partially Executed / Executed outright.
    """

    strategy_id: str
    leg_ref: str
    contract: str
    side: Action
    quantity: int
    price: Decimal
    broker_order_id: str | None = None
    _state: OrderState = field(default=OrderState.PREPARED, init=False, repr=False)

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

    def _copy_with(self, *, state: OrderState) -> Order:
        """Build a new ``Order`` sharing every other field. Bypasses ``__init__`` on purpose --
        used only by :meth:`transition` and, internally, by :class:`OrderBook`, which has already
        checked permission against the ledger-computed EFFECTIVE state before calling this.
        """
        clone = object.__new__(Order)
        for f in dataclasses.fields(self):
            object.__setattr__(clone, f.name, getattr(self, f.name))
        object.__setattr__(clone, "_state", state)
        return clone

    def transition(self, new_state: OrderState) -> Order:
        """Return a NEW ``Order`` in ``new_state``. Refuses any state that implies a fill
        (``Partially Executed``, ``Executed`` -- those are only ever reached via a confirmed fill
        through :meth:`OrderBook.apply_fill`) and anything the transition table forbids for this
        order's own base state. ``OrderBook`` is what actually decides whether a move is legal
        once fills are in play -- it checks the EFFECTIVE (ledger-computed) state, not this
        method's table lookup, which only ever sees the order's own, fill-blind, base state.
        """
        if not isinstance(new_state, OrderState):
            raise ValueError(f"new_state must be an OrderState, got {new_state!r}")
        if new_state in _FILL_IMPLIED_STATES:
            raise ValueError(
                f"{new_state.value} is reached only via a confirmed fill (OrderBook.apply_fill), "
                "never by transition()"
            )
        allowed = ALLOWED_TRANSITIONS.get(self._state, frozenset())
        if new_state not in allowed:
            raise ValueError(f"{self._state.value} -> {new_state.value} is not an allowed order transition")
        return self._copy_with(state=new_state)


@dataclass(frozen=True)
class FillEvent:
    """One broker-confirmed fill message, as received. On its own it changes nothing -- only
    :meth:`OrderBook.apply_fill` may turn it into a state/position change, and only after checking
    it against the exact order it claims to fill and the ledger key it would occupy.

    NOTE (unverified): field names/shape follow the ADR/spec description of a Kite postback, not
    a real Kite Connect response -- verify at W-017's core proof.
    """

    trade_id: str
    broker_order_id: str
    contract: str
    side: Action
    quantity: int
    price: Decimal
    timestamp: datetime.datetime

    def __post_init__(self) -> None:
        _non_empty_str(self.trade_id, "trade_id")
        _non_empty_str(self.broker_order_id, "broker_order_id")
        _non_empty_str(self.contract, "contract")
        if not isinstance(self.side, Action):
            raise ValueError(f"side must be an Action, got {self.side!r}")
        _positive_int(self.quantity, "quantity")
        require_price(self.price, "price", allow_zero=False)
        if not isinstance(self.timestamp, datetime.datetime) or self.timestamp.tzinfo is None:
            raise ValueError(f"timestamp must be a timezone-aware datetime.datetime, got {self.timestamp!r}")


class FillLedger:
    """Append-only store of confirmed fills, keyed by ``(broker_order_id, trade_id)`` -- the
    composite key is what stops a trade id that Kite only guarantees unique PER ORDER from
    colliding across two different orders (the round-2 defect). One full copy of the
    :class:`FillEvent` is kept per key so a replay can be compared for exact equality.

    Internal to :class:`OrderBook`: nothing outside this module appends here directly.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], FillEvent] = {}

    def get(self, broker_order_id: str, trade_id: str) -> FillEvent | None:
        return self._rows.get((broker_order_id, trade_id))

    def append(self, fill: FillEvent) -> None:
        self._rows[(fill.broker_order_id, fill.trade_id)] = fill

    def filled_for(self, broker_order_id: str) -> int:
        """Sum of every confirmed fill's quantity for one order -- the ONLY definition of an
        order's filled quantity (round-3 item 2: never stored, always this sum)."""
        return sum(f.quantity for (boid, _), f in self._rows.items() if boid == broker_order_id)

    def position(self, strategy_id: str, contract: str, orders_by_broker_id: Mapping[str, Order]) -> int:
        """Net confirmed units for one (strategy, contract) -- the signed sum of every ledger row
        whose order belongs to that strategy and contract. Computed fresh every call; nothing is
        cached (Core: one fill ledger is the only source of truth)."""
        total = 0
        for (broker_order_id, _), f in self._rows.items():
            order = orders_by_broker_id.get(broker_order_id)
            if order is None or order.strategy_id != strategy_id or f.contract != contract:
                continue
            total += f.quantity if f.side is Action.BUY else -f.quantity
        return total

    def rows(self) -> tuple[FillEvent, ...]:
        """Every recorded fill, for property tests and reconciliation reads."""
        return tuple(self._rows.values())


@dataclass(frozen=True)
class OrderView:
    """A read-only snapshot of one order: its immutable fields plus ``filled_quantity`` and
    ``state``, both recomputed from the ledger on every read, never stored (round-3 core)."""

    order: Order
    filled_quantity: int
    state: OrderState

    @property
    def strategy_id(self) -> str:
        return self.order.strategy_id

    @property
    def contract(self) -> str:
        return self.order.contract

    @property
    def side(self) -> Action:
        return self.order.side

    @property
    def quantity(self) -> int:
        return self.order.quantity

    @property
    def broker_order_id(self) -> str | None:
        return self.order.broker_order_id


def _effective_state(order: Order, filled: int) -> OrderState:
    if order.state in (OrderState.REJECTED, OrderState.CANCELLED):
        return order.state  # an explicit terminal call wins, whatever was filled before it
    if filled > 0 and filled >= order.quantity:
        return OrderState.EXECUTED
    if filled > 0:
        return OrderState.PARTIALLY_EXECUTED
    return order.state


class OrderBook:
    """Owns registered orders and the :class:`FillLedger` together. A fill is applied ONLY
    through :meth:`apply_fill`, which is the single writer of fill facts; ``filled_quantity`` and
    the effective state are always computed from the ledger, never cached on the order.
    """

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._ledger = FillLedger()
        self._blocked_strategies: set[str] = set()

    # -- registration & views -------------------------------------------------------------

    def add(self, order: Order) -> None:
        """Register an order. Refuses anything that is not freshly ``Prepared`` (round-3 item 3)
        -- an order already Submitted/etc. must have reached that state through this same book.
        """
        if not isinstance(order, Order):
            raise ValueError(f"add needs an Order, got {order!r}")
        if order.state is not OrderState.PREPARED:
            raise ValueError(f"add() only accepts a Prepared order, got {order.state.value}")
        if order.broker_order_id is None:
            raise ValueError("an order needs a broker_order_id before it can be added to the book")
        if order.broker_order_id in self._orders:
            raise ValueError(f"broker_order_id {order.broker_order_id!r} is already registered")
        self._orders[order.broker_order_id] = order

    def _view(self, order: Order) -> OrderView:
        filled = self._ledger.filled_for(order.broker_order_id) if order.broker_order_id else 0
        return OrderView(order, filled, _effective_state(order, filled))

    def order_for(self, broker_order_id: str) -> OrderView:
        try:
            order = self._orders[broker_order_id]
        except KeyError:
            raise ValueError(f"unknown broker order id {broker_order_id!r}") from None
        return self._view(order)

    # -- non-fill transitions ---------------------------------------------------------------

    def transition(self, broker_order_id: str, new_state: OrderState) -> OrderView:
        """A non-fill transition (Submitted, Pending, Rejected, a manual Cancel). Checked against
        the ledger-computed EFFECTIVE state (so a fully filled order can never be Cancelled, even
        though its own base state might still read Submitted) -- not the order's raw base state.
        """
        if new_state in _FILL_IMPLIED_STATES:
            raise ValueError(f"{new_state.value} is reached only via a confirmed fill, not transition()")
        view = self.order_for(broker_order_id)
        allowed = ALLOWED_TRANSITIONS.get(view.state, frozenset())
        if new_state not in allowed:
            raise ValueError(f"{view.state.value} -> {new_state.value} is not an allowed order transition")
        if new_state is OrderState.SUBMITTED and view.strategy_id in self._blocked_strategies:
            raise ValueError(
                f"strategy {view.strategy_id!r} has an unresolved reconciliation mismatch "
                "(ADR-018); submission is blocked until it is resolved"
            )
        updated = view.order._copy_with(state=new_state)  # permission already checked above
        self._orders[broker_order_id] = updated
        return self._view(updated)

    # -- fills: the one entry point -----------------------------------------------------------

    def apply_fill(self, fill: FillEvent) -> OrderView:
        """The one checked entry point for a broker-confirmed fill (AC-2, AC-3, round-3 item 1).

        The (broker_order_id, trade_id) KEY is resolved first, against the ledger alone -- this is
        what makes an identical replay an idempotent no-op REGARDLESS of the order's current
        state (even once it is Executed), and what makes a same-key-but-different fill a
        :class:`FillConflictError` on every one of its differing fields (quantity, contract, side,
        price), not a generic mismatch: the comparison is always against the exact copy already
        recorded at that key, never against the order.

        Only for a genuinely NEW key does order-level validation run -- known order, contract and
        side match, the order open, cumulative filled quantity within the ordered quantity -- and
        only then is the row appended. A fill that completes the order is reflected as
        ``Executed`` on the very next read, computed, never chosen by the caller.
        """
        if not isinstance(fill, FillEvent):
            raise ValueError(f"apply_fill needs a FillEvent, got {fill!r}")

        existing = self._ledger.get(fill.broker_order_id, fill.trade_id)
        if existing is not None:
            order = self._orders.get(fill.broker_order_id)
            if existing == fill:
                # order is guaranteed non-None here: a row can only exist for a broker_order_id
                # that was a known, registered order at the time it was first appended.
                return self._view(order)  # exact replay: documented no-op, nothing moves twice
            raise FillConflictError(
                f"trade_id {fill.trade_id!r} for order {fill.broker_order_id} was already recorded "
                f"with a different fill ({existing}); refusing the conflicting copy ({fill})"
            )

        order = self._orders.get(fill.broker_order_id)
        if order is None:
            raise ValueError(f"unknown broker order id {fill.broker_order_id!r}")
        if fill.contract != order.contract:
            raise ValueError(
                f"fill is for contract {fill.contract!r}, order {order.broker_order_id} is for {order.contract!r}"
            )
        if fill.side is not order.side:
            raise ValueError(f"fill side {fill.side} does not match order side {order.side}")
        current_filled = self._ledger.filled_for(fill.broker_order_id)
        effective = _effective_state(order, current_filled)
        if effective not in _OPEN_STATES:
            raise ValueError(f"order {order.broker_order_id} is {effective.value}; it cannot accept a fill")
        if current_filled + fill.quantity > order.quantity:
            raise ValueError(
                f"fill would take filled quantity to {current_filled + fill.quantity}, "
                f"above ordered quantity {order.quantity}"
            )
        self._ledger.append(fill)
        return self._view(order)

    # -- reads: always computed --------------------------------------------------------------

    def position(self, strategy_id: str, contract: str) -> int:
        return self._ledger.position(strategy_id, contract, self._orders)

    def positions_for(self, strategy_id: str) -> Mapping[str, int]:
        contracts = {o.contract for o in self._orders.values() if o.strategy_id == strategy_id}
        result = {c: self.position(strategy_id, c) for c in contracts}
        return {c: q for c, q in result.items() if q != 0}

    def raw_fills(self) -> tuple[FillEvent, ...]:
        """Every fill row ever appended -- for property tests and reconciliation reads only."""
        return self._ledger.rows()

    # -- reconciliation (ADR-016/ADR-018) -----------------------------------------------------

    def reconcile_cumulative(self, broker_order_id: str, broker_filled_qty: int) -> Literal["ok", "missing_trades"]:
        """Compare the broker's reconciled cumulative filled quantity for an order against what
        is recorded locally (ADR-018: an unresolved mismatch blocks execution).

        - Equal: ``"ok"``.
        - Broker HIGHER: trades are missing locally -- records a mismatch that blocks the next
          ``Submitted`` transition for this order's strategy, and returns ``"missing_trades"``
          (never silently passes an unequal cumulative).
        - Broker LOWER: irreconcilable -- raises :class:`FillConflictError`.
        """
        view = self.order_for(broker_order_id)
        _non_negative_int(broker_filled_qty, "broker_filled_qty")
        if broker_filled_qty == view.filled_quantity:
            return "ok"
        if broker_filled_qty > view.filled_quantity:
            self._blocked_strategies.add(view.strategy_id)
            return "missing_trades"
        raise FillConflictError(
            f"broker reports {broker_filled_qty} filled for order {broker_order_id}, but "
            f"{view.filled_quantity} trades are already recorded locally for it -- irreconcilable"
        )

    def is_submit_blocked(self, strategy_id: str) -> bool:
        return strategy_id in self._blocked_strategies


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
    rows alone (an Executed order row is not a fill; the broker-confirmed ledger, read through
    :class:`OrderBook`, is the only source, Q194). Always raises.
    """
    list(orders)  # touch the iterable so a caller cannot claim it was ignored unread
    raise ValueError(
        "a strategy's position/state must never be derived from order rows alone; "
        "use derive_strategy_position(book, strategy_id) against confirmed fills"
    )
