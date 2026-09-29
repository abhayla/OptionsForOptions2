"""Partial execution: an explicit exception state, the user's four choices, no automatic retry (REQ-058, ADR-017).

Spec basis (REQ-058; ADR-017 Q27, Q192, Q193; ADR-016/ADR-018; ADR-018 Q198; REQ-059; core invariants 4-7, 21):
- AC-1 some legs fill and others fail -> ``ExecutionStatus.PARTIAL_EXCEPTION``; risk (max profit/loss, breakevens),
  live P&L and margin are recomputed by the engine from the broker's REAL legs (``Assessment``).
- AC-2 choices, in this order: Complete Strategy, Retry Failed Leg, Review Manually, Close Partial Strategy.
- AC-3 filled legs are never unwound automatically: nothing here opens an order against a held position except
  ``close_partial_strategy``, which runs only when the user picks it.
- AC-4 completing re-fetches positions AND order status (``BrokerReader``), recomputes the remaining strategy,
  re-checks margin with a fresh broker figure, verifies the missing leg, and prepares only the missing order(s).
- AC-5 "complete" is decided only from broker positions that the fill ledger agrees with, never from orders sent.
- AC-6 no automatic resubmission: this module never loops, schedules or retries; the failure carries the broker's own
  reason text; ``submit_confirmed`` sends a preparation once, only on the user's explicit, matching choice.

W-023 round 3 (independent review). Class: the platform's view of its own orders not kept in step with the broker.
- Core, step 0: every assessment first SYNCS the book with the fresh broker order-status read
  (``OrderBook.mirror_broker_state`` + the ledger's cumulative check), in both directions: a broker order unknown to
  the book, or a book order missing from the read past the grace window, is a reconciliation mismatch.
- "In flight" means non-terminal in that reconciled book, and nothing else (Prepared counts: it may have reached the
  broker). Failures shown to the user come from the reconciled book plus the broker's reason text.
- Orders are registered in the book BEFORE they are sent, under a platform client tag; the broker id is attached on
  acceptance. An unusable id after acceptance blocks the strategy (reconciliation required), never "failed".
- Broker reads carry ``read_at``; the book refuses future-stamped or stale reads (its injected clock).

Nothing here talks to Zerodha: positions, order status and margin come through ``BrokerReader`` (reconciliation, W-021,
is not merged; its reader will implement this Protocol), orders go out only through ``submit_confirmed`` and the private broker sink (W-026). Every order passes
the W-014 gate ``check_pre_execution``.

Orchestrator defaults (not stated by the spec; each also marked where it is used):
- OD-a "Retry Failed Leg" prepares ONE new order for the same contract, side and still-missing quantity of one failed
  leg; placed only after the user confirms. "Complete Strategy" prepares every missing leg.
- OD-b a missing leg with a non-terminal order in the reconciled book is not yet failed: IN_PROGRESS, nothing prepared.
- OD-c the price on a completing/retry order is the planned leg's price; the user reviews it before confirming.
- OD-d margin re-check: available margin re-read from the broker; required = the planner's figure for the new orders.
- OD-e close orders are priced at the broker's LTP; a missing LTP prepares nothing. Buy-backs of shorts go first.
- OD-f a broker position outside the plan, on the wrong side, or larger than planned is a reconciliation mismatch.
- OD-g size caps: at most 20 planned legs, 100 position lines and 200 order statuses per read.
- OD-h one live preparation per strategy: a second Complete/Retry/Close while one waits is REFUSED;
  ``discard_preparation`` or sending it frees the strategy.
- OD-i a book order missing from the broker's read is "unconfirmed" (non-terminal) for ``UNCONFIRMED_GRACE`` (60 s)
  after it was registered, then a reconciliation mismatch.
- OD-j reads stamped more than 5 s ahead of the platform clock, or older than 60 s, are refused (``OrderBook``).
- OD-k client tags ``OFO`` + 9 digits, allocated by the book.
- OD-l a submit that raises ``OrderRefused`` is a definite broker refusal (the order is recorded Rejected); any other
  exception leaves the outcome unknown, so the order stays non-terminal until a read settles it.
- OD-m (owner question Q223) a Close preparation also LISTS cancel requests for the platform's own still-open ENTRY
  orders of the strategy, shown before confirmation, so a late fill cannot leave a naked short. Listed only; nothing
  is sent by this module.
- OD-n (W-026) Strategy Guard on execution: "before" is the strategy version being executed (the plan, which must
  equal that version's legs), "after" is the position the strategy holds if every prepared order fills, both priced
  at the PLAN's entry prices, so a fill price alone never flags. Completing the plan is not a change; a retry that
  still leaves a leg missing, or a close, is. Margin before/after comes from the same ``MarginPlanner``.
- Close is offered in PARTIAL_EXCEPTION and IN_PROGRESS (something filled), never under a mismatch: ADR-018 Q198 makes
  reconciliation the path there, and REQ-059 requires no unresolved mismatch for an exit.
"""
from __future__ import annotations

import dataclasses
import datetime
import hmac
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Final, Protocol

from ofo.engine import Action, Leg, Strategy, strategy_metrics
from ofo.engine.legs import require_decimal, require_price
from ofo.engine.metrics import MultiExpiryError, StrategyMetrics
from ofo.execution.context import ExecutionAction, ExecutionContext, MarginPlanner, active_legs_hash
from ofo.execution.planned import MAX_PLAN_LEGS, ExecutionPlan, PlannedLeg, ident
from ofo.execution.safety import SafetyResult, check_pre_execution
from ofo.engine.interfaces import MarginPlanner as PlanMarginPlanner
from ofo.execution.sequence import BrokerConstraints, PlannedOrder, exit_orders, sequence_plan
from ofo.instruments import Catalogue, EligibilityRegistry
from ofo.orders import TERMINAL_STATES, FillConflictError, Order, OrderBook, OrderState, OrderView
from ofo.execution.send_guard import _BrokerSink, _Transport, allowed_or_refuse, executable_version
from ofo.strategy.guard import GuardBinding, GuardDecision, GuardRefused, _decision, assess_risk_change, proposal_hash
from ofo.strategy.versions import StrategyRecord, VersionError

