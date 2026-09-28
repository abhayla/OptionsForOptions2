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

from .helpers import TICK, audit, fixed_clock, ist, ledger_for

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
    led = ledger_for("u").append(referral_grant("ref-1", NOW, "referred:alice", audit(NOW)))
    with pytest.raises(ValueError, match="already recorded"):
        led.append(referral_grant("ref-2", NOW, "referred:alice", audit(NOW)))
    assert pro_end(led, NOW) == NOW + timedelta(days=30)
    # Same reference under a DIFFERENT source is a different fact and is accepted.
    led.append(_paid("paid-1", NOW, "referred:alice"))


def test_second_trial_in_one_ledger_is_refused():
    """AC-4: one trial per Client ID (ADR-022): a second trial grant is refused, whatever its reference."""
    led = ledger_for("u").append(trial_grant("trial-1", NOW, "registration", audit(NOW)))
    with pytest.raises(ValueError, match="already has a trial"):
        led.append(trial_grant("trial-2", NOW, "registration-again", audit(NOW)))


def test_duplicate_entitlement_id_is_refused():
    """AC-4: two grants with one entitlement_id would make revocation ambiguous; the second is refused."""
    led = ledger_for("u").append(_paid("e-1", NOW, "pay_1"))
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


def test_a_grant_that_would_end_past_the_representable_date_is_refused():
    """AC-1 (round 4, MINOR 3): no silent shortening near year 9999: a grant that could end past it is refused.

    Every accepted ledger is then evaluated without OverflowError, up to the last instant.
    """
    start = datetime(9990, 1, 1, tzinfo=timezone.utc)
    led = ledger_for("u", clock=fixed_clock(start))
    led = led.append(referral_grant("r0", start, "row-0", audit(start), days=MAX_DAYS))
    end = start + timedelta(days=MAX_DAYS)
    assert access_at(led, end - TICK).level is AccessLevel.PRO
    assert access_at(led, end).level is AccessLevel.LIMITED
    assert pro_end(led, start) == end
    with pytest.raises(ValueError, match="representable"):
        led.append(referral_grant("r1", start, "row-1", audit(start), days=MAX_DAYS))


# ---------------------------------------------------------------- finding 3: future grant times


def test_grant_time_far_after_its_recording_is_refused():
    """AC-4: a grant dated 2030 recorded in 2026 would push every later grant out; it is refused."""
    with pytest.raises(ValueError, match="after it was recorded"):
        ledger_for("u").append(
            EntitlementGrant("p", Source.PAID_MONTHLY, ist(2030, 1, 1), timedelta(days=30), "pay", audit(NOW))
        )


def test_grant_time_skew_is_five_minutes_by_default_and_configurable():
    """AC-4: up to 5 minutes of clock skew is accepted, one microsecond more is not; the skew is configurable."""
    skew = timedelta(minutes=5)
    ok = EntitlementGrant("p", Source.PAID_MONTHLY, NOW + skew, timedelta(days=30), "pay", audit(NOW))
    late = EntitlementGrant("p", Source.PAID_MONTHLY, NOW + skew + TICK, timedelta(days=30), "pay", audit(NOW))
    ledger_for("u").append(ok)
    with pytest.raises(ValueError, match="after it was recorded"):
        ledger_for("u").append(late)
    ledger_for("u", clock_skew=timedelta(hours=1)).append(late)
    with pytest.raises(ValueError, match="clock_skew"):
        ledger_for("u", clock_skew=timedelta(minutes=-1))


# ---------------------------------------------------------------- finding 4: backdated revocations


def test_backdated_revocation_is_refused():
    """AC-4: direct revoked on day 100 effective day 5 would re-lay the banked referral into the past; refused."""
    day0 = ist(2026, 9, 1)
    led = ledger_for("u").append(_direct(day0))
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
    led = ledger_for("u").append(_direct(NOW))
    led = led.append(referral_grant("ref-1", NOW, "row-1", audit(NOW)))
    assert banked_days(led) == 30
    led = revoke(led, "ref-1", NOW + timedelta(hours=1), audit(NOW + timedelta(hours=1), "attribution reversed"))
    assert banked_days(led) == 0
    assert _resolved(led, "ref-1").banked == timedelta(0)


# ---------------------------------------------------------------- finding 6: append cost


def test_one_thousand_appends_finish_under_two_seconds():
    """AC-4: append checks only the new event against an index, so 1,000 appends take well under 2 s."""
    led = ledger_for("u")
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
    led = ledger_for("u").append(_paid("p1", NOW, "pay_1"))
    with pytest.raises(ValueError, match="only a trial"):
        led.append(EntitlementStatusChange("p1", Status.ENDED, NOW, audit(NOW)))
    led.append(EntitlementStatusChange("p1", Status.REVOKED, NOW, audit(NOW)))


