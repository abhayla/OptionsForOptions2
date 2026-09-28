"""Access derived from entitlement events, never stored (REQ-017; ADR-023 evaluation rules, ADR-025, ADR-038, ADR-039).

Intervals are half-open ``[start, end)``: at exactly ``end`` the user is LIMITED unless another
entitlement covers that instant.

ADR-023 evaluation rules, all applied when access is EVALUATED (nothing is fixed at grant time):

1. Pro while at least one Pro entitlement is in force, else Limited.
2. Time-limited periods (trial, paid, stacked referral) never overlap and are never lost: each
   starts at the later of its grant time and the end of the periods granted before it.
3. While an open-ended entitlement (Direct Zerodha Customer) is in force, time-limited days are not
   consumed: they are banked and resume when it ends (e.g. eligibility deactivated).
4. Every grant is an event; ``access_at`` reports which entitlements currently give Pro.
5. Periods are laid end to end in grant order at evaluation time, so revoking or ending one early
   pulls the later periods forward.

A referral granted with stacking switched off (``Placement.FROM_GRANT_TIME``) runs from its grant
time on its own and may overlap other Pro (ADR-025 Q63 admin setting).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ofo.entitlements.events import (
    AccessLevel,
    Audit,
    EntitlementGrant,
    MAX_DAYS,
    EntitlementStatusChange,
    Placement,
    Source,
    Status,
)
from ofo.entitlements.ledger import EntitlementLedger

TRIAL_DAYS_DEFAULT = 7
REFERRAL_DAYS_DEFAULT = 30
_ZERO = timedelta(0)
# The last representable instant. Days that would run past it are cut there (year 9999; every
# accepted duration is at most MAX_DAYS, but a long chain of them can reach it), never an OverflowError.
END_OF_TIME = datetime.max.replace(tzinfo=timezone.utc)

Segment = tuple[datetime, datetime | None]  # [start, end); end None = open-ended


@dataclass(frozen=True)
class ResolvedEntitlement:
    """A grant with its status and where its Pro falls on the timeline, as evaluated now.

    ``segments`` are the half-open intervals it gives Pro in (a banked period can be split around
    an open-ended one); ``banked`` is time earned but not scheduled because open-ended Pro has no end.
    """

    grant: EntitlementGrant
    change: EntitlementStatusChange | None
    segments: tuple[Segment, ...]
    banked: timedelta

    def status_at(self, at: datetime) -> Status:
        """REVOKED/ENDED from the change's effective instant; EXPIRED once all its Pro is used; else ACTIVE."""
        _require_aware("at", at)
        if self.change is not None and at >= self.change.effective_at:
            return self.change.status
        if self.banked == _ZERO and self.segments and self.segments[-1][1] is not None and at >= self.segments[-1][1]:
            return Status.EXPIRED
        return Status.ACTIVE

    @property
    def start(self) -> datetime | None:
        """First instant of Pro from this entitlement; ``None`` if none is scheduled."""
        return self.segments[0][0] if self.segments else None

    @property
    def expiry(self) -> datetime | None:
        """End of its last scheduled segment; ``None`` if open-ended or nothing is scheduled."""
        return self.segments[-1][1] if self.segments else None


@dataclass(frozen=True)
class Access:
    """Access at one instant, with the entitlements that produced it. Computed, never persisted."""

    level: AccessLevel
    at: datetime
    contributing: tuple[ResolvedEntitlement, ...]

    @property
    def sources(self) -> tuple[Source, ...]:
        """Which sources give Pro at ``at`` (rule 4), in grant order."""
        return tuple(r.grant.source for r in self.contributing)


# ------------------------------------------------------------------ guards (each has a mutation test)


def _covers(start: datetime, end: datetime | None, at: datetime) -> bool:
    """Half-open interval test: ``start <= at < end``."""
    return start <= at and (end is None or at < end)


def _chain_start(granted_at: datetime, cursor: datetime | None) -> datetime:
    """Rule 2: a stacked period starts at the later of its grant time and the current chain end."""
    if cursor is None:
        return granted_at
    return max(granted_at, cursor)


