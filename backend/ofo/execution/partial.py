"""Partial execution: an explicit exception state, the user's four choices, no automatic retry (REQ-058, ADR-017).

Spec basis (REQ-058; ADR-017 Q27, Q192, Q193; ADR-016/ADR-018; core invariants 4-7, 21):
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

Nothing here talks to Zerodha: positions, order status and margin come through ``BrokerReader`` (reconciliation, W-021,
is not merged; its reader will implement this Protocol), orders go out through ``OrderSubmitter``. Every order passes
the W-014 gate ``check_pre_execution``. The fill ledger (``OrderBook``) must agree with the broker before anything is
prepared; a disagreement blocks the strategy (ADR-018) and is cleared only by ``OrderBook.clear_reconciliation_block``.

Orchestrator defaults (not stated by the spec; each also marked where it is used):
- OD-a "Retry Failed Leg" prepares ONE new order for the same contract, side and still-missing quantity of one failed
  leg; it is placed only after the user confirms. "Complete Strategy" prepares every missing leg, including legs never
  submitted (e.g. a dependent sell held back after its protective buy failed).
- OD-b a missing leg whose order is still open at the broker (Submitted / Pending / Partially Executed) is not yet
  failed: the strategy is IN_PROGRESS and nothing is prepared, because a second order could double the position.
- OD-c the price on a completing/retry order is the planned leg's price; the user reviews it before confirming (the
  Zerodha order-parameter engine of Q28 is separate work).
- OD-d margin re-check: available margin is re-read from the broker; required margin is the planner's figure for the
  orders being prepared (Zerodha's own figure stays final, ADR-016).
- OD-e close orders are priced at the broker's LTP for that contract; a missing LTP prepares nothing (fail closed).
  Buy-backs of short legs are sequenced before sales of long legs so no step leaves a naked short.
- OD-f a broker position in a contract outside the plan, on the wrong side, or larger than planned is a
  reconciliation mismatch: nothing is prepared.
- OD-g size caps: at most 20 planned legs, 100 position lines and 200 order statuses per read.
- OD-h one live preparation per strategy: a second Complete/Retry/Close while one waits for confirmation is REFUSED
  (not handed the same preparation back); ``discard_preparation`` or sending it frees the strategy.

W-023 fix round (verifier AC-4 fail; class: any preparation computed from the broker read alone, ignoring orders
the platform already sent but the broker does not show yet):
(a) ``submit_confirmed`` registers every accepted order in the OrderBook as Submitted, with strategy and version;
(b) what is missing = target - (broker-confirmed + sent, not yet terminal); Complete and Retry prepare nothing while
    any order of the strategy is in flight, Close subtracts exits already in flight;
(c) OD-h above; (d) once Close is chosen, Complete/Retry need a broker read strictly later than the Close read;
(e) every broker read carries a tz-aware ``read_at``; a reconciliation block clears only with a later read.
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
from ofo.execution.safety import SafetyResult, check_pre_execution
from ofo.instruments import Catalogue, EligibilityRegistry
from ofo.orders import FillConflictError, Order, OrderBook, OrderState

MAX_PLAN_LEGS: Final = 20  # orchestrator default OD-g
MAX_POSITION_LINES: Final = 100  # orchestrator default OD-g
MAX_ORDER_STATUSES: Final = 200  # orchestrator default OD-g

_OPEN: Final = frozenset({OrderState.PREPARED, OrderState.SUBMITTED, OrderState.PENDING,
                          OrderState.PARTIALLY_EXECUTED})
_FAILED: Final = frozenset({OrderState.REJECTED, OrderState.CANCELLED})


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
    IN_PROGRESS = "in_progress"  # a missing leg's order is still open at the broker (OD-b)
    NOT_EXECUTED = "not_executed"  # nothing filled at all
    RECONCILIATION_REQUIRED = "reconciliation_required"  # broker and ledger/plan disagree (ADR-018)


def _ident(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty string without surrounding whitespace, got {value!r}")
    return value


def _int(value: object, name: str, *, signed: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or (not signed and value < 0):
        raise ValueError(f"{name} must be {'an' if signed else 'a non-negative'} integer, got {value!r}")
    return value


@dataclass(frozen=True)
class PlannedLeg:
    """One leg the user confirmed: ``contract`` is the broker's trading symbol, ``leg`` the engine leg."""

    leg_ref: str
    contract: str
    leg: Leg

    def __post_init__(self) -> None:
        _ident(self.leg_ref, "leg_ref")
        _ident(self.contract, "contract")
        if not isinstance(self.leg, Leg):
            raise ValueError(f"leg must be an engine Leg, got {self.leg!r}")


