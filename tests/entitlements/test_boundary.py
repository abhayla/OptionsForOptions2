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
from ofo.entitlements.events import AccessLevel, NewGrant, NewStatusChange, Source, Status
from ofo.entitlements.ledger import EntitlementLedger

from .helpers import TICK, at, fixed_clock, ist, ledger_for, note, record

NOW = ist(2026, 9, 29, 12)


def _direct(granted_at: datetime, reference: str = "eligibility:row-42") -> NewGrant:
    return NewGrant("direct-1", Source.DIRECT_ZERODHA_CUSTOMER, granted_at, None, reference, note())


def _paid(entitlement_id: str, granted_at: datetime, reference: str) -> NewGrant:
    return NewGrant(
        entitlement_id, Source.PAID_MONTHLY, granted_at, timedelta(days=30), reference, note()
    )


def _resolved(led: EntitlementLedger, entitlement_id: str):
    (match,) = [r for r in resolve(led) if r.grant.entitlement_id == entitlement_id]
    return match


# ---------------------------------------------------------------- finding 1: duplicate grants


def test_second_grant_with_same_source_and_reference_is_refused():
    """AC-4: the same referral (source + reference) applied twice would give 60 days; the second is refused."""
    led = record(ledger_for("u"), referral_grant("ref-1", NOW, "referred:alice", note()))
    with pytest.raises(ValueError, match="already recorded"):
        record(led, referral_grant("ref-2", NOW, "referred:alice", note()))
    assert pro_end(led, NOW) == NOW + timedelta(days=30)
    # Same reference under a DIFFERENT source is a different fact and is accepted.
    record(led, _paid("paid-1", NOW, "referred:alice"))


def test_second_trial_in_one_ledger_is_refused():
    """AC-4: one trial per Client ID (ADR-022): a second trial grant is refused, whatever its reference."""
    led = record(ledger_for("u"), trial_grant("trial-1", NOW, "registration", note()))
    with pytest.raises(ValueError, match="already has a trial"):
        record(led, trial_grant("trial-2", NOW, "registration-again", note()))


def test_duplicate_entitlement_id_is_refused():
    """AC-4: two grants with one entitlement_id would make revocation ambiguous; the second is refused."""
    led = record(ledger_for("u"), _paid("e-1", NOW, "pay_1"))
    with pytest.raises(ValueError, match="already granted"):
        record(led, referral_grant("e-1", NOW, "row-9", note()))


# ---------------------------------------------------------------- finding 2: absurd durations


def test_durations_above_ten_years_are_refused():
    """AC-3: a duration over 3650 days is refused at construction (days=3_000_000 used to crash access_at)."""
    assert MAX_DAYS == 3650
    with pytest.raises(ValueError, match="3650"):
        referral_grant("r", NOW, "row", note(), days=3_000_000)
    with pytest.raises(ValueError, match="3650"):
        trial_grant("t", NOW, "reg", note(), days=3651)
    with pytest.raises(ValueError, match="3650"):
        NewGrant("p", Source.PAID_ANNUAL, NOW, timedelta(days=3650, microseconds=1), "pay", note())


def test_a_grant_that_would_end_past_the_representable_date_is_refused():
    """AC-1 (round 4, MINOR 3): no silent shortening near year 9999: a grant that could end past it is refused.

    Every accepted ledger is then evaluated without OverflowError, up to the last instant.
    """
    start = datetime(9990, 1, 1, tzinfo=timezone.utc)
    led = ledger_for("u", clock=fixed_clock(start))
    led = record(led, referral_grant("r0", start, "row-0", note(), days=MAX_DAYS))
    end = start + timedelta(days=MAX_DAYS)
    assert access_at(led, end - TICK).level is AccessLevel.PRO
    assert access_at(led, end).level is AccessLevel.LIMITED
    assert pro_end(led, start) == end
    with pytest.raises(ValueError, match="representable"):
        record(led, referral_grant("r1", start, "row-1", note(), days=MAX_DAYS))


# ---------------------------------------------------------------- finding 3: future grant times


def test_grant_time_far_after_its_recording_is_refused():
    """AC-4: a grant dated 2030 recorded in 2026 would push every later grant out; it is refused."""
    with pytest.raises(ValueError, match="after it was recorded"):
        record(ledger_for("u"), NewGrant("p", Source.PAID_MONTHLY, ist(2030, 1, 1), timedelta(days=30), "pay", note()), NOW)


