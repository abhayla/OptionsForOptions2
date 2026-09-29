"""REQ-039: the strategy operational state machine accepts only the owner-approved transitions (W-041).

Expected values come from the spec, never from running the code: ``SPEC_PAIRS`` below is typed from the transition
table in spec/data/domain-model.md §6 (owner-approved Q240, amended by Q243 on 2026-09-29), row by row, with "any live
state" expanded to the five live states Q243 fix 5 lists (Active, Monitoring Paused, Adjustment Proposed, Execution in
Progress, Partially Executed) and "previous live state" to the same five.

Core proof: ``test_ac1_every_from_to_pair_of_the_12_states``. For every one of the 12 states it builds a real
machine in that state (Reconciliation Required once per live state it can be entered from), fires EVERY event the
machine offers, and records which (from, to) pairs actually happened. The observed set must equal the approved table
exactly, each with its approved trigger; every other attempt must raise and leave the state and the transition log
untouched.
"""
from __future__ import annotations

import dataclasses
import datetime
import inspect
import itertools
from decimal import Decimal as D

import pytest
from work_count import assert_linear

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditLog
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution.partial import CHOICE_ORDER
from ofo.reconciliation.compare import ReconciliationError
from ofo.reconciliation.resolution import ResolutionKind
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.state_machine import (
    LIVE_STATES,
    NON_NORMAL_STATES,
    PARTIAL_CHOICES,
    TRANSITIONS,
    StateExplanation,
    StateMachineError,
    StrategyState,
    StrategyStateMachine,
    Trigger,
    allowed_triggers,
)
from ofo.strategy.versions import ExecutionResult, OutcomeKind, Position, ResultStatus, StrategyRecord, VersionError
from ofo.strategy.wording import find_banned_phrases

S = StrategyState
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
AFTER_EXPIRY = datetime.datetime(2026, 10, 28, 9, 20, tzinfo=IST)
QTY = 75
FAR = datetime.datetime(2027, 6, 1, tzinfo=IST)

GOLDEN = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D("39.50")),
))
CONDOR = StrategyDefinition.from_engine("NIFTY", GOLDEN, risk_limits={"max_loss": D("8175")})
DOUBLE = dataclasses.replace(CONDOR, legs=tuple(dataclasses.replace(leg, quantity=2 * QTY) for leg in CONDOR.legs))
PASS = lambda definition: ()  # noqa: E731 - a validator that finds nothing wrong
FAIL = lambda definition: ("max loss is above the risk limit",)  # noqa: E731

# ---- the approved table, typed from spec/data/domain-model.md §6 (Q240) -----------------------------------------
LIVE = (S.ACTIVE, S.MONITORING_PAUSED, S.ADJUSTMENT_PROPOSED, S.EXECUTION_IN_PROGRESS, S.PARTIALLY_EXECUTED)
SPEC_ROWS: dict[tuple[StrategyState, StrategyState], set[Trigger]] = {
    (S.DRAFT, S.READY_FOR_VALIDATION): {Trigger.USER_SUBMITS_FOR_VALIDATION},
    (S.READY_FOR_VALIDATION, S.VALIDATED): {Trigger.VALIDATION_PASSES},
    (S.READY_FOR_VALIDATION, S.DRAFT): {Trigger.VALIDATION_FAILS},
    (S.VALIDATED, S.EXECUTION_IN_PROGRESS): {Trigger.USER_CONFIRMS_EXECUTE},
    (S.EXECUTION_IN_PROGRESS, S.ACTIVE): {Trigger.EXECUTED_AND_RECONCILED},
    (S.EXECUTION_IN_PROGRESS, S.VALIDATED): {Trigger.NOTHING_FILLED},  # Q243 fix 1
    (S.EXECUTION_IN_PROGRESS, S.PARTIALLY_EXECUTED): {Trigger.SOME_LEGS_EXECUTED},  # Q243 fix 4
    (S.PARTIALLY_EXECUTED, S.EXECUTION_IN_PROGRESS): {Trigger.USER_COMPLETES_OR_RETRIES},
    # Q243 fix 2: "Review Manually" is not a transition; Partially Executed -> Reconciliation Required comes only
    # from the "any live state" row below.
    (S.PARTIALLY_EXECUTED, S.EXITED): {Trigger.USER_CLOSES_PARTIAL},
    (S.ACTIVE, S.ADJUSTMENT_PROPOSED): {Trigger.USER_STARTS_MODIFICATION},
    (S.ADJUSTMENT_PROPOSED, S.EXECUTION_IN_PROGRESS): {Trigger.USER_CONFIRMS_PROPOSAL},
    (S.ADJUSTMENT_PROPOSED, S.ACTIVE): {Trigger.USER_WITHDRAWS_PROPOSAL},  # Q243 fix 3
    (S.ACTIVE, S.MONITORING_PAUSED): {Trigger.USER_PAUSES_MONITORING},
    (S.MONITORING_PAUSED, S.ACTIVE): {Trigger.USER_RESUMES_MONITORING},
    (S.ACTIVE, S.EXITED): {Trigger.EXIT_ORDERS_EXECUTED},
    (S.ACTIVE, S.COMPLETED): {Trigger.ALL_LEGS_EXPIRED},
    (S.COMPLETED, S.ARCHIVED): {Trigger.USER_ARCHIVES},
    (S.EXITED, S.ARCHIVED): {Trigger.USER_ARCHIVES},
    (S.DRAFT, S.ARCHIVED): {Trigger.USER_ARCHIVES},
    (S.RECONCILIATION_REQUIRED, S.EXITED): {Trigger.MANUAL_RESOLUTION_BROKER_FLAT},
}
for _live in LIVE:
    SPEC_ROWS.setdefault((_live, S.RECONCILIATION_REQUIRED), set()).add(Trigger.BROKER_DIFFERS)
    SPEC_ROWS[(S.RECONCILIATION_REQUIRED, _live)] = {Trigger.MANUAL_RESOLUTION}
SPEC_PAIRS = frozenset(SPEC_ROWS)


