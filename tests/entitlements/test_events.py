"""Entitlement records store source, start, expiry, status, reference and audit (REQ-017 AC-3)."""

import dataclasses
from datetime import datetime

import pytest

from ofo.entitlements.events import Audit, EntitlementGrant, EntitlementStatusChange, Source, Status

from .helpers import audit, ist


def _grant(**overrides) -> EntitlementGrant:
    fields = dict(
        entitlement_id="paid-1",
        source=Source.PAID_ANNUAL,
        start=ist(2026, 10, 1),
        expiry=ist(2027, 10, 1),
        reference="razorpay:sub_123",
        audit=audit(ist(2026, 10, 1), "annual plan purchased", actor="user:u-1"),
    )
    fields.update(overrides)
    return EntitlementGrant(**fields)


def test_grant_stores_source_start_expiry_status_reference_and_audit():
    """AC-3: a grant keeps every stored field exactly as given, and is immutable."""
    grant = _grant()
    assert grant.source is Source.PAID_ANNUAL
    assert grant.start == ist(2026, 10, 1)
    assert grant.expiry == ist(2027, 10, 1)
    assert grant.status is Status.ACTIVE
    assert grant.reference == "razorpay:sub_123"
    assert grant.audit == Audit("user:u-1", ist(2026, 10, 1), "annual plan purchased")
    with pytest.raises(dataclasses.FrozenInstanceError):
        grant.expiry = ist(2030, 1, 1)


def test_status_change_stores_status_effective_time_and_audit():
    """AC-3: a revocation stores the new status, when it takes effect, and who/when/why."""
    change = EntitlementStatusChange("paid-1", Status.REVOKED, ist(2026, 11, 1), audit(ist(2026, 11, 1), "refund"))
    assert (change.status, change.effective_at, change.audit.reason) == (Status.REVOKED, ist(2026, 11, 1), "refund")
    with pytest.raises(ValueError, match="REVOKED or ENDED"):
        EntitlementStatusChange("paid-1", Status.ACTIVE, ist(2026, 11, 1), audit(ist(2026, 11, 1)))


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"start": datetime(2026, 10, 1)}, "timezone-aware"),
        ({"expiry": datetime(2027, 10, 1)}, "timezone-aware"),
        ({"expiry": ist(2026, 10, 1)}, "must be after start"),
        ({"expiry": ist(2026, 9, 30)}, "must be after start"),
        ({"expiry": None}, "needs an expiry"),
        ({"reference": " "}, "reference"),
        ({"entitlement_id": ""}, "entitlement_id"),
        ({"source": "PAID_ANNUAL"}, "source"),
        ({"audit": None}, "audit"),
    ],
)
def test_invalid_grants_are_refused(overrides, message):
    """AC-3: a grant missing or contradicting a stored field is refused with a clear error."""
    with pytest.raises(ValueError, match=message):
        _grant(**overrides)


def test_only_a_direct_zerodha_customer_may_have_no_expiry():
    """AC-3: expiry None is accepted for a direct customer (ADR-024 "Expiry = none") and refused for a trial."""
    direct = _grant(source=Source.DIRECT_ZERODHA_CUSTOMER, expiry=None)
    assert direct.expiry is None
    with pytest.raises(ValueError, match="needs an expiry"):
        _grant(source=Source.TRIAL, expiry=None)


@pytest.mark.parametrize(
    "actor, recorded_at, reason, message",
    [
        ("", ist(2026, 10, 1), "why", "actor"),
        ("admin", datetime(2026, 10, 1), "why", "timezone-aware"),
        ("admin", ist(2026, 10, 1), "  ", "reason"),
    ],
)
def test_audit_requires_who_when_and_why(actor, recorded_at, reason, message):
    """AC-3: an audit record without actor, aware timestamp or reason is refused."""
    with pytest.raises(ValueError, match=message):
        Audit(actor, recorded_at, reason)
