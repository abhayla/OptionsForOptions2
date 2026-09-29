"""Strategy operational state machine: the owner-approved transitions only (REQ-039, W-041).

Spec basis: REQ-039 AC-1 (the 12 states), AC-2 ("Every state change is an explicit recorded transition; state is never
inferred only from order rows"), AC-3 (every non-normal state says what happened, when, what is blocked and the next
action; Q201); spec/data/domain-model.md §6, the transition table approved by the owner on 2026-09-29 (Q240) with two
fixes: Reconciliation Required is left only through a recorded manual resolution (Q222), and Active <-> Monitoring
Paused happens only when the user pauses or resumes; amended the same day by Q243 (five fixes: nothing filled ->
Validated with the reasons; "Review Manually" is not a transition; a withdrawn proposal is recorded in the version
history; a final partial result is Partially Executed; "any live state" listed); REQ-043 AC-4 (monitoring status is a
separate axis); ADR-019.

One owner per fact, no second source of truth:
- The OPERATIONAL STATE lives only here: it is the target of the last recorded ``StateTransition`` (Draft before the
  first). Nothing else stores it, and it is never derived from order rows.
- Execution, versions, the broker's position, the sticky reconciliation flag and the exit live in
  ``ofo.strategy.versions.StrategyRecord`` (W-012, driven by W-021 reconciliation, W-023 partial execution and
  W-027 modification). Every guard READS them from the record this machine owns; no method accepts a verdict
  ("resolved", "executed", "passed") from its caller (finding caller-supplied-verdict-trusted).
- Monitoring availability (``ofo.marketdata.availability``) and the Zerodha session are separate axes
  (domain-model §5); nothing here reads or writes them, so a lost feed or an expired session never changes the state.
- Every transition is appended to a hash-chained audit log as ``EventType.STRATEGY_CHANGED`` (REQ-064 "strategy
  changes"); the REQ-040 timeline's entry catalogue is fixed to its AC-1 text and has no "state changed" type.

Readings of the table (spec words that needed a concrete meaning; each is reported, none adds a row):
- "any live state" / "previous live state": the five states Q243 fix 5 lists (Active, Monitoring Paused, Adjustment
  Proposed, Execution in Progress, Partially Executed).
- "no leg filled and every order is finally rejected/failed" (Q243 fix 1): the record's REJECTED or FAILED outcome
  for the executing version with the broker still at the version's baseline (the record then closes the proposal).
  The row returns an UN-executed strategy to Validated; for an adjustment of a strategy that already holds a position
  the table has no row, so that case is refused loudly (owner question), never guessed.
- "some legs executed, the rest finally failed/rejected" (Q243 fix 4): the record's PARTIAL, REJECTED or FAILED
  outcome for the executing version whose broker position moved off the baseline but stayed inside baseline..intended
  (the record keeps the proposal open). "Zerodha's positions differ from the recorded fills": the record's own
  comparison (W-012 ``_within_path``, the same range test W-021's ``_classify_held`` uses for a partial execution)
  found a broker position no fill of this version explains; the record sets its sticky flag and the move is
  Reconciliation Required. The machine cannot read the order book (``ofo.orders`` may be imported only by the
  execution flow, tests/execution/test_strategy_only.py AC-3), so the record's results are its fill records.
- "every leg confirmed executed by the broker and reconciled": the record ACTIVATED the executing version, or (after
  returning from Reconciliation Required) a manual adoption made the broker's position the active version.
- "all legs expired": every contract of the active version and of the broker position expired before ``at``'s
  India date.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Callable, Final, Mapping, Protocol, Sequence

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditLog
from ofo.reconciliation.resolution import ResolutionKind
from ofo.strategy.definition import MAX_TEXT, StrategyDefinition
from ofo.strategy.versions import OutcomeKind, Position, StrategyRecord

IST: Final = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
MAX_TRANSITIONS: Final = 100_000
MAX_REASONS: Final = 50
MAX_ID_CHARS: Final = 200
MAX_FUTURE_SKEW: Final = datetime.timedelta(seconds=60)
#: REQ-058 AC-2's four choices in W-023's ``CHOICE_ORDER``. Not imported: only the execution flow may import
#: ``ofo.execution.partial`` (tests/execution/test_strategy_only.py AC-3); test_state_machine asserts they are equal.
PARTIAL_CHOICES: Final = ("Complete Strategy", "Retry Failed Leg", "Review Manually", "Close Partial Strategy")


class StateMachineError(ValueError):
    """A state change the approved table or the strategy record does not allow."""


class StrategyState(Enum):
    """REQ-039 AC-1, in the spec's order."""

    DRAFT = "Draft"
    READY_FOR_VALIDATION = "Ready for Validation"
    VALIDATED = "Validated"
    ACTIVE = "Active"
    MONITORING_PAUSED = "Monitoring Paused"
    ADJUSTMENT_PROPOSED = "Adjustment Proposed"
    EXECUTION_IN_PROGRESS = "Execution in Progress"
    PARTIALLY_EXECUTED = "Partially Executed"
    RECONCILIATION_REQUIRED = "Reconciliation Required"
    COMPLETED = "Completed"
    EXITED = "Exited"
    ARCHIVED = "Archived"


