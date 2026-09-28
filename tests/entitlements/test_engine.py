"""Entitlement engine: derived access, sources, combination and audit (REQ-017 AC-1, AC-2, AC-4).

Rules under test: ADR-023 "Evaluation rules" 1-5 (ADR-045 delegation). Intervals are half-open
[start, end): at exactly ``end`` the user is LIMITED. Boundaries are checked one microsecond (TICK)
either side.
"""

import dataclasses
import typing
from datetime import datetime, timedelta

import pytest

from ofo.entitlements import engine, events, ledger as ledger_module
from ofo.entitlements.engine import (
    access_at,
    banked_days,
    end_trial_early,
    pro_end,
    referral_grant,
    resolve,
    revoke,
    trial_grant,
)
from ofo.entitlements.events import AccessLevel, EntitlementGrant, Source, Status
from ofo.entitlements.ledger import EntitlementLedger

from .helpers import TICK, audit, ist

PRO = AccessLevel.PRO
LIMITED = AccessLevel.LIMITED
DAYS_30 = timedelta(days=30)


def _paid(entitlement_id: str, granted_at: datetime, duration: timedelta = DAYS_30) -> EntitlementGrant:
    return EntitlementGrant(
        entitlement_id, Source.PAID_MONTHLY, granted_at, duration, f"razorpay:{entitlement_id}", audit(granted_at)
    )


def _direct(granted_at: datetime) -> EntitlementGrant:
    return EntitlementGrant(
        "direct-1", Source.DIRECT_ZERODHA_CUSTOMER, granted_at, None, "eligibility:list-row-42", audit(granted_at)
    )


def _paid_until_10_oct() -> EntitlementLedger:
    """Pro until 10 Oct 2026 00:00 IST: a 30-day paid period granted 10 Sep (the ADR-025 Q63 starting state)."""
    return EntitlementLedger("user-1").append(_paid("paid-1", ist(2026, 9, 10)))


def _with_referral_on_20_sep() -> EntitlementLedger:
    return _paid_until_10_oct().append(
        referral_grant("ref-1", ist(2026, 9, 20, 14), "ap-report:row-7", audit(ist(2026, 9, 20, 14)))
    )


def _level(led: EntitlementLedger, at) -> AccessLevel:
    return access_at(led, at).level


def _resolved(led: EntitlementLedger, entitlement_id: str) -> engine.ResolvedEntitlement:
    (match,) = [r for r in resolve(led) if r.grant.entitlement_id == entitlement_id]
    return match


# ---------------------------------------------------------------- AC-1: access is derived, never a flag


def test_trial_boundaries_seven_days_from_registration():
    """AC-1: a trial registered 29 Sep 10:15:30 IST gives Pro on [29 Sep 10:15:30, 6 Oct 10:15:30) and no longer."""
    registered = ist(2026, 9, 29, 10, 15, 30)
    led = EntitlementLedger("user-1").append(trial_grant("trial-1", registered, "registration", audit(registered)))
    trial_end = ist(2026, 10, 6, 10, 15, 30)

    assert (_resolved(led, "trial-1").start, _resolved(led, "trial-1").expiry) == (registered, trial_end)
    assert _level(led, registered - TICK) is LIMITED
    assert _level(led, registered) is PRO
    assert _level(led, trial_end - TICK) is PRO
    assert _level(led, trial_end) is LIMITED
    assert access_at(led, registered).sources == (Source.TRIAL,)
    assert access_at(led, trial_end).contributing == ()