# ---- building a real machine in each state ----------------------------------------------------------------------
class Ctx:
    """One strategy under test: its record, machine, audit log and a clock that only moves forward."""

    def __init__(self) -> None:
        self.now = T0
        self.refs = itertools.count(1)
        self.record = StrategyRecord(CONDOR, at=self.tick(), clock=lambda: FAR)
        self.audit = AuditLog()
        self.machine = StrategyStateMachine("s-1", self.record, audit=self.audit, clock=lambda: FAR)

    def tick(self, at_least: datetime.datetime | None = None) -> datetime.datetime:
        self.now = max(self.now + datetime.timedelta(minutes=1), at_least or self.now)
        return self.now

    def ref(self) -> str:
        return f"r{next(self.refs)}"

    def result(self, status: ResultStatus, position: Position, reasons: tuple[str, ...] = ()) -> None:
        pending = self.record.proposed_version
        number = pending.number if pending is not None else len(self.record.versions) or 1
        self.record.apply_result(ExecutionResult(number, status, position, self.tick(), self.ref(), reasons))

    def observe(self, position: Position) -> None:
        self.record.observe_broker_position(position, at=self.tick(), reference=self.ref())


def full(ctx: Ctx) -> Position:
    return ctx.record.proposed_version.intended_position


def some_legs(ctx: Ctx) -> Position:
    """The first two contracts at the proposal's intended units, the rest still at the baseline."""
    version = ctx.record.proposed_version
    intended, base = version.intended_position.as_dict(), version.baseline.as_dict()
    keys = sorted(intended.keys() | base.keys(), key=str)
    return Position.of({k: (intended.get(k, 0) if i < 2 else base.get(k, 0)) for i, k in enumerate(keys)})


def nothing(ctx: Ctx) -> Position:
    """Nothing filled: the broker still holds exactly the proposal's baseline."""
    return ctx.record.proposed_version.baseline


def overfilled(ctx: Ctx) -> Position:
    intended = full(ctx).as_dict()
    first = sorted(intended, key=str)[0]
    return Position.of({**intended, first: intended[first] * 3})


def odd(ctx: Ctx) -> Position:
    """A broker position that differs from the active version (one short leg bought back in Kite)."""
    held = ctx.record.actual_position.as_dict()
    first = sorted(held, key=str)[0]
    return Position.of({k: v for k, v in held.items() if k != first})


def to_draft() -> Ctx:
    return Ctx()


def to_ready() -> Ctx:
    ctx = to_draft()
    ctx.machine.submit_for_validation(at=ctx.tick(), actor="user-1")
    return ctx


def to_validated() -> Ctx:
    ctx = to_ready()
    ctx.machine.validate(PASS, at=ctx.tick())
    return ctx


def to_executing() -> Ctx:
    ctx = to_validated()
    ctx.machine.confirm_execute(at=ctx.tick(), actor="user-1")
    return ctx


def to_active() -> Ctx:
    ctx = to_executing()
    ctx.result(ResultStatus.COMPLETE, full(ctx))
    ctx.machine.follow_execution(at=ctx.tick())
    return ctx


def to_partial() -> Ctx:
    ctx = to_executing()
    ctx.result(ResultStatus.PARTIAL, some_legs(ctx))
    ctx.machine.follow_execution(at=ctx.tick())
    return ctx


def to_paused() -> Ctx:
    ctx = to_active()
    ctx.machine.pause_monitoring(at=ctx.tick(), actor="user-1")
    return ctx


def to_adjusting() -> Ctx:
    ctx = to_active()
    ctx.machine.start_adjustment(at=ctx.tick(), actor="user-1")
    return ctx


def to_completed() -> Ctx:
    ctx = to_active()
    ctx.machine.complete_at_expiry(at=ctx.tick(AFTER_EXPIRY))
    return ctx


def to_exited() -> Ctx:
    ctx = to_active()
    ctx.observe(Position())
    ctx.machine.confirm_exit(at=ctx.tick(), actor="user-1", reason="exit orders executed")
    return ctx


def to_archived() -> Ctx:
    ctx = to_exited()
    ctx.machine.archive(at=ctx.tick(), actor="user-1")
    return ctx


def to_reconciliation(previous: StrategyState) -> Ctx:
    """Reconciliation Required, entered from ``previous`` through the broker's real disagreement."""
    ctx = BUILD[previous]()
    if previous in (S.EXECUTION_IN_PROGRESS, S.PARTIALLY_EXECUTED):
        ctx.result(ResultStatus.COMPLETE, overfilled(ctx))  # the broker holds more than was asked
    else:
        ctx.observe(odd(ctx))
    if previous is S.EXECUTION_IN_PROGRESS:
        ctx.machine.follow_execution(at=ctx.tick())
    else:
        ctx.machine.sync_broker(at=ctx.tick())
    assert ctx.machine.state is S.RECONCILIATION_REQUIRED
    return ctx


BUILD = {
    S.DRAFT: to_draft,
    S.READY_FOR_VALIDATION: to_ready,
    S.VALIDATED: to_validated,
    S.EXECUTION_IN_PROGRESS: to_executing,
    S.ACTIVE: to_active,
    S.PARTIALLY_EXECUTED: to_partial,
    S.MONITORING_PAUSED: to_paused,
    S.ADJUSTMENT_PROPOSED: to_adjusting,
    S.COMPLETED: to_completed,
    S.EXITED: to_exited,
    S.ARCHIVED: to_archived,
}
FIXTURES = [(state.value, BUILD[state]) for state in BUILD] + [
    (f"Reconciliation Required (from {prev.value})", (lambda p=prev: to_reconciliation(p))) for prev in LIVE
]


# ---- every event the machine offers, each with the record facts that would make it succeed ----------------------
def _try(action) -> None:
    """Best-effort record set-up: the record's own refusal is fine, the machine's reaction is what is tested."""
    try:
        action()
    except (VersionError, ReconciliationError):
        pass


def ev_fill(status: ResultStatus, position_of):
    def run(ctx: Ctx) -> None:
        if ctx.record.proposed_version is not None:
            _try(lambda: ctx.result(status, position_of(ctx)))
        ctx.machine.follow_execution(at=ctx.tick())
    return run


def ev_confirm_adjustment(ctx: Ctx) -> None:
    def propose() -> None:
        version = ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=ctx.record.active_version.number)
        ctx.record.confirm(version.number, at=ctx.tick())
    if ctx.record.active_version is not None:
        _try(propose)
    ctx.machine.confirm_adjustment(at=ctx.tick(), actor="user-1")