@dataclass(frozen=True)
class ExecutionPlan:
    strategy_id: str
    legs: tuple[PlannedLeg, ...]

    def __post_init__(self) -> None:
        _ident(self.strategy_id, "strategy_id")
        legs = tuple(self.legs)
        if not legs or len(legs) > MAX_PLAN_LEGS:
            raise ValueError(f"a plan needs 1..{MAX_PLAN_LEGS} legs, got {len(legs)}")
        if not all(isinstance(p, PlannedLeg) for p in legs):
            raise ValueError("every plan leg must be a PlannedLeg")
        for attr in ("leg_ref", "contract"):
            values = [getattr(p, attr) for p in legs]
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {attr} in the plan: {values}")
        object.__setattr__(self, "legs", legs)

    def by_contract(self, contract: str) -> PlannedLeg | None:
        return next((p for p in self.legs if p.contract == contract), None)


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
    """The broker's current view of one order; ``reason`` is the broker's own text, shown as is (AC-6)."""

    broker_order_id: str
    contract: str
    state: OrderState
    filled_quantity: int
    reason: str | None = None

    def __post_init__(self) -> None:
        _ident(self.broker_order_id, "broker_order_id")
        _ident(self.contract, "contract")
        if not isinstance(self.state, OrderState):
            raise ValueError(f"state must be an OrderState, got {self.state!r}")
        _int(self.filled_quantity, "filled_quantity")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError(f"reason must be the broker's text or None, got {self.reason!r}")


class BrokerReader(Protocol):
    """Fresh reads from the broker (Zerodha is the authority, ADR-016). Any exception means 'could not re-read'.

    Each read returns its lines AND the tz-aware time the broker was read (W-023 fix (e)): a read with no time cannot
    be told apart from a stale one.
    """

    def fetch_positions(self, strategy_id: str) -> tuple[Sequence[BrokerPositionLine], datetime.datetime]: ...

    def fetch_order_statuses(self, strategy_id: str) -> tuple[Sequence[BrokerOrderStatus], datetime.datetime]: ...

    def fetch_available_margin(self) -> Decimal: ...


class OrderSubmitter(Protocol):
    """Sends ONE order to the broker and returns its broker order id; raises when the broker refuses it."""

    def submit(self, order: Order) -> str: ...


@dataclass(frozen=True)
class LegFailure:
    leg_ref: str
    contract: str
    broker_order_id: str
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