def test_no_boolean_free_or_paid_field_and_access_is_recomputed_from_events():
    """AC-1: no boolean or free/paid/pro field exists on any record; appending an event changes derived access."""
    records = [
        events.Audit, events.EntitlementGrant, events.EntitlementStatusChange,
        ledger_module.EntitlementLedger, engine.ResolvedEntitlement, engine.Access,
    ]
    for record in records:
        hints = typing.get_type_hints(record)
        for field in dataclasses.fields(record):
            assert hints[field.name] is not bool, f"{record.__name__}.{field.name} is a boolean flag"
            lowered = field.name.lower()
            assert not any(word in lowered for word in ("free", "paid", "is_pro", "premium")), (
                f"{record.__name__}.{field.name} looks like a stored free/paid flag"
            )

    empty = EntitlementLedger("user-1")
    with_trial = empty.append(trial_grant("trial-1", ist(2026, 9, 29), "registration", audit(ist(2026, 9, 29))))
    assert _level(empty, ist(2026, 9, 30)) is LIMITED  # the original ledger is untouched
    assert _level(with_trial, ist(2026, 9, 30)) is PRO


def test_naive_query_time_is_refused():
    """AC-1: a naive datetime is ambiguous about the instant, so access_at refuses it."""
    with pytest.raises(ValueError, match="timezone-aware"):
        access_at(_paid_until_10_oct(), datetime(2026, 9, 20))


# ---------------------------------------------------------------- AC-2: sources


def test_sources_are_exactly_the_spec_list_and_limited_is_derived():
    """AC-2: sources are Trial, Direct Zerodha Customer, Referral, Paid Monthly, Paid Annual; Expired/Limited is derived."""
    assert {s.value for s in Source} == {
        "TRIAL", "DIRECT_ZERODHA_CUSTOMER", "REFERRAL", "PAID_MONTHLY", "PAID_ANNUAL",
    }
    assert {a.value for a in AccessLevel} == {"PRO", "LIMITED"}
    assert _level(EntitlementLedger("user-1"), ist(2026, 9, 29)) is LIMITED


@pytest.mark.parametrize("source", [Source.TRIAL, Source.REFERRAL, Source.PAID_MONTHLY, Source.PAID_ANNUAL])
def test_each_time_limited_source_gives_pro_only_inside_its_window(source):
    """AC-2: every time-limited source gives Pro on [granted, granted + duration) and Limited after (no grace, ADR-026)."""
    granted = ist(2026, 10, 1)
    led = EntitlementLedger("user-1").append(EntitlementGrant("e-1", source, granted, DAYS_30, "ref-1", audit(granted)))
    assert _level(led, granted - TICK) is LIMITED
    assert _level(led, granted) is PRO
    assert access_at(led, granted).sources == (source,)
    assert _level(led, ist(2026, 10, 31) - TICK) is PRO
    assert _level(led, ist(2026, 10, 31)) is LIMITED


def test_direct_zerodha_customer_pro_has_no_end_while_active():
    """AC-2: Direct Zerodha Customer Pro is open-ended (ADR-024) and stays Pro decades later."""
    start = ist(2026, 9, 29, 9)
    led = EntitlementLedger("user-1").append(_direct(start))
    assert _level(led, start - TICK) is LIMITED
    assert _level(led, start) is PRO
    assert _level(led, ist(2099, 12, 31)) is PRO
    assert _resolved(led, "direct-1").expiry is None
    assert pro_end(led, start) is None


# ---------------------------------------------------------------- AC-4: combination (ADR-023 rules 2, 3, 5) and audit


def test_stacked_referral_real_example_pro_until_10_oct_plus_referral_on_20_sep_is_9_nov():
    """AC-4: Pro until 10 Oct + a referral granted 20 Sep = Pro until 9 Nov (ADR-025 Q63, ADR-038: 30 days)."""
    led = _with_referral_on_20_sep()
    referral = _resolved(led, "ref-1")
    assert referral.segments == ((ist(2026, 10, 10), ist(2026, 11, 9)),)
    assert _level(led, ist(2026, 10, 10) - TICK) is PRO
    assert access_at(led, ist(2026, 10, 10)).sources == (Source.REFERRAL,)
    assert _level(led, ist(2026, 11, 9) - TICK) is PRO
    assert _level(led, ist(2026, 11, 9)) is LIMITED
    assert pro_end(led, ist(2026, 9, 20)) == ist(2026, 11, 9)