def test_grant_time_skew_is_five_minutes_by_default_and_configurable():
    """AC-4: up to 5 minutes of clock skew is accepted, one microsecond more is not; the skew is configurable."""
    skew = timedelta(minutes=5)
    ok = NewGrant("p", Source.PAID_MONTHLY, NOW + skew, timedelta(days=30), "pay", note())
    late = NewGrant("p", Source.PAID_MONTHLY, NOW + skew + TICK, timedelta(days=30), "pay", note())
    record(ledger_for("u"), ok, NOW)
    with pytest.raises(ValueError, match="after it was recorded"):
        record(ledger_for("u"), late, NOW)
    record(ledger_for("u", clock_skew=timedelta(hours=1)), late, NOW)
    with pytest.raises(ValueError, match="clock_skew"):
        ledger_for("u", clock_skew=timedelta(minutes=-1))


# ---------------------------------------------------------------- finding 4: backdated revocations


def test_backdated_revocation_is_refused():
    """AC-4: direct revoked on day 100 effective day 5 would re-lay the banked referral into the past; refused."""
    day0 = ist(2026, 9, 1)
    led = record(ledger_for("u"), _direct(day0))
    led = record(led, referral_grant("ref-1", day0 + timedelta(days=10), "row-1", note()))
    assert banked_days(led) == 30
    with pytest.raises(ValueError, match="backdated"):
        revoke(at(led, day0 + timedelta(days=100)), "direct-1", day0 + timedelta(days=5), note("deactivated"))
    with pytest.raises(ValueError, match="backdated"):
        record(led, NewStatusChange("direct-1", Status.REVOKED, NOW - timedelta(minutes=5) - TICK, note()), NOW)
    later = record(led, NewStatusChange("direct-1", Status.REVOKED, NOW - timedelta(minutes=5), note()), NOW)
    assert banked_days(later) == 0


# ---------------------------------------------------------------- finding 5: surviving mutants


def test_revoking_a_banked_referral_cancels_its_saved_days():
    """AC-4: a revoked referral that is banked behind direct Pro no longer shows 30 days saved."""
    led = record(ledger_for("u"), _direct(NOW))
    led = record(led, referral_grant("ref-1", NOW, "row-1", note()))
    assert banked_days(led) == 30
    led = revoke(at(led, NOW + timedelta(hours=1)), "ref-1", NOW + timedelta(hours=1), note("attribution reversed"))
    assert banked_days(led) == 0
    assert _resolved(led, "ref-1").banked == timedelta(0)


# ---------------------------------------------------------------- finding 6: append cost


def test_one_thousand_appends_finish_under_two_seconds():
    """AC-4: append checks only the new event against an index, so 1,000 appends take well under 2 s."""
    led = ledger_for("u")
    started = time.perf_counter()
    for n in range(1000):
        when = NOW + timedelta(minutes=n)
        led = record(led, _paid(f"p{n}", when, f"pay_{n}"))
    elapsed = time.perf_counter() - started
    assert len(led.events) == 1000
    assert elapsed < 2.0, f"1,000 appends took {elapsed:.2f}s"


# ---------------------------------------------------------------- finding 7: raw ENDED events


def test_ended_is_only_for_a_trial():
    """AC-4: a raw ENDED status on a paid entitlement is refused; a paid period is REVOKED, a trial ENDED."""
    led = record(ledger_for("u"), _paid("p1", NOW, "pay_1"))
    with pytest.raises(ValueError, match="only a trial"):
        record(led, NewStatusChange("p1", Status.ENDED, NOW, note()))
    record(led, NewStatusChange("p1", Status.REVOKED, NOW, note()))


# ---------------------------------------------------------------- caveat 8: status at the query time


def test_status_is_evaluated_at_the_query_time():
    """AC-3: status is ACTIVE inside the period, EXPIRED from its expiry, REVOKED/ENDED from the change instant."""
    led = record(ledger_for("u"), _paid("p1", NOW, "pay_1"))
    paid = _resolved(led, "p1")
    assert paid.status_at(NOW) is Status.ACTIVE
    assert paid.status_at(NOW + timedelta(days=30) - TICK) is Status.ACTIVE
    assert paid.status_at(NOW + timedelta(days=30)) is Status.EXPIRED

    revoked_at = NOW + timedelta(days=3)
    led = revoke(at(led, revoked_at), "p1", revoked_at, note("refund"))
    paid = _resolved(led, "p1")
    assert paid.status_at(revoked_at - TICK) is Status.ACTIVE
    assert paid.status_at(revoked_at) is Status.REVOKED
    assert paid.status_at(NOW + timedelta(days=60)) is Status.REVOKED

    trial_led = record(ledger_for("u2"), trial_grant("t", NOW, "reg", note()))
    ended_at = NOW + timedelta(days=1)
    trial_led = end_trial_early(at(trial_led, ended_at), "t", ended_at, note("ADR-039"))
    assert _resolved(trial_led, "t").status_at(ended_at) is Status.ENDED


