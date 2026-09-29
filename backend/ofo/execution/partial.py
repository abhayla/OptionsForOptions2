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
is not merged; its reader will implement this Protocol), orders go out through ``OrderSubmitter``. Every order passes
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
- Close is offered in PARTIAL_EXCEPTION and IN_PROGRESS (something filled), never under a mismatch: ADR-018 Q198 makes
  reconciliation the path there, and REQ-059 requires no unresolved mismatch for an exit.
"""
from __future__ import annotations

import dataclasses
import datetime
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
from ofo.execution.sequence import sequence_plan
from ofo.instruments import Catalogue, EligibilityRegistry
from ofo.orders import TERMINAL_STATES, FillConflictError, Order, OrderBook, OrderState, OrderView

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
    """Raised by an ``OrderSubmitter`` when the broker definitely refused the order (its text is the message)."""


class OrderSubmitter(Protocol):
    """Sends ONE order (carrying its client tag) and returns the broker order id. Raises ``OrderRefused`` on a
    definite refusal; any other exception means the outcome is unknown (OD-l)."""

    def submit(self, order: Order) -> str: ...


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


class Preparation:
    """Orders prepared for one user choice. Nothing is sent until ``submit_confirmed``; usable once.

    A ready preparation is the strategy's ONE live preparation (held on the ``OrderBook``) until it is sent or the
    user discards it (orchestrator default OD-h). ``cancels`` lists book keys of the platform's own open entry orders
    a Close asks the user to cancel (OD-m; listed only).
    """

    __slots__ = ("choice", "assessment", "orders", "gate", "reason", "book", "strategy_id", "cancels", "_consumed")

    def __init__(self, choice: PartialChoice, assessment: Assessment | None, orders: tuple[Order, ...],
                 gate: SafetyResult | None, reason: str, book: OrderBook | None = None,
                 strategy_id: str | None = None, cancels: tuple[str, ...] = ()) -> None:
        self.choice = choice
        self.assessment = assessment
        self.orders = orders
        self.gate = gate
        self.reason = reason
        self.book = book
        self.strategy_id = strategy_id
        self.cancels = cancels
        self._consumed = False
        if self.ready:
            book.hold_preparation(strategy_id, self)

    @property
    def ready(self) -> bool:
        return (bool(self.orders) and self.gate is not None and not self.gate.blocked and not self._consumed
                and self.book is not None and self.strategy_id is not None)


def discard_preparation(preparation: Preparation) -> None:
    """The user drops a waiting preparation: it can no longer be sent and the strategy is free for a new one."""
    if not isinstance(preparation, Preparation):
        raise ValueError("discard_preparation needs a Preparation")
    preparation._consumed = True
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
        return Preparation(choice, None, (), None, a)
    if a is None:
        return Preparation(choice, None, (), None, reason or "Nothing prepared.")
    return Preparation(choice, a, (), None, reason or f"Nothing prepared: the strategy is {a.status.value}.")


WAITING = ("Another preparation for this strategy is waiting for your confirmation. Confirm or discard it first. "
           "No order has been prepared.")
IN_FLIGHT = ("Orders for this strategy are in flight and Zerodha has not confirmed them yet. No order has been "
             "prepared; check again once they are confirmed.")
NEEDS_FRESH_READ = ("You chose Close Partial Strategy. Completing or retrying needs a fresh read of your Zerodha "
                    "positions taken after that choice. No order has been prepared.")


def _gate(orders: tuple[Order, ...], legs: tuple[Leg, ...], ctx: ExecutionContext, book: OrderBook,
          plan: ExecutionPlan, catalogue: Catalogue, eligibility: EligibilityRegistry, choice: PartialChoice,
          a: Assessment, cancels: tuple[str, ...] = ()) -> Preparation:
    blocked = ctx.reconciliation_blocked_strategy_ids
    if blocked is not None and book.is_submit_blocked(plan.strategy_id):
        ctx = dataclasses.replace(ctx, reconciliation_blocked_strategy_ids=blocked | {plan.strategy_id})
    result = check_pre_execution(Strategy(legs), ctx, catalogue, eligibility, strategy_id=plan.strategy_id)
    if result.blocked:
        return Preparation(choice, a, (), result, "The safety checks blocked this. No order has been prepared.")
    return Preparation(choice, a, orders, result, f"{len(orders)} order(s) ready for your confirmation.", book,
                       plan.strategy_id, cancels)


def _prepare_missing(
    choice: PartialChoice, remaining: Sequence[RemainingLeg], plan: ExecutionPlan, reader: BrokerReader,
    book: OrderBook, planner: MarginPlanner, context: ExecutionContext, catalogue: Catalogue,
    eligibility: EligibilityRegistry, a: Assessment,
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
    # ADR-017 Q26 / REQ-056 AC-3 (W-022): the missing legs go in the full plan's dependency-aware sequence, never
    # "all buys first"; protectors come before the sells that depend on them.
    position = {ref: i for i, ref in enumerate(sequence_plan(plan).sequence)}
    ordered = sorted(remaining, key=lambda r: position[r.planned.leg_ref])
    legs = tuple(dataclasses.replace(r.planned.leg, quantity=r.missing_quantity) for r in ordered)
    orders = tuple(
        # orchestrator default OD-c: the planned leg's price, reviewed by the user before confirming
        Order(plan.strategy_id, r.planned.leg_ref, r.planned.contract, r.planned.leg.action, r.missing_quantity,
              r.planned.leg.entry_price, version_id=context.version_id)
        for r in ordered
    )
    try:
        available = require_decimal(reader.fetch_available_margin(), "margin_available")  # OD-d: fresh read
    except Exception as exc:  # fail closed
        return _not_prepared(choice, a, f"We could not re-read your available margin ({exc}). No order has been "
                                        "prepared.")
    required = require_decimal(planner.required_margin(Strategy(legs)), "margin_required")  # OD-d
    ctx = dataclasses.replace(context, margin_available=available, margin_required=required)
    return _gate(orders, legs, ctx, book, plan, catalogue, eligibility, choice, a)


def _live(choice: PartialChoice, book: OrderBook, plan: ExecutionPlan) -> Preparation | None:
    """Orchestrator default OD-h: a second prepare while one waits is REFUSED (not handed the same one back)."""
    if not isinstance(book, OrderBook) or not isinstance(plan, ExecutionPlan):
        raise ValueError("a preparation needs an ExecutionPlan and an OrderBook")
    return _not_prepared(choice, None, WAITING) if book.has_live_preparation(plan.strategy_id) else None


def complete_strategy(
    plan: ExecutionPlan, reader: BrokerReader, book: OrderBook, planner: MarginPlanner, context: ExecutionContext,
    catalogue: Catalogue, eligibility: EligibilityRegistry,
) -> Preparation:
    """AC-4: re-fetch, sync, recompute the remaining strategy, re-check margin, verify the missing legs, prepare only
    them. A late fill that closes the gap makes the strategy COMPLETE and prepares nothing."""
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
    return _prepare_missing(choice, a.remaining, plan, reader, book, planner, context, catalogue, eligibility, a)


def retry_failed_leg(
    plan: ExecutionPlan, leg_ref: str, reader: BrokerReader, book: OrderBook, planner: MarginPlanner,
    context: ExecutionContext, catalogue: Catalogue, eligibility: EligibilityRegistry,
) -> Preparation:
    """Orchestrator default OD-a: one new order for the same contract as one FAILED leg, after the same re-reads."""
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
    return _prepare_missing(choice, (target,), plan, reader, book, planner, context, catalogue, eligibility, a)


def review_manually(assessment: Assessment) -> Preparation:
    """Review Manually: show the state and the broker's reasons; prepare nothing."""
    if not isinstance(assessment, Assessment):
        raise ValueError("review_manually needs an Assessment")
    return Preparation(PartialChoice.REVIEW_MANUALLY, assessment, (), None,
                       "Review the filled and failed legs below. No order has been prepared.")


