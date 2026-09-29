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
    AuditNote,
    EntitlementGrant,
    EntitlementStatusChange,
    NewGrant,
    NewStatusChange,
    Placement,
    Source,
    Status,
)

from .helpers import ist, ledger_for, note, record, stamped

YEAR = timedelta(days=365)


def _grant(**overrides) -> EntitlementGrant:
    fields = dict(
        entitlement_id="paid-1",
        source=Source.PAID_ANNUAL,
        granted_at=ist(2026, 10, 1),
        duration=YEAR,
        reference="razorpay:sub_123",
        audit=stamped(ist(2026, 10, 1), "annual plan purchased", actor="user:u-1"),
    )
    fields.update(overrides)
    return EntitlementGrant(**fields)


def _new_grant(**overrides) -> NewGrant:
    fields = dict(
        entitlement_id="paid-1",
        source=Source.PAID_ANNUAL,
        granted_at=ist(2026, 10, 1),
        duration=YEAR,
        reference="razorpay:sub_123",
        note=note("annual plan purchased", actor="user:u-1"),
    )
    fields.update(overrides)
    return NewGrant(**fields)


def test_entitlement_stores_source_start_expiry_status_reference_and_audit():
    """AC-3: the recorded grant keeps source/reference as given and an audit of who/why from the caller plus
    WHEN from the ledger clock (00:03 IST 1 Oct, not the 00:00 grant time); the resolved record gives start, expiry
    and status."""
    recorded = ist(2026, 10, 1, 0, 3)  # the ledger clock, 3 minutes after the grant time (inside the 5-minute skew)
    led = record(ledger_for("u-1"), _new_grant(), recorded)
    grant = led.grant("paid-1")
    assert isinstance(grant, EntitlementGrant)
    assert grant.source is Source.PAID_ANNUAL
    assert (grant.granted_at, grant.duration) == (ist(2026, 10, 1), YEAR)
    assert grant.reference == "razorpay:sub_123"
    assert grant.audit == Audit("user:u-1", recorded, "annual plan purchased")
    assert grant.placement is Placement.STACKED
    with pytest.raises(dataclasses.FrozenInstanceError):
        grant.duration = timedelta(days=1)

    (resolved,) = resolve(led)
    assert (resolved.start, resolved.expiry, resolved.status_at(ist(2026, 10, 1))) == (ist(2026, 10, 1), ist(2027, 10, 1), Status.ACTIVE)


def test_status_change_stores_status_effective_time_and_audit():
    """AC-3: a revocation stores the new status, when it takes effect, and who/when/why."""
    change = EntitlementStatusChange("paid-1", Status.REVOKED, ist(2026, 11, 1), stamped(ist(2026, 11, 1), "refund"))
    assert (change.status, change.effective_at, change.audit.reason) == (Status.REVOKED, ist(2026, 11, 1), "refund")
    for build, who in ((EntitlementStatusChange, stamped(ist(2026, 11, 1))), (NewStatusChange, note())):
        with pytest.raises(ValueError, match="REVOKED or ENDED"):
            build("paid-1", Status.ACTIVE, ist(2026, 11, 1), who)
        with pytest.raises(ValueError, match="timezone-aware"):
            build("paid-1", Status.REVOKED, datetime(2026, 11, 1), who)
        with pytest.raises(ValueError, match="entitlement_id"):
            build(" ", Status.REVOKED, ist(2026, 11, 1), who)
    with pytest.raises(ValueError, match="audit must be an Audit"):
        EntitlementStatusChange("paid-1", Status.REVOKED, ist(2026, 11, 1), note())
    with pytest.raises(ValueError, match="note must be an AuditNote"):
        NewStatusChange("paid-1", Status.REVOKED, ist(2026, 11, 1), stamped(ist(2026, 11, 1)))


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
    """AC-3: a grant missing or contradicting a stored field is refused with a clear error, in the recorded
    form and in the new-event form alike (the new form has ``note`` in place of ``audit``)."""
    with pytest.raises(ValueError, match=message):
        _grant(**overrides)
    if "audit" in overrides:
        overrides, message = {"note": overrides["audit"]}, "note must be an AuditNote"
    with pytest.raises(ValueError, match=message):
        _new_grant(**overrides)


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


def test_a_new_event_has_no_recorded_time_to_supply():
    """AC-3 (ADR-023 Q225 clarification): the caller's audit part is who and why only; no new-event type
    has a recorded_at field, and a stamped Audit is refused where a note is expected."""
    assert [f.name for f in dataclasses.fields(AuditNote)] == ["actor", "reason"]
    for new_type in (NewGrant, NewStatusChange):
        names = [f.name for f in dataclasses.fields(new_type)]
        assert "recorded_at" not in names and "audit" not in names, new_type.__name__
    with pytest.raises(TypeError):
        AuditNote("admin", "why", recorded_at=ist(2026, 9, 3))  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="actor"):
        AuditNote(" ", "why")
    with pytest.raises(ValueError, match="reason"):
        AuditNote("admin", "")
    with pytest.raises(ValueError, match="note must be an AuditNote"):
        _new_grant(note=stamped(ist(2026, 9, 3)))