MAX_POSITION_LINES: Final = 100  # orchestrator default OD-g
MAX_ORDER_STATUSES: Final = 200  # orchestrator default OD-g
UNCONFIRMED_GRACE: Final = datetime.timedelta(seconds=60)  # orchestrator default OD-i
_FAILED_STATES: Final = frozenset({OrderState.REJECTED, OrderState.CANCELLED})


class PartialChoice(Enum):
    COMPLETE_STRATEGY = "Complete Strategy"
    RETRY_FAILED_LEG = "Retry Failed Leg"
    REVIEW_MANUALLY = "Review Manually"
    CLOSE_PARTIAL_STRATEGY = "Close Partial Strategy"


#: ADR-017 Q27 / REQ-058 AC-2: the order the user is offered them in (Complete first).
CHOICE_ORDER: Final[tuple[PartialChoice, ...]] = (
    PartialChoice.COMPLETE_STRATEGY,
    PartialChoice.RETRY_FAILED_LEG,
    PartialChoice.REVIEW_MANUALLY,
    PartialChoice.CLOSE_PARTIAL_STRATEGY,
)


class ExecutionStatus(Enum):
    COMPLETE = "complete"  # broker positions equal the plan and the ledger agrees
    PARTIAL_EXCEPTION = "partial_exception"  # some legs filled, a missing leg failed (AC-1)
    IN_PROGRESS = "in_progress"  # a missing leg has a non-terminal order in the reconciled book (OD-b)
    NOT_EXECUTED = "not_executed"  # nothing filled at all
    RECONCILIATION_REQUIRED = "reconciliation_required"  # broker and book/plan disagree (ADR-018)


_ident = ident