def _placement(stacking: bool) -> Placement:
    """ADR-025 Q63: the admin stacking setting decides where a referral's days go."""
    return Placement.STACKED if stacking else Placement.FROM_GRANT_TIME


def _add(at: datetime, duration: timedelta) -> datetime:
    """``at + duration``, cut at END_OF_TIME instead of raising OverflowError."""
    try:
        return min(at + duration, END_OF_TIME)
    except OverflowError:
        return END_OF_TIME


def _consume(start: datetime, duration: timedelta, open_ended: list[Segment]) -> tuple[tuple[Segment, ...], timedelta]:
    """Rule 3: lay ``duration`` from ``start`` on time NOT covered by open-ended Pro.

    Returns the segments and the time left banked (non-zero only when an open-ended entitlement with
    no end blocks the rest).
    """
    segments: list[Segment] = []
    remaining, cursor = duration, start
    while remaining > _ZERO:
        # With the half-open _covers every blocking end is already > cursor, so the "end > cursor" test
        # is defensive only (it keeps the loop finite if _covers were ever made inclusive); nothing relies on it.
        blocking = [end for s, end in open_ended if _covers(s, end, cursor) and (end is None or end > cursor)]
        if blocking:
            if None in blocking:
                return tuple(segments), remaining
            cursor = max(e for e in blocking if e is not None)
            continue
        natural_end = _add(cursor, remaining)
        upcoming = [s for s, _ in open_ended if cursor < s < natural_end]
        if upcoming:
            cut = min(upcoming)
            segments.append((cursor, cut))
            remaining -= cut - cursor
            cursor = cut
        else:
            segments.append((cursor, natural_end))
            remaining = _ZERO
    return tuple(segments), _ZERO


def _truncate(
    segments: tuple[Segment, ...], banked: timedelta, change: EntitlementStatusChange | None
) -> tuple[tuple[Segment, ...], timedelta]:
    """A revocation or early end cuts Pro at ``effective_at`` and cancels banked (unstarted) time."""
    if change is None:
        return segments, banked
    cut = change.effective_at
    kept = tuple((s, cut if e is None else min(e, cut)) for s, e in segments if s < cut)
    return kept, _ZERO


def _owes_pro(resolved: ResolvedEntitlement, at: datetime) -> bool:
    """Caveat 9: an entitlement still owes Pro at ``at`` if it is running, queued later, or banked."""
    return resolved.banked > _ZERO or any(e is None or at < e for _, e in resolved.segments)


def _next_cursor(previous: datetime | None, natural: tuple[Segment, ...], kept: tuple[Segment, ...]) -> datetime | None:
    """Rule 5: the chain continues from where this period ACTUALLY ends (``kept``, after any revocation),
    never from where it would have ended (``natural``); continuing from ``natural`` would leave a Limited gap."""
    if kept:
        return kept[-1][1]
    return previous


# ------------------------------------------------------------------ evaluation


def _require_aware(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got {value!r}")


def _require_days(days: int) -> None:
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}, got {days!r}")


def _open_ended_segments(ledger: EntitlementLedger) -> list[Segment]:
    segments: list[Segment] = []
    for grant in ledger.grants():
        if grant.duration is None:
            kept, _ = _truncate(((grant.granted_at, None),), _ZERO, ledger.status_change(grant.entitlement_id))
            segments.extend(kept)
    return segments


def resolve(ledger: EntitlementLedger) -> tuple[ResolvedEntitlement, ...]:
    """Lay every entitlement on the timeline by the ADR-023 evaluation rules, in grant order."""
    open_ended = _open_ended_segments(ledger)
    resolved: list[ResolvedEntitlement] = []
    cursor: datetime | None = None
    chain_banked = False
    for grant in ledger.grants():
        change = ledger.status_change(grant.entitlement_id)
        if grant.duration is None:
            segments, banked = _truncate(((grant.granted_at, None),), _ZERO, change)
        elif grant.placement is Placement.FROM_GRANT_TIME:
            segments, banked = _truncate(((grant.granted_at, _add(grant.granted_at, grant.duration)),), _ZERO, change)
        else:
            if chain_banked:
                natural, banked = (), grant.duration
            else:
                natural, banked = _consume(_chain_start(grant.granted_at, cursor), grant.duration, open_ended)
            segments, banked = _truncate(natural, banked, change)
            cursor = _next_cursor(cursor, natural, segments)
            chain_banked = chain_banked or banked > _ZERO
        resolved.append(ResolvedEntitlement(grant, change, segments, banked))
    return tuple(resolved)


