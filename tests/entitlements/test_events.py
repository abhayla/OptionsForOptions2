"""Entitlement records store source, start, expiry, status, reference and audit (REQ-017 AC-3).

Under ADR-023 rule 5 the start and expiry of a time-limited entitlement are computed when access is
evaluated, so the grant stores its grant time and duration, and the resolved entitlement carries the
start, expiry and status.
"""

import dataclasses
from datetime import datetime, timedelta

import pytest

from ofo.entitlements.engine import resolve
from ofo.entitlements.events import (
    Audit,
    EntitlementGrant,
    EntitlementStatusChange,
    Placement,
    Source,
    Status,
)
from ofo.entitlements.ledger import EntitlementLedger

from .helpers import audit, ist

YEAR = timedelta(days=365)


def _grant(**overrides) -> EntitlementGrant:
    fields = dict(
        entitlement_id="paid-1",
        source=Source.PAID_ANNUAL,
        granted_at=ist(2026, 10, 1),
        duration=YEAR,
        reference="razorpay:sub_123",
        audit=audit(ist(2026, 10, 1), "annual plan purchased", actor="user:u-1"),
    )
    fields.update(overrides)
    return EntitlementGrant(**fields)


def test_entitlement_stores_source_start_expiry_status_reference_and_audit():
    """AC-3: the grant keeps source/reference/audit as given; the resolved record gives start, expiry and status."""
    grant = _grant()
    assert grant.source is Source.PAID_ANNUAL
    assert (grant.granted_at, grant.duration) == (ist(2026, 10, 1), YEAR)
    assert grant.reference == "razorpay:sub_123"
    assert grant.audit == Audit("user:u-1", ist(2026, 10, 1), "annual plan purchased")
    assert grant.placement is Placement.STACKED
    with pytest.raises(dataclasses.FrozenInstanceError):
        grant.duration = timedelta(days=1)

    (resolved,) = resolve(EntitlementLedger("u-1").append(grant))
    assert (resolved.start, resolved.expiry, resolved.status) == (ist(2026, 10, 1), ist(2027, 10, 1), Status.ACTIVE)


def test_status_change_stores_status_effective_time_and_audit():
    """AC-3: a revocation stores the new status, when it takes effect, and who/when/why."""
    change = EntitlementStatusChange("paid-1", Status.REVOKED, ist(2026, 11, 1), audit(ist(2026, 11, 1), "refund"))
    assert (change.status, change.effective_at, change.audit.reason) == (Status.REVOKED, ist(2026, 11, 1), "refund")
    with pytest.raises(ValueError, match="REVOKED or ENDED"):
        EntitlementStatusChange("paid-1", Status.ACTIVE, ist(2026, 11, 1), audit(ist(2026, 11, 1)))
    with pytest.raises(ValueError, match="timezone-aware"):
        EntitlementStatusChange("paid-1", Status.REVOKED, datetime(2026, 11, 1), audit(ist(2026, 11, 1)))


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"granted_at": datetime(2026, 10, 1)}, "timezone-aware"),
        ({"duration": timedelta(0)}, "positive timedelta"),
        ({"duration": -YEAR}, "positive timedelta"),
        ({"duration": 365}, "positive timedelta"),
        ({"duration": None}, "needs a duration"),
        ({"reference": " "}, "reference"),
        ({"entitlement_id": ""}, "entitlement_id"),
        ({"source": "PAID_ANNUAL"}, "source"),
        ({"audit": None}, "audit"),
        ({"placement": Placement.FROM_GRANT_TIME}, "only a referral"),
        ({"placement": "stacked"}, "placement"),
    ],
)
def test_invalid_grants_are_refused(overrides, message):
    """AC-3: a grant missing or contradicting a stored field is refused with a clear error."""
    with pytest.raises(ValueError, match=message):
        _grant(**overrides)


def test_only_a_direct_zerodha_customer_is_open_ended():
    """AC-3: no duration is accepted for a direct customer (ADR-024 "Expiry = none") and refused for a trial."""
    direct = _grant(source=Source.DIRECT_ZERODHA_CUSTOMER, duration=None)
    assert direct.duration is None
    with pytest.raises(ValueError, match="needs a duration"):
        _grant(source=Source.TRIAL, duration=None)
    with pytest.raises(ValueError, match="open-ended"):
        _grant(source=Source.DIRECT_ZERODHA_CUSTOMER, duration=YEAR)


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
