"""Append-only, immutable ledger of one user's entitlement events (REQ-017 AC-4; ADR-023 Q225).

Two ways in, with different checks (owner decision Q225, 2026-09-29):

- A NEW event (``append`` of a ``NewGrant`` / ``NewStatusChange``) is stamped with ``recorded_at`` from the
  ledger's own clock and checked against the CURRENT settings: integrity (order, unique ids and references, one trial, a change
  names a grant not yet changed, ENDED only for a trial, representable dates) plus policy (clock,
  clock skew both ways, the free-day cap).
- STORED history (``EntitlementLedger.load``) is loaded with the integrity checks only and is never
  re-judged by today's settings: lowering the free-day cap from 90 to 30 or the skew from 5 minutes
  to 1 does not break a history that was legal when written. ``load`` takes only a ``StoredHistory``,
  which only ``EntitlementLedger.stored()`` (or the store adapter, via ``_restore``) produces, so the
  load path is not a way to add a new event without the policy checks.

Time rules for a new event (owner clarification to ADR-023 Q225, 2026-09-29: '"recorded at" is stamped by
the ledger from its own clock; a caller can never supply it. Every new event's own date (granted/effective)
must lie within the clock-skew window of that stamp, both ways.'):
- ``recorded_at`` = the ledger's ``clock()`` (real UTC now by default) at append; no public append path takes
  a recorded time, and ``append`` refuses an already-stamped ``EntitlementGrant`` / ``EntitlementStatusChange``;
- a grant's ``granted_at`` and a status change's ``effective_at`` must lie within ``clock_skew`` (5 minutes by
  default) of that stamp, both ways: nothing is backdated and nothing is post-dated;
- ``paid_at`` (the gateway's time, audit only, never moves the schedule) may be earlier than the stamp (a late
  webhook) but not later than stamp + skew.
A late payment webhook is recorded with ``granted_at`` = when we record it (the full duration runs
from then) and the gateway's own time in ``paid_at``, kept for audit; it never rewrites history.
Backdated corrections are refused; if one is ever needed it must be a separate, explicit correction
event with its own rules; none exists yet.

Checks run against an index of what is already recorded, so appending or loading one event costs the
same however long the history is (the optional free-day cap is the one exception: it evaluates the
schedule, and only for a new free grant when a cap is set).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ofo.entitlements.events import (
    Audit,
    EntitlementEvent,
    EntitlementGrant,
    EntitlementStatusChange,
    NewEvent,
    NewGrant,
    NewStatusChange,
    Source,
    Status,
)

DEFAULT_CLOCK_SKEW = timedelta(minutes=5)
FREE_SOURCES = (Source.TRIAL, Source.REFERRAL)
PAID_SOURCES = (Source.PAID_MONTHLY, Source.PAID_ANNUAL)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _reference_key(grant: EntitlementGrant) -> tuple[str, str]:
    """One fact grants once: references compare stripped and case-folded, and a payment reference is one
    payment whichever paid plan it was recorded under."""
    family = "PAID" if grant.source in PAID_SOURCES else grant.source.value
    return family, grant.reference.strip().casefold()


@dataclass(frozen=True)
class _Index:
    """What the ledger already holds, for O(1) checks of the next event."""

    last_recorded_at: datetime | None = None
    grants: dict[str, EntitlementGrant] = field(default_factory=dict)
    reference_keys: frozenset[tuple[str, str]] = frozenset()
    trial_id: str | None = None
    changes: dict[str, EntitlementStatusChange] = field(default_factory=dict)
    latest: datetime | None = None  # latest grant or effective instant recorded
    total: timedelta = timedelta(0)  # sum of every time-limited duration recorded

    def with_event(self, event: EntitlementEvent) -> _Index:
        if isinstance(event, EntitlementGrant):
            return _Index(
                event.audit.recorded_at,
                {**self.grants, event.entitlement_id: event},
                self.reference_keys | {_reference_key(event)},
                event.entitlement_id if event.source is Source.TRIAL else self.trial_id,
                self.changes,
                _later(self.latest, event.granted_at),
                self.total + (event.duration or timedelta(0)),
            )
        return _Index(
            event.audit.recorded_at, self.grants, self.reference_keys, self.trial_id,
            {**self.changes, event.entitlement_id: event},
            _later(self.latest, event.effective_at),
            self.total,
        )


def _later(a: datetime | None, b: datetime) -> datetime:
    return b if a is None else max(a, b)


# ------------------------------------------------------------------ guards (each has a mutation test)


def _check_order(index: _Index, event: EntitlementEvent) -> None:
    if index.last_recorded_at is not None and event.audit.recorded_at < index.last_recorded_at:
        raise ValueError("events must be appended in recorded_at order; the ledger is append-only")


def _check_new_event_type(draft: object) -> None:
    """``append`` takes only a NEW event; a recorded event carries a caller-chosen ``recorded_at`` (Q225)."""
    if isinstance(draft, (EntitlementGrant, EntitlementStatusChange)):
        raise ValueError(
            "append takes a NewGrant or NewStatusChange: recorded_at is stamped by the ledger's clock, "
            "never supplied by the caller"
        )
    if not isinstance(draft, (NewGrant, NewStatusChange)):
        raise ValueError(f"not a new entitlement event: {draft!r}")


def _check_constructed_empty(events: object) -> None:
    """A ledger's constructor takes no events: events carry a recorded_at, and only the ledger stamps one."""
    if events != ():
        raise ValueError(
            "a ledger is constructed empty: append new events (the ledger stamps recorded_at) or load stored history"
        )