class Trigger(Enum):
    """The trigger column of domain-model §6, one member per phrase."""

    USER_SUBMITS_FOR_VALIDATION = "user submits for validation"
    VALIDATION_PASSES = "validation passes"
    VALIDATION_FAILS = "validation fails (with reasons)"
    USER_CONFIRMS_EXECUTE = "user confirms Execute Strategy"
    EXECUTED_AND_RECONCILED = "every leg confirmed executed by the broker and reconciled"
    NOTHING_FILLED = "no leg filled and every order is finally rejected/failed"
    ADJUSTMENT_NOTHING_FILLED = "an adjustment whose every order is finally rejected/failed with nothing filled"
    SOME_LEGS_EXECUTED = "some legs executed, the rest finally failed/rejected"
    USER_COMPLETES_OR_RETRIES = "user chooses complete or retry"
    USER_CLOSES_PARTIAL = "user chooses close partial"
    USER_STARTS_MODIFICATION = "user starts a modification, or accepts a detected opportunity to review"
    USER_CONFIRMS_PROPOSAL = "user confirms the proposal"
    USER_WITHDRAWS_PROPOSAL = "user withdraws the proposal"
    USER_PAUSES_MONITORING = "the user explicitly pauses monitoring of this strategy"
    USER_RESUMES_MONITORING = "the user resumes monitoring of this strategy"
    BROKER_DIFFERS = "broker state differs from platform state"
    MANUAL_RESOLUTION = "a recorded manual resolution on the latest run"
    MANUAL_RESOLUTION_BROKER_FLAT = "a recorded manual resolution: broker flat -> Exited"
    EXIT_ORDERS_EXECUTED = "exit orders confirmed executed"
    ALL_LEGS_EXPIRED = "all legs expired or closed at expiry"
    USER_ARCHIVES = "user archives"


_S, _T = StrategyState, Trigger
_FINAL_FAILURES: Final = frozenset({OutcomeKind.REJECTED, OutcomeKind.FAILED})
_FILL_KINDS: Final = _FINAL_FAILURES | {OutcomeKind.PARTIAL}
LIVE_STATES: Final = frozenset({
    _S.ACTIVE, _S.MONITORING_PAUSED, _S.ADJUSTMENT_PROPOSED, _S.EXECUTION_IN_PROGRESS, _S.PARTIALLY_EXECUTED,
})
NON_NORMAL_STATES: Final = frozenset({
    _S.EXECUTION_IN_PROGRESS, _S.PARTIALLY_EXECUTED, _S.RECONCILIATION_REQUIRED, _S.MONITORING_PAUSED,
    _S.ADJUSTMENT_PROPOSED,
})