def ev_withdraw_proposal(ctx: Ctx) -> None:
    """The user made a proposed version (not confirmed) and withdraws it."""
    if ctx.record.active_version is not None:
        _try(lambda: ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=ctx.record.active_version.number))
    ctx.machine.withdraw_adjustment(at=ctx.tick(), actor="user-1")


def ev_close_partial(ctx: Ctx) -> None:
    if ctx.record.proposed_version is not None:  # the closing orders executed: the broker is flat again
        _try(lambda: ctx.result(ResultStatus.REJECTED, Position()))
    ctx.machine.close_partial(at=ctx.tick(), actor="user-1")


def ev_resolve_adopt(ctx: Ctx) -> None:
    _try(lambda: ctx.record.reconcile(at=ctx.tick(), actor="user-1", resolution="adopt the broker position"))
    ctx.machine.resolve_reconciliation(at=ctx.tick())


def ev_resolve_flat(ctx: Ctx) -> None:
    _try(lambda: ctx.observe(Position()))
    _try(lambda: ctx.record.mark_exited(at=ctx.tick(), actor="user-1", resolution="broker flat"))
    ctx.machine.resolve_reconciliation(at=ctx.tick())


def ev_exit(ctx: Ctx) -> None:
    _try(lambda: ctx.observe(Position()))
    ctx.machine.confirm_exit(at=ctx.tick(), actor="user-1", reason="exit orders executed")


def ev_broker_differs(ctx: Ctx) -> None:
    """A reconciliation run (or, with a proposal in flight, a broker result outside the plan) shows a difference."""
    if ctx.record.proposed_version is not None:
        _try(lambda: ctx.result(ResultStatus.COMPLETE, overfilled(ctx)))
    elif ctx.record.actual_position.lines:
        _try(lambda: ctx.observe(odd(ctx)))
    ctx.machine.sync_broker(at=ctx.tick())


EVENTS = {
    "submit": lambda ctx: ctx.machine.submit_for_validation(at=ctx.tick(), actor="user-1"),
    "validate_pass": lambda ctx: ctx.machine.validate(PASS, at=ctx.tick()),
    "validate_fail": lambda ctx: ctx.machine.validate(FAIL, at=ctx.tick()),
    "execute": lambda ctx: ctx.machine.confirm_execute(at=ctx.tick(), actor="user-1"),
    "fill_complete": ev_fill(ResultStatus.COMPLETE, full),
    "fill_partial": ev_fill(ResultStatus.PARTIAL, some_legs),
    "fill_mismatch": ev_fill(ResultStatus.COMPLETE, overfilled),
    "fill_rejected_nothing": ev_fill(ResultStatus.REJECTED, nothing),
    "fill_failed_some": ev_fill(ResultStatus.FAILED, some_legs),
    "broker_differs": ev_broker_differs,
    "partial_complete_or_retry": lambda ctx: ctx.machine.continue_execution(at=ctx.tick(), actor="user-1"),
    "partial_review": lambda ctx: ctx.machine.review_partial(),
    "partial_close": ev_close_partial,
    "start_adjustment": lambda ctx: ctx.machine.start_adjustment(at=ctx.tick(), actor="user-1"),
    "confirm_adjustment": ev_confirm_adjustment,
    "withdraw_adjustment": lambda ctx: ctx.machine.withdraw_adjustment(at=ctx.tick(), actor="user-1"),
    "withdraw_proposal": ev_withdraw_proposal,
    "pause": lambda ctx: ctx.machine.pause_monitoring(at=ctx.tick(), actor="user-1"),
    "resume": lambda ctx: ctx.machine.resume_monitoring(at=ctx.tick(), actor="user-1"),
    "resolve_adopt": ev_resolve_adopt,
    "resolve_flat": ev_resolve_flat,
    "exit": ev_exit,
    "expire": lambda ctx: ctx.machine.complete_at_expiry(at=ctx.tick(AFTER_EXPIRY)),
    "archive": lambda ctx: ctx.machine.archive(at=ctx.tick(), actor="user-1"),
}


def test_ac1_the_approved_table_is_exactly_the_spec_rows_for_all_144_pairs():
    """AC-1: the 12 states are exactly REQ-039's list; of all 144 (from, to) pairs only the Q240 rows are allowed."""
    ac1 = ("Draft, Ready for Validation, Validated, Active, Monitoring Paused, Adjustment Proposed, Execution in "
           "Progress, Partially Executed, Reconciliation Required, Completed, Exited, Archived")
    assert [s.value for s in StrategyState] == ac1.split(", ")
    assert set(LIVE_STATES) == set(LIVE)
    pairs = list(itertools.product(StrategyState, repeat=2))
    assert len(pairs) == 144
    for pair in pairs:
        assert set(allowed_triggers(*pair)) == SPEC_ROWS.get(pair, set()), pair
    assert {pair: set(triggers) for pair, triggers in TRANSITIONS.items()} == SPEC_ROWS
    assert len(SPEC_PAIRS) == 30


def test_ac1_every_from_to_pair_of_the_12_states():
    """AC-1 (core proof): fire every event in every state; exactly the approved (from, to) pairs happen, each with
    its approved trigger, and every other attempt raises and changes nothing."""
    observed: dict[tuple[StrategyState, StrategyState], set[Trigger]] = {}
    for (label, build), (event, fire) in itertools.product(FIXTURES, EVENTS.items()):
        ctx = build()
        before_state, before_log = ctx.machine.state, ctx.machine.transitions
        try:
            fire(ctx)
        except (StateMachineError, VersionError, ReconciliationError):
            assert ctx.machine.state is before_state, (label, event)
            assert ctx.machine.transitions == before_log, (label, event)
            continue
        added = ctx.machine.transitions[len(before_log):]
        if not added:
            assert ctx.machine.state is before_state, (label, event)
            continue
        for step in added:
            pair = (step.from_state, step.to_state)
            assert pair in SPEC_PAIRS, f"{label} + {event} made the unapproved move {pair}"
            assert step.trigger in SPEC_ROWS[pair], (label, event, step.trigger)
            observed.setdefault(pair, set()).add(step.trigger)
    assert set(observed) == SPEC_PAIRS, f"approved pairs never reached: {sorted(SPEC_PAIRS - set(observed), key=str)}"
    assert observed == SPEC_ROWS