# ---------------------------------------------------------------- caveat 8: status at the query time


def test_status_is_evaluated_at_the_query_time():
    """AC-3: status is ACTIVE inside the period, EXPIRED from its expiry, REVOKED/ENDED from the change instant."""
    led = ledger_for("u").append(_paid("p1", NOW, "pay_1"))
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

    trial_led = ledger_for("u2").append(trial_grant("t", NOW, "reg", audit(NOW)))
    ended_at = NOW + timedelta(days=1)
    trial_led = end_trial_early(trial_led, "t", ended_at, audit(ended_at, "ADR-039"))
    assert _resolved(trial_led, "t").status_at(ended_at) is Status.ENDED


def test_banked_entitlement_is_not_expired_while_days_are_saved():
    """AC-3: a referral banked behind direct Pro is still ACTIVE (owed), not EXPIRED."""
    led = ledger_for("u").append(_direct(NOW)).append(referral_grant("ref-1", NOW, "row-1", audit(NOW)))
    assert _resolved(led, "ref-1").status_at(NOW + timedelta(days=400)) is Status.ACTIVE


# ---------------------------------------------------------------- caveat 9: ending a banked trial


def test_ending_a_banked_trial_cancels_its_remaining_days():
    """AC-4: ADR-039 on a trial paused behind direct Pro: ending it cancels the banked trial days (no second trial)."""
    registered = ist(2026, 9, 29)
    led = ledger_for("u").append(trial_grant("trial-1", registered, "reg", audit(registered)))
    led = led.append(_direct(ist(2026, 10, 1)))
    assert banked_days(led) == 5

    connected = ist(2026, 10, 10)
    led = end_trial_early(led, "trial-1", connected, audit(connected, "Client ID already used a trial (ADR-039)"))
    assert banked_days(led) == 0
    deactivated = ist(2026, 11, 1)
    led = revoke(led, "direct-1", deactivated, audit(deactivated, "eligibility deactivated"))
    assert access_at(led, deactivated).level is AccessLevel.LIMITED
    assert _resolved(led, "trial-1").segments == ((registered, ist(2026, 10, 1)),)


# ================================================================ round 4 (second review of the class)

OCT_1 = ist(2026, 10, 1)


def test_backdated_open_ended_grant_is_refused():
    """AC-4 (round 4, MAJOR A): a DIRECT grant recorded 31 Oct dated 30 Sep would re-credit the trial days; refused."""
    led = ledger_for("u").append(trial_grant("trial-1", OCT_1, "registration", audit(OCT_1)))
    backdated = EntitlementGrant(
        "direct-1", Source.DIRECT_ZERODHA_CUSTOMER, ist(2026, 9, 30), None, "eligibility:row-42", audit(ist(2026, 10, 31))
    )
    with pytest.raises(ValueError, match="backdated"):
        led.append(backdated)
    # Within the skew it is accepted (same rule as a revocation).
    ok = EntitlementGrant(
        "direct-1", Source.DIRECT_ZERODHA_CUSTOMER, ist(2026, 10, 31) - timedelta(minutes=5), None, "eligibility:row-42",
        audit(ist(2026, 10, 31)),
    )
    led.append(ok)


def test_late_payment_webhook_keeps_paid_at_for_audit_and_runs_its_full_duration_from_recording():
    """AC-3 (round 4, MAJOR A): a webhook recorded 31 Oct for a payment made 30 Oct: paid_at = 30 Oct is kept,
    the 30 days run from 31 Oct (granted_at = recording time), and history is not rewritten."""
    recorded = ist(2026, 10, 31, 9)
    paid = EntitlementGrant(
        "paid-1", Source.PAID_MONTHLY, recorded, timedelta(days=30), "pay_ABC", audit(recorded, "razorpay webhook"),
        paid_at=ist(2026, 10, 30, 18),
    )
    led = ledger_for("u").append(paid)
    assert led.grant("paid-1").paid_at == ist(2026, 10, 30, 18)
    assert access_at(led, ist(2026, 10, 31)).level is AccessLevel.LIMITED
    assert pro_end(led, recorded) == recorded + timedelta(days=30)
    with pytest.raises(ValueError, match="paid_at"):
        EntitlementGrant("r", Source.REFERRAL, recorded, timedelta(days=30), "row", audit(recorded), paid_at=recorded)
    with pytest.raises(ValueError, match="paid_at"):
        EntitlementGrant(
            "p", Source.PAID_MONTHLY, recorded, timedelta(days=30), "pay", audit(recorded), paid_at=datetime(2026, 10, 30)
        )


