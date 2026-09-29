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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
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
#: Read-only (issue #29 item 3): a MappingProxyType over frozensets, so no caller can widen a row at runtime.
ALLOWED_TRANSITIONS: Final[Mapping[OrderState, frozenset[OrderState]]] = MappingProxyType({
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
})

#: Effective states in which a fill may still legally arrive.
_OPEN_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.SUBMITTED, OrderState.PENDING, OrderState.PARTIALLY_EXECUTED}
)
#: States a fill-implying transition can never target directly (AC-1/round-3 item 2).
_FILL_IMPLIED_STATES: Final[frozenset[OrderState]] = frozenset(
    {OrderState.PARTIALLY_EXECUTED, OrderState.EXECUTED}
)


def _non_empty_str(value: object, field_name: str) -> str:
    """A non-empty identifier with no surrounding whitespace (issue #29 item 2): ``"T1 "`` is refused, never
    normalised, so a padded copy of an id can never become a second ledger key."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    if value != value.strip():
        raise ValueError(f"{field_name} must not have surrounding whitespace, got {value!r}")
    return value


@dataclass(frozen=True)
class ReconciliationEvent:
    """One audited change to a strategy's reconciliation block (ADR-018; issue #29 item 1).

    ``kind`` is ``"blocked"`` (a reconcile found the broker's cumulative filled quantity differs from the ledger) or
    ``"cleared"`` (an explicit call, after a fresh reconcile of every order of the strategy agreed).
    """

    strategy_id: str
    kind: Literal["blocked", "cleared"]
    broker_order_id: str | None
    broker_filled: int | None
    local_filled: int | None
    actor: str | None
    reason: str | None
    at: datetime.datetime | None


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer, got {value!r}")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer, got {value!r}")
    return value


def _aware(value: object, field_name: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime, got {value!r}")
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
    version_id: str | None = None  # the strategy version this order executes (W-023 fix (a))
    client_tag: str | None = None  # the platform's own id, set before the broker sees the order
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
        if self.version_id is not None:
            _non_empty_str(self.version_id, "version_id")
        if self.client_tag is not None:
            _non_empty_str(self.client_tag, "client_tag")

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
    def key(self) -> str:
        """The book's key: the platform client tag when the platform sent it, else the broker id."""
        return self.order.client_tag or self.order.broker_order_id  # type: ignore[return-value]

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


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


#: Orchestrator defaults (W-023 round 3): how far ahead of the platform clock a broker read may be stamped, and how
#: old a read may be, before it is refused. A refused read sets no block time and clears no block.
MAX_READ_FUTURE_SKEW: Final = datetime.timedelta(seconds=5)
MAX_READ_AGE: Final = datetime.timedelta(seconds=60)


class OrderBook:
    """Owns registered orders and the :class:`FillLedger` together. A fill is applied ONLY
    through :meth:`apply_fill`, which is the single writer of fill facts; ``filled_quantity`` and
    the effective state are always computed from the ledger, never cached on the order.

    W-023 round 3: orders are keyed by the platform's client tag when the platform sent them (registered BEFORE the
    broker sees them; the broker id is attached when the broker accepts), else by the broker id. The ledger stays
    keyed by ``(broker_order_id, trade_id)``. The broker's order-status read is mirrored onto the book's own orders
    by :meth:`mirror_broker_state`, so a rejected order never stays Submitted.
    """

    def __init__(
        self, *, clock: Callable[[], datetime.datetime] = _utc_now,
        max_read_age: datetime.timedelta = MAX_READ_AGE, max_future_skew: datetime.timedelta = MAX_READ_FUTURE_SKEW,
    ) -> None:
        self._clock = clock
        self._max_read_age = max_read_age
        self._max_future_skew = max_future_skew
        self._orders: dict[str, Order] = {}
        self._by_broker: dict[str, str] = {}
        self._registered_at: dict[str, datetime.datetime] = {}
        self._tag_counter = 0
        self._ledger = FillLedger()
        self._blocked_strategies: set[str] = set()
        self._reconciliation_events: list[ReconciliationEvent] = []
        self._blocked_at: dict[str, datetime.datetime] = {}  # latest accepted read/time that set each block
        self._live_preparation: dict[str, object] = {}  # strategy -> the one unconsumed preparation (its owner)
        self._closing_read_at: dict[str, datetime.datetime] = {}  # strategy -> read on which Close was chosen

    # -- clock & read freshness -----------------------------------------------------------

    def now(self) -> datetime.datetime:
        return _aware(self._clock(), "clock")

    def check_read(self, read_at: object) -> datetime.datetime:
        """Refuse a broker read stamped in the future (beyond the skew) or older than the age limit."""
        _aware(read_at, "read_at")
        now = self.now()
        if read_at > now + self._max_future_skew:
            raise ValueError(f"broker read stamped in the future ({read_at.isoformat()}, now {now.isoformat()})")
        if read_at < now - self._max_read_age:
            raise ValueError(f"stale broker read ({read_at.isoformat()}, now {now.isoformat()})")
        return read_at

    # -- registration & views -------------------------------------------------------------

    def next_client_tag(self) -> str:
        """Orchestrator default: platform client tags ``OFO`` + 9 digits (Kite allows short alphanumeric tags)."""
        self._tag_counter += 1
        return f"OFO{self._tag_counter:09d}"

    def add(self, order: Order) -> None:
        """Register an order. Refuses anything that is not freshly ``Prepared`` (round-3 item 3). The order needs a
        client tag (platform-sent, registered before sending) or a broker id."""
        if not isinstance(order, Order):
            raise ValueError(f"add needs an Order, got {order!r}")
        if order.state is not OrderState.PREPARED:
            raise ValueError(f"add() only accepts a Prepared order, got {order.state.value}")
        if order.client_tag is None and order.broker_order_id is None:
            raise ValueError("an order needs a client_tag or a broker_order_id before it can be added to the book")
        key = order.client_tag or order.broker_order_id
        if key in self._orders:
            raise ValueError(f"order {key!r} is already registered")
        if order.broker_order_id is not None and order.broker_order_id in self._by_broker:
            raise ValueError(f"broker_order_id {order.broker_order_id!r} is already registered")
        self._orders[key] = order
        if order.broker_order_id is not None:
            self._by_broker[order.broker_order_id] = key
        self._registered_at[key] = self.now()

    def attach_broker_id(self, client_tag: str, broker_order_id: object) -> OrderView:
        """The broker accepted the order sent under ``client_tag``: record its id. Refuses an empty, padded or
        already-used id, or a tag that already has a different id."""
        order = self._by_key(client_tag)
        boid = _non_empty_str(broker_order_id, "broker_order_id")
        if order.broker_order_id == boid:
            return self._view(order)
        if order.broker_order_id is not None:
            raise ValueError(f"order {client_tag!r} already has broker id {order.broker_order_id!r}")
        if boid in self._by_broker:
            raise ValueError(f"broker_order_id {boid!r} is already registered to another order")
        updated = order._copy_with(state=order.state)
        object.__setattr__(updated, "broker_order_id", boid)
        self._orders[client_tag] = updated
        self._by_broker[boid] = client_tag
        return self._view(updated)

    def _by_key(self, key: str) -> Order:
        try:
            return self._orders[key]
        except KeyError:
            raise ValueError(f"unknown order {key!r}") from None

    def _key_for_broker(self, broker_order_id: str) -> str:
        try:
            return self._by_broker[broker_order_id]
        except KeyError:
            raise ValueError(f"unknown broker order id {broker_order_id!r}") from None

    def _view(self, order: Order) -> OrderView:
        filled = self._ledger.filled_for(order.broker_order_id) if order.broker_order_id else 0
        return OrderView(order, filled, _effective_state(order, filled))

    def order_for(self, broker_order_id: str) -> OrderView:
        return self._view(self._orders[self._key_for_broker(broker_order_id)])

    def order_for_key(self, key: str) -> OrderView:
        return self._view(self._by_key(key))

    def find(self, broker_order_id: str | None, client_tag: str | None) -> OrderView | None:
        """The book's order a broker status line refers to: by broker id, else by the platform's client tag."""
        if broker_order_id is not None and broker_order_id in self._by_broker:
            return self._view(self._orders[self._by_broker[broker_order_id]])
        if client_tag is not None and client_tag in self._orders:
            return self._view(self._orders[client_tag])
        return None

    def registered_at(self, key: str) -> datetime.datetime:
        return self._registered_at[key]

    # -- non-fill transitions ---------------------------------------------------------------

    def transition(self, broker_order_id: str, new_state: OrderState) -> OrderView:
        """A non-fill transition, by broker id. See :meth:`transition_key`."""
        return self.transition_key(self._key_for_broker(broker_order_id), new_state)

    def transition_key(self, key: str, new_state: OrderState, *, from_broker: bool = False) -> OrderView:
        """A non-fill transition (Submitted, Pending, Rejected, a manual Cancel). Checked against
        the ledger-computed EFFECTIVE state (so a fully filled order can never be Cancelled, even
        though its own base state might still read Submitted) -- not the order's raw base state.
        A platform SEND (``Submitted``, not ``from_broker``) is refused while the strategy is blocked.
        """
        if new_state in _FILL_IMPLIED_STATES:
            raise ValueError(f"{new_state.value} is reached only via a confirmed fill, not transition()")
        view = self._view(self._by_key(key))
        allowed = ALLOWED_TRANSITIONS.get(view.state, frozenset())
        if new_state not in allowed:
            raise ValueError(f"{view.state.value} -> {new_state.value} is not an allowed order transition")
        if new_state is OrderState.SUBMITTED and not from_broker and view.strategy_id in self._blocked_strategies:
            raise ValueError(
                f"strategy {view.strategy_id!r} has an unresolved reconciliation mismatch "
                "(ADR-018); submission is blocked until it is resolved"
            )
        updated = view.order._copy_with(state=new_state)  # permission already checked above
        self._orders[key] = updated
        return self._view(updated)

    def mirror_broker_state(self, key: str, broker_state: OrderState) -> OrderView:
        """Bring one book order in line with the broker's status for it (W-023 round 3, step 0).

        Prepared -> Submitted first when the broker has it at all; then Pending / Rejected / Cancelled as reported.
        Executed / Partially Executed come only from the ledger (fills), never from this call. A broker state the
        book cannot reach from its own (e.g. Rejected after a fill, or anything after a terminal state) raises.
        """
        view = self._view(self._by_key(key))
        if view.state is broker_state:
            return view
        if view.state in TERMINAL_STATES:
            raise ValueError(f"book has {key!r} {view.state.value}; the broker reports {broker_state.value}")
        if view.state is OrderState.PREPARED and broker_state is not OrderState.PREPARED:
            view = self.transition_key(key, OrderState.SUBMITTED, from_broker=True)
        if broker_state in (OrderState.PENDING, OrderState.REJECTED, OrderState.CANCELLED) \
                and view.state is not broker_state:
            view = self.transition_key(key, broker_state, from_broker=True)
        return view

    # -- fills: the one entry point -----------------------------------------------------------

    def apply_fill(self, fill: FillEvent) -> OrderView:
        """The one checked entry point for a broker-confirmed fill (AC-2, AC-3, round-3 item 1).

        The (broker_order_id, trade_id) KEY is resolved first, against the ledger alone -- an identical replay is an
        idempotent no-op regardless of the order's state; a same-key-but-different fill is a
        :class:`FillConflictError`. Only for a genuinely NEW key does order-level validation run -- known order,
        contract and side match, the order open, cumulative filled quantity within the ordered quantity.
        """
        if not isinstance(fill, FillEvent):
            raise ValueError(f"apply_fill needs a FillEvent, got {fill!r}")

        existing = self._ledger.get(fill.broker_order_id, fill.trade_id)
        if existing is not None:
            order = self._orders[self._by_broker[fill.broker_order_id]]
            if existing == fill:
                return self._view(order)  # exact replay: documented no-op, nothing moves twice
            raise FillConflictError(
                f"trade_id {fill.trade_id!r} for order {fill.broker_order_id} was already recorded "
                f"with a different fill ({existing}); refusing the conflicting copy ({fill})"
            )

        key = self._by_broker.get(fill.broker_order_id)
        if key is None:
            raise ValueError(f"unknown broker order id {fill.broker_order_id!r}")
        order = self._orders[key]
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

    def _orders_by_broker(self) -> dict[str, Order]:
        return {boid: self._orders[key] for boid, key in self._by_broker.items()}

    def position(self, strategy_id: str, contract: str) -> int:
        return self._ledger.position(strategy_id, contract, self._orders_by_broker())

    def positions_for(self, strategy_id: str) -> Mapping[str, int]:
        contracts = {o.contract for o in self._orders.values() if o.strategy_id == strategy_id}
        result = {c: self.position(strategy_id, c) for c in contracts}
        return {c: q for c, q in result.items() if q != 0}

    def raw_fills(self) -> tuple[FillEvent, ...]:
        """Every fill row ever appended -- for property tests and reconciliation reads only."""
        return self._ledger.rows()

    def views_for(self, strategy_id: str) -> tuple[OrderView, ...]:
        """Every registered order of one strategy, with ledger-computed state and filled quantity."""
        return tuple(self._view(o) for o in self._orders.values() if o.strategy_id == strategy_id)

    # -- reconciliation (ADR-016/ADR-018) -----------------------------------------------------

    def _block(self, strategy_id: str, at: datetime.datetime, event: ReconciliationEvent) -> None:
        self._blocked_strategies.add(strategy_id)
        previous = self._blocked_at.get(strategy_id)
        self._blocked_at[strategy_id] = at if previous is None else max(previous, at)
        self._reconciliation_events.append(event)

    def reconcile_cumulative(
        self, broker_order_id: str, broker_filled_qty: int, *, read_at: datetime.datetime,
    ) -> Literal["ok", "missing_trades"]:
        """Compare the broker's reconciled cumulative filled quantity for an order against what
        is recorded locally (ADR-018: an unresolved mismatch blocks execution).

        - Equal: ``"ok"``.
        - Broker HIGHER: trades are missing locally -- blocks the strategy, returns ``"missing_trades"``.
        - Broker LOWER: irreconcilable -- blocks the strategy exactly as HIGHER does (issue #29 item 1,
          core invariant 6), THEN raises :class:`FillConflictError`.

        ``read_at`` must pass :meth:`check_read` (not future-stamped, not stale); a refused read sets nothing.
        Either block stays until :meth:`clear_reconciliation_block` succeeds with a LATER read.
        """
        self.check_read(read_at)
        view = self.order_for(broker_order_id)
        _non_negative_int(broker_filled_qty, "broker_filled_qty")
        if broker_filled_qty == view.filled_quantity:
            return "ok"
        self._block(view.strategy_id, read_at, ReconciliationEvent(
            view.strategy_id, "blocked", broker_order_id, broker_filled_qty, view.filled_quantity, None, None,
            read_at))
        if broker_filled_qty > view.filled_quantity:
            return "missing_trades"
        raise FillConflictError(
            f"broker reports {broker_filled_qty} filled for order {broker_order_id}, but "
            f"{view.filled_quantity} trades are already recorded locally for it -- irreconcilable"
        )

    def block_strategy(self, strategy_id: str, reason: str) -> None:
        """Block a strategy for a mismatch found outside a fill count (e.g. an unusable broker id after
        acceptance, a broker order unknown to the book). Stamped with the platform clock."""
        _non_empty_str(strategy_id, "strategy_id")
        _non_empty_str(reason, "reason")
        now = self.now()
        self._block(strategy_id, now, ReconciliationEvent(strategy_id, "blocked", None, None, None, None, reason, now))

    def is_submit_blocked(self, strategy_id: str) -> bool:
        return strategy_id in self._blocked_strategies

    def clear_reconciliation_block(
        self, strategy_id: str, broker_filled: Mapping[str, int], *, read_at: datetime.datetime, actor: str,
        reason: str, at: datetime.datetime,
    ) -> ReconciliationEvent:
        """The one way to lift a reconciliation block (issue #29 item 1; ADR-018 "until it is resolved").

        ``broker_filled`` is a FRESH broker read: the cumulative filled quantity of EVERY order of this strategy that
        has a broker id, keyed by broker order id. Refused (block kept) when the strategy is not blocked, when the
        read is future-stamped or stale (:meth:`check_read`), when it is not strictly LATER than the read that set
        the block, when any order is missing from the read, when the read names an order that is not this
        strategy's, or when any count differs from the ledger. Only then is the block lifted, with an audit event.
        """
        _non_empty_str(strategy_id, "strategy_id")
        _non_empty_str(actor, "actor")
        _non_empty_str(reason, "reason")
        _aware(at, "at")
        self.check_read(read_at)
        if strategy_id not in self._blocked_strategies:
            raise ValueError(f"strategy {strategy_id!r} is not blocked; there is nothing to clear")
        blocked_at = self._blocked_at[strategy_id]
        if read_at <= blocked_at:
            raise ValueError(f"stale broker read ({read_at.isoformat()}); the block was set at "
                             f"{blocked_at.isoformat()} and only a later read can clear it")
        if not isinstance(broker_filled, Mapping):
            raise ValueError("broker_filled must be a mapping of broker order id to filled quantity")
        mine = {o.broker_order_id for o in self._orders.values()
                if o.strategy_id == strategy_id and o.broker_order_id is not None}
        unknown = sorted(set(broker_filled) - mine)
        if unknown:
            raise ValueError(f"broker read names orders that are not this strategy's: {unknown}")
        missing = sorted(mine - set(broker_filled))
        if missing:
            raise ValueError(f"a fresh broker read must cover every order of the strategy; missing {missing}")
        disagreeing = []
        for boid in sorted(mine):
            if self.reconcile_cumulative(boid, broker_filled[boid], read_at=read_at) != "ok":  # lower raises here
                disagreeing.append(boid)
        if disagreeing:
            raise FillConflictError(f"broker read still disagrees with the ledger for {disagreeing}; block kept")
        self._blocked_strategies.discard(strategy_id)
        del self._blocked_at[strategy_id]
        event = ReconciliationEvent(strategy_id, "cleared", None, None, None, actor, reason, at)
        self._reconciliation_events.append(event)
        return event

    # -- per-strategy execution locks (W-023) ---------------------------------------------

    def hold_preparation(self, strategy_id: str, owner: object) -> None:
        """Record ``owner`` as the strategy's one live (unconsumed) preparation; refuse if another holds it."""
        current = self._live_preparation.get(strategy_id)
        if current is not None and current is not owner:
            raise ValueError(f"strategy {strategy_id!r} already has a preparation waiting for confirmation")
        self._live_preparation[strategy_id] = owner

    def release_preparation(self, strategy_id: str, owner: object) -> None:
        """Only the holder releases its own hold (shared state records its owner)."""
        if self._live_preparation.get(strategy_id) is owner:
            del self._live_preparation[strategy_id]

    def has_live_preparation(self, strategy_id: str) -> bool:
        return strategy_id in self._live_preparation

    def mark_closing(self, strategy_id: str, read_at: datetime.datetime) -> None:
        """Close Partial Strategy was chosen on the (accepted) broker read taken at ``read_at``."""
        self.check_read(read_at)
        self._closing_read_at[strategy_id] = read_at

    def closing_read_at(self, strategy_id: str) -> datetime.datetime | None:
        return self._closing_read_at.get(strategy_id)

    def clear_closing(self, strategy_id: str, read_at: datetime.datetime) -> None:
        """Forget the Close choice once a read strictly later than the one it was made on has been assessed."""
        marked = self._closing_read_at.get(strategy_id)
        if marked is not None and read_at > marked:
            del self._closing_read_at[strategy_id]

    def reconciliation_events(self, strategy_id: str) -> tuple[ReconciliationEvent, ...]:
        """Every block/clear event for one strategy, oldest first (append-only audit trail)."""
        return tuple(e for e in self._reconciliation_events if e.strategy_id == strategy_id)


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
