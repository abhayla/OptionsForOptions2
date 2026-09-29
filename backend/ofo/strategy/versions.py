"""Activity history before the first execution, versions after; proposed vs active; broker actual wins.

Spec: REQ-038 AC-2..AC-4; ADR-019 (Q135 simple activity history, no manual version management; Q190 every
meaningful modification after execution is a new version; Q191 a proposed version becomes active only after
confirmation and execution + reconciliation); ADR-016..ADR-018 (Zerodha is the authority; submitted is not
executed; no silent rewrite of what the user asked for); spec/data/domain-model.md §3.

Scope: this module does NOT implement the 12-state machine of domain-model §6 (that transition table is a
proposal awaiting owner review). It tracks only what REQ-038 needs: whether anything has executed, the active
version, the one pending proposed version, and the broker's actual position. No broker call happens here: an
execution/reconciliation result is an input object (``ExecutionResult``).

Rules implemented:
- Before anything has executed, a meaningful edit appends a ``HistoryEntry`` (with restore); no version.
- Asking to execute creates a proposed ``Version`` (an execution attempt is not a definition change). A proposal
  whose result shows nothing filled leaves the strategy un-executed, so later edits are history entries again.
- Once anything has executed, a meaningful edit creates a new proposed ``Version``. Versions are frozen and kept.
- A proposal activates only when (a) the user confirmed it and (b) a COMPLETE result arrives whose broker
  position equals the version's intended position. Anything else leaves the active version unchanged and
  records an ``ExecutionOutcome`` (intended vs actual).
- The result's status word is never trusted alone: any contract whose actual units fall outside the range
  baseline..intended makes the outcome MISMATCH, whatever the word. ``Version.baseline`` is the previous active
  version's intended position, fixed when the proposal is created: the window never slides with later reports.
- Every result replaces the recorded actual position with the broker's position: the broker wins.
- MISMATCH, REJECTED and FAILED close the proposal. Standing invariant, re-checked after every result: either a
  proposal is pending, or the broker's position equals the active version's intended position, or the sticky
  ``reconciliation_required`` flag is set (ADR-018: an unresolved mismatch blocks execution). While it is set,
  edit/restore/propose/confirm refuse, and a late result is recorded (``BLOCKED`` or ``MISMATCH``) but activates
  nothing. Only ``reconcile()`` - explicit, audited, and only to a definition equal to the broker's position
  (ADR-018 Q198 "adopt actual broker position") - clears it.
- Reconciliation (REQ-060, W-021) adds two entry points: ``observe_broker_position()`` records a broker position
  seen outside an execution result (a reconciliation run, e.g. a change made in Zerodha) and sets the same sticky
  flag through the same invariant; ``mark_exited()`` closes a strategy whose broker position is flat (ADR-019 Q200
  Exited; deferred issue #19: a flat broker position cannot be adopted as a definition, so without this the
  strategy stayed blocked forever). An exited strategy accepts no further change.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from ofo.strategy.definition import (
    MAX_TEXT,
    MAX_UNITS,
    Contract,
    DefinitionLeg,
    StrategyDefinition,
    contract_sort_key,
    describe_contract,
)
from ofo.engine.legs import Action, Instrument, require_price
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

MAX_HISTORY = 10_000
MAX_VERSIONS = 1_000
MAX_OUTCOMES = 10_000
MAX_POSITION_LINES = 100
#: How far ahead of the clock a timestamp may be (clock skew between services), never more.
MAX_FUTURE_SKEW = datetime.timedelta(seconds=60)


class VersionError(ValueError):
    """A history/version operation is not allowed in the current state, or its input is invalid."""


def _require_aware(at: object, label: str) -> datetime.datetime:
    if not isinstance(at, datetime.datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise VersionError(f"{label} must be a timezone-aware datetime, got {at!r}")
    return at


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT or (not allow_empty and not value.strip()):
        raise VersionError(f"{label} must be a {'' if allow_empty else 'non-empty '}string of at most {MAX_TEXT} chars")
    return value


@dataclass(frozen=True)
class Position:
    """Net signed units per contract (long positive, short negative). Zero lines mean flat and are dropped."""

    lines: tuple[tuple[Contract, int], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.lines, tuple):
            raise VersionError(f"position lines must be a tuple of (contract, units), got {self.lines!r}")
        if len(self.lines) > MAX_POSITION_LINES:
            raise VersionError(f"a position has at most {MAX_POSITION_LINES} lines, got {len(self.lines)}")
        seen: set[Contract] = set()
        kept = []
        for line in self.lines:
            if not isinstance(line, tuple) or len(line) != 2:
                raise VersionError(f"a position line must be (contract, units), got {line!r}")
            contract, units = line
            check_contract(contract)
            if contract in seen:
                raise VersionError(f"duplicate position line for {describe_contract(contract)}")
            seen.add(contract)
            if isinstance(units, bool) or not isinstance(units, int) or abs(units) > MAX_UNITS:
                raise VersionError(f"units must be an int within +/-{MAX_UNITS}, got {units!r}")
            if units:
                kept.append((contract, units))
        object.__setattr__(self, "lines", tuple(sorted(kept, key=lambda item: contract_sort_key(item[0]))))

    @classmethod
    def of(cls, units_by_contract: dict[Contract, int]) -> "Position":
        return cls(tuple(units_by_contract.items()))

    def as_dict(self) -> dict[Contract, int]:
        return dict(self.lines)

    def differences(self, other: "Position") -> tuple[tuple[Contract, int, int], ...]:
        """(contract, units here, units in ``other``) for every contract where the two differ."""
        mine, theirs = self.as_dict(), other.as_dict()
        keys = sorted(mine.keys() | theirs.keys(), key=contract_sort_key)
        return tuple((key, mine.get(key, 0), theirs.get(key, 0)) for key in keys if mine.get(key, 0) != theirs.get(key, 0))


@dataclass(frozen=True)
class HistoryEntry:
    """One activity-history entry (before the first execution). ``before`` is None only for the creation entry."""

    seq: int
    at: datetime.datetime
    kind: str
    changes: tuple[str, ...]
    before: StrategyDefinition | None
    after: StrategyDefinition


@dataclass(frozen=True)
class Version:
    """A preserved strategy version: what was asked, when, why, by whom (Q190). Never edited after creation."""

    number: int
    definition: StrategyDefinition
    based_on: int | None
    created_at: datetime.datetime
    initiator: str
    reason: str
    changes: tuple[str, ...]
    baseline: Position = Position()  # the previous active version's intended position when this was proposed

    @property
    def intended_position(self) -> Position:
        return Position.of(self.definition.intended_position())


class ResultStatus(Enum):
    """What the execution/reconciliation result reports. COMPLETE = every required order executed and reconciled."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionResult:
    """Input object: the broker's execution + reconciliation outcome for one proposed version."""

    version_number: int
    status: ResultStatus
    broker_position: Position
    at: datetime.datetime
    reference: str

    def __post_init__(self) -> None:
        if isinstance(self.version_number, bool) or not isinstance(self.version_number, int):
            raise VersionError(f"version_number must be an int, got {self.version_number!r}")
        if not isinstance(self.status, ResultStatus):
            raise VersionError(f"status must be a ResultStatus, got {self.status!r}")
        if not isinstance(self.broker_position, Position):
            raise VersionError(f"broker_position must be a Position, got {self.broker_position!r}")
        _require_aware(self.at, "result time")
        _require_text(self.reference, "result reference")


