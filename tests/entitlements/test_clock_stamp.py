"""The ledger stamps recorded_at from its own clock (REQ-017 AC-3, AC-4; ADR-023 Q225 clarification, round 6).

Owner clarification (2026-09-29, after W-007 round 5): '"recorded at" is stamped by the ledger from its own
clock; a caller can never supply it. Every new event's own date (granted/effective) must lie within the
clock-skew window of that stamp, both ways.'

Round 5's verifier broke the ledger three ways because recorded_at was a caller field bounded only from above:
(1) a revoke with recorded_at = effective_at = 3 Sep accepted on 3 Oct; (2) a paid grant recorded 8 Sep
accepted on 3 Oct (the customer paying today would lose 25 of 30 days); (3) a DIRECT grant recorded 2 Sep,
revoked 3 Oct, gave back 6 already-used trial days. Every test here uses a realistic 2026 clock (round 5's
year-9000 test clock is what hid the hole). Expected dates are hand-computed.
"""

import inspect
from datetime import datetime, timedelta

import pytest

from ofo.entitlements import engine
from ofo.entitlements.engine import access_at, pro_end, referral_grant, resolve, revoke, trial_grant
from ofo.entitlements.events import (
    AccessLevel,
    EntitlementGrant,
    EntitlementStatusChange,
    NewGrant,
    NewStatusChange,
    Source,
    Status,
)
from ofo.entitlements.ledger import EntitlementLedger

from .helpers import TICK, at, fixed_clock, ist, ledger_for, note, record, stamped

PRO = AccessLevel.PRO
LIMITED = AccessLevel.LIMITED
DAYS_30 = timedelta(days=30)
OCT_3 = ist(2026, 10, 3, 10)  # the ledger clock in the verifier's attacks


def _paid(entitlement_id: str, granted_at: datetime, paid_at: datetime | None = None) -> NewGrant:
    return NewGrant(
        entitlement_id, Source.PAID_MONTHLY, granted_at, DAYS_30, f"razorpay:{entitlement_id}", note(), paid_at=paid_at
    )


def _direct(granted_at: datetime) -> NewGrant:
    return NewGrant("direct-1", Source.DIRECT_ZERODHA_CUSTOMER, granted_at, None, "eligibility:row-42", note())


# ---------------------------------------------------------------- the three round-5 attacks


def test_attack_1_revoke_dated_25_days_back_is_refused():
    """AC-4: on 3 Oct a revoke effective 3 Sep (round 5 accepted it with recorded_at = 3 Sep) is refused as
    backdated, and the same change forged with a stamped 3 Sep audit is refused by append; Pro is untouched."""
    led = record(ledger_for("u"), _paid("p", ist(2026, 9, 20)))  # Pro 20 Sep - 20 Oct
    with pytest.raises(ValueError, match="backdated"):
        revoke(at(led, OCT_3), "p", ist(2026, 9, 3), note("fraud", actor="admin:a"))
    forged = EntitlementStatusChange("p", Status.REVOKED, ist(2026, 9, 3), stamped(ist(2026, 9, 3), "fraud"))
    with pytest.raises(ValueError, match="recorded_at is stamped by the ledger"):
        at(led, OCT_3).append(forged)
    assert led.status_change("p") is None
    assert access_at(led, OCT_3).level is PRO
    assert pro_end(led, OCT_3) == ist(2026, 10, 20)


def test_attack_2_paid_grant_dated_8_sep_is_refused_and_a_late_webhook_keeps_its_full_month():
    """AC-4: on 3 Oct a paid grant dated 8 Sep (round 5 accepted it: Pro 8 Sep - 8 Oct, 25 of 30 days lost) is
    refused; recorded the right way (granted now, the gateway's 8 Sep in paid_at) it runs 3 Oct 10:00 -
    2 Nov 10:00, the full 30 days."""
    led = ledger_for("u")
    with pytest.raises(ValueError, match="backdated"):
        record(led, _paid("p", ist(2026, 9, 8)), OCT_3)
    forged = EntitlementGrant("p", Source.PAID_MONTHLY, ist(2026, 9, 8), DAYS_30, "razorpay:p", stamped(ist(2026, 9, 8)))
    with pytest.raises(ValueError, match="recorded_at is stamped by the ledger"):
        at(led, OCT_3).append(forged)
    late = record(led, _paid("p", OCT_3, paid_at=ist(2026, 9, 8)), OCT_3)
    (paid,) = resolve(late)
    assert (paid.start, paid.expiry) == (OCT_3, ist(2026, 11, 2, 10))
    assert paid.grant.paid_at == ist(2026, 9, 8)
    assert paid.grant.audit.recorded_at == OCT_3