def test_banked_entitlement_is_not_expired_while_days_are_saved():
    """AC-3: a referral banked behind direct Pro is still ACTIVE (owed), not EXPIRED."""
    led = record(record(ledger_for("u"), _direct(NOW)), referral_grant("ref-1", NOW, "row-1", note()))
    assert _resolved(led, "ref-1").status_at(NOW + timedelta(days=400)) is Status.ACTIVE


# ---------------------------------------------------------------- caveat 9: ending a banked trial


def test_ending_a_banked_trial_cancels_its_remaining_days():
    """AC-4: ADR-039 on a trial paused behind direct Pro: ending it cancels the banked trial days (no second trial)."""
    registered = ist(2026, 9, 29)
    led = record(ledger_for("u"), trial_grant("trial-1", registered, "reg", note()))
    led = record(led, _direct(ist(2026, 10, 1)))
    assert banked_days(led) == 5

    connected = ist(2026, 10, 10)
    led = end_trial_early(at(led, connected), "trial-1", connected, note("Client ID already used a trial (ADR-039)"))
    assert banked_days(led) == 0
    deactivated = ist(2026, 11, 1)
    led = revoke(at(led, deactivated), "direct-1", deactivated, note("eligibility deactivated"))
    assert access_at(led, deactivated).level is AccessLevel.LIMITED
    assert _resolved(led, "trial-1").segments == ((registered, ist(2026, 10, 1)),)


# ================================================================ round 4 (second review of the class)

OCT_1 = ist(2026, 10, 1)


def test_backdated_open_ended_grant_is_refused():
    """AC-4 (round 4, MAJOR A): a DIRECT grant recorded 31 Oct dated 30 Sep would re-credit the trial days; refused."""
    led = record(ledger_for("u"), trial_grant("trial-1", OCT_1, "registration", note()))
    backdated = NewGrant(
        "direct-1", Source.DIRECT_ZERODHA_CUSTOMER, ist(2026, 9, 30), None, "eligibility:row-42", note()
    )
    with pytest.raises(ValueError, match="backdated"):
        record(led, backdated, ist(2026, 10, 31))
    # Within the skew it is accepted (same rule as a revocation).
    ok = NewGrant(
        "direct-1", Source.DIRECT_ZERODHA_CUSTOMER, ist(2026, 10, 31) - timedelta(minutes=5), None, "eligibility:row-42",
        note(),
    )
    record(led, ok, ist(2026, 10, 31))


def test_late_payment_webhook_keeps_paid_at_for_audit_and_runs_its_full_duration_from_recording():
    """AC-3 (round 4, MAJOR A): a webhook recorded 31 Oct for a payment made 30 Oct: paid_at = 30 Oct is kept,
    the 30 days run from 31 Oct (granted_at = recording time), and history is not rewritten."""
    recorded = ist(2026, 10, 31, 9)
    paid = NewGrant(
        "paid-1", Source.PAID_MONTHLY, recorded, timedelta(days=30), "pay_ABC", note("razorpay webhook"),
        paid_at=ist(2026, 10, 30, 18),
    )
    led = record(ledger_for("u"), paid)
    assert led.grant("paid-1").paid_at == ist(2026, 10, 30, 18)
    assert access_at(led, ist(2026, 10, 31)).level is AccessLevel.LIMITED
    assert pro_end(led, recorded) == recorded + timedelta(days=30)
    with pytest.raises(ValueError, match="paid_at"):
        NewGrant("r", Source.REFERRAL, recorded, timedelta(days=30), "row", note(), paid_at=recorded)
    with pytest.raises(ValueError, match="paid_at"):
        NewGrant(
            "p", Source.PAID_MONTHLY, recorded, timedelta(days=30), "pay", note(), paid_at=datetime(2026, 10, 30)
        )