def test_ac1_reconciliation_required_returns_only_to_the_state_it_came_from():
    """AC-1: "Reconciliation Required -> previous live state" -- never to another live state."""
    for previous in LIVE:
        ctx = to_reconciliation(previous)
        ev_resolve_adopt(ctx)
        assert ctx.machine.state is previous
        assert ctx.machine.transitions[-1].trigger is Trigger.MANUAL_RESOLUTION


def test_ac1_an_agreeing_run_or_no_resolution_never_leaves_reconciliation_required():
    """AC-1 (Q222, Q240): only a recorded manual resolution leaves Reconciliation Required."""
    ctx = to_reconciliation(S.ACTIVE)
    active_position = ctx.record.active_version.intended_position
    with pytest.raises(StateMachineError, match="manual resolution"):
        ctx.machine.resolve_reconciliation(at=ctx.tick())
    ctx.observe(active_position)  # a later run finds the broker agreeing again
    assert ctx.record.reconciliation_required  # W-021: agreement never clears the record's flag
    with pytest.raises(StateMachineError, match="manual resolution"):
        ctx.machine.resolve_reconciliation(at=ctx.tick())
    assert ctx.machine.sync_broker(at=ctx.tick()) is None
    assert ctx.machine.state is S.RECONCILIATION_REQUIRED


def test_ac1_a_resolution_recorded_before_the_mismatch_does_not_count():
    """AC-1 (Q222): the machine reads the resolution itself and it must postdate the difference that put the strategy
    into Reconciliation Required; no method takes a "resolved" flag, so an old resolution cannot be replayed."""
    ctx = to_active()
    ctx.observe(odd(ctx))
    ctx.record.reconcile(at=ctx.tick(), actor="user-1", resolution="adopt")  # resolved before the machine looked
    assert ctx.record.outcomes[-1].kind is OutcomeKind.RECONCILED
    ctx.observe(odd(ctx))  # a NEW difference from the adopted version
    ctx.machine.sync_broker(at=ctx.tick())
    assert ctx.machine.state is S.RECONCILIATION_REQUIRED and ctx.record.reconciliation_required
    with pytest.raises(StateMachineError, match="manual resolution"):
        ctx.machine.resolve_reconciliation(at=ctx.tick())
    for name in ("resolve_reconciliation", "sync_broker", "follow_execution"):
        params = inspect.signature(getattr(StrategyStateMachine, name)).parameters
        assert set(params) == {"self", "at"}, name  # nothing but the time: the verdict is read, never passed


def test_ac1_monitoring_paused_is_entered_and_left_only_by_the_user():
    """AC-1 (Q240, REQ-043 AC-4): Active <-> Monitoring Paused only on the user's pause/resume; a broker sync with
    nothing to reconcile (a lost feed or expired session is not a broker difference) leaves Active alone."""
    assert allowed_triggers(S.ACTIVE, S.MONITORING_PAUSED) == frozenset({Trigger.USER_PAUSES_MONITORING})
    assert allowed_triggers(S.MONITORING_PAUSED, S.ACTIVE) == frozenset({Trigger.USER_RESUMES_MONITORING})
    ctx = to_active()
    assert ctx.machine.sync_broker(at=ctx.tick()) is None
    assert ctx.machine.state is S.ACTIVE
    with pytest.raises(StateMachineError, match="actor"):
        ctx.machine.pause_monitoring(at=ctx.tick(), actor="")
    ctx.machine.pause_monitoring(at=ctx.tick(), actor="user-1")
    assert ctx.machine.transitions[-1].actor == "user-1"
    with pytest.raises(StateMachineError):
        ctx.machine.pause_monitoring(at=ctx.tick(), actor="user-1")  # already paused
    ctx.machine.resume_monitoring(at=ctx.tick(), actor="user-1")
    assert ctx.machine.state is S.ACTIVE


def test_ac1_guards_read_the_record_not_the_caller():
    """AC-1: each guarded move reads the owning StrategyRecord (finding caller-supplied-verdict-trusted)."""
    # Execute refuses when the draft changed after validation.
    ctx = to_validated()
    ctx.record.edit(DOUBLE, at=ctx.tick())
    with pytest.raises(StateMachineError, match="changed after validation"):
        ctx.machine.confirm_execute(at=ctx.tick(), actor="user-1")
    # Active only after the record activated the executing version; nothing new leaves the state as is.
    ctx = to_executing()
    assert ctx.machine.follow_execution(at=ctx.tick()) is None
    assert ctx.machine.state is S.EXECUTION_IN_PROGRESS
    # A partial result with nothing filled is not "some legs executed".
    ctx.result(ResultStatus.PARTIAL, Position())
    assert ctx.machine.follow_execution(at=ctx.tick()) is None
    # Exit only when the broker is flat.
    ctx = to_active()
    with pytest.raises(VersionError, match="still holds"):
        ctx.machine.confirm_exit(at=ctx.tick(), actor="user-1", reason="exit")
    # Completed only after every leg's expiry has passed (IST date).
    with pytest.raises(StateMachineError, match="expir"):
        ctx.machine.complete_at_expiry(at=ctx.tick(datetime.datetime(2026, 10, 27, 15, 45, tzinfo=IST)))
    # A user move on a live state while the record says the broker differs is refused, not silently allowed.
    ctx = to_active()
    ctx.observe(odd(ctx))
    with pytest.raises(StateMachineError, match="reconciliation"):
        ctx.machine.pause_monitoring(at=ctx.tick(), actor="user-1")
    with pytest.raises(StateMachineError, match="reconciliation"):
        ctx.machine.start_adjustment(at=ctx.tick(), actor="user-1")
    # Withdrawing a proposal the user already confirmed (orders may be out) is refused by the record itself.
    ctx = to_adjusting()
    version = ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1)
    ctx.record.confirm(version.number, at=ctx.tick())
    with pytest.raises(VersionError, match="confirmed"):
        ctx.machine.withdraw_adjustment(at=ctx.tick(), actor="user-1")
    assert ctx.machine.state is S.ADJUSTMENT_PROPOSED and ctx.record.proposed_version is version
    # Confirming an adjustment needs a confirmed proposal created after the adjustment started.
    ctx = to_adjusting()
    with pytest.raises(StateMachineError, match="proposal"):
        ctx.machine.confirm_adjustment(at=ctx.tick(), actor="user-1")
    ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1)
    with pytest.raises(StateMachineError, match="confirmed"):
        ctx.machine.confirm_adjustment(at=ctx.tick(), actor="user-1")
    # Complete/Retry needs the executing version still pending and confirmed.
    ctx = to_partial()
    ctx.result(ResultStatus.REJECTED, Position())
    with pytest.raises(StateMachineError, match="pending"):
        ctx.machine.continue_execution(at=ctx.tick(), actor="user-1")