def test_recorded_at_after_the_clock_is_refused_so_the_ledger_never_freezes():
    """AC-4 (round 4, MAJOR B): a grant recorded in 2106 is refused against the injected clock, so later appends work."""
    now = ist(2026, 9, 29, 12)
    led = ledger_for("u", clock=fixed_clock(now))
    far = ist(2106, 1, 1)
    with pytest.raises(ValueError, match="clock"):
        led.append(EntitlementGrant("p", Source.PAID_MONTHLY, far, timedelta(days=30), "pay_1", audit(far)))
    skew = timedelta(minutes=5)
    led = led.append(_paid("p1", now + skew, "pay_1"))
    with pytest.raises(ValueError, match="clock"):
        led.append(_paid("p2", now + skew + TICK, "pay_2"))
    led.append(_paid("p3", now + skew, "pay_3"))  # the ledger is not frozen


def test_default_clock_is_the_real_utc_now():
    """AC-4 (round 4, MAJOR B): without an injected clock the ledger uses the real time: a grant a year ahead is refused."""
    from ofo.entitlements.ledger import EntitlementLedger

    real_now = datetime.now(timezone.utc)
    EntitlementLedger("u").append(_paid("p1", real_now, "pay_1"))
    ahead = real_now + timedelta(days=365)
    with pytest.raises(ValueError, match="clock"):
        EntitlementLedger("u").append(_paid("p2", ahead, "pay_2"))


@pytest.mark.parametrize("variant", ["alice ", "ALICE", "  Alice	"])
def test_references_are_normalised_before_the_duplicate_check(variant):
    """AC-4 (round 4, MINOR 1): "alice", "alice " and "ALICE" are one referral; the variant is refused."""
    led = ledger_for("u").append(referral_grant("ref-1", NOW, "alice", audit(NOW)))
    with pytest.raises(ValueError, match="already recorded"):
        led.append(referral_grant("ref-2", NOW, variant, audit(NOW)))


def test_one_payment_reference_grants_once_across_monthly_and_annual():
    """AC-4 (round 4, MINOR 1): the same payment reference under PAID_MONTHLY and PAID_ANNUAL is one payment."""
    led = ledger_for("u").append(_paid("p1", NOW, "pay_XYZ"))
    annual = EntitlementGrant("p2", Source.PAID_ANNUAL, NOW, timedelta(days=365), "PAY_xyz ", audit(NOW))
    with pytest.raises(ValueError, match="already recorded"):
        led.append(annual)
    # A referral and a payment that happen to share a reference are different facts: both stand.
    both = ledger_for("u").append(referral_grant("r", NOW, "alice", audit(NOW))).append(_paid("p", NOW, "alice"))
    assert len(both.grants()) == 2


def test_maximum_accumulated_free_days_cap_of_90():
    """AC-4 (round 4, MINOR 2; REQ-021 AC-5): with a 90-day cap, a 4th unused 30-day referral is refused;
    once days are used, a new one fits again. Paid days never count."""
    start = ist(2026, 10, 1)
    led = ledger_for("u", max_free_days=90)
    for n in range(3):
        led = led.append(referral_grant(f"r{n}", start, f"row-{n}", audit(start)))
    with pytest.raises(ValueError, match="maximum accumulated free days"):
        led.append(referral_grant("r3", start, "row-3", audit(start)))
    led = led.append(_paid("p1", start, "pay_1"))  # paid days are not free days
    later = ist(2026, 10, 31)  # 30 free days used by now: 60 unused + 30 new = 90
    led = led.append(referral_grant("r4", later, "row-4", audit(later)))
    assert len(led.grants()) == 5


def test_free_day_cap_counts_trial_days_and_defaults_to_no_cap():
    """AC-4 (round 4, MINOR 2): trial days count toward the cap; the default (owner has not set one) is no cap."""
    start = ist(2026, 10, 1)
    capped = ledger_for("u", max_free_days=30).append(trial_grant("t", start, "reg", audit(start)))
    with pytest.raises(ValueError, match="maximum accumulated free days"):
        capped.append(referral_grant("r0", start, "row-0", audit(start)))
    uncapped = ledger_for("u")
    for n in range(20):
        uncapped = uncapped.append(referral_grant(f"r{n}", start, f"row-{n}", audit(start)))
    assert len(uncapped.grants()) == 20
    for bad in (0, -1, 30.0, True):
        with pytest.raises(ValueError, match="max_free_days"):
            ledger_for("u", max_free_days=bad)