def access_at(ledger: EntitlementLedger, at: datetime) -> Access:
    """PRO if any entitlement's schedule covers ``at`` (half-open), else LIMITED; with who gives it."""
    _require_aware("at", at)
    contributing = tuple(r for r in resolve(ledger) if any(_covers(s, e, at) for s, e in r.segments))
    return Access(AccessLevel.PRO if contributing else AccessLevel.LIMITED, at, contributing)


def banked_time(ledger: EntitlementLedger) -> timedelta:
    """Earned Pro time waiting behind open-ended Pro (rule 3)."""
    return sum((r.banked for r in resolve(ledger)), _ZERO)


def banked_days(ledger: EntitlementLedger) -> int:
    """Whole banked days, for display ("30 referral days saved")."""
    return banked_time(ledger).days


def pro_end(ledger: EntitlementLedger, at: datetime) -> datetime | None:
    """End of the unbroken Pro coverage running at ``at``: ``None`` if open-ended, ``at`` if Limited."""
    _require_aware("at", at)
    segments = [segment for r in resolve(ledger) for segment in r.segments]
    cursor = at
    while True:
        ends = [e for s, e in segments if _covers(s, e, cursor)]
        if None in ends:
            return None
        finite = [e for e in ends if e is not None]
        # "max(finite) <= cursor" cannot happen with the half-open _covers; defensive only, nothing relies on it.
        if not finite or max(finite) <= cursor:
            return cursor
        cursor = max(finite)


# ------------------------------------------------------------------ event builders


def trial_grant(
    entitlement_id: str, registered_at: datetime, reference: str, audit: Audit, days: int = TRIAL_DAYS_DEFAULT
) -> EntitlementGrant:
    """The registration trial: ``days`` of Pro (7 by default, ADR-023 Q88) granted at registration."""
    _require_days(days)
    return EntitlementGrant(entitlement_id, Source.TRIAL, registered_at, timedelta(days=days), reference, audit)


def referral_grant(
    entitlement_id: str,
    granted_at: datetime,
    reference: str,
    audit: Audit,
    days: int = REFERRAL_DAYS_DEFAULT,
    stacking: bool = True,
) -> EntitlementGrant:
    """A referral reward of ``days`` days (ADR-038), stacked unless the admin switched stacking off."""
    _require_days(days)
    if not isinstance(stacking, bool):
        raise ValueError(f"stacking must be True or False, got {stacking!r}")
    return EntitlementGrant(
        entitlement_id, Source.REFERRAL, granted_at, timedelta(days=days), reference, audit, _placement(stacking)
    )


def revoke(ledger: EntitlementLedger, entitlement_id: str, effective_at: datetime, audit: Audit) -> EntitlementLedger:
    """Revoke an entitlement from ``effective_at``: a new event, the grant stays in the history."""
    return ledger.append(EntitlementStatusChange(entitlement_id, Status.REVOKED, effective_at, audit))


def end_trial_early(ledger: EntitlementLedger, trial_id: str, at: datetime, audit: Audit) -> EntitlementLedger:
    """End a trial that still owes Pro at ``at`` (ADR-039: an already-trialled Client ID was connected).

    Covers a running trial and one whose days are banked behind open-ended Pro: either way its
    remaining days are cancelled, because ADR-039's intent is "no second trial".
    """
    _require_aware("at", at)
    grant = ledger.grant(trial_id)
    if grant.source is not Source.TRIAL:
        raise ValueError(f"{trial_id!r} is a {grant.source.value} entitlement, not a trial")
    (trial,) = [r for r in resolve(ledger) if r.grant.entitlement_id == trial_id]
    if at < grant.granted_at or not _owes_pro(trial, at):
        raise ValueError(f"trial {trial_id!r} is not running at {at.isoformat()}")
    return ledger.append(EntitlementStatusChange(trial_id, Status.ENDED, at, audit))