def test_ac1_after_adopting_during_execution_the_strategy_becomes_active_only_through_the_table():
    """AC-1: a mismatch during execution -> Reconciliation Required -> (adopt) Execution in Progress -> Active,
    each step an approved row; the adopted version is what the broker holds, reconciled."""
    ctx = to_reconciliation(S.EXECUTION_IN_PROGRESS)
    ev_resolve_adopt(ctx)
    assert ctx.machine.state is S.EXECUTION_IN_PROGRESS
    ctx.machine.follow_execution(at=ctx.tick())
    assert ctx.machine.state is S.ACTIVE
    assert [(t.from_state, t.to_state) for t in ctx.machine.transitions[-3:]] == [
        (S.EXECUTION_IN_PROGRESS, S.RECONCILIATION_REQUIRED),
        (S.RECONCILIATION_REQUIRED, S.EXECUTION_IN_PROGRESS),
        (S.EXECUTION_IN_PROGRESS, S.ACTIVE),
    ]


def test_ac2_every_state_change_is_an_explicit_recorded_and_audited_transition():
    """AC-2: each change is a recorded transition (from, to, trigger, actor, time, detail) with one hash-chained
    STRATEGY_CHANGED audit event; the state is the last transition's target, never inferred from order rows."""
    ctx = to_exited()
    moves = [(t.from_state, t.to_state, t.trigger) for t in ctx.machine.transitions]
    assert moves == [
        (S.DRAFT, S.READY_FOR_VALIDATION, Trigger.USER_SUBMITS_FOR_VALIDATION),
        (S.READY_FOR_VALIDATION, S.VALIDATED, Trigger.VALIDATION_PASSES),
        (S.VALIDATED, S.EXECUTION_IN_PROGRESS, Trigger.USER_CONFIRMS_EXECUTE),
        (S.EXECUTION_IN_PROGRESS, S.ACTIVE, Trigger.EXECUTED_AND_RECONCILED),
        (S.ACTIVE, S.EXITED, Trigger.EXIT_ORDERS_EXECUTED),
    ]
    assert [t.seq for t in ctx.machine.transitions] == [0, 1, 2, 3, 4]
    assert [t.actor for t in ctx.machine.transitions] == ["user-1", "system", "user-1", "system", "user-1"]
    assert ctx.machine.state is ctx.machine.transitions[-1].to_state is S.EXITED
    events = ctx.audit.events
    assert [e.event_type for e in events] == [EventType.STRATEGY_CHANGED] * 5
    assert [(e.payload["from"], e.payload["to"], e.payload["trigger"]) for e in events] == [
        (a.value, b.value, c.value) for a, b, c in moves]
    assert {e.correlation_id for e in events} == {"state:s-1"}
    assert ctx.audit.verify().ok
    # validation failure reasons are kept on the transition.
    ctx = to_ready()
    ctx.machine.validate(FAIL, at=ctx.tick())
    assert ctx.machine.transitions[-1].detail == (("reasons", "max loss is above the risk limit"),)


def test_ac2_state_cannot_be_set_or_inferred_from_rows():
    """AC-2: no raw state change; a machine is never built on a record that already traded (its state would have to
    be guessed from its rows)."""
    ctx = to_active()
    with pytest.raises(AttributeError):
        ctx.machine.state = S.EXITED  # type: ignore[misc]
    with pytest.raises(AttributeError):
        ctx.machine._transitions = []  # type: ignore[attr-defined]
    with pytest.raises(StateMachineError, match="already"):
        StrategyStateMachine("s-2", ctx.record, clock=lambda: FAR)
    with pytest.raises(StateMachineError, match="StrategyRecord"):
        StrategyStateMachine("s-2", object(), clock=lambda: FAR)  # type: ignore[arg-type]
    with pytest.raises(StateMachineError, match="strategy id"):
        StrategyStateMachine("", StrategyRecord(CONDOR, at=T0, clock=lambda: FAR), clock=lambda: FAR)
    assert isinstance(ctx.machine.transitions, tuple)


@pytest.mark.parametrize("bad_at, message", [
    (datetime.datetime(2026, 10, 1, 12, 0), "timezone-aware"),
    (datetime.datetime(2026, 9, 1, 12, 0, tzinfo=IST), "before"),
    (datetime.datetime(2028, 1, 1, tzinfo=IST), "future"),
])
def test_ac2_transition_times_are_aware_chronological_and_not_in_the_future(bad_at, message):
    """AC-2: a transition time is timezone-aware, not before the last one, and not ahead of the clock."""
    ctx = to_draft()
    ctx.machine.submit_for_validation(at=ctx.tick(), actor="user-1")
    with pytest.raises(StateMachineError, match=message):
        ctx.machine.validate(PASS, at=bad_at)
    assert ctx.machine.state is S.READY_FOR_VALIDATION


@pytest.mark.parametrize("reasons", [("",), (5,), tuple(f"r{i}" for i in range(51)), "not a tuple", None])
def test_ac2_validator_output_is_checked_not_trusted(reasons):
    """AC-2: a validator's reasons must be a sequence of non-empty strings of bounded size (fail closed)."""
    ctx = to_ready()
    with pytest.raises(StateMachineError, match="reasons"):
        ctx.machine.validate(lambda d: reasons, at=ctx.tick())
    assert ctx.machine.state is S.READY_FOR_VALIDATION


def test_ac2_validation_runs_on_the_records_own_draft():
    """AC-2: the machine hands its record's draft to the validator; it never takes a definition from the caller."""
    ctx = to_ready()
    seen = []
    ctx.machine.validate(lambda d: seen.append(d) or (), at=ctx.tick())
    assert seen == [ctx.record.definition]