class OutcomeKind(Enum):
    ACTIVATED = "activated"
    PARTIAL = "partial"
    REJECTED = "rejected"
    FAILED = "failed"
    MISMATCH = "mismatch"  # the result's claim and the broker position disagree: reconcile before anything else
    BLOCKED = "blocked"  # a late result recorded while reconciliation is required; it activates nothing
    RECONCILED = "reconciled"  # an explicit, audited manual reconciliation (ADR-018 Q198)
    OBSERVED = "observed"  # a broker position recorded by a reconciliation run, outside any execution result
    EXITED = "exited"  # the broker position is flat and the strategy was closed (ADR-019 Q200)


@dataclass(frozen=True)
class ExecutionOutcome:
    """What happened to one proposed version: intended (what the user asked) vs actual (what the broker holds)."""

    version_number: int
    kind: OutcomeKind
    intended: Position
    actual: Position
    at: datetime.datetime
    reference: str

    @property
    def differences(self) -> tuple[tuple[Contract, int, int], ...]:
        """(contract, intended units, actual units) wherever the broker's actual differs from the version."""
        return self.intended.differences(self.actual)


def _within_path(previous: Position, intended: Position, actual: Position) -> bool:
    """True when every contract's actual units sit between its previous and intended units (inclusive).

    First execution: previous is 0, so actual must be on the intended side and no larger. Increase 75 -> 150:
    75..150. Reduction 150 -> 75: 75..150. A contract in neither previous nor intended must be 0.
    """
    before, after, now = previous.as_dict(), intended.as_dict(), actual.as_dict()
    for key in before.keys() | after.keys() | now.keys():
        low, high = sorted((before.get(key, 0), after.get(key, 0)))
        if not low <= now.get(key, 0) <= high:
            return False
    return True