def _stamp(draft: NewEvent, recorded_at: datetime) -> EntitlementEvent:
    """Turn a new event into its recorded form, stamped with the ledger clock's reading (``Audit`` refuses a
    reading that is not a timezone-aware datetime)."""
    audit = Audit(draft.note.actor, recorded_at, draft.note.reason)
    if isinstance(draft, NewGrant):
        return EntitlementGrant(
            draft.entitlement_id, draft.source, draft.granted_at, draft.duration, draft.reference, audit,
            draft.placement, draft.paid_at,
        )
    return EntitlementStatusChange(draft.entitlement_id, draft.status, draft.effective_at, audit)


def _check_paid_at_not_future(grant: EntitlementGrant, skew: timedelta) -> None:
    if grant.paid_at is not None and grant.paid_at > grant.audit.recorded_at + skew:
        raise ValueError(
            f"paid_at {grant.paid_at.isoformat()} is more than {skew} after it was recorded "
            f"({grant.audit.recorded_at.isoformat()}); a payment cannot be in the future"
        )


def _check_unique_id(index: _Index, grant: EntitlementGrant) -> None:
    if grant.entitlement_id in index.grants:
        raise ValueError(f"entitlement {grant.entitlement_id!r} already granted")


def _check_unique_reference(index: _Index, grant: EntitlementGrant) -> None:
    if _reference_key(grant) in index.reference_keys:
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


def _check_grant_not_backdated(grant: EntitlementGrant, skew: timedelta) -> None:
    if grant.granted_at < grant.audit.recorded_at - skew:
        raise ValueError(
            f"granted_at {grant.granted_at.isoformat()} is backdated before it was recorded "
            f"({grant.audit.recorded_at.isoformat()}); a late payment keeps its gateway time in paid_at"
        )


def _check_change_target(index: _Index, change: EntitlementStatusChange) -> None:
    if change.entitlement_id not in index.grants:
        raise ValueError(f"no entitlement {change.entitlement_id!r} to change")
    if change.entitlement_id in index.changes:
        raise ValueError(f"entitlement {change.entitlement_id!r} is already revoked or ended")


def _check_ended_only_for_trial(index: _Index, change: EntitlementStatusChange) -> None:
    if change.status is Status.ENDED and index.grants[change.entitlement_id].source is not Source.TRIAL:
        raise ValueError("ENDED is only a trial's early end (ADR-039); revoke any other entitlement")


def _check_change_not_postdated(change: EntitlementStatusChange, skew: timedelta) -> None:
    if change.effective_at > change.audit.recorded_at + skew:
        raise ValueError(
            f"change effective {change.effective_at.isoformat()} is more than {skew} after it was recorded "
            f"({change.audit.recorded_at.isoformat()}); a status change is never post-dated"
        )