def test_ac2_one_by_one_transitions_stay_linear():
    """AC-2: appending transitions one at a time does not re-check the whole log each time."""
    def make(n: int):
        ctx = to_active()

        def run() -> None:
            for _ in range(n):
                ctx.machine.pause_monitoring(at=ctx.tick(), actor="user-1")
                ctx.machine.resume_monitoring(at=ctx.tick(), actor="user-1")
        return run
    assert_linear(make, 250)


EXPECTED_EXPLANATIONS = {
    S.EXECUTION_IN_PROGRESS: (
        "Orders for version 1 were sent to Zerodha. Waiting for Zerodha to confirm every leg.",
        ("new execution", "modification", "exit", "archive"),
        "Wait for Zerodha to confirm the orders. Nothing is retried automatically.",
    ),
    S.PARTIALLY_EXECUTED: (
        "Some legs of version 1 executed and others did not.",
        ("new execution", "modification", "archive"),
        "Choose one: Complete Strategy, Retry Failed Leg, Review Manually, Close Partial Strategy.",
    ),
    S.RECONCILIATION_REQUIRED: (
        "Zerodha's position differs from this strategy's (1 contract differs).",
        ("new execution", "adjustment execution", "exit orders", "modification", "archive"),
        "Reconcile: adopt actual broker position, close/reconcile through a prepared order, or mark as requiring "
        "attention. If Zerodha shows no position, the strategy can be marked exited.",
    ),
    S.MONITORING_PAUSED: (
        "Monitoring of this strategy was paused by user-1.",
        ("rule alerts", "rule-triggered order preparation"),
        "Resume monitoring to receive alerts again.",
    ),
    S.ADJUSTMENT_PROPOSED: (
        "A modification of version 1 was started by user-1.",
        ("new execution", "a second modification"),
        "Confirm or withdraw the proposal.",
    ),
}


def test_ac3_every_non_normal_state_says_what_happened_when_what_is_blocked_and_next():
    """AC-3 (Q201): each non-normal state gives what happened, when (the transition time), what is blocked and the
    next action; the reconciliation choices are W-021's own ResolutionKind words and the partial choices W-023's
    CHOICE_ORDER; normal states have no exception to explain."""
    assert set(NON_NORMAL_STATES) == set(EXPECTED_EXPLANATIONS)
    builds = {**BUILD, S.RECONCILIATION_REQUIRED: lambda: to_reconciliation(S.ACTIVE)}
    for state, (happened, blocked, next_action) in EXPECTED_EXPLANATIONS.items():
        ctx = builds[state]()
        explanation = ctx.machine.explain()
        assert explanation == StateExplanation(state, happened, ctx.machine.transitions[-1].at, blocked, next_action)
        text = " ".join((explanation.what_happened, explanation.next_action, *explanation.blocked))
        assert find_banned_phrases(text) == [], state
        assert "went wrong" not in text.lower()
    assert PARTIAL_CHOICES == tuple(c.value for c in CHOICE_ORDER)  # W-023's words, in its order
    assert ", ".join(c.value for c in CHOICE_ORDER) in EXPECTED_EXPLANATIONS[S.PARTIALLY_EXECUTED][2]
    for kind in (ResolutionKind.ADOPT_BROKER_POSITION, ResolutionKind.PREPARE_CLOSING_ORDER,
                 ResolutionKind.MARK_REQUIRES_ATTENTION):
        assert kind.value in EXPECTED_EXPLANATIONS[S.RECONCILIATION_REQUIRED][2]
    for state in set(StrategyState) - set(NON_NORMAL_STATES):
        if state in BUILD:
            assert BUILD[state]().machine.explain() is None, state


def test_ac1_each_guard_refuses_on_the_records_facts():
    """AC-1: the remaining guards, one refusal each, every fact read from the record or the machine's own log."""
    with pytest.raises(StateMachineError, match="AuditLog"):
        StrategyStateMachine("s-2", StrategyRecord(CONDOR, at=T0, clock=lambda: FAR), audit=[], clock=lambda: FAR)
    ctx = to_active()
    with pytest.raises(StateMachineError, match="no execution is in progress"):
        ctx.machine.follow_execution(at=ctx.tick())
    with pytest.raises(StateMachineError, match="no reconciliation is required"):
        ctx.machine.resolve_reconciliation(at=ctx.tick())
    with pytest.raises(StateMachineError, match="reason"):
        ctx.machine.confirm_exit(at=ctx.tick(), actor="user-1", reason="")
    # A proposal already pending (made outside the machine) must get its result before a modification starts.
    ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1)
    with pytest.raises(StateMachineError, match="already pending"):
        ctx.machine.start_adjustment(at=ctx.tick(), actor="user-1")
    # A fully rejected ADJUSTMENT (nothing filled, a position still held) has no approved row: the Q243 fix 1 row
    # returns an un-executed strategy to Validated, which a strategy holding a position is not. Refused loudly.
    ctx = to_adjusting()
    ev_confirm_adjustment(ctx)
    ctx.result(ResultStatus.REJECTED, ctx.record.active_version.intended_position)
    with pytest.raises(StateMachineError, match="no approved row"):
        ctx.machine.follow_execution(at=ctx.tick())
    assert ctx.machine.state is S.EXECUTION_IN_PROGRESS
    # Closing needs the record to exit: with a proposal still pending (orders may be working) it refuses.
    ctx = to_partial()
    with pytest.raises(VersionError, match="awaiting"):
        ctx.machine.close_partial(at=ctx.tick(), actor="user-1")
    # Withdraw, resume and expiry refuse while the record says the broker differs.
    ctx = to_adjusting()
    ctx.observe(odd(ctx))
    with pytest.raises(StateMachineError, match="reconciliation"):
        ctx.machine.withdraw_adjustment(at=ctx.tick(), actor="user-1")
    ctx = to_paused()
    ctx.observe(odd(ctx))
    with pytest.raises(StateMachineError, match="reconciliation"):
        ctx.machine.resume_monitoring(at=ctx.tick(), actor="user-1")
    ctx = to_active()
    ctx.observe(odd(ctx))
    with pytest.raises(StateMachineError, match="reconciliation"):
        ctx.machine.complete_at_expiry(at=ctx.tick(AFTER_EXPIRY))
    # A completed strategy is not live: a later broker difference does not pull it into Reconciliation Required.
    ctx = to_completed()
    ctx.observe(odd(ctx))
    assert ctx.machine.sync_broker(at=ctx.tick()) is None
    assert ctx.machine.state is S.COMPLETED
    # An adoption followed by a NEW difference (the flag set again) does not unblock.
    ctx = to_reconciliation(S.ACTIVE)
    ctx.record.reconcile(at=ctx.tick(), actor="user-1", resolution="adopt")
    ctx.observe(odd(ctx))
    with pytest.raises(StateMachineError, match="manual resolution"):
        ctx.machine.resolve_reconciliation(at=ctx.tick())