def test_attack_3_backdated_direct_cannot_give_back_used_trial_days():
    """AC-4: trial registered 27 Sep 00:00; on 3 Oct 10:00 a DIRECT grant dated 2 Sep is refused (round 5 banked
    the whole trial behind it and, after the 3 Oct revoke, gave Pro to 10 Oct). The real DIRECT at 3 Oct 10:00
    banks only the 14 unused hours (168 h - 154 h used), so after a revoke at 12:00 the trial ends 4 Oct 02:00."""
    led = record(ledger_for("u"), trial_grant("t", ist(2026, 9, 27), "registration", note()))
    with pytest.raises(ValueError, match="backdated"):
        record(led, _direct(ist(2026, 9, 2)), OCT_3)
    forged = EntitlementGrant(
        "direct-1", Source.DIRECT_ZERODHA_CUSTOMER, ist(2026, 9, 2), None, "eligibility:row-42", stamped(ist(2026, 9, 2))
    )
    with pytest.raises(ValueError, match="recorded_at is stamped by the ledger"):
        at(led, OCT_3).append(forged)

    led = record(led, _direct(OCT_3))
    revoked_at = ist(2026, 10, 3, 12)
    led = revoke(at(led, revoked_at), "direct-1", revoked_at, note("eligibility deactivated"))
    assert pro_end(led, revoked_at) == ist(2026, 10, 4, 2)
    assert access_at(led, ist(2026, 10, 4, 2)).level is LIMITED
    assert access_at(led, ist(2026, 10, 9)).level is LIMITED


# ---------------------------------------------------------------- recorded_at comes from the clock, never the caller


def test_recorded_at_is_the_ledger_clock_reading_for_every_new_event():
    """AC-3: a grant dated 09:57 and a revoke effective 10:02 appended at clock 10:00 are both recorded at
    10:00, the clock's reading, not their own dates."""
    clock = fixed_clock(ist(2026, 10, 1, 10))
    led = EntitlementLedger("u", clock=clock).append(_paid("p", ist(2026, 10, 1, 9, 57)))
    led = led.append(NewStatusChange("p", Status.REVOKED, ist(2026, 10, 1, 10, 2), note("refund")))
    assert [e.audit.recorded_at for e in led.events] == [ist(2026, 10, 1, 10), ist(2026, 10, 1, 10)]
    assert led.events[1].audit.reason == "refund"


def test_no_public_new_event_path_takes_a_recorded_time():
    """AC-4: append, the builders, revoke and end_trial_early, and the new-event types, have no recorded_at or
    audit parameter; passing recorded_at is a TypeError."""
    paths = [
        EntitlementLedger.append, engine.trial_grant, engine.referral_grant, engine.revoke, engine.end_trial_early,
        NewGrant, NewStatusChange,
    ]
    for path in paths:
        params = set(inspect.signature(path).parameters)
        assert not params & {"recorded_at", "audit"}, f"{path.__name__}{sorted(params)}"
    led = record(ledger_for("u"), _paid("p", ist(2026, 9, 20)))
    with pytest.raises(TypeError):
        revoke(led, "p", ist(2026, 9, 20), note(), recorded_at=ist(2026, 9, 20))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        led.append(NewStatusChange("p", Status.REVOKED, ist(2026, 9, 20), note()), recorded_at=ist(2026, 9, 20))


@pytest.mark.parametrize("bad", ["not an event", None, ("p",)])
def test_append_refuses_anything_but_a_new_event(bad):
    """AC-4: append takes only a NewGrant or NewStatusChange."""
    with pytest.raises(ValueError, match="not a new entitlement event"):
        ledger_for("u").append(bad)


def test_a_naive_or_missing_clock_reading_is_refused():
    """AC-4: a clock that returns a naive datetime (ambiguous instant) or no datetime cannot stamp an event."""
    for reading, message in ((datetime(2026, 10, 1, 10), "timezone-aware"), (None, "must be a datetime")):
        with pytest.raises(ValueError, match=message):
            EntitlementLedger("u", clock=lambda r=reading: r).append(_paid("p", ist(2026, 10, 1, 10)))


# ---------------------------------------------------------------- both skew boundaries, exactly

STAMP = ist(2026, 10, 1, 10)