def _check_not_backdated(change: EntitlementStatusChange, skew: timedelta) -> None:
    if change.effective_at < change.audit.recorded_at - skew:
        raise ValueError(
            f"change effective {change.effective_at.isoformat()} is backdated before it was recorded "
            f"({change.audit.recorded_at.isoformat()}); backdated corrections need a correction event"
        )


def _check_representable(index: _Index, event: EntitlementEvent) -> None:
    """No resolved instant can pass the last representable datetime: every period ends by the latest
    instant recorded plus the sum of all durations (a conservative bound), so check that bound."""
    after = index.with_event(event)
    try:
        after.latest + after.total
    except OverflowError:
        raise ValueError(
            "this event could place Pro past the last representable date (year 9999); refused rather than shortened"
        ) from None


def _check_free_day_cap(ledger: EntitlementLedger, grant: EntitlementGrant) -> None:
    """REQ-021 AC-5: unused free days (trial + referral, not paid) may not exceed the admin's cap."""
    if ledger.max_free_days is None or grant.source not in FREE_SOURCES:
        return
    from ofo.entitlements.engine import unused_free_time  # engine depends on ledger; import at use

    unused = unused_free_time(ledger, grant.granted_at)
    if unused + grant.duration > timedelta(days=ledger.max_free_days):
        raise ValueError(
            f"maximum accumulated free days is {ledger.max_free_days}: {unused.days} unused free days "
            f"+ {grant.duration.days} new would exceed it"
        )


def _check_event_type(event: object) -> None:
    if not isinstance(event, (EntitlementGrant, EntitlementStatusChange)):
        raise ValueError(f"not an entitlement event: {event!r}")


def _check_integrity(index: _Index, event: EntitlementEvent) -> None:
    """Checks that hold for ANY event, new or stored, whatever today's settings are."""
    _check_event_type(event)
    _check_order(index, event)
    if isinstance(event, EntitlementGrant):
        _check_unique_id(index, event)
        _check_unique_reference(index, event)
        _check_single_trial(index, event)
    else:
        _check_change_target(index, event)
        _check_ended_only_for_trial(index, event)
    _check_representable(index, event)


def _check_policy(ledger: EntitlementLedger, event: EntitlementEvent) -> None:
    """Checks against the CURRENT settings; applied to a new event only, never to stored history (Q225).

    ``event`` is already stamped with the ledger clock, so every bound below is relative to that stamp."""
    skew = ledger.clock_skew
    if isinstance(event, EntitlementGrant):
        _check_not_future(event, skew)
        _check_grant_not_backdated(event, skew)
        _check_paid_at_not_future(event, skew)
        _check_free_day_cap(ledger, event)
    else:
        _check_change_not_postdated(event, skew)
        _check_not_backdated(event, skew)


def _check_next(ledger: EntitlementLedger, event: EntitlementEvent) -> None:
    """Raise ``ValueError`` unless the stamped ``event`` may follow what ``ledger`` holds as a NEW event."""
    _check_integrity(ledger._index, event)
    _check_policy(ledger, event)