def test_ac2_the_transition_log_is_capped(monkeypatch):
    """AC-2: absurd sizes are refused; the log has a hard cap (lowered here to 2 so the test is quick)."""
    import ofo.strategy.state_machine as module
    monkeypatch.setattr(module, "MAX_TRANSITIONS", 2)
    ctx = to_validated()
    with pytest.raises(StateMachineError, match="full"):
        ctx.machine.confirm_execute(at=ctx.tick(), actor="user-1")
    assert ctx.machine.state is S.VALIDATED and ctx.record.proposed_version is None


# ---- Q243 (owner, 2026-09-29): five fixes to the §6 table ------------------------------------------------------
REASONS = ("RMS:Margin Exceeds, Required:95000.00, Available:40000.00", "Order rejected: strike not tradable")


def test_ac1_q243_fix1_nothing_filled_and_every_order_rejected_returns_to_validated_with_the_reasons():
    """AC-1 (Q243 fix 1): no leg filled and every order finally rejected/failed -> Validated, the rejection reasons
    shown; the user may execute again. The machine reads the record's own result, never a caller flag."""
    ctx = to_executing()
    ctx.result(ResultStatus.REJECTED, Position(), REASONS)
    step = ctx.machine.follow_execution(at=ctx.tick())
    assert ctx.machine.state is S.VALIDATED
    assert (step.from_state, step.to_state, step.trigger) == (S.EXECUTION_IN_PROGRESS, S.VALIDATED,
                                                             Trigger.NOTHING_FILLED)
    assert step.detail == (("version", "1"), ("reasons", "; ".join(REASONS)))
    assert ctx.audit.events[-1].payload["to"] == "Validated"
    assert ctx.machine.explain() == StateExplanation(
        S.VALIDATED,
        f"Zerodha rejected every order of version 1 and nothing was filled. Reasons: {REASONS[0]}; {REASONS[1]}.",
        step.at, (), "Execute again, or edit the strategy.")
    # Execute again: a new proposed version, back to Execution in Progress through the approved row.
    ctx.machine.confirm_execute(at=ctx.tick(), actor="user-1")
    assert ctx.machine.state is S.EXECUTION_IN_PROGRESS
    assert ctx.machine.transitions[-1].detail == (("version", "2"),)
    # A FAILED result with no broker text says so instead of inventing a reason.
    ctx.result(ResultStatus.FAILED, Position())
    assert ctx.machine.follow_execution(at=ctx.tick()).detail == (("version", "2"),
                                                                  ("reasons", "Zerodha gave no reason"))
    assert ctx.machine.state is S.VALIDATED


def test_ac1_q243_fix1_only_when_nothing_filled_and_the_result_is_final():
    """AC-1 (Q243 fix 1, negatives): a rejection with some legs filled is Partially Executed, not Validated; a
    non-final (PARTIAL) result with nothing filled changes nothing yet."""
    ctx = to_executing()
    ctx.result(ResultStatus.REJECTED, some_legs(ctx), REASONS)
    assert ctx.machine.follow_execution(at=ctx.tick()).to_state is S.PARTIALLY_EXECUTED
    ctx = to_executing()
    ctx.result(ResultStatus.PARTIAL, Position())
    assert ctx.machine.follow_execution(at=ctx.tick()) is None
    assert ctx.machine.state is S.EXECUTION_IN_PROGRESS


@pytest.mark.parametrize("status", [ResultStatus.REJECTED, ResultStatus.FAILED])
def test_ac1_q243_fix4_a_final_failure_with_some_legs_filled_is_partially_executed(status):
    """AC-1 (Q243 fix 4): some legs executed, the rest finally failed/rejected -> Partially Executed, even though the
    platform's intended legs differ from the fills; the proposal stays open for Complete/Retry; no reconciliation."""
    ctx = to_executing()
    ctx.result(status, some_legs(ctx))
    assert ctx.record.proposed_version.number == 1 and ctx.record.proposal_confirmed
    assert not ctx.record.reconciliation_required
    step = ctx.machine.follow_execution(at=ctx.tick())
    assert (step.to_state, step.trigger) == (S.PARTIALLY_EXECUTED, Trigger.SOME_LEGS_EXECUTED)
    ctx.machine.continue_execution(at=ctx.tick(), actor="user-1")  # Complete Strategy: the missing legs go out
    ctx.result(ResultStatus.COMPLETE, full(ctx))
    assert ctx.machine.follow_execution(at=ctx.tick()).to_state is S.ACTIVE


def test_ac1_q243_fix4_reconciliation_required_only_when_the_broker_differs_from_the_fills():
    """AC-1 (Q243 fix 4): a broker position the fills cannot explain (outside baseline..intended) is Reconciliation
    Required, during execution and after a partial."""
    ctx = to_executing()
    ctx.result(ResultStatus.REJECTED, overfilled(ctx))
    assert ctx.record.reconciliation_required
    assert ctx.machine.follow_execution(at=ctx.tick()).to_state is S.RECONCILIATION_REQUIRED
    ctx = to_partial()
    ctx.result(ResultStatus.REJECTED, overfilled(ctx))
    step = ctx.machine.sync_broker(at=ctx.tick())
    assert (step.from_state, step.to_state, step.trigger) == (S.PARTIALLY_EXECUTED, S.RECONCILIATION_REQUIRED,
                                                             Trigger.BROKER_DIFFERS)