def test_three_stacked_referrals_add_ninety_days():
    """AC-4: three referrals stack end to end: 10 Oct + 90 days = 8 Jan 2027 (ADR-038)."""
    led = _paid_until_10_oct()
    for n in range(3):
        led = led.append(referral_grant(f"ref-{n}", ist(2026, 9, 20, 14 + n), f"row-{n}", audit(ist(2026, 9, 20, 14 + n))))
    assert _resolved(led, "ref-2").segments == ((ist(2026, 12, 9), ist(2027, 1, 8)),)
    assert pro_end(led, ist(2026, 9, 21)) == ist(2027, 1, 8)
    assert _level(led, ist(2027, 1, 8)) is LIMITED


def test_rule2_paid_bought_during_trial_starts_when_the_trial_ends():
    """AC-4: rule 2: trial ends 5 Oct, subscribe 2 Oct -> paid runs from 5 Oct; no overlap, no lost day.

    A 30-day paid period is [5 Oct 00:00, 4 Nov 00:00): the last day of Pro is 3 Nov ("5 Oct - 3 Nov").
    """
    registered = ist(2026, 9, 28)
    led = EntitlementLedger("user-1").append(trial_grant("trial-1", registered, "registration", audit(registered)))
    led = led.append(_paid("paid-1", ist(2026, 10, 2)))

    assert _resolved(led, "trial-1").segments == ((registered, ist(2026, 10, 5)),)
    assert _resolved(led, "paid-1").segments == ((ist(2026, 10, 5), ist(2026, 11, 4)),)
    assert access_at(led, ist(2026, 10, 3)).sources == (Source.TRIAL,)  # no overlap
    assert access_at(led, ist(2026, 10, 5)).sources == (Source.PAID_MONTHLY,)
    assert _level(led, ist(2026, 11, 3, 23, 59, 59)) is PRO
    assert _level(led, ist(2026, 11, 4)) is LIMITED


def test_rule2_a_grant_after_a_gap_starts_at_its_grant_time():
    """AC-4: rule 2 red case: a Limited user's referral does not reach back; it starts when granted."""
    led = _paid_until_10_oct().append(referral_grant("ref-1", ist(2026, 12, 1, 9), "row-1", audit(ist(2026, 12, 1, 9))))
    assert _resolved(led, "ref-1").segments == ((ist(2026, 12, 1, 9), ist(2026, 12, 31, 9)),)
    assert _level(led, ist(2026, 11, 1)) is LIMITED


def test_stacking_off_runs_the_referral_from_its_grant_time_and_may_overlap():
    """AC-4: with stacking switched off the referral runs 20 Sep 14:00 - 20 Oct 14:00, overlapping the paid period."""
    led = _paid_until_10_oct().append(
        referral_grant("ref-1", ist(2026, 9, 20, 14), "row-1", audit(ist(2026, 9, 20, 14)), stacking=False)
    )
    assert _resolved(led, "ref-1").segments == ((ist(2026, 9, 20, 14), ist(2026, 10, 20, 14)),)
    assert access_at(led, ist(2026, 9, 25)).sources == (Source.PAID_MONTHLY, Source.REFERRAL)
    assert _level(led, ist(2026, 10, 20, 14)) is LIMITED


def test_rule3_referral_days_are_banked_during_direct_pro_and_start_when_it_ends():
    """AC-4: rule 3: a referral during Direct Customer Pro is recorded, banked (30 days saved), and starts on deactivation."""
    led = EntitlementLedger("user-1").append(_direct(ist(2026, 9, 1)))
    led = led.append(referral_grant("ref-1", ist(2026, 9, 20), "row-1", audit(ist(2026, 9, 20))))

    assert [g.entitlement_id for g in led.grants()] == ["direct-1", "ref-1"]
    assert banked_days(led) == 30
    assert _resolved(led, "ref-1").segments == ()
    assert access_at(led, ist(2026, 9, 25)).sources == (Source.DIRECT_ZERODHA_CUSTOMER,)

    deactivated = revoke(led, "direct-1", ist(2026, 12, 1), audit(ist(2026, 12, 1), "eligibility deactivated", "admin:a"))
    assert banked_days(deactivated) == 0
    assert _resolved(deactivated, "ref-1").segments == ((ist(2026, 12, 1), ist(2026, 12, 31)),)
    assert access_at(deactivated, ist(2026, 12, 1)).sources == (Source.REFERRAL,)
    assert _level(deactivated, ist(2026, 12, 31) - TICK) is PRO
    assert _level(deactivated, ist(2026, 12, 31)) is LIMITED


