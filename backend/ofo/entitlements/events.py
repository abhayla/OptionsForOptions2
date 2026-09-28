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
    """Recorded status of an entitlement. Natural expiry is derived by the engine, not recorded."""

    ACTIVE = "active"
    REVOKED = "revoked"
    ENDED = "ended"


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

    def __post_init__(self) -> None:
        _require_text("entitlement_id", self.entitlement_id)
        if not isinstance(self.source, Source):
            raise ValueError(f"source must be a Source, got {self.source!r}")
        _require_aware("granted_at", self.granted_at)
        _require_text("reference", self.reference)
        if not isinstance(self.audit, Audit):
            raise ValueError("audit must be an Audit record")
        if not isinstance(self.placement, Placement):
            raise ValueError(f"placement must be a Placement, got {self.placement!r}")
        if self.placement is Placement.FROM_GRANT_TIME and self.source is not Source.REFERRAL:
            raise ValueError("only a referral can run from its grant time (stacking switched off)")
        if self.duration is None:
            if self.source is not Source.DIRECT_ZERODHA_CUSTOMER:
                raise ValueError(f"{self.source.value} entitlement needs a duration; only direct customers have none")
            return
        if self.source is Source.DIRECT_ZERODHA_CUSTOMER:
            raise ValueError("a direct customer entitlement is open-ended; it takes no duration")
        if not isinstance(self.duration, timedelta) or self.duration <= timedelta(0):
            raise ValueError(f"duration must be a positive timedelta, got {self.duration!r}")


@dataclass(frozen=True)
class EntitlementStatusChange:
    """Revokes or ends an entitlement from ``effective_at`` onward. Never deletes the grant."""

    entitlement_id: str
    status: Status
    effective_at: datetime
    audit: Audit

    def __post_init__(self) -> None:
        _require_text("entitlement_id", self.entitlement_id)
        if self.status not in (Status.REVOKED, Status.ENDED):
            raise ValueError(f"a status change must be REVOKED or ENDED, got {self.status!r}")
        _require_aware("effective_at", self.effective_at)
        if not isinstance(self.audit, Audit):
            raise ValueError("audit must be an Audit record")


EntitlementEvent = EntitlementGrant | EntitlementStatusChange