def check_contract(contract: object) -> None:
    """A position contract passes the same guards as a definition leg (engine money guard on the strike)."""
    if not isinstance(contract, tuple) or len(contract) != 4:
        raise VersionError(f"a contract must be (underlying, Instrument, strike, expiry), got {contract!r}")
    underlying, instrument, strike, expiry = contract
    if underlying not in SUPPORTED_UNDERLYINGS:
        raise VersionError(f"contract underlying must be one of {sorted(SUPPORTED_UNDERLYINGS)}, got {underlying!r}")
    if not isinstance(instrument, Instrument):
        raise VersionError(f"contract instrument must be an Instrument, got {instrument!r}")
    if instrument is Instrument.FUT:
        if strike is not None:
            raise VersionError("a futures contract has no strike")
    else:
        try:
            require_price(strike, "contract strike", allow_zero=False)
        except ValueError as exc:
            raise VersionError(str(exc)) from exc
    if not isinstance(expiry, datetime.date) or isinstance(expiry, datetime.datetime):
        raise VersionError(f"contract expiry must be a datetime.date, got {expiry!r}")


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class StrategyRecord:
    """One strategy's definition history, versions and broker-actual position. Change it only via methods."""

    __slots__ = (
        "_clock", "_last_at", "_draft", "_history", "_versions", "_outcomes", "_active", "_pending",
        "_confirmed", "_actual", "_executed", "_references", "_reconcile", "_exited",
        "_observed_at",
    )

    def __init__(
        self,
        definition: StrategyDefinition,
        *,
        at: datetime.datetime,
        clock: Callable[[], datetime.datetime] = _utc_now,
    ) -> None:
        if not isinstance(definition, StrategyDefinition):
            raise VersionError(f"a strategy record needs a StrategyDefinition, got {definition!r}")
        self._set("_clock", clock)
        self._set("_last_at", None)
        self._stamp(at)
        self._set("_draft", definition)
        self._set("_history", [HistoryEntry(0, at, "created", (), None, definition)])
        self._set("_versions", [])
        self._set("_outcomes", [])
        self._set("_active", None)
        self._set("_pending", None)
        self._set("_confirmed", False)
        self._set("_actual", Position())
        self._set("_executed", False)
        self._set("_references", set())
        self._set("_reconcile", False)
        self._set("_exited", False)
        self._set("_observed_at", None)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"StrategyRecord is changed only through its methods; cannot set {name!r}")

    def _set(self, name: str, value: object) -> None:
        object.__setattr__(self, name, value)

    def _check_time(self, at: object) -> datetime.datetime:
        """The checks of ``_stamp`` without recording the time."""
        _require_aware(at, "timestamp")
        if self._last_at is not None and at < self._last_at:
            raise VersionError(f"timestamp {at.isoformat()} is before the last recorded event {self._last_at.isoformat()}")
        if at > self._clock() + MAX_FUTURE_SKEW:
            raise VersionError(f"timestamp {at.isoformat()} is in the future")
        return at

    def _stamp(self, at: object) -> datetime.datetime:
        self._check_time(at)
        self._set("_last_at", at)
        return at

    # ---- read side -------------------------------------------------------------------------------------------

    @property
    def has_executed(self) -> bool:
        return self._executed

    @property
    def reconciliation_required(self) -> bool:
        """Sticky: the broker's position differs from the active version with no proposal pending (ADR-018)."""
        return self._reconcile

    @property
    def last_observed_at(self) -> datetime.datetime | None:
        """Time of the reconciliation run that last set ``actual_position``; None if anything else set it since
        (an execution result), so a resolution must wait for a fresh run (W-021 fix round)."""
        return self._observed_at

    @property
    def exited(self) -> bool:
        """The strategy was closed because the broker position went flat; it accepts no further change."""
        return self._exited

    @property
    def history(self) -> tuple[HistoryEntry, ...]:
        return tuple(self._history)

    @property
    def versions(self) -> tuple[Version, ...]:
        return tuple(self._versions)

    @property
    def outcomes(self) -> tuple[ExecutionOutcome, ...]:
        return tuple(self._outcomes)

    @property
    def active_version(self) -> Version | None:
        return None if self._active is None else self._versions[self._active - 1]

    @property
    def proposed_version(self) -> Version | None:
        return None if self._pending is None else self._versions[self._pending - 1]

    @property
    def actual_position(self) -> Position:
        """The broker's position as last reported. It wins over any version's intended position."""
        return self._actual

    @property
    def definition(self) -> StrategyDefinition:
        """The accepted definition: the active version's, or the Builder draft before any version is active."""
        active = self.active_version
        return self._draft if active is None else active.definition

    def version(self, number: int) -> Version:
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(self._versions):
            raise VersionError(f"no version {number!r}")
        return self._versions[number - 1]

    def outcomes_for(self, number: int) -> tuple[ExecutionOutcome, ...]:
        self.version(number)
        return tuple(o for o in self._outcomes if o.version_number == number)

    # ---- write side ------------------------------------------------------------------------------------------

    def edit(
        self,
        new: StrategyDefinition,
        *,
        at: datetime.datetime,
        initiator: str = "user",
        reason: str = "",
        based_on: int | None = None,
    ) -> HistoryEntry | Version | None:
        """Apply a user edit. Before execution: a history entry. After: a proposed version. No change: None."""
        if not isinstance(new, StrategyDefinition):
            raise VersionError(f"edit needs a StrategyDefinition, got {new!r}")
        _require_text(initiator, "initiator")
        _require_text(reason, "reason", allow_empty=True)
        self._refuse_while_blocked("edit")
        if not self._executed:
            if based_on is not None:
                raise VersionError("before the first execution there are no versions to base an edit on")
            return self._append_history("changed", new, at)
        active = self.active_version
        if active is None:
            raise VersionError("executed with no active version: the strategy has no accepted definition to change")
        if based_on is not None and based_on != active.number:
            raise VersionError(f"version {based_on} is not the active version ({active.number}); old versions are read-only")
        changes = new.changes_from(active.definition)
        if not changes:
            return None
        self._stamp(at)
        return self._add_version(new, active.number, at, initiator, reason, changes)

    def restore(self, seq: int, *, at: datetime.datetime) -> HistoryEntry | None:
        """Restore an earlier Builder configuration (before execution only); the current one stays in history."""
        self._refuse_while_blocked("restore")
        if self._executed:
            raise VersionError("after the first execution, restore by proposing a new version")
        if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq < len(self._history):
            raise VersionError(f"no history entry {seq!r}")
        return self._append_history(f"restored entry {seq}", self._history[seq].after, at)

    def propose_execution(self, *, at: datetime.datetime, initiator: str = "user", reason: str = "") -> Version:
        """Before the first execution: turn the Builder draft into proposed version N for execution."""
        self._refuse_while_blocked("propose an execution")
        if self._executed:
            raise VersionError("already executed; changes after execution are proposed through edit()")
        _require_text(initiator, "initiator")
        _require_text(reason, "reason", allow_empty=True)
        self._stamp(at)
        return self._add_version(self._draft, None, at, initiator, reason, ("execution requested",))

    def confirm(self, number: int, *, at: datetime.datetime) -> None:
        """The user's explicit confirmation of the pending proposed version."""
        self._refuse_if_exited("confirm")
        if self._reconcile:
            raise VersionError("cannot confirm: reconciliation required (broker position differs from the active version)")
        if self._pending is None or number != self._pending:
            raise VersionError(f"version {number!r} is not the pending proposed version")
        if self._confirmed:
            raise VersionError(f"version {number} is already confirmed")
        self._stamp(at)
        self._set("_confirmed", True)

    def apply_result(self, result: ExecutionResult) -> ExecutionOutcome:
        """Record an execution/reconciliation result. Activates the proposal only on a reconciled COMPLETE.

        While reconciliation is required, a late result for the latest version is still recorded (the broker's
        position wins) but can activate nothing: its outcome is MISMATCH or BLOCKED and the flag stays set.
        """
        if not isinstance(result, ExecutionResult):
            raise VersionError(f"apply_result needs an ExecutionResult, got {result!r}")
        self._refuse_if_exited("apply a result")
        if self._reconcile:
            if result.version_number != len(self._versions):
                raise VersionError(f"version {result.version_number} is not the latest version; late result refused")
        else:
            if self._pending is None or result.version_number != self._pending:
                raise VersionError(f"version {result.version_number} is not the pending proposed version")
            if not self._confirmed:
                raise VersionError(f"version {result.version_number} was never confirmed by the user; it cannot activate")
        if result.reference in self._references:
            raise VersionError(f"result {result.reference!r} was already applied")
        if len(self._outcomes) >= MAX_OUTCOMES:
            raise VersionError(f"outcome log is full ({MAX_OUTCOMES})")
        self._stamp(result.at)
        proposal = self._versions[result.version_number - 1]
        intended, actual = proposal.intended_position, result.broker_position
        kind = self._classify(result.status, proposal.baseline, intended, actual)
        self._references.add(result.reference)
        self._set("_actual", actual)
        self._set("_observed_at", None)
        if actual.lines:
            self._set("_executed", True)
        if self._reconcile:
            if kind is not OutcomeKind.MISMATCH:
                kind = OutcomeKind.BLOCKED
        elif kind is OutcomeKind.ACTIVATED:
            self._set("_active", proposal.number)
            self._set("_executed", True)
        if kind is not OutcomeKind.PARTIAL:
            self._set("_pending", None)
            self._set("_confirmed", False)
        outcome = ExecutionOutcome(proposal.number, kind, intended, actual, result.at, result.reference)
        self._outcomes.append(outcome)
        self._recheck_invariant()
        return outcome

    def reconcile(
        self,
        *,
        at: datetime.datetime,
        actor: str,
        resolution: str,
        definition: StrategyDefinition | None = None,
    ) -> Version:
        """Explicit, audited manual reconciliation (ADR-018 Q198 "adopt actual broker position").

        The ONLY way to clear ``reconciliation_required``. Records a new version equal to the broker's position
        (``definition``, or one built from the broker's position keeping the current rules, risk limits and
        preferences), makes it active, and logs a RECONCILED outcome with actor, time and resolution. Refused when
        nothing needs reconciling, or when the recorded resolution would still differ from the broker's position.
        """
        self._refuse_if_exited("reconcile")
        if not self._reconcile:
            raise VersionError("no reconciliation required: the broker position matches the active version")
        _require_text(actor, "actor")
        _require_text(resolution, "resolution")
        base = self.definition
        if definition is None:
            definition = _definition_from(self._actual, base)
        if not isinstance(definition, StrategyDefinition):
            raise VersionError(f"reconcile needs a StrategyDefinition or None, got {definition!r}")
        if Position.of(definition.intended_position()) != self._actual:
            raise VersionError("the resolution still differs from the broker's actual position; not reconciled")
        if len(self._outcomes) >= MAX_OUTCOMES:
            raise VersionError(f"outcome log is full ({MAX_OUTCOMES})")
        self._stamp(at)
        changes = ("manual reconciliation",) + (definition.changes_from(base) or ("adopted broker position",))
        version = self._add_version(definition, self._active, at, actor, resolution, changes, pending=False)
        reference = f"reconcile:v{version.number}"
        self._references.add(reference)
        self._set("_active", version.number)
        self._set("_executed", True)
        self._set("_reconcile", False)
        self._outcomes.append(ExecutionOutcome(
            version.number, OutcomeKind.RECONCILED, version.intended_position, self._actual, at, reference))
        return version

    def observe_broker_position(
        self, position: Position, *, at: datetime.datetime, reference: str
    ) -> ExecutionOutcome | None:
        """Record this strategy's broker position as seen by a reconciliation run (REQ-060 AC-4; ADR-016).

        The broker wins: the recorded actual position is replaced. With no proposal pending, a position that
        differs from the active version sets the sticky ``reconciliation_required`` flag (the same invariant
        ``apply_result`` keeps) and logs an OBSERVED outcome when the picture or the flag changed. EVERY run is
        recorded, agreeing or not, so the stored broker picture is never older than the latest run (W-021 fix
        round: resolutions acted on a stale copy). Agreement never clears the flag; only an explicit resolution does.
        """
        self.check_observation(position, at=at, reference=reference)
        self._stamp(at)
        self._references.add(reference)
        was_flagged, before = self._reconcile, self._actual
        self._set("_actual", position)
        self._set("_observed_at", at)
        self._recheck_invariant()
        if not self._reconcile or (was_flagged and before == position):
            return None
        active = self.active_version
        outcome = ExecutionOutcome(
            0 if active is None else active.number, OutcomeKind.OBSERVED, self._active_intended(), position, at,
            reference,
        )
        self._outcomes.append(outcome)
        return outcome

    def check_observation(self, position: Position, *, at: datetime.datetime, reference: str) -> None:
        """Raise exactly when ``observe_broker_position`` would refuse; change nothing (two-phase recording).

        Note (not built, W-021 fix round 2): every run adds one reference to ``_references``, so a persistent
        store needs compaction (e.g. keep references newer than the last resolution) before it grows unbounded.
        """
        self._refuse_if_exited("record a broker position")
        if not isinstance(position, Position):
            raise VersionError(f"observe_broker_position needs a Position, got {position!r}")
        _require_text(reference, "observation reference")
        if reference in self._references:
            raise VersionError(f"observation {reference!r} was already recorded")
        if len(self._outcomes) >= MAX_OUTCOMES:
            raise VersionError(f"outcome log is full ({MAX_OUTCOMES})")
        self._check_time(at)

    def mark_exited(self, *, at: datetime.datetime, actor: str, resolution: str) -> ExecutionOutcome:
        """Explicit, audited close of a strategy whose broker position is flat (ADR-019 Q200 Exited; issue #19).

        Allowed only when the recorded broker position is flat, something was executed, and no proposal is in
        flight. Clears ``reconciliation_required``: nothing is left at the broker to disagree with.
        """
        self._refuse_if_exited("exit")
        _require_text(actor, "actor")
        _require_text(resolution, "resolution")
        if not self._executed:
            raise VersionError("nothing was ever executed; a strategy that never traded cannot exit")
        if self._pending is not None:
            raise VersionError(f"cannot exit: proposed version {self._pending} is awaiting its execution result")
        if self._actual.lines:
            raise VersionError("cannot mark exited: the broker still holds a position for this strategy")
        if len(self._outcomes) >= MAX_OUTCOMES:
            raise VersionError(f"outcome log is full ({MAX_OUTCOMES})")
        self._stamp(at)
        active = self.active_version
        reference = f"exited:{len(self._outcomes)}"
        self._references.add(reference)
        self._set("_exited", True)
        self._set("_reconcile", False)
        outcome = ExecutionOutcome(
            0 if active is None else active.number, OutcomeKind.EXITED, self._active_intended(), self._actual, at,
            reference,
        )
        self._outcomes.append(outcome)
        return outcome

    # ---- internals -------------------------------------------------------------------------------------------

    @staticmethod
    def _classify(status: ResultStatus, baseline: Position, intended: Position, actual: Position) -> OutcomeKind:
        """Positions decide, the status word never does (ADR-018: an unresolved mismatch blocks execution).

        First, for EVERY status: each contract's actual units must lie between the version's FIXED baseline and
        its intended units (inclusive). An unasked contract, a side flip or an overfill falls outside -> MISMATCH.
        Only then does the status word choose between the outcomes it is consistent with.
        """
        if not _within_path(baseline, intended, actual):
            return OutcomeKind.MISMATCH
        if status is ResultStatus.COMPLETE:
            return OutcomeKind.ACTIVATED if actual == intended else OutcomeKind.MISMATCH
        if status is ResultStatus.PARTIAL:
            return OutcomeKind.PARTIAL
        return OutcomeKind.REJECTED if status is ResultStatus.REJECTED else OutcomeKind.FAILED

    def _active_intended(self) -> Position:
        active = self.active_version
        return Position() if active is None else active.intended_position

    def _recheck_invariant(self) -> None:
        """No proposal pending and the broker differs from the active version -> reconciliation required (sticky)."""
        if self._pending is None and self._actual != self._active_intended():
            self._set("_reconcile", True)

    def _refuse_if_exited(self, what: str) -> None:
        if self._exited:
            raise VersionError(f"cannot {what}: the strategy has exited")

    def _refuse_while_blocked(self, what: str) -> None:
        self._refuse_if_exited(what)
        if self._reconcile:
            raise VersionError(f"cannot {what}: reconciliation required (broker position differs from the active version)")
        if self._pending is not None:
            raise VersionError(f"cannot {what}: proposed version {self._pending} is awaiting its execution result")

    def _append_history(self, kind: str, new: StrategyDefinition, at: datetime.datetime) -> HistoryEntry | None:
        changes = new.changes_from(self._draft)
        if not changes:
            return None
        if len(self._history) >= MAX_HISTORY:
            raise VersionError(f"activity history is full ({MAX_HISTORY})")
        self._stamp(at)
        entry = HistoryEntry(len(self._history), at, kind, changes, self._draft, new)
        self._history.append(entry)
        self._set("_draft", new)
        return entry

    def _add_version(
        self,
        definition: StrategyDefinition,
        based_on: int | None,
        at: datetime.datetime,
        initiator: str,
        reason: str,
        changes: tuple[str, ...],
        *,
        pending: bool = True,
    ) -> Version:
        if len(self._versions) >= MAX_VERSIONS:
            raise VersionError(f"version list is full ({MAX_VERSIONS})")
        version = Version(
            len(self._versions) + 1, definition, based_on, at, initiator, reason, changes, self._active_intended()
        )
        self._versions.append(version)
        if pending:
            self._set("_pending", version.number)
            self._set("_confirmed", False)
        return version


def _definition_from(position: Position, like: StrategyDefinition) -> StrategyDefinition:
    """A definition whose intended position equals ``position``, keeping ``like``'s rules, limits and preferences."""
    if not position.lines:
        raise VersionError("the broker position is flat; there is no position to adopt as a strategy definition")
    underlyings = {contract[0] for contract, _ in position.lines}
    if len(underlyings) != 1:
        raise VersionError(f"the broker position spans {sorted(underlyings)}; adopt it with an explicit definition")
    legs = tuple(
        DefinitionLeg(Action.BUY if units > 0 else Action.SELL, instrument, strike, expiry, abs(units))
        for (_underlying, instrument, strike, expiry), units in position.lines
    )
    try:
        return StrategyDefinition(
            underlyings.pop(), legs, like.rules_ref, like.risk_limits, like.preferences,
        )
    except ValueError as exc:
        raise VersionError(f"the broker position cannot be adopted as a definition: {exc}") from exc
