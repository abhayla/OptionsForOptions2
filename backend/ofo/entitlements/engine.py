"""Access derived from entitlement events, never stored (REQ-017; ADR-023, ADR-025, ADR-038, ADR-039).

Interval rule: an entitlement gives Pro on the half-open interval ``[start, end)``. At exactly
``end`` the user is LIMITED unless another entitlement covers that instant.

Stacking rule (ADR-025 Q63, ADR-038): a referral reward starts at the later of its grant time and the
end of the user's current finite Pro coverage, and lasts the configured number of days (30 by
default). Pro until 10 Oct + a referral on 20 Sep = Pro until 9 Nov. The start is fixed when the
reward is granted, so the end date shown to the user never moves afterwards.

Indefinite coverage (a Direct Zerodha Customer) is not stacked on: it has no end to start after.
The referral is still recorded (ADR-023 T1 #272 §21 example) and runs alongside it. The spec does not
state further evaluation rules for this case (ADR-023: "not stated in the transcripts").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ofo.entitlements.events import (
    AccessLevel,
    Audit,
    EntitlementGrant,
    EntitlementStatusChange,
    Source,
    Status,
)
from ofo.entitlements.ledger import EntitlementLedger

TRIAL_DAYS_DEFAULT = 7
REFERRAL_DAYS_DEFAULT = 30


@dataclass(frozen=True)
class ResolvedEntitlement:
    """A grant together with its resolved status and effective end (``None`` = no end)."""

    grant: EntitlementGrant
    status: Status
    end: datetime | None


@dataclass(frozen=True)
class Access:
    """Access at one instant, with the entitlements that produced it. Computed, never persisted."""

    level: AccessLevel
    at: datetime
    contributing: tuple[ResolvedEntitlement, ...]


def _covers(start: datetime, end: datetime | None, at: datetime) -> bool:
    """Half-open interval test: ``start <= at < end``."""
    return start <= at and (end is None or at < end)


def _effective_end(grant: EntitlementGrant, change: EntitlementStatusChange | None) -> datetime | None:
    """A revocation or early end cuts the interval at ``effective_at``; nothing else changes it."""
    if change is None:
        return grant.expiry
    if grant.expiry is None:
        return change.effective_at
    return min(grant.expiry, change.effective_at)


def _stacked_start(granted_at: datetime, current_end: datetime, stacking: bool) -> datetime:
    """Start of a referral reward: after the current Pro end when stacking is on."""
    if stacking:
        return max(granted_at, current_end)
    return granted_at


def _require_aware(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got {value!r}")


def _require_days(days: int) -> None:
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError(f"days must be a positive whole number, got {days!r}")


def resolve(ledger: EntitlementLedger) -> tuple[ResolvedEntitlement, ...]:
    """Every entitlement in the ledger with its resolved status and effective end."""
    resolved = []
    for grant in ledger.grants():
        change = ledger.status_change(grant.entitlement_id)
        status = Status.ACTIVE if change is None else change.status
        resolved.append(ResolvedEntitlement(grant, status, _effective_end(grant, change)))
    return tuple(resolved)


def access_at(ledger: EntitlementLedger, at: datetime) -> Access:
    """PRO if any entitlement covers ``at`` (half-open), else LIMITED; with the contributing entitlements."""
    _require_aware("at", at)
    contributing = tuple(r for r in resolve(ledger) if _covers(r.grant.start, r.end, at))
    level = AccessLevel.PRO if contributing else AccessLevel.LIMITED
    return Access(level, at, contributing)


def finite_pro_end(ledger: EntitlementLedger, at: datetime) -> datetime:
    """End of the unbroken finite Pro coverage running at ``at``; ``at`` itself when there is none.

    Indefinite entitlements are ignored (see module docstring).
    """
    _require_aware("at", at)
    finite = [r for r in resolve(ledger) if r.end is not None]
    cursor = at
    while True:
        ends = [r.end for r in finite if _covers(r.grant.start, r.end, cursor)]
        if not ends or max(ends) <= cursor:
            return cursor
        cursor = max(ends)


def trial_grant(
    entitlement_id: str, registered_at: datetime, reference: str, audit: Audit, days: int = TRIAL_DAYS_DEFAULT
) -> EntitlementGrant:
    """The registration trial: Pro for ``days`` (7 by default, ADR-023 Q88) from registration."""
    _require_aware("registered_at", registered_at)
    _require_days(days)
    return EntitlementGrant(
        entitlement_id, Source.TRIAL, registered_at, registered_at + timedelta(days=days), reference, audit
    )


def grant_referral(
    ledger: EntitlementLedger,
    entitlement_id: str,
    granted_at: datetime,
    reference: str,
    audit: Audit,
    days: int = REFERRAL_DAYS_DEFAULT,
    stacking: bool = True,
) -> EntitlementLedger:
    """Record a referral reward of ``days`` days, stacked on current Pro when ``stacking`` (ADR-025, ADR-038)."""
    _require_aware("granted_at", granted_at)
    _require_days(days)
    if not isinstance(stacking, bool):
        raise ValueError(f"stacking must be True or False, got {stacking!r}")
    start = _stacked_start(granted_at, finite_pro_end(ledger, granted_at), stacking)
    grant = EntitlementGrant(entitlement_id, Source.REFERRAL, start, start + timedelta(days=days), reference, audit)
    return ledger.append(grant)


def revoke(ledger: EntitlementLedger, entitlement_id: str, effective_at: datetime, audit: Audit) -> EntitlementLedger:
    """Revoke an entitlement from ``effective_at``: a new event, the grant stays in the history."""
    return ledger.append(EntitlementStatusChange(entitlement_id, Status.REVOKED, effective_at, audit))


def end_trial_early(ledger: EntitlementLedger, trial_id: str, at: datetime, audit: Audit) -> EntitlementLedger:
    """End a RUNNING trial at ``at`` (ADR-039: an already-trialled Client ID was connected)."""
    _require_aware("at", at)
    grant = ledger.grant(trial_id)
    if grant.source is not Source.TRIAL:
        raise ValueError(f"{trial_id!r} is a {grant.source.value} entitlement, not a trial")
    change = ledger.status_change(trial_id)
    if not _covers(grant.start, _effective_end(grant, change), at):
        raise ValueError(f"trial {trial_id!r} is not running at {at.isoformat()}")
    return ledger.append(EntitlementStatusChange(trial_id, Status.ENDED, at, audit))