def _aware(value: object, name: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got {value!r}")
    return value


def _mismatches(
    plan: ExecutionPlan, positions: Sequence[BrokerPositionLine], statuses: Sequence[BrokerOrderStatus],
    book: OrderBook, read_at: datetime.datetime,
) -> list[str]:
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
    for status in statuses:
        try:
            book.reconcile_cumulative(status.broker_order_id, status.filled_quantity, read_at=read_at)
        except (FillConflictError, ValueError) as exc:
            out.append(f"order {status.broker_order_id}: {exc}")
    ledger = dict(book.positions_for(plan.strategy_id))
    broker = {line.contract: line.net_quantity for line in positions if line.net_quantity}
    if ledger != broker:
        out.append(f"confirmed fills {ledger} differ from the broker's positions {broker}")
    if book.is_submit_blocked(plan.strategy_id):
        out.append("this strategy has an unresolved reconciliation mismatch")
    return out


def assess(
    plan: ExecutionPlan, positions: Sequence[BrokerPositionLine], statuses: Sequence[BrokerOrderStatus],
    book: OrderBook, planner: MarginPlanner, *, read_at: datetime.datetime,
) -> Assessment:
    """Classify an execution from the broker's positions and order statuses, the ledger checked against both.

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

    mismatches = _mismatches(plan, positions, statuses, book, read_at)
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
    failures = tuple(
        LegFailure(plan.by_contract(s.contract).leg_ref, s.contract, s.broker_order_id, s.state,
                   s.reason if s.reason else "no reason given by the broker")
        for s in statuses if s.state in _FAILED and s.contract in missing_contracts and plan.by_contract(s.contract)
    )
    open_missing = any(s.state in _OPEN and s.contract in missing_contracts for s in statuses)

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
    )


class Preparation:
    """Orders prepared for one user choice. Nothing is sent until ``submit_confirmed``; usable once.

    A ready preparation is the strategy's ONE live preparation (held on the ``OrderBook``) until it is sent or the
    user discards it (orchestrator default OD-h).
    """

    __slots__ = ("choice", "assessment", "orders", "gate", "reason", "book", "strategy_id", "_consumed")

    def __init__(self, choice: PartialChoice, assessment: Assessment | None, orders: tuple[Order, ...],
                 gate: SafetyResult | None, reason: str, book: OrderBook | None = None,
                 strategy_id: str | None = None) -> None:
        self.choice = choice
        self.assessment = assessment
        self.orders = orders
        self.gate = gate
        self.reason = reason
        self.book = book
        self.strategy_id = strategy_id
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


_SENT_OPEN: Final = frozenset({OrderState.SUBMITTED, OrderState.PENDING, OrderState.PARTIALLY_EXECUTED})


def _in_flight(book: OrderBook, strategy_id: str) -> dict[str, int]:
    """Signed units of every order the platform SENT for this strategy that is not yet terminal and not yet filled
    (W-023 fix (b)): the broker's read may not show them yet, so they count as if they will fill."""
    out: dict[str, int] = {}
    for view in book.views_for(strategy_id):
        if view.state in _SENT_OPEN:
            open_units = view.quantity - view.filled_quantity
            out[view.contract] = out.get(view.contract, 0) + (open_units if view.side is Action.BUY else -open_units)
    return {c: u for c, u in out.items() if u}


def _refetch(plan: ExecutionPlan, reader: BrokerReader, book: OrderBook,
             planner: MarginPlanner) -> Assessment | str:
    """AC-4: re-read positions AND order status before anything is prepared; any failure prepares nothing."""
    try:
        positions, positions_at = reader.fetch_positions(plan.strategy_id)
        statuses, statuses_at = reader.fetch_order_statuses(plan.strategy_id)
        read_at = min(_aware(positions_at, "positions read_at"), _aware(statuses_at, "order status read_at"))
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
          a: Assessment) -> Preparation:
    blocked = ctx.reconciliation_blocked_strategy_ids
    if blocked is not None and book.is_submit_blocked(plan.strategy_id):
        ctx = dataclasses.replace(ctx, reconciliation_blocked_strategy_ids=blocked | {plan.strategy_id})
    result = check_pre_execution(Strategy(legs), ctx, catalogue, eligibility, strategy_id=plan.strategy_id)
    if result.blocked:
        return Preparation(choice, a, (), result, "The safety checks blocked this. No order has been prepared.")
    return Preparation(choice, a, orders, result, f"{len(orders)} order(s) ready for your confirmation.", book,
                       plan.strategy_id)


def _prepare_missing(
    choice: PartialChoice, remaining: Sequence[RemainingLeg], plan: ExecutionPlan, reader: BrokerReader,
    book: OrderBook, planner: MarginPlanner, context: ExecutionContext, catalogue: Catalogue,
    eligibility: EligibilityRegistry, a: Assessment,
) -> Preparation:
    if context.action is ExecutionAction.EXIT:
        raise ValueError("completing or retrying uses the entry/adjustment context, not an EXIT context")
    # W-023 fix (d): once Close was chosen, only a read taken after that choice may complete or retry.
    closing = book.closing_read_at(plan.strategy_id)
    if closing is not None and a.read_at <= closing:
        return _not_prepared(choice, a, NEEDS_FRESH_READ)
    book.clear_closing(plan.strategy_id, a.read_at)
    # W-023 fix (b): what is missing = target - (broker-confirmed + sent, not yet terminal). While anything is in
    # flight nothing is prepared at all (a pending order may fill, or its failure may still arrive).
    if _in_flight(book, plan.strategy_id):
        return _not_prepared(choice, a, IN_FLIGHT)
    # ADR-017 Q26: protective buys before the sells that depend on them.
    ordered = sorted(remaining, key=lambda r: 0 if r.planned.leg.action is Action.BUY else 1)
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
    """Orchestrator default OD-h: a second prepare while one waits is REFUSED (not handed the same one back), so a
    second press can never look like a second, separate set of orders."""
    if not isinstance(book, OrderBook) or not isinstance(plan, ExecutionPlan):
        raise ValueError("a preparation needs an ExecutionPlan and an OrderBook")
    return _not_prepared(choice, None, WAITING) if book.has_live_preparation(plan.strategy_id) else None