class StoredHistory:
    """A user's recorded events, as stored. Produced only by ``EntitlementLedger.stored()`` or ``_restore``.

    It cannot be built, extended or edited by a caller, so ``EntitlementLedger.load`` never receives an
    event that was not stamped and checked by a ledger when it was recorded.
    """

    __slots__ = ("user_id", "events")
    user_id: str
    events: tuple[EntitlementEvent, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("a StoredHistory comes only from EntitlementLedger.stored() or the store; append new events")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("a StoredHistory is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("a StoredHistory is immutable")

    def __repr__(self) -> str:
        return f"StoredHistory({self.user_id!r}, {len(self.events)} events)"


def _check_stored_history(history: object) -> None:
    """``load`` takes only a real StoredHistory (not a subclass, a raw sequence or a ledger)."""
    if type(history) is not StoredHistory:
        raise ValueError("load takes a StoredHistory from EntitlementLedger.stored(); append new events instead")


def _restore(user_id: str, events: tuple[EntitlementEvent, ...]) -> StoredHistory:
    """The store adapter's entry point: rows read back from the append-only store (none is built yet).

    ``load`` still runs the integrity checks on what this returns, so a corrupted store is refused.
    """
    history = object.__new__(StoredHistory)
    object.__setattr__(history, "user_id", user_id)
    object.__setattr__(history, "events", tuple(events))
    return history


@dataclass(frozen=True)
class EntitlementLedger:
    """Every entitlement event of one user, in the order recorded.

    ``append`` returns a NEW ledger; nothing is ever edited or removed, so ``events`` is the complete
    audit history. A ledger is constructed EMPTY: new events come in through ``append`` (stamped by the
    ledger clock) and stored history through ``load`` (integrity checks only, Q225); the constructor
    refuses ``events``. Settings: ``clock_skew`` (see module docstring), ``clock`` (returns an aware "now";
    real UTC by default, injected in tests) and ``max_free_days`` (admin cap on unused trial + referral
    days, REQ-021 AC-5; ``None`` = no cap, the default until the owner sets a number).
    """

    user_id: str
    events: tuple[EntitlementEvent, ...] = ()
    clock_skew: timedelta = DEFAULT_CLOCK_SKEW
    clock: Callable[[], datetime] = utc_now
    max_free_days: int | None = None
    _index: _Index = field(default_factory=_Index, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        _check_constructed_empty(self.events)
        if not isinstance(self.clock_skew, timedelta) or self.clock_skew < timedelta(0):
            raise ValueError(f"clock_skew must be a non-negative timedelta, got {self.clock_skew!r}")
        if not callable(self.clock):
            raise ValueError("clock must be a callable returning an aware datetime")
        cap = self.max_free_days
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
            raise ValueError(f"max_free_days must be a positive whole number or None, got {cap!r}")

    def _with(self, events: tuple[EntitlementEvent, ...], index: _Index) -> EntitlementLedger:
        built = object.__new__(EntitlementLedger)
        for name, value in (
            ("user_id", self.user_id), ("events", events), ("clock_skew", self.clock_skew),
            ("clock", self.clock), ("max_free_days", self.max_free_days), ("_index", index),
        ):
            object.__setattr__(built, name, value)
        return built

    def append(self, draft: NewEvent) -> EntitlementLedger:
        """Stamp ``draft`` with the ledger clock and return a new ledger with it added.

        Raise ``ValueError`` if it is not a new event, or not a valid next event under the current settings.
        """
        _check_new_event_type(draft)
        event = _stamp(draft, self.clock())
        _check_next(self, event)
        return self._with(self.events + (event,), self._index.with_event(event))

    def stored(self) -> StoredHistory:
        """This ledger's events as stored history, for ``load`` under other settings."""
        return _restore(self.user_id, self.events)

    @classmethod
    def load(
        cls,
        history: StoredHistory,
        *,
        clock_skew: timedelta = DEFAULT_CLOCK_SKEW,
        clock: Callable[[], datetime] = utc_now,
        max_free_days: int | None = None,
    ) -> EntitlementLedger:
        """Rebuild a ledger from stored history under the given (current) settings (owner decision Q225).

        Integrity checks only (order, ids, references, change targets, representable dates); caps, clock
        and skew are NOT re-applied to stored events. Events appended afterwards get the full new-event
        checks under these settings.
        """
        _check_stored_history(history)
        empty = cls(history.user_id, clock_skew=clock_skew, clock=clock, max_free_days=max_free_days)
        index = _Index()
        for event in history.events:
            _check_integrity(index, event)
            index = index.with_event(event)
        return empty._with(history.events, index)

    def grants(self) -> tuple[EntitlementGrant, ...]:
        return tuple(self._index.grants.values())

    def grant(self, entitlement_id: str) -> EntitlementGrant:
        try:
            return self._index.grants[entitlement_id]
        except KeyError:
            raise ValueError(f"no entitlement {entitlement_id!r} in ledger of {self.user_id!r}") from None

    def status_change(self, entitlement_id: str) -> EntitlementStatusChange | None:
        return self._index.changes.get(entitlement_id)
