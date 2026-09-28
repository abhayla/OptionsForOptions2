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
- Every result replaces the recorded actual position with the broker's position: the broker wins.
- With a proposal unresolved, or executed but no active version (reconciliation required), edits are refused.
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
    StrategyDefinition,
    contract_sort_key,
    describe_contract,
)
from ofo.engine.legs import Instrument

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
            if not isinstance(contract, tuple) or len(contract) != 4 or not isinstance(contract[1], Instrument):
                raise VersionError(f"a contract must be (underlying, Instrument, strike, expiry), got {contract!r}")
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


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class StrategyRecord:
    """One strategy's definition history, versions and broker-actual position. Change it only via methods."""

    __slots__ = (
        "_clock", "_last_at", "_draft", "_history", "_versions", "_outcomes", "_active", "_pending",
        "_confirmed", "_actual", "_executed", "_references",
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

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"StrategyRecord is changed only through its methods; cannot set {name!r}")

    def _set(self, name: str, value: object) -> None:
        object.__setattr__(self, name, value)

    def _stamp(self, at: object) -> datetime.datetime:
        _require_aware(at, "timestamp")
        if self._last_at is not None and at < self._last_at:
            raise VersionError(f"timestamp {at.isoformat()} is before the last recorded event {self._last_at.isoformat()}")
        if at > self._clock() + MAX_FUTURE_SKEW:
            raise VersionError(f"timestamp {at.isoformat()} is in the future")
        self._set("_last_at", at)
        return at

    # ---- read side -------------------------------------------------------------------------------------------

    @property
    def has_executed(self) -> bool:
        return self._executed

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
        self._refuse_while_pending("edit")
        if not self._executed:
            if based_on is not None:
                raise VersionError("before the first execution there are no versions to base an edit on")
            return self._append_history("changed", new, at)
        active = self.active_version
        if active is None:
            raise VersionError("executed with no active version: reconciliation is required before any change")
        if based_on is not None and based_on != active.number:
            raise VersionError(f"version {based_on} is not the active version ({active.number}); old versions are read-only")
        changes = new.changes_from(active.definition)
        if not changes:
            return None
        self._stamp(at)
        return self._add_version(new, active.number, at, initiator, reason, changes)

    def restore(self, seq: int, *, at: datetime.datetime) -> HistoryEntry | None:
        """Restore an earlier Builder configuration (before execution only); the current one stays in history."""
        if self._executed:
            raise VersionError("after the first execution, restore by proposing a new version")
        self._refuse_while_pending("restore")
        if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq < len(self._history):
            raise VersionError(f"no history entry {seq!r}")
        return self._append_history(f"restored entry {seq}", self._history[seq].after, at)

    def propose_execution(self, *, at: datetime.datetime, initiator: str = "user", reason: str = "") -> Version:
        """Before the first execution: turn the Builder draft into proposed version N for execution."""
        if self._executed:
            raise VersionError("already executed; changes after execution are proposed through edit()")
        self._refuse_while_pending("propose an execution")
        _require_text(initiator, "initiator")
        _require_text(reason, "reason", allow_empty=True)
        self._stamp(at)
        return self._add_version(self._draft, None, at, initiator, reason, ("execution requested",))

    def confirm(self, number: int, *, at: datetime.datetime) -> None:
        """The user's explicit confirmation of the pending proposed version."""
        if self._pending is None or number != self._pending:
            raise VersionError(f"version {number!r} is not the pending proposed version")
        if self._confirmed:
            raise VersionError(f"version {number} is already confirmed")
        self._stamp(at)
        self._set("_confirmed", True)

    def apply_result(self, result: ExecutionResult) -> ExecutionOutcome:
        """Record an execution/reconciliation result. Activates the proposal only on a reconciled COMPLETE."""
        if not isinstance(result, ExecutionResult):
            raise VersionError(f"apply_result needs an ExecutionResult, got {result!r}")
        if self._pending is None or result.version_number != self._pending:
            raise VersionError(f"version {result.version_number} is not the pending proposed version")
        if not self._confirmed:
            raise VersionError(f"version {result.version_number} was never confirmed by the user; it cannot activate")
        if result.reference in self._references:
            raise VersionError(f"result {result.reference!r} was already applied")
        if len(self._outcomes) >= MAX_OUTCOMES:
            raise VersionError(f"outcome log is full ({MAX_OUTCOMES})")
        self._stamp(result.at)
        proposal = self._versions[self._pending - 1]
        intended, previous, actual = proposal.intended_position, self._actual, result.broker_position
        kind = self._classify(result.status, intended, previous, actual)
        self._references.add(result.reference)
        self._set("_actual", actual)
        if actual.lines:
            self._set("_executed", True)
        if kind is OutcomeKind.ACTIVATED:
            self._set("_active", proposal.number)
            self._set("_executed", True)
        if kind in (OutcomeKind.ACTIVATED, OutcomeKind.REJECTED, OutcomeKind.FAILED):
            self._set("_pending", None)
            self._set("_confirmed", False)
        outcome = ExecutionOutcome(proposal.number, kind, intended, actual, result.at, result.reference)
        self._outcomes.append(outcome)
        return outcome

    # ---- internals -------------------------------------------------------------------------------------------

    @staticmethod
    def _classify(status: ResultStatus, intended: Position, previous: Position, actual: Position) -> OutcomeKind:
        if status is ResultStatus.COMPLETE:
            return OutcomeKind.ACTIVATED if actual == intended else OutcomeKind.MISMATCH
        if status is ResultStatus.PARTIAL:
            return OutcomeKind.PARTIAL
        if actual != previous:  # "rejected"/"failed" yet the broker position moved: never trust the label
            return OutcomeKind.MISMATCH
        return OutcomeKind.REJECTED if status is ResultStatus.REJECTED else OutcomeKind.FAILED

    def _refuse_while_pending(self, what: str) -> None:
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
    ) -> Version:
        if len(self._versions) >= MAX_VERSIONS:
            raise VersionError(f"version list is full ({MAX_VERSIONS})")
        version = Version(len(self._versions) + 1, definition, based_on, at, initiator, reason, changes)
        self._versions.append(version)
        self._set("_pending", version.number)
        self._set("_confirmed", False)
        return version