def test_rule3_a_running_referral_pauses_while_direct_pro_is_in_force():
    """AC-4: rule 3: 10 of 30 referral days used before direct Pro starts; the other 20 are banked, then resume."""
    led = EntitlementLedger("user-1").append(referral_grant("ref-1", ist(2026, 9, 1), "row-1", audit(ist(2026, 9, 1))))
    led = led.append(_direct(ist(2026, 9, 11)))
    assert banked_days(led) == 20
    assert _resolved(led, "ref-1").segments == ((ist(2026, 9, 1), ist(2026, 9, 11)),)

    led = revoke(led, "direct-1", ist(2026, 11, 1), audit(ist(2026, 11, 1), "eligibility deactivated"))
    assert _resolved(led, "ref-1").segments == ((ist(2026, 9, 1), ist(2026, 9, 11)), (ist(2026, 11, 1), ist(2026, 11, 21)))
    assert _level(led, ist(2026, 11, 21)) is LIMITED


def test_rule5_revoking_paid_pulls_the_stacked_referral_forward():
    """AC-4: rule 5: paid to 10 Oct + referral granted 20 Sep (10 Oct - 9 Nov); paid revoked 25 Sep -> referral 25 Sep - 25 Oct."""
    before = _with_referral_on_20_sep()
    led = revoke(before, "paid-1", ist(2026, 9, 25), audit(ist(2026, 9, 25), "refund", actor="admin:ops"))

    assert _resolved(led, "ref-1").segments == ((ist(2026, 9, 25), ist(2026, 10, 25)),)
    assert _level(led, ist(2026, 9, 25) - TICK) is PRO
    assert access_at(led, ist(2026, 9, 25)).sources == (Source.REFERRAL,)  # no Limited gap
    assert _level(led, ist(2026, 10, 25) - TICK) is PRO
    assert _level(led, ist(2026, 10, 25)) is LIMITED
    assert len(led.events) == len(before.events) + 1
    assert led.events[:2] == before.events  # nothing deleted or edited


def test_rule5_adr039_trial_end_pulls_a_queued_paid_period_forward():
    """AC-4: rule 5 + ADR-039: trial ended 3 Oct 12:00 -> the paid period queued for 5 Oct starts 3 Oct 12:00."""
    registered = ist(2026, 9, 28)
    led = EntitlementLedger("user-1").append(trial_grant("trial-1", registered, "registration", audit(registered)))
    led = led.append(_paid("paid-1", ist(2026, 10, 2)))
    led = end_trial_early(led, "trial-1", ist(2026, 10, 3, 12), audit(ist(2026, 10, 3, 12), "Client ID already trialled"))
    assert _resolved(led, "paid-1").segments == ((ist(2026, 10, 3, 12), ist(2026, 11, 2, 12)),)
    assert access_at(led, ist(2026, 10, 3, 12)).sources == (Source.PAID_MONTHLY,)


def test_revocation_is_a_new_audited_event_and_cuts_access_at_its_instant():
    """AC-4: revoking is appended, never a deletion; access is Limited from the revocation instant."""
    before = _paid_until_10_oct()
    led = revoke(before, "paid-1", ist(2026, 10, 1), audit(ist(2026, 10, 1), "payment reversed", actor="admin:ops"))

    assert led.events[0] is before.events[0]
    assert _level(led, ist(2026, 10, 1) - TICK) is PRO
    assert _level(led, ist(2026, 10, 1)) is LIMITED
    resolved = _resolved(led, "paid-1")
    assert (resolved.status, resolved.expiry) == (Status.REVOKED, ist(2026, 10, 1))
    change = led.status_change("paid-1")
    assert (change.audit.actor, change.audit.reason) == ("admin:ops", "payment reversed")
    with pytest.raises(ValueError, match="already revoked or ended"):
        revoke(led, "paid-1", ist(2026, 10, 2), audit(ist(2026, 10, 2)))
    with pytest.raises(ValueError, match="no entitlement"):
        revoke(led, "missing", ist(2026, 10, 2), audit(ist(2026, 10, 2)))