def complete_strategy(
    plan: ExecutionPlan, reader: BrokerReader, book: OrderBook, planner: MarginPlanner, context: ExecutionContext,
    catalogue: Catalogue, eligibility: EligibilityRegistry,
) -> Preparation:
    """AC-4: re-fetch, recompute the remaining strategy, re-check margin, verify the missing legs, prepare only them.

    A late fill that closes the gap makes the strategy COMPLETE and prepares nothing. Nothing is prepared while
    another preparation waits, while any sent order is in flight, or after Close on a read not newer than it.
    """
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

    Exit quantity per leg = held (broker-confirmed) - exits already sent and not yet terminal (W-023 fix (b):
    target 0 - (confirmed + in flight)). An in-flight order that would ADD to a leg prepares nothing.
    """
    choice = PartialChoice.CLOSE_PARTIAL_STRATEGY
    waiting = _live(choice, book, plan)
    if waiting is not None:
        return waiting
    a = _refetch(plan, reader, book, planner)
    if isinstance(a, str):
        return _not_prepared(choice, a)
    if a.status is not ExecutionStatus.PARTIAL_EXCEPTION:
        return _not_prepared(choice, a)
    book.mark_closing(plan.strategy_id, a.read_at)  # fix (d): Complete/Retry now need a read newer than this one
    if any(leg.ltp is None for leg in a.actual_legs):  # orchestrator default OD-e: fail closed without a price
        return _not_prepared(choice, a, "Zerodha did not give a current price for every filled leg. No order has "
                                        "been prepared.")
    in_flight = _in_flight(book, plan.strategy_id)
    flip = {Action.BUY: Action.SELL, Action.SELL: Action.BUY}
    pairs = []
    for leg in a.actual_legs:
        planned = next(p for p in plan.legs if (p.leg.instrument, p.leg.strike, p.leg.expiry)
                       == (leg.instrument, leg.strike, leg.expiry))
        held = leg.quantity if leg.action is Action.BUY else -leg.quantity
        pending = in_flight.pop(planned.contract, 0)
        if pending and (pending > 0) == (held > 0):
            return _not_prepared(choice, a, IN_FLIGHT)  # an in-flight order would add to this leg
        still_open = abs(held + pending)
        if still_open:
            pairs.append((planned, dataclasses.replace(leg, action=flip[leg.action], quantity=still_open,
                                                       entry_price=leg.ltp, ltp=None)))
    if in_flight:  # an in-flight order on a contract the strategy does not hold would open a position
        return _not_prepared(choice, a, IN_FLIGHT)
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
    return _gate(orders, legs, ctx, book, plan, catalogue, eligibility, choice, a)


@dataclass(frozen=True)
class SubmissionResult:
    """What was sent. Sending is not executing (ADR-016): completeness is only ever decided by ``assess``."""

    submitted: tuple[tuple[str, str], ...]  # (leg_ref, broker order id)
    failed: tuple[str, str] | None  # (leg_ref, the broker's text)
    not_sent: tuple[str, ...]


def submit_confirmed(
    preparation: Preparation, *, choice: PartialChoice, confirmed_by: str, submitter: OrderSubmitter,
) -> SubmissionResult:
    """Send a preparation's orders ONCE, only for the user's explicit choice (AC-6: never automatic, never retried).

    Orders go in their prepared sequence; the first refusal stops the rest (a dependent leg is never sent after its
    protective leg failed, invariant 21), and nothing is resent. A preparation can be sent only once. Each accepted
    order is registered in the OrderBook as Submitted, with its strategy, leg and version (W-023 fix (a)), so every
    later preparation counts it as in flight.
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
        try:
            broker_order_id = _ident(submitter.submit(order), "broker order id")
        except Exception as exc:  # no retry: record the broker's text and stop
            rest = tuple(o.leg_ref for o in preparation.orders[index + 1:])
            return SubmissionResult(tuple(sent), (order.leg_ref, str(exc)), rest)
        book.add(dataclasses.replace(order, broker_order_id=broker_order_id))
        book.transition(broker_order_id, OrderState.SUBMITTED)
        sent.append((order.leg_ref, broker_order_id))
    return SubmissionResult(tuple(sent), None, ())