@pytest.mark.parametrize("skew", [timedelta(minutes=5), timedelta(minutes=1), timedelta(0)])
def test_grant_time_boundaries_are_exactly_plus_and_minus_the_skew(skew):
    """AC-4: granted_at = stamp - skew and stamp + skew are accepted; one microsecond outside either is refused."""
    for granted, ok, message in (
        (STAMP - skew, True, None), (STAMP + skew, True, None),
        (STAMP - skew - TICK, False, "backdated"), (STAMP + skew + TICK, False, "after it was recorded"),
    ):
        led = ledger_for("u", clock=fixed_clock(STAMP), clock_skew=skew)
        if ok:
            assert led.append(_paid("p", granted)).grant("p").granted_at == granted
        else:
            with pytest.raises(ValueError, match=message):
                led.append(_paid("p", granted))


@pytest.mark.parametrize("skew", [timedelta(minutes=5), timedelta(minutes=1), timedelta(0)])
@pytest.mark.parametrize("status", [Status.REVOKED, Status.ENDED])
def test_effective_time_boundaries_are_exactly_plus_and_minus_the_skew(skew, status):
    """AC-4: effective_at = stamp - skew and stamp + skew are accepted; one microsecond outside is refused."""
    registered = ist(2026, 9, 29)
    for effective, ok, message in (
        (STAMP - skew, True, None), (STAMP + skew, True, None),
        (STAMP - skew - TICK, False, "backdated"), (STAMP + skew + TICK, False, "post-dated"),
    ):
        led = record(ledger_for("u", clock_skew=skew), trial_grant("t", registered, "reg", note()))
        change = NewStatusChange("t", status, effective, note())
        if ok:
            assert record(led, change, STAMP).status_change("t").effective_at == effective
        else:
            with pytest.raises(ValueError, match=message):
                record(led, change, STAMP)


def test_paid_at_may_be_earlier_but_never_after_the_stamp_plus_skew():
    """AC-4: paid_at (audit only) may be 25 days before the stamp (late webhook) or stamp + skew, never later."""
    skew = timedelta(minutes=5)
    for paid_at in (STAMP - timedelta(days=25), STAMP + skew):
        led = ledger_for("u", clock=fixed_clock(STAMP)).append(_paid("p", STAMP, paid_at=paid_at))
        assert led.grant("p").paid_at == paid_at
    with pytest.raises(ValueError, match="paid_at .* after it was recorded"):
        ledger_for("u", clock=fixed_clock(STAMP)).append(_paid("p", STAMP, paid_at=STAMP + skew + TICK))


# ---------------------------------------------------------------- ADR-023 examples, each recorded at its own "now"


def test_adr023_examples_replay_with_the_clock_at_each_events_time():
    """AC-4: with the ledger clock set to each event's own moment: paid to 10 Oct + referral 20 Sep -> referral
    10 Oct - 9 Nov; paid revoked 25 Sep -> referral 25 Sep - 25 Oct; trial ends 5 Oct, subscribe 2 Oct ->
    paid 5 Oct - 4 Nov. Every stamp is the clock reading at that step."""
    led = record(ledger_for("u"), _paid("paid-1", ist(2026, 9, 10)))  # 10 Sep + 30 days = 10 Oct
    led = record(led, referral_grant("ref-1", ist(2026, 9, 20, 14), "row-7", note()))
    assert [(r.start, r.expiry) for r in resolve(led)][1] == (ist(2026, 10, 10), ist(2026, 11, 9))
    revoked = revoke(at(led, ist(2026, 9, 25)), "paid-1", ist(2026, 9, 25), note("refund"))
    assert [(r.start, r.expiry) for r in resolve(revoked)][1] == (ist(2026, 9, 25), ist(2026, 10, 25))
    assert [e.audit.recorded_at for e in revoked.events] == [ist(2026, 9, 10), ist(2026, 9, 20, 14), ist(2026, 9, 25)]

    trial = record(ledger_for("u2"), trial_grant("t", ist(2026, 9, 28), "reg", note()))  # ends 5 Oct
    trial = record(trial, _paid("paid-2", ist(2026, 10, 2)))
    assert [(r.start, r.expiry) for r in resolve(trial)] == [
        (ist(2026, 9, 28), ist(2026, 10, 5)), (ist(2026, 10, 5), ist(2026, 11, 4)),
    ]
    assert [e.audit.recorded_at for e in trial.events] == [ist(2026, 9, 28), ist(2026, 10, 2)]