def _table() -> dict[tuple[StrategyState, StrategyState], frozenset[Trigger]]:
    rows: dict[tuple[StrategyState, StrategyState], set[Trigger]] = {
        (_S.DRAFT, _S.READY_FOR_VALIDATION): {_T.USER_SUBMITS_FOR_VALIDATION},
        (_S.READY_FOR_VALIDATION, _S.VALIDATED): {_T.VALIDATION_PASSES},
        (_S.READY_FOR_VALIDATION, _S.DRAFT): {_T.VALIDATION_FAILS},
        (_S.VALIDATED, _S.EXECUTION_IN_PROGRESS): {_T.USER_CONFIRMS_EXECUTE},
        (_S.EXECUTION_IN_PROGRESS, _S.ACTIVE): {_T.EXECUTED_AND_RECONCILED},
        (_S.EXECUTION_IN_PROGRESS, _S.VALIDATED): {_T.NOTHING_FILLED},
        (_S.EXECUTION_IN_PROGRESS, _S.ADJUSTMENT_PROPOSED): {_T.ADJUSTMENT_NOTHING_FILLED},  # Q245
        (_S.EXECUTION_IN_PROGRESS, _S.PARTIALLY_EXECUTED): {_T.SOME_LEGS_EXECUTED},
        (_S.PARTIALLY_EXECUTED, _S.EXECUTION_IN_PROGRESS): {_T.USER_COMPLETES_OR_RETRIES},
        (_S.PARTIALLY_EXECUTED, _S.EXITED): {_T.USER_CLOSES_PARTIAL},
        (_S.ACTIVE, _S.ADJUSTMENT_PROPOSED): {_T.USER_STARTS_MODIFICATION},
        (_S.ADJUSTMENT_PROPOSED, _S.EXECUTION_IN_PROGRESS): {_T.USER_CONFIRMS_PROPOSAL},
        (_S.ADJUSTMENT_PROPOSED, _S.ACTIVE): {_T.USER_WITHDRAWS_PROPOSAL},
        (_S.ACTIVE, _S.MONITORING_PAUSED): {_T.USER_PAUSES_MONITORING},
        (_S.MONITORING_PAUSED, _S.ACTIVE): {_T.USER_RESUMES_MONITORING},
        (_S.RECONCILIATION_REQUIRED, _S.EXITED): {_T.MANUAL_RESOLUTION_BROKER_FLAT},
        (_S.ACTIVE, _S.EXITED): {_T.EXIT_ORDERS_EXECUTED},
        (_S.ACTIVE, _S.COMPLETED): {_T.ALL_LEGS_EXPIRED},
        (_S.COMPLETED, _S.ARCHIVED): {_T.USER_ARCHIVES},
        (_S.EXITED, _S.ARCHIVED): {_T.USER_ARCHIVES},
        (_S.DRAFT, _S.ARCHIVED): {_T.USER_ARCHIVES},
    }
    for live in LIVE_STATES:
        rows[(live, _S.RECONCILIATION_REQUIRED)] = {_T.BROKER_DIFFERS}
        rows[(_S.RECONCILIATION_REQUIRED, live)] = {_T.MANUAL_RESOLUTION}
    return {pair: frozenset(triggers) for pair, triggers in rows.items()}


#: domain-model §6 (Q240): (from, to) -> the triggers that may cause it. Every other pair is refused.
TRANSITIONS: Final[Mapping[tuple[StrategyState, StrategyState], frozenset[Trigger]]] = MappingProxyType(_table())


def allowed_triggers(from_state: StrategyState, to_state: StrategyState) -> frozenset[Trigger]:
    """The triggers the approved table allows for ``from_state -> to_state`` (empty: the move is refused)."""
    return TRANSITIONS.get((from_state, to_state), frozenset())


class DraftValidator(Protocol):
    """Runs the validation checks on a draft and returns the reasons it fails (empty: it passes)."""

    def __call__(self, definition: StrategyDefinition) -> Sequence[str]: ...


@dataclass(frozen=True)
class StateTransition:
    """One recorded state change (AC-2): what moved, why, who or what caused it, and when."""

    seq: int
    from_state: StrategyState
    to_state: StrategyState
    trigger: Trigger
    actor: str
    at: datetime.datetime
    detail: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class StateExplanation:
    """AC-3 (Q201): what happened, when, what is blocked, and the next action, for a non-normal state."""

    state: StrategyState
    what_happened: str
    since: datetime.datetime
    blocked: tuple[str, ...]
    next_action: str


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise StateMachineError(f"{label} must be a non-empty string of at most {MAX_TEXT} characters, got {value!r}")
    return value


