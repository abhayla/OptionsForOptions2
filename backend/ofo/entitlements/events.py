"""Immutable entitlement events (REQ-017 AC-2, AC-3; ADR-023).

An entitlement is created by an ``EntitlementGrant`` and can later be revoked or ended early by an
``EntitlementStatusChange``. Neither is ever edited or deleted: a change is a new event with its own
audit record. There is no free/paid flag anywhere; access is derived by ``ofo.entitlements.engine``.

All datetimes must be timezone-aware. Asia/Kolkata is a display concern only; comparisons are on
absolute instants, so any aware datetime works.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Source(Enum):
    """Where a Pro entitlement came from (ADR-023 entitlement engine list)."""

    TRIAL = "TRIAL"
    DIRECT_ZERODHA_CUSTOMER = "DIRECT_ZERODHA_CUSTOMER"
    REFERRAL = "REFERRAL"
    PAID_MONTHLY = "PAID_MONTHLY"
    PAID_ANNUAL = "PAID_ANNUAL"


class Status(Enum):
    """Recorded status of an entitlement. Natural expiry is derived from ``expiry``, not recorded."""

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


@dataclass(frozen=True)
class EntitlementGrant:
    """One entitlement: Pro from ``start`` (inclusive) to ``expiry`` (exclusive).

    ``expiry`` is ``None`` only for a Direct Zerodha Customer (ADR-024: free Pro, expiry none).
    """

    entitlement_id: str
    source: Source
    start: datetime
    expiry: datetime | None
    reference: str
    audit: Audit

    def __post_init__(self) -> None:
        _require_text("entitlement_id", self.entitlement_id)
        if not isinstance(self.source, Source):
            raise ValueError(f"source must be a Source, got {self.source!r}")
        _require_aware("start", self.start)
        _require_text("reference", self.reference)
        if not isinstance(self.audit, Audit):
            raise ValueError("audit must be an Audit record")
        if self.expiry is None:
            if self.source is not Source.DIRECT_ZERODHA_CUSTOMER:
                raise ValueError(f"{self.source.value} entitlement needs an expiry; only direct customers have none")
            return
        _require_aware("expiry", self.expiry)
        if self.expiry <= self.start:
            raise ValueError(f"expiry {self.expiry.isoformat()} must be after start {self.start.isoformat()}")

    @property
    def status(self) -> Status:
        """A grant is recorded ACTIVE; a later status-change event changes the resolved status."""
        return Status.ACTIVE


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
