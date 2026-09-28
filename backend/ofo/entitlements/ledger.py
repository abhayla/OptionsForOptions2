"""Append-only, immutable ledger of one user's entitlement events (REQ-017 AC-4).

The ledger is the input boundary: it refuses any event outside the domain, so every ledger it
accepts can be evaluated. Checks run against an index of what is already recorded, so appending one
event costs the same however long the history is.

Backdated corrections (a revocation effective before it was recorded) are refused. If one is ever
needed it must be a separate, explicit correction event with its own rules; none exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ofo.entitlements.events import EntitlementEvent, EntitlementGrant, EntitlementStatusChange, Source, Status

DEFAULT_CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class _Index:
    """What the ledger already holds, for O(1) checks of the next event."""

    last_recorded_at: datetime | None = None
    grants: dict[str, EntitlementGrant] = field(default_factory=dict)
    source_references: frozenset[tuple[Source, str]] = frozenset()
    trial_id: str | None = None
    changes: dict[str, EntitlementStatusChange] = field(default_factory=dict)

    def with_event(self, event: EntitlementEvent) -> _Index:
        if isinstance(event, EntitlementGrant):
            return _Index(
                event.audit.recorded_at,
                {**self.grants, event.entitlement_id: event},
                self.source_references | {(event.source, event.reference)},
                event.entitlement_id if event.source is Source.TRIAL else self.trial_id,
                self.changes,
            )
        return _Index(
            event.audit.recorded_at, self.grants, self.source_references, self.trial_id,
            {**self.changes, event.entitlement_id: event},
        )


# ------------------------------------------------------------------ guards (each has a mutation test)


def _check_order(index: _Index, event: EntitlementEvent) -> None:
    if index.last_recorded_at is not None and event.audit.recorded_at < index.last_recorded_at:
        raise ValueError("events must be appended in recorded_at order; the ledger is append-only")


def _check_unique_id(index: _Index, grant: EntitlementGrant) -> None:
    if grant.entitlement_id in index.grants:
        raise ValueError(f"entitlement {grant.entitlement_id!r} already granted")


def _check_unique_source_reference(index: _Index, grant: EntitlementGrant) -> None:
    if (grant.source, grant.reference) in index.source_references:
        raise ValueError(f"{grant.source.value} {grant.reference!r} is already recorded; one fact grants once")


def _check_single_trial(index: _Index, grant: EntitlementGrant) -> None:
    if grant.source is Source.TRIAL and index.trial_id is not None:
        raise ValueError("this ledger already has a trial; one trial per Client ID (ADR-022)")


def _check_not_future(grant: EntitlementGrant, skew: timedelta) -> None:
    if grant.granted_at > grant.audit.recorded_at + skew:
        raise ValueError(
            f"granted_at {grant.granted_at.isoformat()} is more than {skew} after it was recorded "
            f"({grant.audit.recorded_at.isoformat()})"
        )


def _check_change_target(index: _Index, change: EntitlementStatusChange) -> None:
    if change.entitlement_id not in index.grants:
        raise ValueError(f"no entitlement {change.entitlement_id!r} to change")
    if change.entitlement_id in index.changes:
        raise ValueError(f"entitlement {change.entitlement_id!r} is already revoked or ended")


def _check_ended_only_for_trial(index: _Index, change: EntitlementStatusChange) -> None:
    if change.status is Status.ENDED and index.grants[change.entitlement_id].source is not Source.TRIAL:
        raise ValueError("ENDED is only a trial's early end (ADR-039); revoke any other entitlement")


def _check_not_backdated(change: EntitlementStatusChange, skew: timedelta) -> None:
    if change.effective_at < change.audit.recorded_at - skew:
        raise ValueError(
            f"change effective {change.effective_at.isoformat()} is backdated before it was recorded "
            f"({change.audit.recorded_at.isoformat()}); backdated corrections need a correction event"
        )


def _check_next(index: _Index, event: EntitlementEvent, skew: timedelta) -> None:
    """Raise ``ValueError`` unless ``event`` may follow what ``index`` holds."""
    if not isinstance(event, (EntitlementGrant, EntitlementStatusChange)):
        raise ValueError(f"not an entitlement event: {event!r}")
    _check_order(index, event)
    if isinstance(event, EntitlementGrant):
        _check_unique_id(index, event)
        _check_unique_source_reference(index, event)
        _check_single_trial(index, event)
        _check_not_future(event, skew)
    else:
        _check_change_target(index, event)
        _check_ended_only_for_trial(index, event)
        _check_not_backdated(event, skew)


@dataclass(frozen=True)
class EntitlementLedger:
    """Every entitlement event of one user, in the order recorded.

    ``append`` returns a NEW ledger; nothing is ever edited or removed, so ``events`` is the complete
    audit history. ``clock_skew`` is how far a grant time may run ahead of its recording, and how far
    a status change may take effect before its recording (5 minutes by default).
    """

    user_id: str
    events: tuple[EntitlementEvent, ...] = ()
    clock_skew: timedelta = DEFAULT_CLOCK_SKEW
    _index: _Index = field(default_factory=_Index, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        if not isinstance(self.events, tuple):
            raise ValueError("events must be a tuple")
        if not isinstance(self.clock_skew, timedelta) or self.clock_skew < timedelta(0):
            raise ValueError(f"clock_skew must be a non-negative timedelta, got {self.clock_skew!r}")
        index = _Index()
        for event in self.events:
            _check_next(index, event, self.clock_skew)
            index = index.with_event(event)
        object.__setattr__(self, "_index", index)

    def append(self, event: EntitlementEvent) -> EntitlementLedger:
        """Return a new ledger with ``event`` added; raise ``ValueError`` if it is not a valid next event."""
        _check_next(self._index, event, self.clock_skew)
        appended = object.__new__(EntitlementLedger)
        object.__setattr__(appended, "user_id", self.user_id)
        object.__setattr__(appended, "events", self.events + (event,))
        object.__setattr__(appended, "clock_skew", self.clock_skew)
        object.__setattr__(appended, "_index", self._index.with_event(event))
        return appended

    def grants(self) -> tuple[EntitlementGrant, ...]:
        return tuple(self._index.grants.values())

    def grant(self, entitlement_id: str) -> EntitlementGrant:
        try:
            return self._index.grants[entitlement_id]
        except KeyError:
            raise ValueError(f"no entitlement {entitlement_id!r} in ledger of {self.user_id!r}") from None

    def status_change(self, entitlement_id: str) -> EntitlementStatusChange | None:
        return self._index.changes.get(entitlement_id)