def _differs(n: int) -> str:
    return "1 contract differs" if n == 1 else f"{n} contracts differ"


_RECONCILE_NEXT: Final = (
    f"Reconcile: {ResolutionKind.ADOPT_BROKER_POSITION.value}, {ResolutionKind.PREPARE_CLOSING_ORDER.value}, or "
    f"{ResolutionKind.MARK_REQUIRES_ATTENTION.value}. If Zerodha shows no position, the strategy can be marked exited."
)
_BLOCKED: Final[Mapping[StrategyState, tuple[str, ...]]] = MappingProxyType({
    _S.EXECUTION_IN_PROGRESS: ("new execution", "modification", "exit", "archive"),
    _S.PARTIALLY_EXECUTED: ("new execution", "modification", "archive"),
    _S.RECONCILIATION_REQUIRED: ("new execution", "adjustment execution", "exit orders", "modification", "archive"),
    _S.MONITORING_PAUSED: ("rule alerts", "rule-triggered order preparation"),
    _S.ADJUSTMENT_PROPOSED: ("new execution", "a second modification"),
})


class StrategyStateMachine:
    """The operational state of one strategy. Changed only through the event methods below, each an approved row."""

    __slots__ = ("_id", "_record", "_audit", "_clock", "_transitions", "_mark", "_validated", "_executing")

    def __init__(
        self,
        strategy_id: str,
        record: StrategyRecord,
        *,
        audit: AuditLog | None = None,
        clock: Callable[[], datetime.datetime] = _utc_now,
    ) -> None:
        if not isinstance(strategy_id, str) or not strategy_id.strip() or len(strategy_id) > MAX_ID_CHARS:
            raise StateMachineError(f"strategy id must be a non-empty string of at most {MAX_ID_CHARS} characters")
        if not isinstance(record, StrategyRecord):
            raise StateMachineError(f"a state machine needs a StrategyRecord, got {record!r}")
        if record.has_executed or record.versions or record.exited or record.reconciliation_required:
            raise StateMachineError("the record has already been executed or versioned; its state cannot be inferred "
                                    "from its rows (REQ-039 AC-2), start the machine with the strategy's draft")
        if audit is not None and not isinstance(audit, AuditLog):
            raise StateMachineError(f"audit must be an AuditLog, got {audit!r}")
        for name, value in (("_id", strategy_id), ("_record", record), ("_audit", audit or AuditLog()),
                            ("_clock", clock), ("_transitions", []), ("_mark", 0), ("_validated", None),
                            ("_executing", None)):
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"the strategy state changes only through its transitions; cannot set {name!r}")

    def _set(self, name: str, value: object) -> None:
        object.__setattr__(self, name, value)

    # ---- read side ---------------------------------------------------------------------------------------------

    @property
    def state(self) -> StrategyState:
        return self._transitions[-1].to_state if self._transitions else StrategyState.DRAFT

    @property
    def transitions(self) -> tuple[StateTransition, ...]:
        return tuple(self._transitions)

    @property
    def record(self) -> StrategyRecord:
        return self._record

    @property
    def audit(self) -> AuditLog:
        return self._audit

    def explain(self) -> StateExplanation | None:
        """AC-3: the explanation of a non-normal state, or of a Validated strategy whose execution was rejected
        (Q243 fix 1); None for a normal one."""
        state = self.state
        entry = self._transitions[-1] if self._transitions else None
        if entry is not None and entry.trigger is _T.NOTHING_FILLED:
            reasons = dict(entry.detail)["reasons"]
            return StateExplanation(state, f"Zerodha rejected every order of version {self._executing} and nothing "
                                           f"was filled. Reasons: {reasons}.", entry.at, (),
                                    "Execute again, or edit the strategy.")
        if state not in NON_NORMAL_STATES or entry is None:
            return None
        if entry.trigger is _T.ADJUSTMENT_NOTHING_FILLED:
            reasons = dict(entry.detail)["reasons"]
            return StateExplanation(state, f"Zerodha rejected every order of adjustment version {self._executing} and "
                                           f"nothing was filled. The original version stays active. Reasons: "
                                           f"{reasons}.", entry.at, _BLOCKED[state],
                                    "Execute the adjustment again, or withdraw it.")
        if state is _S.EXECUTION_IN_PROGRESS:
            happened = f"Orders for version {self._executing} were sent to Zerodha. Waiting for Zerodha to confirm every leg."
            next_action = "Wait for Zerodha to confirm the orders. Nothing is retried automatically."
        elif state is _S.PARTIALLY_EXECUTED:
            happened = f"Some legs of version {self._executing} executed and others did not."
            next_action = "Choose one: " + ", ".join(PARTIAL_CHOICES) + "."
        elif state is _S.RECONCILIATION_REQUIRED:
            count = len(self._record.actual_position.differences(self._active_intended()))
            happened = f"Zerodha's position differs from this strategy's ({_differs(count)})."
            next_action = _RECONCILE_NEXT
        elif state is _S.MONITORING_PAUSED:
            happened = f"Monitoring of this strategy was paused by {entry.actor}."
            next_action = "Resume monitoring to receive alerts again."
        else:
            active = self._record.active_version
            happened = f"A modification of version {active.number if active else '-'} was started by {entry.actor}."
            next_action = "Confirm or withdraw the proposal."
        return StateExplanation(state, happened, entry.at, _BLOCKED[state], next_action)

    # ---- events: Draft to execution ----------------------------------------------------------------------------

    def submit_for_validation(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        self._precheck(_S.READY_FOR_VALIDATION, _T.USER_SUBMITS_FOR_VALIDATION, at, actor)
        return self._commit(_S.READY_FOR_VALIDATION, _T.USER_SUBMITS_FOR_VALIDATION, actor, at)

    def validate(self, validator: DraftValidator, *, at: datetime.datetime) -> StateTransition:
        """Run ``validator`` on the record's own draft: no reasons -> Validated; reasons -> back to Draft with them."""
        self._precheck(_S.VALIDATED, _T.VALIDATION_PASSES, at, "system")
        definition = self._record.definition
        reasons = validator(definition)
        if (isinstance(reasons, (str, bytes)) or not isinstance(reasons, (tuple, list)) or len(reasons) > MAX_REASONS
                or not all(isinstance(r, str) and r.strip() and len(r) <= MAX_TEXT for r in reasons)):
            raise StateMachineError(f"validation reasons must be a list of at most {MAX_REASONS} non-empty strings, "
                                    f"got {reasons!r}")
        if reasons:
            return self._commit(_S.DRAFT, _T.VALIDATION_FAILS, "system", at, (("reasons", "; ".join(reasons)),))
        self._set("_validated", definition)
        return self._commit(_S.VALIDATED, _T.VALIDATION_PASSES, "system", at)

    def confirm_execute(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        """The user confirms Execute Strategy: the validated draft becomes the confirmed proposed version."""
        self._precheck(_S.EXECUTION_IN_PROGRESS, _T.USER_CONFIRMS_EXECUTE, at, actor)
        if self._record.definition != self._validated:
            raise StateMachineError("the strategy changed after validation; this draft was never validated")
        version = self._record.propose_execution(at=at, initiator=actor)
        self._record.confirm(version.number, at=at)
        self._set("_executing", version.number)
        return self._commit(_S.EXECUTION_IN_PROGRESS, _T.USER_CONFIRMS_EXECUTE, actor, at,
                            (("version", str(version.number)),))

    def follow_execution(self, *, at: datetime.datetime) -> StateTransition | None:
        """Read the record's execution outcomes since this state began and move as the table says; None if nothing
        decisive happened yet (no result, or a result with nothing filled)."""
        state = self.state
        if state is not _S.EXECUTION_IN_PROGRESS:
            raise StateMachineError(f"no execution is in progress (state is {state.value})")
        if self._record.reconciliation_required:
            return self._broker_differs(at)
        outcomes = self._record.outcomes[self._mark:]
        if not outcomes:
            return None
        last, record = outcomes[-1], self._record
        active = record.active_version
        if active is not None and (
                (last.kind is OutcomeKind.ACTIVATED and last.version_number == self._executing == active.number)
                or last.kind is OutcomeKind.RECONCILED):
            self._precheck(_S.ACTIVE, _T.EXECUTED_AND_RECONCILED, at, "system")
            return self._commit(_S.ACTIVE, _T.EXECUTED_AND_RECONCILED, "system", at,
                                (("version", str(active.number)),))
        pending = record.proposed_version
        if (last.kind in _FILL_KINDS and pending is not None and last.version_number == self._executing
                == pending.number and last.actual != pending.baseline):  # Q243 fix 4: the record kept it open
            self._precheck(_S.PARTIALLY_EXECUTED, _T.SOME_LEGS_EXECUTED, at, "system")
            return self._commit(_S.PARTIALLY_EXECUTED, _T.SOME_LEGS_EXECUTED, "system", at,
                                (("version", str(pending.number)),))
        if last.kind in _FINAL_FAILURES:  # nothing filled (a fill kept the proposal open, caught above)
            reasons = "; ".join(last.reasons) or "Zerodha gave no reason"
            detail = (("version", str(last.version_number)), ("reasons", reasons))
            if active is not None:  # an ADJUSTMENT (the record holds an active version): Q245
                self._precheck(_S.ADJUSTMENT_PROPOSED, _T.ADJUSTMENT_NOTHING_FILLED, at, "system")
                return self._commit(_S.ADJUSTMENT_PROPOSED, _T.ADJUSTMENT_NOTHING_FILLED, "system", at, detail)
            self._precheck(_S.VALIDATED, _T.NOTHING_FILLED, at, "system")
            return self._commit(_S.VALIDATED, _T.NOTHING_FILLED, "system", at, detail)
        return None

    def continue_execution(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        """Partially Executed: the user chose Complete Strategy or Retry Failed Leg (W-023). The executing version must
        still be pending and confirmed in the record; W-023 prepares and sends the missing orders."""
        self._precheck(_S.EXECUTION_IN_PROGRESS, _T.USER_COMPLETES_OR_RETRIES, at, actor)
        pending = self._record.proposed_version  # a set reconciliation flag always means no proposal (W-012)
        if pending is None or pending.number != self._executing or not self._record.proposal_confirmed:
            raise StateMachineError(f"version {self._executing} is no longer pending and confirmed; nothing to "
                                    "complete or retry")
        return self._commit(_S.EXECUTION_IN_PROGRESS, _T.USER_COMPLETES_OR_RETRIES, actor, at,
                            (("version", str(pending.number)),))

    def review_partial(self) -> StateExplanation:
        """Partially Executed: the user chose Review Manually. A view, not a transition (Q243 fix 2): the state stays
        Partially Executed and nothing is recorded; the review shows the partial's explanation."""
        state = self.state
        if state is not _S.PARTIALLY_EXECUTED:
            raise StateMachineError(f"{PARTIAL_CHOICES[2]} is offered only in Partially Executed (state is "
                                    f"{state.value})")
        return self.explain()  # type: ignore[return-value]  # Partially Executed is a non-normal state

    def close_partial(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        """Partially Executed: the user chose Close Partial Strategy and the closing orders left the broker flat
        (the record's ``mark_exited`` checks flat, executed and nothing pending)."""
        self._precheck(_S.EXITED, _T.USER_CLOSES_PARTIAL, at, actor)
        if not self._record.exited:
            self._record.mark_exited(at=at, actor=actor, resolution=PARTIAL_CHOICES[3])
        return self._commit(_S.EXITED, _T.USER_CLOSES_PARTIAL, actor, at)

    # ---- events: an active strategy ------------------------------------------------------------------------------

    def start_adjustment(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        self._precheck(_S.ADJUSTMENT_PROPOSED, _T.USER_STARTS_MODIFICATION, at, actor)
        self._refuse_if_broker_differs()
        pending = self._record.proposed_version
        if pending is not None:
            raise StateMachineError(f"proposed version {pending.number} is already pending; its result comes first")
        return self._commit(_S.ADJUSTMENT_PROPOSED, _T.USER_STARTS_MODIFICATION, actor, at)

    def confirm_adjustment(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        """Needs the record to hold a proposed version confirmed by the user (W-027 ``confirm_modification``);
        ``start_adjustment`` refused while one was already pending, so this one was created since."""
        self._precheck(_S.EXECUTION_IN_PROGRESS, _T.USER_CONFIRMS_PROPOSAL, at, actor)
        pending = self._record.proposed_version  # a set reconciliation flag always means no proposal (W-012)
        if pending is None:
            raise StateMachineError("no proposal was created since the modification started")
        if not self._record.proposal_confirmed:
            raise StateMachineError(f"proposed version {pending.number} is not confirmed by the user")
        self._set("_executing", pending.number)
        return self._commit(_S.EXECUTION_IN_PROGRESS, _T.USER_CONFIRMS_PROPOSAL, actor, at,
                            (("version", str(pending.number)),))

    def withdraw_adjustment(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        """Adjustment Proposed -> Active (Q243 fix 3). An unconfirmed proposed version is withdrawn in the record,
        which appends a WITHDRAWN entry to the version history; the record refuses a confirmed one."""
        self._precheck(_S.ACTIVE, _T.USER_WITHDRAWS_PROPOSAL, at, actor)
        self._refuse_if_broker_differs()
        pending = self._record.proposed_version
        if pending is None:
            return self._commit(_S.ACTIVE, _T.USER_WITHDRAWS_PROPOSAL, actor, at)
        self._record.withdraw(pending.number, at=at, actor=actor)
        return self._commit(_S.ACTIVE, _T.USER_WITHDRAWS_PROPOSAL, actor, at, (("version", str(pending.number)),))

    def pause_monitoring(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        self._precheck(_S.MONITORING_PAUSED, _T.USER_PAUSES_MONITORING, at, actor)
        self._refuse_if_broker_differs()
        return self._commit(_S.MONITORING_PAUSED, _T.USER_PAUSES_MONITORING, actor, at)

    def resume_monitoring(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        self._precheck(_S.ACTIVE, _T.USER_RESUMES_MONITORING, at, actor)
        self._refuse_if_broker_differs()
        return self._commit(_S.ACTIVE, _T.USER_RESUMES_MONITORING, actor, at)

    def confirm_exit(self, *, at: datetime.datetime, actor: str, reason: str) -> StateTransition:
        """Exit orders confirmed executed: the record's broker position must be flat (``mark_exited`` checks it)."""
        self._precheck(_S.EXITED, _T.EXIT_ORDERS_EXECUTED, at, actor)
        _require_text(reason, "reason")
        if not self._record.exited:
            self._record.mark_exited(at=at, actor=actor, resolution=reason)
        return self._commit(_S.EXITED, _T.EXIT_ORDERS_EXECUTED, actor, at)

    def complete_at_expiry(self, *, at: datetime.datetime) -> StateTransition:
        self._precheck(_S.COMPLETED, _T.ALL_LEGS_EXPIRED, at, "system")
        self._refuse_if_broker_differs()
        today = at.astimezone(IST).date()
        expiries = [leg.expiry for leg in self._record.definition.legs]  # Active: the active version's legs
        expiries += [contract[3] for contract, _ in self._record.actual_position.lines]
        if not all(expiry < today for expiry in expiries):
            raise StateMachineError(f"not every leg has expired by {today.isoformat()} (India date)")
        return self._commit(_S.COMPLETED, _T.ALL_LEGS_EXPIRED, "system", at)

    def archive(self, *, at: datetime.datetime, actor: str) -> StateTransition:
        self._precheck(_S.ARCHIVED, _T.USER_ARCHIVES, at, actor)
        return self._commit(_S.ARCHIVED, _T.USER_ARCHIVES, actor, at)

    # ---- events: reconciliation --------------------------------------------------------------------------------

    def sync_broker(self, *, at: datetime.datetime) -> StateTransition | None:
        """After a reconciliation run: a live strategy whose record says the broker differs moves to Reconciliation
        Required. Nothing else changes here (an agreeing run, a lost feed, an expired session: None)."""
        if self.state in LIVE_STATES and self._record.reconciliation_required:
            return self._broker_differs(at)
        return None

    def resolve_reconciliation(self, *, at: datetime.datetime) -> StateTransition:
        """Leave Reconciliation Required only on a manual resolution the record holds since this state began (Q222):
        an adoption (RECONCILED, flag cleared) returns to the previous live state; a broker-flat exit goes to Exited."""
        state = self.state
        if state is not _S.RECONCILIATION_REQUIRED:
            raise StateMachineError(f"no reconciliation is required (state is {state.value})")
        if self._record.exited:  # mark_exited: an explicit, audited resolution that needs a flat broker
            self._precheck(_S.EXITED, _T.MANUAL_RESOLUTION_BROKER_FLAT, at, "system")
            return self._commit(_S.EXITED, _T.MANUAL_RESOLUTION_BROKER_FLAT, "system", at)
        # Entered only with the record's flag set (sync_broker / follow_execution), and only reconcile() -- which
        # appends a RECONCILED outcome -- or mark_exited (above) clears it (W-012): a cleared flag IS the resolution.
        if not self._record.reconciliation_required:
            previous = self._transitions[-1].from_state
            self._precheck(previous, _T.MANUAL_RESOLUTION, at, "system")
            return self._commit(previous, _T.MANUAL_RESOLUTION, "system", at)
        raise StateMachineError("no recorded manual resolution since reconciliation was required; an agreeing run "
                                "alone never unblocks the strategy (Q222)")

    # ---- internals ---------------------------------------------------------------------------------------------

    def _active_intended(self) -> Position:
        active = self._record.active_version
        return active.intended_position if active is not None else Position()

    def _broker_differs(self, at: datetime.datetime) -> StateTransition:
        self._precheck(_S.RECONCILIATION_REQUIRED, _T.BROKER_DIFFERS, at, "system")
        return self._commit(_S.RECONCILIATION_REQUIRED, _T.BROKER_DIFFERS, "system", at)

    def _refuse_if_broker_differs(self) -> None:
        if self._record.reconciliation_required:
            raise StateMachineError("reconciliation required: the broker's position differs from this strategy; "
                                    "sync the broker state first")

    def _precheck(self, to_state: StrategyState, trigger: Trigger, at: object, actor: object) -> None:
        """Refuse before anything is touched: the move must be an approved row, the time valid, the actor named."""
        state = self.state
        if trigger not in allowed_triggers(state, to_state):
            raise StateMachineError(f"{state.value} -> {to_state.value} on '{trigger.value}' is not an approved "
                                    "transition (domain-model §6, Q240)")
        if not isinstance(at, datetime.datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise StateMachineError(f"transition time must be a timezone-aware datetime, got {at!r}")
        if self._transitions and at < self._transitions[-1].at:
            raise StateMachineError(f"transition time {at.isoformat()} is before the last transition "
                                    f"({self._transitions[-1].at.isoformat()})")
        if at > self._clock() + MAX_FUTURE_SKEW:
            raise StateMachineError(f"transition time {at.isoformat()} is in the future")
        _require_text(actor, "actor")
        if len(self._transitions) >= MAX_TRANSITIONS:
            raise StateMachineError(f"transition log is full ({MAX_TRANSITIONS})")

    def _commit(
        self, to_state: StrategyState, trigger: Trigger, actor: str, at: datetime.datetime,
        detail: tuple[tuple[str, str], ...] = (),
    ) -> StateTransition:
        from_state = self.state  # every caller ran _precheck(to_state, trigger) first: the table's only gate
        step = StateTransition(len(self._transitions), from_state, to_state, trigger, actor, at, detail)
        self._audit.append(EventType.STRATEGY_CHANGED, actor=actor, timestamp=at, correlation_id=f"state:{self._id}",
                           payload={"strategy_id": self._id, "from": from_state.value, "to": to_state.value,
                                    "trigger": trigger.value, "detail": [list(pair) for pair in detail]})
        self._transitions.append(step)
        if from_state is not _S.RECONCILIATION_REQUIRED:  # a return keeps the window that holds the resolution
            self._set("_mark", len(self._record.outcomes))
        return step