def test_trial_is_ended_early_when_an_already_trialled_client_id_is_connected():
    """AC-4: ADR-039: a running trial ends at the connection instant, as an audited ENDED event."""
    registered = ist(2026, 9, 29, 10)
    led = EntitlementLedger("u").append(trial_grant("trial-1", registered, "reg", audit(registered)))
    connected = ist(2026, 10, 1, 12)
    led = end_trial_early(led, "trial-1", connected, audit(connected, "Client ID already used a trial (ADR-039)"))

    assert _level(led, connected - TICK) is PRO
    assert _level(led, connected) is LIMITED
    resolved = _resolved(led, "trial-1")
    assert (resolved.status, resolved.expiry) == (Status.ENDED, connected)


def test_trial_early_end_rejects_non_trials_and_trials_not_running():
    """AC-4: only a running trial can be ended early; anything else is refused, not silently applied."""
    registered = ist(2026, 9, 29, 10)
    led = EntitlementLedger("u").append(trial_grant("trial-1", registered, "reg", audit(registered)))
    with pytest.raises(ValueError, match="not running"):
        end_trial_early(led, "trial-1", ist(2026, 10, 6, 10), audit(ist(2026, 10, 6, 10)))
    with pytest.raises(ValueError, match="not running"):
        end_trial_early(led, "trial-1", registered - TICK, audit(registered))
    with pytest.raises(ValueError, match="not a trial"):
        end_trial_early(_paid_until_10_oct(), "paid-1", ist(2026, 9, 20), audit(ist(2026, 9, 20)))


def test_every_change_is_an_audit_record_in_append_order():
    """AC-4: every event carries who/when/why; events cannot be appended out of recorded order."""
    led = _paid_until_10_oct().append(referral_grant("ref-1", ist(2026, 9, 20), "row-1", audit(ist(2026, 9, 20), "AP report")))
    led = revoke(led, "ref-1", ist(2026, 9, 22), audit(ist(2026, 9, 22), "attribution reversed", actor="admin:a"))
    assert [(e.audit.actor, e.audit.reason) for e in led.events] == [
        ("system", "test"), ("system", "AP report"), ("admin:a", "attribution reversed"),
    ]
    late = trial_grant("t", ist(2026, 9, 1), "reg", audit(ist(2026, 9, 1)))
    with pytest.raises(ValueError, match="recorded_at order"):
        led.append(late)
    assert not hasattr(led, "remove") and isinstance(led.events, tuple)


@pytest.mark.parametrize("days", [0, -30, True, 30.0])
def test_reward_and_trial_days_must_be_positive_whole_numbers(days):
    """AC-4: an invalid configured day count is refused rather than defaulted."""
    with pytest.raises(ValueError, match="days"):
        referral_grant("r", ist(2026, 9, 20), "row", audit(ist(2026, 9, 20)), days=days)
    with pytest.raises(ValueError, match="days"):
        trial_grant("t", ist(2026, 9, 20), "reg", audit(ist(2026, 9, 20)), days=days)


def test_admin_configured_reward_days_and_invalid_stacking_flag():
    """AC-4: the reward day count is configurable (ADR-038); a non-boolean stacking setting is refused."""
    led = _paid_until_10_oct().append(referral_grant("r", ist(2026, 9, 20), "row", audit(ist(2026, 9, 20)), days=45))
    assert _resolved(led, "r").expiry == ist(2026, 10, 10) + timedelta(days=45)
    with pytest.raises(ValueError, match="stacking"):
        referral_grant("r", ist(2026, 9, 20), "row", audit(ist(2026, 9, 20)), stacking="on")