def _int(value: object, name: str, *, signed: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or (not signed and value < 0):
        raise ValueError(f"{name} must be {'an' if signed else 'a non-negative'} integer, got {value!r}")
    return value


def _aware(value: object, name: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got {value!r}")
    return value


@dataclass(frozen=True)
class BrokerPositionLine:
    """One broker position line attributed to the strategy: signed net units (long +, short -)."""

    contract: str
    net_quantity: int
    average_price: Decimal
    ltp: Decimal | None = None

    def __post_init__(self) -> None:
        _ident(self.contract, "contract")
        _int(self.net_quantity, "net_quantity", signed=True)
        require_price(self.average_price, "average_price", allow_zero=False)
        if self.ltp is not None:
            require_price(self.ltp, "ltp")


@dataclass(frozen=True)
class BrokerOrderStatus:
    """The broker's current view of one order; ``reason`` is the broker's own text, shown as is (AC-6).
    ``client_tag`` is the platform tag the order was sent with, when the broker echoes it."""

    broker_order_id: str
    contract: str
    state: OrderState
    filled_quantity: int
    reason: str | None = None
    client_tag: str | None = None

    def __post_init__(self) -> None:
        _ident(self.broker_order_id, "broker_order_id")
        _ident(self.contract, "contract")
        if not isinstance(self.state, OrderState):
            raise ValueError(f"state must be an OrderState, got {self.state!r}")
        _int(self.filled_quantity, "filled_quantity")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError(f"reason must be the broker's text or None, got {self.reason!r}")
        if self.client_tag is not None:
            _ident(self.client_tag, "client_tag")


class BrokerReader(Protocol):
    """Fresh reads from the broker (Zerodha is the authority, ADR-016). Any exception means 'could not re-read'.

    Each read returns its lines AND the tz-aware time the broker was read.
    """

    def fetch_positions(self, strategy_id: str) -> tuple[Sequence[BrokerPositionLine], datetime.datetime]: ...

    def fetch_order_statuses(self, strategy_id: str) -> tuple[Sequence[BrokerOrderStatus], datetime.datetime]: ...

    def fetch_available_margin(self) -> Decimal: ...


class OrderRefused(Exception):
    """Raised by the broker transport when the broker definitely refused the order (its text is the message). Any
    other exception means the outcome is unknown (OD-l). The transport is private to ``ofo.execution.send_guard``."""


@dataclass(frozen=True)
class LegFailure:
    leg_ref: str
    contract: str
    broker_order_id: str | None
    state: OrderState
    reason: str  # the broker's own text (AC-6); "no reason given by the broker" when it sent none


@dataclass(frozen=True)
class RemainingLeg:
    planned: PlannedLeg
    missing_quantity: int


@dataclass(frozen=True)
class Assessment:
    strategy_id: str
    status: ExecutionStatus
    actual_legs: tuple[Leg, ...]  # the broker's real legs, as engine legs (entry = broker average price)
    remaining: tuple[RemainingLeg, ...]
    failures: tuple[LegFailure, ...]
    mismatches: tuple[str, ...]
    metrics: StrategyMetrics | None  # engine, on actual_legs (AC-1)
    live_pnl: Decimal | None  # engine, on actual_legs, when the broker gave every LTP
    margin_required: Decimal | None  # planner, on actual_legs
    choices: tuple[PartialChoice, ...]  # CHOICE_ORDER only in PARTIAL_EXCEPTION
    read_at: datetime.datetime  # the older of the two broker reads this assessment rests on
    open_orders: tuple[OrderView, ...]  # non-terminal in the reconciled book: the ONLY meaning of "in flight"


def _sync_book(
    plan: ExecutionPlan, statuses: Sequence[BrokerOrderStatus], book: OrderBook, read_at: datetime.datetime,
    grace: datetime.timedelta,
) -> tuple[list[str], dict[str, str]]:
    """Step 0: bring the book's own orders in line with the broker's order-status read, in both directions.

    Returns the mismatches found and the broker's reason text per book key.
    """
    mismatches: list[str] = []
    reasons: dict[str, str] = {}
    seen: set[str] = set()
    for status in statuses:
        view = book.find(status.broker_order_id, status.client_tag)
        if view is None:
            mismatches.append(f"Zerodha shows order {status.broker_order_id} that the platform has no record of")
            continue
        if view.strategy_id != plan.strategy_id:
            mismatches.append(f"order {status.broker_order_id} belongs to another strategy")
            continue
        try:
            if view.broker_order_id is None:  # accepted but its id never recorded: learn it from the read
                view = book.attach_broker_id(view.key, status.broker_order_id)
            seen.add(view.key)
            if status.reason:
                reasons[view.key] = status.reason
            book.reconcile_cumulative(status.broker_order_id, status.filled_quantity, read_at=read_at)
            if view.broker_order_id != status.broker_order_id:
                raise ValueError(f"book has broker id {view.broker_order_id!r} for {view.key!r}")
            book.mirror_broker_state(view.key, status.state)
        except (FillConflictError, ValueError) as exc:
            mismatches.append(f"order {status.broker_order_id}: {exc}")
    now = book.now()
    for view in book.views_for(plan.strategy_id):
        if view.state in TERMINAL_STATES or view.key in seen:
            continue
        if now - book.registered_at(view.key) > grace:  # OD-i: unconfirmed past the grace window
            mismatches.append(f"order {view.key} is not in Zerodha's order list {grace.total_seconds():.0f}s after "
                              "it was sent")
    return mismatches, reasons


def _position_mismatches(plan: ExecutionPlan, positions: Sequence[BrokerPositionLine], book: OrderBook) -> list[str]:
    out: list[str] = []
    for line in positions:
        planned = plan.by_contract(line.contract)
        if planned is None:
            out.append(f"{line.contract}: the broker shows a position outside this strategy's plan")
            continue
        sign = 1 if planned.leg.action is Action.BUY else -1
        if line.net_quantity * sign < 0 or abs(line.net_quantity) > planned.leg.quantity:
            out.append(f"{line.contract}: the broker shows {line.net_quantity} units; the plan allows 0 to "
                       f"{sign * planned.leg.quantity}")
    ledger = dict(book.positions_for(plan.strategy_id))
    broker = {line.contract: line.net_quantity for line in positions if line.net_quantity}
    if ledger != broker:
        out.append(f"confirmed fills {ledger} differ from the broker's positions {broker}")
    return out


def assess(
    plan: ExecutionPlan, positions: Sequence[BrokerPositionLine], statuses: Sequence[BrokerOrderStatus],
    book: OrderBook, planner: MarginPlanner, *, read_at: datetime.datetime,
    grace: datetime.timedelta = UNCONFIRMED_GRACE,
) -> Assessment:
    """Sync the book with the broker's order statuses (step 0), then classify the execution.

    ``read_at`` is when the broker was read (the older of the two reads when they differ).
    """
    if not isinstance(plan, ExecutionPlan) or not isinstance(book, OrderBook):
        raise ValueError("assess needs an ExecutionPlan and an OrderBook")
    _aware(read_at, "read_at")
    positions, statuses = tuple(positions), tuple(statuses)
    if len(positions) > MAX_POSITION_LINES or len(statuses) > MAX_ORDER_STATUSES:
        raise ValueError(f"too many lines: {len(positions)} positions, {len(statuses)} order statuses")
    if not all(isinstance(p, BrokerPositionLine) for p in positions):
        raise ValueError("positions must be BrokerPositionLine values")
    if not all(isinstance(s, BrokerOrderStatus) for s in statuses):
        raise ValueError("statuses must be BrokerOrderStatus values")
    for name, keys in (("position contract", [p.contract for p in positions]),
                       ("broker order id", [s.broker_order_id for s in statuses])):
        if len(set(keys)) != len(keys):
            raise ValueError(f"duplicate {name} in the broker read: {keys}")

    mismatches, reasons = _sync_book(plan, statuses, book, read_at, grace)
    mismatches += _position_mismatches(plan, positions, book)
    if book.is_submit_blocked(plan.strategy_id):
        mismatches.append("this strategy has an unresolved reconciliation mismatch")

    held = {p.contract: p for p in positions if p.net_quantity}
    actual: list[Leg] = []
    remaining: list[RemainingLeg] = []
    for planned in plan.legs:
        line = held.get(planned.contract)
        units = abs(line.net_quantity) if line is not None else 0
        if line is not None and not mismatches:
            actual.append(dataclasses.replace(planned.leg, quantity=units, entry_price=line.average_price,
                                              ltp=line.ltp))
        if units < planned.leg.quantity:
            remaining.append(RemainingLeg(planned, planned.leg.quantity - units))

    missing_contracts = {r.planned.contract for r in remaining}
    views = book.views_for(plan.strategy_id)
    open_orders = tuple(v for v in views if v.state not in TERMINAL_STATES)
    failures = tuple(
        LegFailure(plan.by_contract(v.contract).leg_ref, v.contract, v.broker_order_id, v.state,
                   reasons.get(v.key) or "no reason given by the broker")
        for v in views
        if v.state in _FAILED_STATES and v.contract in missing_contracts and plan.by_contract(v.contract)
    )
    open_missing = any(v.contract in missing_contracts for v in open_orders)

    if mismatches:
        status = ExecutionStatus.RECONCILIATION_REQUIRED
    elif not remaining:
        status = ExecutionStatus.COMPLETE  # AC-5: from positions the ledger agrees with, never from orders sent
    elif open_missing:
        status = ExecutionStatus.IN_PROGRESS  # orchestrator default OD-b
    elif not actual:
        status = ExecutionStatus.NOT_EXECUTED
    else:
        status = ExecutionStatus.PARTIAL_EXCEPTION

    metrics = live = margin = None
    if actual:
        strategy = Strategy(tuple(actual))
        try:
            metrics = strategy_metrics(strategy)
        except MultiExpiryError:
            metrics = None  # exact at-expiry metrics do not exist for a multi-expiry position
        if all(leg.ltp is not None for leg in actual):
            live = strategy.live_pnl()
        margin = require_decimal(planner.required_margin(strategy), "margin_required")
    return Assessment(
        strategy_id=plan.strategy_id, status=status, actual_legs=tuple(actual), remaining=tuple(remaining),
        failures=failures, mismatches=tuple(mismatches), metrics=metrics, live_pnl=live, margin_required=margin,
        choices=CHOICE_ORDER if status is ExecutionStatus.PARTIAL_EXCEPTION else (), read_at=read_at,
        open_orders=open_orders,
    )


_MINT: Final = object()  # module-private: only this module's flow mints a Preparation (W-026)
_GATE_ORDERS: dict[int, tuple[SafetyResult, str]] = {}  # gate result -> the orders it was run for (W-026)
_MAX_OPEN_GATES: Final = 1000  # orchestrator default: oldest dropped first (a dropped one must be prepared again)


def _orders_digest(orders: Sequence[Order]) -> str:
    rows = sorted([o.strategy_id, str(o.version_id), o.leg_ref, o.contract, o.side.value, str(o.quantity),
                   format(o.price.normalize(), "f")] for o in orders)
    return proposal_hash(rows)


def _prep(*args: object, **kwargs: object) -> Preparation:
    return Preparation(*args, _mint=_MINT, **kwargs)  # type: ignore[arg-type]


class Preparation:
    """Orders prepared for one user choice. Nothing is sent until ``submit_confirmed``; usable once.

    A ready preparation is the strategy's ONE live preparation (held on the ``OrderBook``) until it is sent or the
    user discards it (orchestrator default OD-h). ``cancels`` lists book keys of the platform's own open entry orders
    a Close asks the user to cancel (OD-m; listed only).

    W-026 (REQ-036 AC-2/AC-3, finding caller-supplied-verdict-trusted): only this module's flow mints one (a
    module-private sentinel; a direct construction is refused), it is immutable, and it is sealed to its own orders
    and gate result. ``plan`` is the flow's grounded plan; ``guard`` the Strategy Guard decision shown to the user.
    """

    __slots__ = ("choice", "assessment", "orders", "gate", "reason", "book", "strategy_id", "cancels", "guard",
                 "plan", "catalogue", "slices", "_seal", "_consumed")

    def __init__(self, choice: PartialChoice, assessment: Assessment | None, orders: tuple[Order, ...],
                 gate: SafetyResult | None, reason: str, book: OrderBook | None = None,
                 strategy_id: str | None = None, cancels: tuple[str, ...] = (),
                 guard: GuardDecision | None = None, plan: ExecutionPlan | None = None,
                 catalogue: Catalogue | None = None, slices: tuple[PlannedOrder, ...] = (), *,
                 _mint: object = None) -> None:
        if _mint is not _MINT:
            raise ValueError("a Preparation is made only by the strategy's execution flow (REQ-036 AC-3)")
        orders = tuple(orders)
        for name, value in (("choice", choice), ("assessment", assessment), ("orders", orders), ("gate", gate),
                            ("reason", reason), ("book", book), ("strategy_id", strategy_id), ("cancels", cancels),
                            ("guard", guard), ("plan", plan), ("catalogue", catalogue), ("slices", tuple(slices)),
                            ("_seal", (_orders_digest(orders), gate)),
                            ("_consumed", False)):
            object.__setattr__(self, name, value)
        if self.ready:
            book.hold_preparation(strategy_id, self)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("a Preparation cannot be changed after the flow made it")

    @property
    def ready(self) -> bool:
        return (bool(self.orders) and self.gate is not None and not self.gate.blocked and not self._consumed
                and self.book is not None and self.strategy_id is not None)


def discard_preparation(preparation: Preparation) -> None:
    """The user drops a waiting preparation: it can no longer be sent and the strategy is free for a new one."""
    if not isinstance(preparation, Preparation):
        raise ValueError("discard_preparation needs a Preparation")
    object.__setattr__(preparation, "_consumed", True)
    if preparation.gate is not None:
        _GATE_ORDERS.pop(id(preparation.gate), None)
    if preparation.book is not None and preparation.strategy_id is not None:
        preparation.book.release_preparation(preparation.strategy_id, preparation)


def _refetch(plan: ExecutionPlan, reader: BrokerReader, book: OrderBook,
             planner: MarginPlanner) -> Assessment | str:
    """AC-4: re-read positions AND order status (each read checked for freshness) before anything is prepared."""
    try:
        positions, positions_at = reader.fetch_positions(plan.strategy_id)
        statuses, statuses_at = reader.fetch_order_statuses(plan.strategy_id)
        read_at = min(book.check_read(positions_at), book.check_read(statuses_at))
    except Exception as exc:  # fail closed: any read error means we do not know the broker's state
        return f"We could not re-read your Zerodha positions and orders ({exc}). No order has been prepared."
    return assess(plan, positions, statuses, book, planner, read_at=read_at)


def _not_prepared(choice: PartialChoice, a: Assessment | str | None, reason: str | None = None) -> Preparation:
    if isinstance(a, str):
        return _prep(choice, None, (), None, a)
    if a is None:
        return _prep(choice, None, (), None, reason or "Nothing prepared.")
    return _prep(choice, a, (), None, reason or f"Nothing prepared: the strategy is {a.status.value}.")


WAITING = ("Another preparation for this strategy is waiting for your confirmation. Confirm or discard it first. "
           "No order has been prepared.")
IN_FLIGHT = ("Orders for this strategy are in flight and Zerodha has not confirmed them yet. No order has been "
             "prepared; check again once they are confirmed.")
NEEDS_FRESH_READ = ("You chose Close Partial Strategy. Completing or retrying needs a fresh read of your Zerodha "
                    "positions taken after that choice. No order has been prepared.")


def _version_number(version_id: object) -> int:
    """The record's own version id convention, ``v<n>`` (``gate_inputs_from_record``, ``modification``)."""
    if not isinstance(version_id, str) or not version_id.startswith("v") or not version_id[1:].isdigit():
        raise ValueError(f"version_id must name a version of the strategy's record as 'v<n>', got {version_id!r}")
    return int(version_id[1:])


def _record_with_version(book: OrderBook, strategy_id: str, version_id: object) -> StrategyRecord:
    """REQ-036 AC-1: the strategy must have a record and ``version_id`` must be a version in it, else refuse."""
    record = book.record_for(strategy_id)
    try:
        record.version(_version_number(version_id))
    except VersionError as exc:
        raise ValueError(f"strategy {strategy_id!r} has no version {version_id!r}; no order is prepared or sent "
                         "(REQ-036 AC-1)") from exc
    return record


def _grounded_plan(book: OrderBook, plan: ExecutionPlan, version_id: str,
                   catalogue: Catalogue | None = None) -> StrategyRecord:
    """The plan must BE the named version of the strategy's record: same legs (side, type, strike, expiry, units),
    the version must be the record's active or pending one, and (when a catalogue is given, at preparation) every
    contract symbol must be that leg's instrument in the catalogue."""
    record = _record_with_version(book, plan.strategy_id, version_id)
    version = executable_version(record, _version_number(version_id))
    if catalogue is not None:
        symbols = {e.contract.tradingsymbol: e.contract for e in catalogue.all_entries()}
        for p in plan.legs:
            c = symbols.get(p.contract)
            if (c is None or c.name != version.definition.underlying or c.instrument_type != p.leg.instrument.value
                    or c.expiry != p.leg.expiry or (p.leg.strike is not None and c.strike != p.leg.strike)):
                raise ValueError(f"plan contract {p.contract!r} is not the catalogue instrument of its leg "
                                 "(REQ-036 AC-3); nothing is prepared")
    planned = sorted((p.leg.action.value, p.leg.instrument.value, str(p.leg.strike), p.leg.expiry.isoformat(),
                      p.leg.quantity) for p in plan.legs)
    stored = sorted((d.action.value, d.instrument.value, str(d.strike), d.expiry.isoformat(), d.quantity)
                    for d in version.definition.legs)
    if planned != stored:
        raise ValueError(f"the execution plan is not version {version_id!r} of strategy {plan.strategy_id!r}; "
                         "only the strategy's own version can be executed (REQ-036 AC-3)")
    return record


def _orders_binding(strategy_id: str, orders: tuple[Order, ...]) -> GuardBinding:
    """Strategy Guard binding of an execution: strategy, version and the exact orders (leg, contract, side, qty,
    price). Recomputed at submit from the orders as they stand then."""
    versions = {o.version_id for o in orders}
    if len(versions) != 1 or any(o.strategy_id != strategy_id for o in orders):
        raise ValueError("every order of one submission must belong to the same strategy and version")
    rows = sorted([o.leg_ref, o.contract, o.side.value, str(o.quantity), format(o.price.normalize(), "f")]
                  for o in orders)
    (version_id,) = versions
    return GuardBinding(strategy_id, version_id, proposal_hash({"strategy_id": strategy_id, "version_id": version_id,
                                                                "orders": rows}))


def _after_legs(plan: ExecutionPlan, a: Assessment, orders: tuple[Order, ...]) -> tuple[Leg, ...]:
    """Orchestrator default OD-n: the position if every order fills, per planned contract, at the plan's prices."""
    held = {(leg.instrument, leg.strike, leg.expiry): leg.quantity for leg in a.actual_legs}
    units = {p.contract: held.get((p.leg.instrument, p.leg.strike, p.leg.expiry), 0) for p in plan.legs}
    for order in orders:
        planned = plan.by_contract(order.contract)
        if planned is None:
            raise ValueError(f"order for {order.contract!r} is not a leg of the strategy's plan")
        units[order.contract] += order.quantity if order.side is planned.leg.action else -order.quantity
    if any(u < 0 for u in units.values()):
        raise ValueError("these orders would flip a leg of the strategy; nothing is prepared")
    return tuple(dataclasses.replace(p.leg, quantity=units[p.contract], ltp=None) for p in plan.legs
                 if units[p.contract] > 0)


def _margin_or_unknown(planner: MarginPlanner, legs: tuple[Leg, ...]) -> Decimal | None:
    if not legs:
        return Decimal("0")  # guard OD-G3: no position, no margin
    try:
        return require_decimal(planner.required_margin(Strategy(legs)), "margin_required")
    except Exception:  # a failing planner is unknown, never 0 (the guard treats unknown as a change)
        return None


def _gate(orders: tuple[Order, ...], legs: tuple[Leg, ...], ctx: ExecutionContext, book: OrderBook,
          plan: ExecutionPlan, catalogue: Catalogue, eligibility: EligibilityRegistry, choice: PartialChoice,
          a: Assessment, record: StrategyRecord, planner: MarginPlanner,
          cancels: tuple[str, ...] = (), slices: tuple[PlannedOrder, ...] = ()) -> Preparation:
    blocked = ctx.reconciliation_blocked_strategy_ids
    if blocked is not None and book.is_submit_blocked(plan.strategy_id):
        ctx = dataclasses.replace(ctx, reconciliation_blocked_strategy_ids=blocked | {plan.strategy_id})
    result = check_pre_execution(Strategy(legs), ctx, catalogue, eligibility, strategy_id=plan.strategy_id)
    if result.blocked:
        return _prep(choice, a, (), result, "The safety checks blocked this. No order has been prepared.")
    # REQ-036 AC-5 (Strategy Guard), run only after the gate passed, on this flow's own grounded inputs (OD-n).
    before = tuple(p.leg for p in plan.legs)
    after = _after_legs(plan, a, orders)
    decision = _decision(_orders_binding(plan.strategy_id, orders), assess_risk_change(
        Strategy(before), Strategy(after) if after else None,
        _margin_or_unknown(planner, before), _margin_or_unknown(planner, after),
    ))
    if len(_GATE_ORDERS) >= _MAX_OPEN_GATES:  # one in, one out: the store never grows past the cap
        del _GATE_ORDERS[next(iter(_GATE_ORDERS))]
    _GATE_ORDERS[id(result)] = (result, _orders_digest(orders))  # this gate result belongs to THESE orders
    reason = f"{len(orders)} order(s) ready for your confirmation."
    if decision.changes_risk_profile:
        reason = f"{decision.message}. {reason}"
    return _prep(choice, a, orders, result, reason, book, plan.strategy_id, cancels, decision, plan, catalogue,
                 slices)


def _prepare_missing(
    choice: PartialChoice, remaining: Sequence[RemainingLeg], plan: ExecutionPlan, reader: BrokerReader,
    book: OrderBook, planner: MarginPlanner, context: ExecutionContext, catalogue: Catalogue,
    eligibility: EligibilityRegistry, a: Assessment, margin_planner: PlanMarginPlanner | None,
    constraints: BrokerConstraints | None,
) -> Preparation:
    if context.action is ExecutionAction.EXIT:
        raise ValueError("completing or retrying uses the entry/adjustment context, not an EXIT context")
    # Once Close was chosen, only a read taken after that choice may complete or retry.
    closing = book.closing_read_at(plan.strategy_id)
    if closing is not None and a.read_at <= closing:
        return _not_prepared(choice, a, NEEDS_FRESH_READ)
    book.clear_closing(plan.strategy_id, a.read_at)
    # In flight = non-terminal in the reconciled book. While anything is, nothing is prepared.
    if a.open_orders:
        return _not_prepared(choice, a, IN_FLIGHT)
    record = _grounded_plan(book, plan, context.version_id, catalogue)  # REQ-036 AC-1/AC-3
    # ADR-017 Q26 / REQ-056 AC-2/AC-3 (W-022, W-028): the missing units go through the FULL plan's sequence with the
    # plan's own margin planner and broker constraints: protectors before the sells that depend on them, never "all
    # buys first"; freeze-limit slices, each a whole number of catalogue lots; batches never span a step.
    missing = {r.planned.leg_ref: r.missing_quantity for r in remaining}
    seq = sequence_plan(plan, margin_planner, constraints, catalogue=catalogue, quantities=missing)
    legs = tuple(dataclasses.replace(plan.by_ref(ref).leg, quantity=missing[ref])
                 for ref in dict.fromkeys(o.leg_ref for o in seq.orders))
    orders = tuple(
        # orchestrator default OD-c: the planned leg's price, reviewed by the user before confirming
        Order(plan.strategy_id, s.leg_ref, plan.by_ref(s.leg_ref).contract, plan.by_ref(s.leg_ref).leg.action,
              s.quantity, plan.by_ref(s.leg_ref).leg.entry_price, version_id=context.version_id)
        for s in seq.orders
    )
    try:
        available = require_decimal(reader.fetch_available_margin(), "margin_available")  # OD-d: fresh read
    except Exception as exc:  # fail closed
        return _not_prepared(choice, a, f"We could not re-read your available margin ({exc}). No order has been "
                                        "prepared.")
    required = require_decimal(planner.required_margin(Strategy(legs)), "margin_required")  # OD-d
    ctx = dataclasses.replace(context, margin_available=available, margin_required=required)
    return _gate(orders, legs, ctx, book, plan, catalogue, eligibility, choice, a, record, planner,
                 slices=seq.orders)


def _live(choice: PartialChoice, book: OrderBook, plan: ExecutionPlan) -> Preparation | None:
    """Orchestrator default OD-h: a second prepare while one waits is REFUSED (not handed the same one back)."""
    if not isinstance(book, OrderBook) or not isinstance(plan, ExecutionPlan):
        raise ValueError("a preparation needs an ExecutionPlan and an OrderBook")
    return _not_prepared(choice, None, WAITING) if book.has_live_preparation(plan.strategy_id) else None


def complete_strategy(
    plan: ExecutionPlan, reader: BrokerReader, book: OrderBook, planner: MarginPlanner, context: ExecutionContext,
    catalogue: Catalogue, eligibility: EligibilityRegistry, *, margin_planner: PlanMarginPlanner | None = None,
    constraints: BrokerConstraints | None = None,
) -> Preparation:
    """AC-4: re-fetch, sync, recompute the remaining strategy, re-check margin, verify the missing legs, prepare only
    them. A late fill that closes the gap makes the strategy COMPLETE and prepares nothing.

    W-028: ``margin_planner`` and ``constraints`` are the same engine margin planner and broker constraints the plan
    (``sequence_plan``) uses; the missing units are prepared as that plan's lot-aligned freeze slices."""
    choice = PartialChoice.COMPLETE_STRATEGY
    waiting = _live(choice, book, plan)
    if waiting is not None:
        return waiting
    a = _refetch(plan, reader, book, planner)
    if isinstance(a, str):
        return _not_prepared(choice, a)
    if a.status is ExecutionStatus.COMPLETE:
        return _not_prepared(choice, a,
                             "Zerodha now shows every leg filled. The strategy is complete; nothing was prepared.")
    if a.status is ExecutionStatus.IN_PROGRESS:
        return _not_prepared(choice, a, IN_FLIGHT)
    if a.status is not ExecutionStatus.PARTIAL_EXCEPTION:
        return _not_prepared(choice, a)
    return _prepare_missing(choice, a.remaining, plan, reader, book, planner, context, catalogue, eligibility, a,
                            margin_planner, constraints)


def retry_failed_leg(
    plan: ExecutionPlan, leg_ref: str, reader: BrokerReader, book: OrderBook, planner: MarginPlanner,
    context: ExecutionContext, catalogue: Catalogue, eligibility: EligibilityRegistry, *,
    margin_planner: PlanMarginPlanner | None = None, constraints: BrokerConstraints | None = None,
) -> Preparation:
    """Orchestrator default OD-a: new order(s) for the same contract as one FAILED leg, after the same re-reads.
    W-028: the still-missing units are sent as the plan's lot-aligned freeze slices (same planner and constraints)."""
    _ident(leg_ref, "leg_ref")
    choice = PartialChoice.RETRY_FAILED_LEG
    waiting = _live(choice, book, plan)
    if waiting is not None:
        return waiting
    a = _refetch(plan, reader, book, planner)
    if isinstance(a, str):
        return _not_prepared(choice, a)
    if a.status is ExecutionStatus.IN_PROGRESS:
        return _not_prepared(choice, a, IN_FLIGHT)
    if a.status is not ExecutionStatus.PARTIAL_EXCEPTION:
        return _not_prepared(choice, a)
    if leg_ref not in {f.leg_ref for f in a.failures}:
        raise ValueError(f"leg {leg_ref!r} has no failed order to retry")
    (target,) = [r for r in a.remaining if r.planned.leg_ref == leg_ref]
    return _prepare_missing(choice, (target,), plan, reader, book, planner, context, catalogue, eligibility, a,
                            margin_planner, constraints)


def review_manually(assessment: Assessment) -> Preparation:
    """Review Manually: show the state and the broker's reasons; prepare nothing."""
    if not isinstance(assessment, Assessment):
        raise ValueError("review_manually needs an Assessment")
    return _prep(PartialChoice.REVIEW_MANUALLY, assessment, (), None,
                       "Review the filled and failed legs below. No order has been prepared.")


def close_partial_strategy(
    plan: ExecutionPlan, reader: BrokerReader, book: OrderBook, planner: MarginPlanner, context: ExecutionContext,
    catalogue: Catalogue, eligibility: EligibilityRegistry, *, constraints: BrokerConstraints | None = None,
) -> Preparation:
    """Close Partial Strategy: reduce-only exits for exactly the filled legs, through the gate as an EXIT.

    Exit quantity per leg = held (broker-confirmed) - exits already open in the reconciled book. The platform's own
    open ENTRY orders are listed as cancel requests (OD-m). Not offered under a reconciliation mismatch.

    W-032 (REQ-056 AC-10, deferred #50): each exit is sent as the same lot-aligned freeze slices Complete and Retry
    use (``sequence.exit_orders`` -> ``slice_quantity``; ``constraints`` as for them, default the labelled UNVERIFIED
    placeholder). Step 1 = buy-backs of shorts, step 2 = sells of longs (OD-e); a batch never spans the two.
    """
    choice = PartialChoice.CLOSE_PARTIAL_STRATEGY
    waiting = _live(choice, book, plan)
    if waiting is not None:
        return waiting
    a = _refetch(plan, reader, book, planner)
    if isinstance(a, str):
        return _not_prepared(choice, a)
    if a.status not in (ExecutionStatus.PARTIAL_EXCEPTION, ExecutionStatus.IN_PROGRESS) or not a.actual_legs:
        return _not_prepared(choice, a)
    record = _grounded_plan(book, plan, context.version_id, catalogue)  # REQ-036 AC-1/AC-3
    book.mark_closing(plan.strategy_id, a.read_at)  # Complete/Retry now need a read newer than this one
    if any(leg.ltp is None for leg in a.actual_legs):  # orchestrator default OD-e: fail closed without a price
        return _not_prepared(choice, a, "Zerodha did not give a current price for every filled leg. No order has "
                                        "been prepared.")
    exits_open: dict[str, int] = {}
    cancels: list[str] = []
    for view in a.open_orders:
        planned = plan.by_contract(view.contract)
        if planned is not None and view.side is planned.leg.action:
            cancels.append(view.key)  # an entry order still open: listed for cancellation (OD-m)
        else:
            exits_open[view.contract] = exits_open.get(view.contract, 0) + view.quantity - view.filled_quantity
    flip = {Action.BUY: Action.SELL, Action.SELL: Action.BUY}
    pairs = []
    for leg in a.actual_legs:
        planned = next(p for p in plan.legs if (p.leg.instrument, p.leg.strike, p.leg.expiry)
                       == (leg.instrument, leg.strike, leg.expiry))
        still_open = leg.quantity - exits_open.get(planned.contract, 0)
        if still_open > 0:
            pairs.append((planned, dataclasses.replace(leg, action=flip[leg.action], quantity=still_open,
                                                       entry_price=leg.ltp, ltp=None)))
    if not pairs:
        return _not_prepared(choice, a, "Exit orders for every filled leg are already in flight. No order has been "
                                        "prepared.")
    pairs.sort(key=lambda pl: 0 if pl[1].action is Action.BUY else 1)  # OD-e: buy back shorts first
    groups = [[(p.leg_ref, e.quantity) for p, e in pairs if e.action is side] for side in (Action.BUY, Action.SELL)]
    slices = exit_orders(plan, [g for g in groups if g], constraints, catalogue)  # W-032: freeze slices, whole lots
    exits = {p.leg_ref: e for p, e in pairs}
    orders = tuple(Order(plan.strategy_id, s.leg_ref, plan.by_ref(s.leg_ref).contract, exits[s.leg_ref].action,
                         s.quantity, exits[s.leg_ref].entry_price, version_id=context.version_id) for s in slices)
    legs = tuple(e for _, e in pairs)
    # The held legs come from THIS call's fresh broker read (the authority, ADR-016), not from a caller.
    ctx = dataclasses.replace(
        context, action=ExecutionAction.EXIT, active_legs=a.actual_legs, active_version_id=context.version_id,
        active_legs_hash=active_legs_hash(plan.strategy_id, context.version_id, a.actual_legs),
    )
    return _gate(orders, legs, ctx, book, plan, catalogue, eligibility, choice, a, record, planner, tuple(cancels),
                 slices)


@dataclass(frozen=True)
class SubmissionResult:
    """What was sent. Sending is not executing (ADR-016): completeness is only ever decided by ``assess``."""

    submitted: tuple[tuple[str, str], ...]  # (leg_ref, broker order id)
    failed: tuple[str, str] | None  # (leg_ref, the broker's text) -- a definite refusal or an unknown outcome
    not_sent: tuple[str, ...]
    needs_reconciliation: tuple[str, ...] = ()  # client tags accepted by the broker with an unusable id


def _mark_sent(book: OrderBook, client_tag: str) -> None:
    """Prepared -> Submitted in the book. If the book refuses, the order simply stays Prepared: still non-terminal,
    so it still counts as in flight until a broker read settles it."""
    try:
        book.transition_key(client_tag, OrderState.SUBMITTED)
    except ValueError:
        return


_SEND_KIND: Final = {PartialChoice.COMPLETE_STRATEGY: "complete", PartialChoice.RETRY_FAILED_LEG: "retry",
                     PartialChoice.CLOSE_PARTIAL_STRATEGY: "close"}


def _authorised_orders(preparation: Preparation, book: OrderBook, strategy_id: str,
                       acknowledgement: str | None) -> tuple[Order, ...]:
    """W-026: permission to send is RE-DERIVED here, never taken from the preparation's word. The preparation must
    be the flow's own, unchanged since it was sealed, with a gate result run for exactly these orders; every order
    must be a permitted leg of the bound record's executable version (``send_guard.allowed_or_refuse``); a Strategy
    Guard change needs this preparation's own token (AC-5)."""
    orders = preparation.orders
    if preparation.plan is None or preparation.catalogue is None or not all(isinstance(o, Order) for o in orders):
        raise ValueError("this preparation was not made by the strategy's execution flow; nothing was sent")
    digest = _orders_digest(orders)
    if preparation._seal[0] != digest or preparation._seal[1] is not preparation.gate:
        raise ValueError("this preparation changed after it was checked; nothing was sent")
    issued = _GATE_ORDERS.get(id(preparation.gate))
    if issued is None or issued[0] is not preparation.gate or issued[1] != digest:
        raise ValueError("the safety check result does not belong to these orders; nothing was sent")
    binding = _orders_binding(strategy_id, orders)
    # AC-1/AC-3: bound record, executable version, and every plan symbol is its leg's catalogue instrument
    record = _grounded_plan(book, preparation.plan, binding.version_id, preparation.catalogue)
    allowed_or_refuse(
        choice=_SEND_KIND.get(preparation.choice, "none"), orders=orders,
        version=record.version(_version_number(binding.version_id)),
        planned={p.contract: (p.leg_ref, p.leg.action, p.leg.quantity) for p in preparation.plan.legs},
        book=book, strategy_id=strategy_id,
    )
    guard = preparation.guard
    if guard is None or guard.binding != binding:
        raise GuardRefused("Strategy Guard has not checked this exact action; nothing was sent")
    if guard.acknowledgement is not None and (
            not isinstance(acknowledgement, str) or not hmac.compare_digest(acknowledgement, guard.acknowledgement)):
        raise GuardRefused(f"{guard.message}. Acknowledge it to proceed. Nothing was sent.")
    _GATE_ORDERS.pop(id(preparation.gate), None)
    return orders


def submit_confirmed(
    preparation: Preparation, *, choice: PartialChoice, confirmed_by: str, submitter: _Transport,
    acknowledgement: str | None = None,
) -> SubmissionResult:
    """Send a preparation's orders ONCE, only for the user's explicit choice (AC-6: never automatic, never retried).

    Each order is registered in the book (Prepared, under a new client tag) BEFORE it is sent, so it is in flight from
    that moment. On acceptance its broker id is attached; an unusable id (empty, padded, already used) blocks the
    strategy for reconciliation and stops the rest. The first refusal stops the rest (invariant 21); nothing is resent.

    REQ-036: every order must belong to this strategy and a version in its record (AC-1), and the strategy's own
    Strategy Guard must have checked exactly these orders; when they change the risk profile, ``acknowledgement``
    must be that decision's own token (AC-5). The decision is consumed: a token never works twice.
    """
    if not isinstance(preparation, Preparation):
        raise ValueError("submit_confirmed needs a Preparation")
    if choice is not preparation.choice:
        raise ValueError(f"the user chose {choice!r}; this preparation is for {preparation.choice!r}")
    _ident(confirmed_by, "confirmed_by")
    if not preparation.ready:
        raise ValueError("this preparation has no orders, did not pass the safety checks, or was already sent")
    book, strategy_id = preparation.book, preparation.strategy_id
    if book.is_submit_blocked(strategy_id):
        raise ValueError(f"strategy {strategy_id!r} has an unresolved reconciliation mismatch; nothing was sent")
    orders = _authorised_orders(preparation, book, strategy_id, acknowledgement)
    # W-026 round 3: the sink re-derives every broker field from the record and the catalogue, BEFORE anything is
    # registered or sent; a refusal here sends nothing.
    sink = _BrokerSink(submitter, book=book, strategy_id=strategy_id, catalogue=preparation.catalogue,
                       choice=_SEND_KIND[preparation.choice],
                       leg_slots={p.leg_ref: (p.leg.instrument.value, p.leg.strike, p.leg.expiry)
                                  for p in preparation.plan.legs})
    tagged_orders = tuple(dataclasses.replace(o, client_tag=book.next_client_tag()) for o in orders)
    requests = sink.resolve_all(tagged_orders)
    object.__setattr__(preparation, "_consumed", True)
    book.release_preparation(strategy_id, preparation)
    sent: list[tuple[str, str]] = []
    for index, order in enumerate(orders):
        tagged, request = tagged_orders[index], requests[index]
        tag = tagged.client_tag
        book.add(tagged)  # registered BEFORE the broker sees it
        rest = tuple(dict.fromkeys(o.leg_ref for o in orders[index + 1:]))  # W-028: one entry per leg with unsent slices
        try:
            broker_order_id = sink.submit(request)
        except OrderRefused as exc:  # no retry: a definite refusal, recorded and shown with the broker's text
            book.mirror_broker_state(tag, OrderState.REJECTED)
            return SubmissionResult(tuple(sent), (order.leg_ref, str(exc)), rest)
        except Exception as exc:  # no retry: outcome unknown (OD-l), the order stays in flight until a read
            _mark_sent(book, tag)
            return SubmissionResult(tuple(sent), (order.leg_ref, f"outcome unknown: {exc}"), rest)
        try:
            book.attach_broker_id(tag, broker_order_id)
        except ValueError as exc:  # accepted, but its id cannot be recorded: reconciliation, never "failed"
            _mark_sent(book, tag)
            book.block_strategy(strategy_id, f"order {tag} accepted with unusable broker id: {exc}")
            return SubmissionResult(tuple(sent), None, rest, (tag,))
        _mark_sent(book, tag)
        sent.append((order.leg_ref, broker_order_id))
    return SubmissionResult(tuple(sent), None, ())