def close_partial_strategy(
    plan: ExecutionPlan, reader: BrokerReader, book: OrderBook, planner: MarginPlanner, context: ExecutionContext,
    catalogue: Catalogue, eligibility: EligibilityRegistry,
) -> Preparation:
    """Close Partial Strategy: reduce-only exits for exactly the filled legs, through the gate as an EXIT.

    Exit quantity per leg = held (broker-confirmed) - exits already open in the reconciled book. The platform's own
    open ENTRY orders are listed as cancel requests (OD-m). Not offered under a reconciliation mismatch.
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
    orders = tuple(Order(plan.strategy_id, p.leg_ref, p.contract, e.action, e.quantity, e.entry_price,
                         version_id=context.version_id) for p, e in pairs)
    legs = tuple(e for _, e in pairs)
    # The held legs come from THIS call's fresh broker read (the authority, ADR-016), not from a caller.
    ctx = dataclasses.replace(
        context, action=ExecutionAction.EXIT, active_legs=a.actual_legs, active_version_id=context.version_id,
        active_legs_hash=active_legs_hash(plan.strategy_id, context.version_id, a.actual_legs),
    )
    return _gate(orders, legs, ctx, book, plan, catalogue, eligibility, choice, a, tuple(cancels))


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


def submit_confirmed(
    preparation: Preparation, *, choice: PartialChoice, confirmed_by: str, submitter: OrderSubmitter,
) -> SubmissionResult:
    """Send a preparation's orders ONCE, only for the user's explicit choice (AC-6: never automatic, never retried).

    Each order is registered in the book (Prepared, under a new client tag) BEFORE it is sent, so it is in flight from
    that moment. On acceptance its broker id is attached; an unusable id (empty, padded, already used) blocks the
    strategy for reconciliation and stops the rest. The first refusal stops the rest (invariant 21); nothing is resent.
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
    preparation._consumed = True
    book.release_preparation(strategy_id, preparation)
    sent: list[tuple[str, str]] = []
    for index, order in enumerate(preparation.orders):
        tag = book.next_client_tag()
        tagged = dataclasses.replace(order, client_tag=tag)
        book.add(tagged)  # registered BEFORE the broker sees it
        rest = tuple(o.leg_ref for o in preparation.orders[index + 1:])
        try:
            broker_order_id = submitter.submit(tagged)
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