def test_ac1_q243_fix2_review_manually_is_a_view_not_a_transition():
    """AC-1 (Q243 fix 2): "Review Manually" keeps Partially Executed and opens the review; nothing is recorded."""
    assert allowed_triggers(S.PARTIALLY_EXECUTED, S.RECONCILIATION_REQUIRED) == frozenset({Trigger.BROKER_DIFFERS})
    assert "USER_REVIEWS" not in Trigger.__members__
    ctx = to_partial()
    log, events = ctx.machine.transitions, ctx.audit.events
    assert ctx.machine.review_partial() == ctx.machine.explain()
    assert ctx.machine.state is S.PARTIALLY_EXECUTED
    assert ctx.machine.transitions == log and ctx.audit.events == events
    with pytest.raises(StateMachineError, match="Partially Executed"):
        to_active().machine.review_partial()


def test_ac1_q243_fix3_withdrawing_an_unconfirmed_proposal_is_recorded_in_the_version_history():
    """AC-1 (Q243 fix 3): Adjustment Proposed -> Active when the user withdraws the proposal; the withdrawal is a
    WITHDRAWN entry in the record's history; the version itself is kept and the active version is unchanged."""
    ctx = to_adjusting()
    proposal = ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1)
    step = ctx.machine.withdraw_adjustment(at=ctx.tick(), actor="user-1")
    assert (step.from_state, step.to_state, step.trigger) == (S.ADJUSTMENT_PROPOSED, S.ACTIVE,
                                                             Trigger.USER_WITHDRAWS_PROPOSAL)
    assert step.detail == (("version", "2"),)
    withdrawn = ctx.record.outcomes[-1]
    assert (withdrawn.version_number, withdrawn.kind, withdrawn.actor, withdrawn.at, withdrawn.reference) == (
        2, OutcomeKind.WITHDRAWN, "user-1", step.at, "withdrawn:v2")
    assert withdrawn.intended == proposal.intended_position
    assert ctx.record.proposed_version is None and ctx.record.active_version.number == 1
    assert ctx.record.versions[-1] is proposal and not ctx.record.reconciliation_required
    assert ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1).number == 3  # the strategy can be modified again
    # With no proposal made yet there is nothing in the version history to withdraw; the state change is recorded.
    ctx = to_adjusting()
    count = len(ctx.record.outcomes)
    assert ctx.machine.withdraw_adjustment(at=ctx.tick(), actor="user-1").detail == ()
    assert len(ctx.record.outcomes) == count


def test_ac1_q243_fix3_a_confirmed_or_executing_proposal_cannot_be_withdrawn():
    """AC-1 (Q243 fix 3): only an UNCONFIRMED proposal can be withdrawn; every other withdrawal is refused by the
    record and changes nothing."""
    ctx = to_active()
    with pytest.raises(VersionError, match="no proposed version"):
        ctx.record.withdraw(2, at=ctx.tick(), actor="user-1")
    proposal = ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1)
    with pytest.raises(VersionError, match="not the pending"):
        ctx.record.withdraw(1, at=ctx.tick(), actor="user-1")
    with pytest.raises(VersionError, match="actor"):
        ctx.record.withdraw(2, at=ctx.tick(), actor="")
    with pytest.raises(VersionError, match="before"):
        ctx.record.withdraw(2, at=T0, actor="user-1")
    ctx.record.confirm(proposal.number, at=ctx.tick())
    with pytest.raises(VersionError, match="confirmed"):
        ctx.record.withdraw(2, at=ctx.tick(), actor="user-1")
    ctx.result(ResultStatus.PARTIAL, some_legs(ctx))  # executing: some legs already at the broker
    with pytest.raises(VersionError, match="confirmed"):
        ctx.record.withdraw(2, at=ctx.tick(), actor="user-1")
    assert ctx.record.proposed_version is proposal
    assert OutcomeKind.WITHDRAWN not in {o.kind for o in ctx.record.outcomes}
    ctx = to_exited()
    with pytest.raises(VersionError, match="exited"):
        ctx.record.withdraw(1, at=ctx.tick(), actor="user-1")


def test_ac1_q243_fix3_the_withdrawal_log_is_capped(monkeypatch):
    """AC-1: the outcome log keeps its hard cap for withdrawals too (lowered here so the test is quick)."""
    import ofo.strategy.versions as versions
    ctx = to_active()
    ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1)
    monkeypatch.setattr(versions, "MAX_OUTCOMES", len(ctx.record.outcomes))
    with pytest.raises(VersionError, match="full"):
        ctx.record.withdraw(2, at=ctx.tick(), actor="user-1")
    assert ctx.record.proposed_version.number == 2


@pytest.mark.parametrize("reasons", ["one text", ("",), (5,), tuple(f"r{i}" for i in range(51)), ("x" * 201,)])
def test_ac1_q243_rejection_reasons_are_checked(reasons):
    """AC-1 (Q243 fix 1): the broker's reason texts are a bounded tuple of non-empty strings (fail closed)."""
    with pytest.raises(VersionError, match="reasons"):
        ExecutionResult(1, ResultStatus.REJECTED, Position(), T0, "r1", reasons)


def test_ac1_q243_fix5_any_live_state_is_exactly_the_five_listed():
    """AC-1 (Q243 fix 5): broker differs -> Reconciliation Required from exactly Active, Monitoring Paused,
    Adjustment Proposed, Execution in Progress, Partially Executed; from no other state."""
    for state in StrategyState:
        expected = {Trigger.BROKER_DIFFERS} if state in LIVE else set()
        assert set(allowed_triggers(state, S.RECONCILIATION_REQUIRED)) == expected, state
    for previous in LIVE:
        assert to_reconciliation(previous).machine.transitions[-1].from_state is previous


def test_ac1_q243_fix3_a_withdrawal_that_leaves_the_broker_differing_requires_reconciliation():
    """AC-1 (Q243 fix 3, ADR-018): while a proposal is pending a broker change is not judged; once it is withdrawn
    the broker is compared with the active version again, and a difference blocks (Reconciliation Required)."""
    ctx = to_adjusting()
    ctx.record.edit(DOUBLE, at=ctx.tick(), based_on=1)
    ctx.observe(odd(ctx))  # a change in Kite while the proposal waits
    assert not ctx.record.reconciliation_required
    ctx.machine.withdraw_adjustment(at=ctx.tick(), actor="user-1")
    assert ctx.record.reconciliation_required
    assert ctx.machine.sync_broker(at=ctx.tick()).to_state is S.RECONCILIATION_REQUIRED
