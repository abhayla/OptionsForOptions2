"""Input-boundary guards: the ledger refuses events outside the domain (W-007 round 3, REQ-017 AC-3/AC-4).

Class: the ledger accepted duplicate grants, absurd durations, future grant times, backdated
revocations and raw status events that the builders would never produce. Each test here was red on
the round-2 code (41b1568) and names the review finding it reproduces.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from ofo.entitlements.engine import (
    MAX_DAYS,
    access_at,
    banked_days,
    end_trial_early,
    pro_end,
    referral_grant,
    resolve,
    revoke,
    trial_grant,
)
from ofo.entitlements.events import AccessLevel, EntitlementGrant, EntitlementStatusChange, Source, Status
from ofo.entitlements.ledger import EntitlementLedger

from .helpers import TICK, audit, ist

NOW = ist(2026, 9, 29, 12)


def _direct(granted_at: datetime, reference: str = "eligibility:row-42") -> EntitlementGrant:
    return EntitlementGrant("direct-1", Source.DIRECT_ZERODHA_CUSTOMER, granted_at, None, reference, audit(granted_at))


def _paid(entitlement_id: str, granted_at: datetime, reference: str) -> EntitlementGrant:
    return EntitlementGrant(
        entitlement_id, Source.PAID_MONTHLY, granted_at, timedelta(days=30), reference, audit(granted_at)
    )


def _resolved(led: EntitlementLedger, entitlement_id: str):
    (match,) = [r for r in resolve(led) if r.grant.entitlement_id == entitlement_id]
    return match


# ---------------------------------------------------------------- finding 1: duplicate grants


def test_second_grant_with_same_source_and_reference_is_refused():
    """AC-4: the same referral (source + reference) applied twice would give 60 days; the second is refused."""
    led = EntitlementLedger("u").append(referral_grant("ref-1", NOW, "referred:alice", audit(NOW)))
    with pytest.raises(ValueError, match="already recorded"):
        led.append(referral_grant("ref-2", NOW, "referred:alice", audit(NOW)))
    assert pro_end(led, NOW) == NOW + timedelta(days=30)
    # Same reference under a DIFFERENT source is a different fact and is accepted.
    led.append(_paid("paid-1", NOW, "referred:alice"))


def test_second_trial_in_one_ledger_is_refused():
    """AC-4: one trial per Client ID (ADR-022): a second trial grant is refused, whatever its reference."""
    led = EntitlementLedger("u").append(trial_grant("trial-1", NOW, "registration", audit(NOW)))
    with pytest.raises(ValueError, match="already has a trial"):
        led.append(trial_grant("trial-2", NOW, "registration-again", audit(NOW)))


def test_duplicate_entitlement_id_is_refused():
    """AC-4: two grants with one entitlement_id would make revocation ambiguous; the second is refused."""
    led = EntitlementLedger("u").append(_paid("e-1", NOW, "pay_1"))
    with pytest.raises(ValueError, match="already granted"):
        led.append(referral_grant("e-1", NOW, "row-9", audit(NOW)))


# ---------------------------------------------------------------- finding 2: absurd durations


def test_durations_above_ten_years_are_refused():
    """AC-3: a duration over 3650 days is refused at construction (days=3_000_000 used to crash access_at)."""
    assert MAX_DAYS == 3650
    with pytest.raises(ValueError, match="3650"):
        referral_grant("r", NOW, "row", audit(NOW), days=3_000_000)
    with pytest.raises(ValueError, match="3650"):
        trial_grant("t", NOW, "reg", audit(NOW), days=3651)
    with pytest.raises(ValueError, match="3650"):
        EntitlementGrant("p", Source.PAID_ANNUAL, NOW, timedelta(days=3650, microseconds=1), "pay", audit(NOW))


def test_access_never_crashes_on_an_accepted_ledger_at_the_cap_near_the_end_of_time():
    """AC-1: cap-sized grants chained past year 9999 are evaluated without OverflowError (end clamped)."""
    start = datetime(9990, 1, 1, tzinfo=timezone.utc)
    led = EntitlementLedger("u")
    for n in range(3):
        led = led.append(referral_grant(f"r{n}", start, f"row-{n}", audit(start), days=MAX_DAYS))
    last = datetime.max.replace(tzinfo=timezone.utc)
    assert access_at(led, start).level is AccessLevel.PRO
    assert access_at(led, last - TICK).level is AccessLevel.PRO
    assert pro_end(led, start) == last
    assert access_at(led, start + timedelta(days=MAX_DAYS)).sources == (Source.REFERRAL,)


# ---------------------------------------------------------------- finding 3: future grant times


def test_grant_time_far_after_its_recording_is_refused():
    """AC-4: a grant dated 2030 recorded in 2026 would push every later grant out; it is refused."""
    with pytest.raises(ValueError, match="after it was recorded"):
        EntitlementLedger("u").append(
            EntitlementGrant("p", Source.PAID_MONTHLY, ist(2030, 1, 1), timedelta(days=30), "pay", audit(NOW))
        )


def test_grant_time_skew_is_five_minutes_by_default_and_configurable():
    """AC-4: up to 5 minutes of clock skew is accepted, one microsecond more is not; the skew is configurable."""
    skew = timedelta(minutes=5)
    ok = EntitlementGrant("p", Source.PAID_MONTHLY, NOW + skew, timedelta(days=30), "pay", audit(NOW))
    late = EntitlementGrant("p", Source.PAID_MONTHLY, NOW + skew + TICK, timedelta(days=30), "pay", audit(NOW))
    EntitlementLedger("u").append(ok)
    with pytest.raises(ValueError, match="after it was recorded"):
        EntitlementLedger("u").append(late)
    EntitlementLedger("u", clock_skew=timedelta(hours=1)).append(late)
    with pytest.raises(ValueError, match="clock_skew"):
        EntitlementLedger("u", clock_skew=timedelta(minutes=-1))


# ---------------------------------------------------------------- finding 4: backdated revocations


def test_backdated_revocation_is_refused():
    """AC-4: direct revoked on day 100 effective day 5 would re-lay the banked referral into the past; refused."""
    day0 = ist(2026, 9, 1)
    led = EntitlementLedger("u").append(_direct(day0))
    led = led.append(referral_grant("ref-1", day0 + timedelta(days=10), "row-1", audit(day0 + timedelta(days=10))))
    assert banked_days(led) == 30
    with pytest.raises(ValueError, match="backdated"):
        revoke(led, "direct-1", day0 + timedelta(days=5), audit(day0 + timedelta(days=100), "deactivated"))
    with pytest.raises(ValueError, match="backdated"):
        led.append(
            EntitlementStatusChange(
                "direct-1", Status.REVOKED, NOW - timedelta(minutes=5) - TICK, audit(NOW)
            )
        )
    later = led.append(
        EntitlementStatusChange("direct-1", Status.REVOKED, NOW - timedelta(minutes=5), audit(NOW))
    )
    assert banked_days(later) == 0


# ---------------------------------------------------------------- finding 5: surviving mutants


def test_revoking_a_banked_referral_cancels_its_saved_days():
    """AC-4: a revoked referral that is banked behind direct Pro no longer shows 30 days saved."""
    led = EntitlementLedger("u").append(_direct(NOW))
    led = led.append(referral_grant("ref-1", NOW, "row-1", audit(NOW)))
    assert banked_days(led) == 30
    led = revoke(led, "ref-1", NOW + timedelta(hours=1), audit(NOW + timedelta(hours=1), "attribution reversed"))
    assert banked_days(led) == 0
    assert _resolved(led, "ref-1").banked == timedelta(0)


# ---------------------------------------------------------------- finding 6: append cost


def test_one_thousand_appends_finish_under_two_seconds():
    """AC-4: append checks only the new event against an index, so 1,000 appends take well under 2 s."""
    led = EntitlementLedger("u")
    started = time.perf_counter()
    for n in range(1000):
        at = NOW + timedelta(minutes=n)
        led = led.append(_paid(f"p{n}", at, f"pay_{n}"))
    elapsed = time.perf_counter() - started
    assert len(led.events) == 1000
    assert elapsed < 2.0, f"1,000 appends took {elapsed:.2f}s"


# ---------------------------------------------------------------- finding 7: raw ENDED events


def test_ended_is_only_for_a_trial():
    """AC-4: a raw ENDED status on a paid entitlement is refused; a paid period is REVOKED, a trial ENDED."""
    led = EntitlementLedger("u").append(_paid("p1", NOW, "pay_1"))
    with pytest.raises(ValueError, match="only a trial"):
        led.append(EntitlementStatusChange("p1", Status.ENDED, NOW, audit(NOW)))
    led.append(EntitlementStatusChange("p1", Status.REVOKED, NOW, audit(NOW)))


# ---------------------------------------------------------------- caveat 8: status at the query time


def test_status_is_evaluated_at_the_query_time():
    """AC-3: status is ACTIVE inside the period, EXPIRED from its expiry, REVOKED/ENDED from the change instant."""
    led = EntitlementLedger("u").append(_paid("p1", NOW, "pay_1"))
    paid = _resolved(led, "p1")
    assert paid.status_at(NOW) is Status.ACTIVE
    assert paid.status_at(NOW + timedelta(days=30) - TICK) is Status.ACTIVE
    assert paid.status_at(NOW + timedelta(days=30)) is Status.EXPIRED

    revoked_at = NOW + timedelta(days=3)
    led = revoke(led, "p1", revoked_at, audit(revoked_at, "refund"))
    paid = _resolved(led, "p1")
    assert paid.status_at(revoked_at - TICK) is Status.ACTIVE
    assert paid.status_at(revoked_at) is Status.REVOKED
    assert paid.status_at(NOW + timedelta(days=60)) is Status.REVOKED

    trial_led = EntitlementLedger("u2").append(trial_grant("t", NOW, "reg", audit(NOW)))
    ended_at = NOW + timedelta(days=1)
    trial_led = end_trial_early(trial_led, "t", ended_at, audit(ended_at, "ADR-039"))
    assert _resolved(trial_led, "t").status_at(ended_at) is Status.ENDED


def test_banked_entitlement_is_not_expired_while_days_are_saved():
    """AC-3: a referral banked behind direct Pro is still ACTIVE (owed), not EXPIRED."""
    led = EntitlementLedger("u").append(_direct(NOW)).append(referral_grant("ref-1", NOW, "row-1", audit(NOW)))
    assert _resolved(led, "ref-1").status_at(NOW + timedelta(days=400)) is Status.ACTIVE


# ---------------------------------------------------------------- caveat 9: ending a banked trial


def test_ending_a_banked_trial_cancels_its_remaining_days():
    """AC-4: ADR-039 on a trial paused behind direct Pro: ending it cancels the banked trial days (no second trial)."""
    registered = ist(2026, 9, 29)
    led = EntitlementLedger("u").append(trial_grant("trial-1", registered, "reg", audit(registered)))
    led = led.append(_direct(ist(2026, 10, 1)))
    assert banked_days(led) == 5

    connected = ist(2026, 10, 10)
    led = end_trial_early(led, "trial-1", connected, audit(connected, "Client ID already used a trial (ADR-039)"))
    assert banked_days(led) == 0
    deactivated = ist(2026, 11, 1)
    led = revoke(led, "direct-1", deactivated, audit(deactivated, "eligibility deactivated"))
    assert access_at(led, deactivated).level is AccessLevel.LIMITED
    assert _resolved(led, "trial-1").segments == ((registered, ist(2026, 10, 1)),)