def test_a_grant_dated_after_the_clock_is_refused_so_the_ledger_never_freezes():
    """AC-4 (round 4, MAJOR B; round 6): with the clock fixed at 29 Sep 12:00 a grant dated 2106 is refused, a grant
    at clock + skew is accepted and one at clock + skew + 1us refused, and later appends still work."""
    now = ist(2026, 9, 29, 12)
    led = ledger_for("u", clock=fixed_clock(now))
    far = ist(2106, 1, 1)
    with pytest.raises(ValueError, match="after it was recorded"):
        led.append(NewGrant("p", Source.PAID_MONTHLY, far, timedelta(days=30), "pay_1", note()))
    skew = timedelta(minutes=5)
    led = led.append(_paid("p1", now + skew, "pay_1"))
    with pytest.raises(ValueError, match="after it was recorded"):
        led.append(_paid("p2", now + skew + TICK, "pay_2"))
    led = led.append(_paid("p3", now + skew, "pay_3"))  # the ledger is not frozen
    assert [e.audit.recorded_at for e in led.events] == [now, now]


def test_default_clock_is_the_real_utc_now():
    """AC-4 (round 4, MAJOR B; round 6): without an injected clock the ledger stamps the real time, and a grant
    a year ahead of it is refused."""
    from ofo.entitlements.ledger import EntitlementLedger

    before = datetime.now(timezone.utc)
    led = EntitlementLedger("u").append(_paid("p1", before, "pay_1"))
    after = datetime.now(timezone.utc)
    assert before <= led.events[0].audit.recorded_at <= after
    with pytest.raises(ValueError, match="after it was recorded"):
        EntitlementLedger("u").append(_paid("p2", before + timedelta(days=365), "pay_2"))


@pytest.mark.parametrize("variant", ["alice ", "ALICE", "  Alice	"])
def test_references_are_normalised_before_the_duplicate_check(variant):
    """AC-4 (round 4, MINOR 1): "alice", "alice " and "ALICE" are one referral; the variant is refused."""
    led = record(ledger_for("u"), referral_grant("ref-1", NOW, "alice", note()))
    with pytest.raises(ValueError, match="already recorded"):
        record(led, referral_grant("ref-2", NOW, variant, note()))


def test_one_payment_reference_grants_once_across_monthly_and_annual():
    """AC-4 (round 4, MINOR 1): the same payment reference under PAID_MONTHLY and PAID_ANNUAL is one payment."""
    led = record(ledger_for("u"), _paid("p1", NOW, "pay_XYZ"))
    annual = NewGrant("p2", Source.PAID_ANNUAL, NOW, timedelta(days=365), "PAY_xyz ", note())
    with pytest.raises(ValueError, match="already recorded"):
        record(led, annual)
    # A referral and a payment that happen to share a reference are different facts: both stand.
    both = record(record(ledger_for("u"), referral_grant("r", NOW, "alice", note())), _paid("p", NOW, "alice"))
    assert len(both.grants()) == 2


def test_maximum_accumulated_free_days_cap_of_90():
    """AC-4 (round 4, MINOR 2; REQ-021 AC-5): with a 90-day cap, a 4th unused 30-day referral is refused;
    once days are used, a new one fits again. Paid days never count."""
    start = ist(2026, 10, 1)
    led = ledger_for("u", max_free_days=90)
    for n in range(3):
        led = record(led, referral_grant(f"r{n}", start, f"row-{n}", note()))
    with pytest.raises(ValueError, match="maximum accumulated free days"):
        record(led, referral_grant("r3", start, "row-3", note()))
    led = record(led, _paid("p1", start, "pay_1"))  # paid days are not free days
    later = ist(2026, 10, 31)  # 30 free days used by now: 60 unused + 30 new = 90
    led = record(led, referral_grant("r4", later, "row-4", note()))
    assert len(led.grants()) == 5


def test_free_day_cap_counts_trial_days_and_defaults_to_no_cap():
    """AC-4 (round 4, MINOR 2): trial days count toward the cap; the default (owner has not set one) is no cap."""
    start = ist(2026, 10, 1)
    capped = record(ledger_for("u", max_free_days=30), trial_grant("t", start, "reg", note()))
    with pytest.raises(ValueError, match="maximum accumulated free days"):
        record(capped, referral_grant("r0", start, "row-0", note()))
    uncapped = ledger_for("u")
    for n in range(20):
        uncapped = record(uncapped, referral_grant(f"r{n}", start, f"row-{n}", note()))
    assert len(uncapped.grants()) == 20
    for bad in (0, -1, 30.0, True):
        with pytest.raises(ValueError, match="max_free_days"):
            ledger_for("u", max_free_days=bad)
