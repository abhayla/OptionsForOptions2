"""Immutable entitlement events (REQ-017 AC-2, AC-3; ADR-023).

An entitlement is created by an ``EntitlementGrant`` and can later be revoked or ended early by an
``EntitlementStatusChange``. Neither is ever edited or deleted: a change is a new event with its own
audit record. There is no free/paid flag anywhere; access is derived by ``ofo.entitlements.engine``.

All datetimes must be timezone-aware. Asia/Kolkata is a display concern only; comparisons are on
absolute instants, so any aware datetime works.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Source(Enum):
    """Where a Pro entitlement came from (ADR-023 entitlement engine list)."""

    TRIAL = "TRIAL"
    DIRECT_ZERODHA_CUSTOMER = "DIRECT_ZERODHA_CUSTOMER"
    REFERRAL = "REFERRAL"
    PAID_MONTHLY = "PAID_MONTHLY"
    PAID_ANNUAL = "PAID_ANNUAL"


class Status(Enum):
    """Status of an entitlement at a query time.

    REVOKED and ENDED are recorded by a status-change event (ENDED only for a trial, ADR-039);
    EXPIRED is never recorded: it is derived when the query time reaches the resolved expiry.
    """

    ACTIVE = "active"
    REVOKED = "revoked"
    ENDED = "ended"
    EXPIRED = "expired"


MAX_DAYS = 3650
MAX_DURATION = timedelta(days=MAX_DAYS)


class AccessLevel(Enum):
    """Derived access. LIMITED is the Expired/Limited state of ADR-023: read-only, never locked."""

    PRO = "PRO"
    LIMITED = "LIMITED"


def _require_aware(name: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware, got naive {value.isoformat()}")


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class Audit:
    """Who made a change, when it was recorded, and why (REQ-017 AC-3, AC-4)."""

    actor: str
    recorded_at: datetime
    reason: str

    def __post_init__(self) -> None:
        _require_text("actor", self.actor)
        _require_aware("recorded_at", self.recorded_at)
        _require_text("reason", self.reason)


class Placement(Enum):
    """Where a time-limited grant's days go on the timeline (ADR-023 evaluation rules 2 and 5).

    STACKED: laid end to end after the Pro already granted, in grant order (the default).
    FROM_GRANT_TIME: a referral with the admin's stacking setting switched off (ADR-025 Q63);
    it runs from its grant time and may overlap other Pro.
    """

    STACKED = "stacked"
    FROM_GRANT_TIME = "from_grant_time"


@dataclass(frozen=True)
class EntitlementGrant:
    """One entitlement as granted: the grant time and HOW MUCH Pro, not fixed dates.

    This is the RECORDED form, with the ``recorded_at`` the ledger stamped; a caller builds a ``NewGrant``.
    ``granted_at`` is when the platform grants it (within the ledger's clock skew of recording);
    ``paid_at`` optionally keeps the payment gateway's time for audit and never moves the schedule.

    ``duration`` is ``None`` only for a Direct Zerodha Customer (ADR-024: free Pro, expiry none),
    whose Pro is open-ended from ``granted_at``. For every other source the actual start and expiry
    are computed when access is evaluated (ADR-023 rule 5), so a revocation earlier in the
    sequence pulls later periods forward; see ``ofo.entitlements.engine.resolve``.
    """

    entitlement_id: str
    source: Source
    granted_at: datetime
    duration: timedelta | None
    reference: str
    audit: Audit
    placement: Placement = Placement.STACKED
    paid_at: datetime | None = None  # payment gateway's own time, audit only (a late webhook keeps it here)

    def __post_init__(self) -> None:
        _check_grant_fields(self)
        if not isinstance(self.audit, Audit):
            raise ValueError("audit must be an Audit record")


@dataclass(frozen=True)
class EntitlementStatusChange:
    """Revokes or ends an entitlement from ``effective_at`` onward. Never deletes the grant."""

    entitlement_id: str
    status: Status
    effective_at: datetime
    audit: Audit

    def __post_init__(self) -> None:
        _check_change_fields(self)
        if not isinstance(self.audit, Audit):
            raise ValueError("audit must be an Audit record")


EntitlementEvent = EntitlementGrant | EntitlementStatusChange
"""A RECORDED event: carries its ``Audit`` with the ``recorded_at`` the ledger stamped. Only stored history
(``EntitlementLedger.load``) takes these; a new event is a ``NewGrant`` / ``NewStatusChange``."""


# ------------------------------------------------------------------ new events: no recorded_at (ADR-023 Q225)


@dataclass(frozen=True)
class AuditNote:
    """The caller's part of an audit record: who and why. WHEN it is recorded is never the caller's to say:
    the ledger stamps ``recorded_at`` from its own clock (owner clarification to ADR-023 Q225, 2026-09-29)."""

    actor: str
    reason: str

    def __post_init__(self) -> None:
        _require_text("actor", self.actor)
        _require_text("reason", self.reason)


@dataclass(frozen=True)
class NewGrant:
    """A grant to be recorded: every field of ``EntitlementGrant`` except the recording time.

    ``EntitlementLedger.append`` stamps it with the ledger clock and refuses it unless ``granted_at`` lies
    within the clock skew of that stamp, both ways.
    """

    entitlement_id: str
    source: Source
    granted_at: datetime
    duration: timedelta | None
    reference: str
    note: AuditNote
    placement: Placement = Placement.STACKED
    paid_at: datetime | None = None

    def __post_init__(self) -> None:
        _check_grant_fields(self)
        if not isinstance(self.note, AuditNote):
            raise ValueError("note must be an AuditNote (who and why; the ledger stamps when)")


@dataclass(frozen=True)
class NewStatusChange:
    """A revocation or early end to be recorded; the ledger stamps it and bounds ``effective_at`` by the skew."""

    entitlement_id: str
    status: Status
    effective_at: datetime
    note: AuditNote

    def __post_init__(self) -> None:
        _check_change_fields(self)
        if not isinstance(self.note, AuditNote):
            raise ValueError("note must be an AuditNote (who and why; the ledger stamps when)")


NewEvent = NewGrant | NewStatusChange


def _check_grant_fields(grant: EntitlementGrant | NewGrant) -> None:
    """Every grant field except the audit, shared by the recorded and the new form."""
    _require_text("entitlement_id", grant.entitlement_id)
    if not isinstance(grant.source, Source):
        raise ValueError(f"source must be a Source, got {grant.source!r}")
    _require_aware("granted_at", grant.granted_at)
    _require_text("reference", grant.reference)
    if not isinstance(grant.placement, Placement):
        raise ValueError(f"placement must be a Placement, got {grant.placement!r}")
    if grant.paid_at is not None:
        if grant.source not in (Source.PAID_MONTHLY, Source.PAID_ANNUAL):
            raise ValueError("paid_at is only for a paid entitlement")
        _require_aware("paid_at", grant.paid_at)
    if grant.placement is Placement.FROM_GRANT_TIME and grant.source is not Source.REFERRAL:
        raise ValueError("only a referral can run from its grant time (stacking switched off)")
    if grant.duration is None:
        if grant.source is not Source.DIRECT_ZERODHA_CUSTOMER:
            raise ValueError(f"{grant.source.value} entitlement needs a duration; only direct customers have none")
        return
    if grant.source is Source.DIRECT_ZERODHA_CUSTOMER:
        raise ValueError("a direct customer entitlement is open-ended; it takes no duration")
    if not isinstance(grant.duration, timedelta) or grant.duration <= timedelta(0):
        raise ValueError(f"duration must be a positive timedelta, got {grant.duration!r}")
    if grant.duration > MAX_DURATION:
        raise ValueError(f"duration {grant.duration} is over the {MAX_DAYS}-day maximum")


def _check_change_fields(change: EntitlementStatusChange | NewStatusChange) -> None:
    _require_text("entitlement_id", change.entitlement_id)
    if change.status not in (Status.REVOKED, Status.ENDED):
        raise ValueError(f"a status change must be REVOKED or ENDED, got {change.status!r}")
    _require_aware("effective_at", change.effective_at)
