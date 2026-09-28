"""Entitlement engine: derived access, sources, combination and audit (REQ-017 AC-1, AC-2, AC-4).

Boundary rule under test: an entitlement covers the half-open interval [start, end); at exactly
``end`` the user is LIMITED. Every boundary is checked one microsecond (TICK) either side.
"""

import dataclasses
import typing
from datetime import timedelta

import pytest

from ofo.entitlements import engine, events, ledger as ledger_module
from ofo.entitlements.engine import (
    access_at,
    end_trial_early,
    finite_pro_end,
    grant_referral,
    resolve,
    revoke,
    trial_grant,
)
from ofo.entitlements.events import AccessLevel, EntitlementGrant, Source, Status
from ofo.entitlements.ledger import EntitlementLedger

from .helpers import TICK, audit, ist

PRO = AccessLevel.PRO
LIMITED = AccessLevel.LIMITED


def _paid_until_10_oct() -> EntitlementLedger:
    """Pro until 10 Oct 2026 00:00 IST from a paid month (the ADR-025 Q63 example's starting state)."""
    paid = EntitlementGrant(
        "paid-1", Source.PAID_MONTHLY, ist(2026, 9, 10), ist(2026, 10, 10), "razorpay:pay_001", audit(ist(2026, 9, 10))
    )
    return EntitlementLedger("user-1").append(paid)


def _level(led: EntitlementLedger, at) -> AccessLevel:
    return access_at(led, at).level


# ---------------------------------------------------------------- AC-1: access is derived, never a flag


def test_trial_boundaries_seven_days_from_registration():
    """AC-1: a trial registered 29 Sep 10:15:30 IST gives Pro on [29 Sep 10:15:30, 6 Oct 10:15:30) and no longer."""
    registered = ist(2026, 9, 29, 10, 15, 30)
    trial = trial_grant("trial-1", registered, "registration:user-1", audit(registered, "registration"))
    led = EntitlementLedger("user-1").append(trial)

    assert trial.expiry == ist(2026, 10, 6, 10, 15, 30)
    assert _level(led, registered - TICK) is LIMITED
    assert _level(led, registered) is PRO
    assert _level(led, ist(2026, 10, 6, 10, 15, 30) - TICK) is PRO
    assert _level(led, ist(2026, 10, 6, 10, 15, 30)) is LIMITED
    at_start = access_at(led, registered)
    assert [r.grant for r in at_start.contributing] == [trial]
    assert access_at(led, ist(2026, 10, 6, 10, 15, 30)).contributing == ()


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


# ---------------------------------------------------------------- AC-2: sources


def test_sources_are_exactly_the_spec_list_and_limited_is_derived():
    """AC-2: sources are Trial, Direct Zerodha Customer, Referral, Paid Monthly, Paid Annual; Expired/Limited is derived."""
    assert {s.value for s in Source} == {
        "TRIAL", "DIRECT_ZERODHA_CUSTOMER", "REFERRAL", "PAID_MONTHLY", "PAID_ANNUAL",
    }
    assert {a.value for a in AccessLevel} == {"PRO", "LIMITED"}
    assert _level(EntitlementLedger("user-1"), ist(2026, 9, 29)) is LIMITED


@pytest.mark.parametrize("source", [Source.TRIAL, Source.REFERRAL, Source.PAID_MONTHLY, Source.PAID_ANNUAL])
def test_each_finite_source_gives_pro_only_inside_its_window(source):
    """AC-2: every finite source gives Pro on [start, expiry) and Limited at expiry (no grace period, ADR-026)."""
    start, expiry = ist(2026, 10, 1), ist(2026, 10, 31)
    led = EntitlementLedger("user-1").append(
        EntitlementGrant("e-1", source, start, expiry, "ref-1", audit(start))
    )
    assert _level(led, start - TICK) is LIMITED
    assert _level(led, start) is PRO
    assert _level(led, expiry - TICK) is PRO
    assert _level(led, expiry) is LIMITED


def test_direct_zerodha_customer_pro_has_no_end_while_active():
    """AC-2: Direct Zerodha Customer Pro has no expiry (ADR-024) and stays Pro decades later."""
    start = ist(2026, 9, 29, 9)
    led = EntitlementLedger("user-1").append(
        EntitlementGrant("direct-1", Source.DIRECT_ZERODHA_CUSTOMER, start, None, "eligibility:AB1234", audit(start))
    )
    assert _level(led, start - TICK) is LIMITED
    assert _level(led, start) is PRO
    assert _level(led, ist(2099, 12, 31)) is PRO
    assert resolve(led)[0].end is None


# ---------------------------------------------------------------- AC-4: combination and audit


def test_stacked_referral_real_example_pro_until_10_oct_plus_referral_on_20_sep_is_9_nov():
    """AC-4: Pro until 10 Oct + a referral granted 20 Sep = Pro until 9 Nov (ADR-025 Q63, ADR-038: 30 days)."""
    led = grant_referral(
        _paid_until_10_oct(), "ref-1", ist(2026, 9, 20, 14), "ap-report:row-7", audit(ist(2026, 9, 20, 14))
    )
    referral = led.grant("ref-1")
    assert referral.start == ist(2026, 10, 10)
    assert referral.expiry == ist(2026, 11, 9)
    assert _level(led, ist(2026, 10, 10) - TICK) is PRO
    handover = access_at(led, ist(2026, 10, 10))
    assert handover.level is PRO
    assert [r.grant.entitlement_id for r in handover.contributing] == ["ref-1"]
    assert _level(led, ist(2026, 11, 9) - TICK) is PRO
    assert _level(led, ist(2026, 11, 9)) is LIMITED


def test_three_stacked_referrals_add_ninety_days():
    """AC-4: three referrals stack end to end: 10 Oct + 90 days = 8 Jan 2027 (ADR-038)."""
    led = _paid_until_10_oct()
    for n in range(3):
        led = grant_referral(led, f"ref-{n}", ist(2026, 9, 20, 14 + n), f"row-{n}", audit(ist(2026, 9, 20, 14 + n)))
    assert led.grant("ref-2").expiry == ist(2027, 1, 8)
    assert finite_pro_end(led, ist(2026, 9, 21)) == ist(2027, 1, 8)
    assert _level(led, ist(2027, 1, 8)) is LIMITED


def test_stacking_off_starts_the_referral_at_its_grant_time():
    """AC-4: with stacking switched off the referral runs from its grant time: 20 Sep 14:00 to 20 Oct 14:00."""
    led = grant_referral(
        _paid_until_10_oct(), "ref-1", ist(2026, 9, 20, 14), "row-1", audit(ist(2026, 9, 20, 14)), stacking=False
    )
    assert led.grant("ref-1").start == ist(2026, 9, 20, 14)
    assert led.grant("ref-1").expiry == ist(2026, 10, 20, 14)
    assert _level(led, ist(2026, 10, 20, 14)) is LIMITED


def test_referral_for_a_limited_user_starts_at_grant_time_and_stacks_on_a_running_trial():
    """AC-4: a Limited user's referral starts at once; a trial user's referral starts when the trial ends."""
    limited = grant_referral(EntitlementLedger("u"), "ref-1", ist(2026, 12, 1, 9), "row-1", audit(ist(2026, 12, 1, 9)))
    assert (limited.grant("ref-1").start, limited.grant("ref-1").expiry) == (ist(2026, 12, 1, 9), ist(2026, 12, 31, 9))

    registered = ist(2026, 9, 29, 10)
    on_trial = EntitlementLedger("u").append(trial_grant("t", registered, "reg", audit(registered)))
    on_trial = grant_referral(on_trial, "ref-1", ist(2026, 10, 1), "row-1", audit(ist(2026, 10, 1)))
    assert on_trial.grant("ref-1").start == ist(2026, 10, 6, 10)
    assert on_trial.grant("ref-1").expiry == ist(2026, 11, 5, 10)


def test_referral_during_direct_customer_pro_is_still_recorded():
    """AC-4: a referral for an indefinite direct customer is recorded in history (ADR-023 T1 #272 §21)."""
    start = ist(2026, 9, 1)
    led = EntitlementLedger("u").append(
        EntitlementGrant("direct-1", Source.DIRECT_ZERODHA_CUSTOMER, start, None, "eligibility", audit(start))
    )
    led = grant_referral(led, "ref-1", ist(2026, 9, 20), "row-1", audit(ist(2026, 9, 20)))
    assert [g.entitlement_id for g in led.grants()] == ["direct-1", "ref-1"]
    assert led.grant("ref-1").start == ist(2026, 9, 20)
    ids = {r.grant.entitlement_id for r in access_at(led, ist(2026, 9, 25)).contributing}
    assert ids == {"direct-1", "ref-1"}


def test_revocation_is_a_new_audited_event_and_cuts_access_at_its_instant():
    """AC-4: revoking is appended, never a deletion; access is Limited from the revocation instant."""
    before = _paid_until_10_oct()
    led = revoke(before, "paid-1", ist(2026, 10, 1), audit(ist(2026, 10, 1), "payment reversed", actor="admin:ops"))

    assert len(led.events) == len(before.events) + 1
    assert led.events[0] is before.events[0]  # the grant is still there, unchanged
    assert _level(led, ist(2026, 10, 1) - TICK) is PRO
    assert _level(led, ist(2026, 10, 1)) is LIMITED
    (resolved,) = resolve(led)
    assert (resolved.status, resolved.end) == (Status.REVOKED, ist(2026, 10, 1))
    change = led.status_change("paid-1")
    assert (change.audit.actor, change.audit.reason) == ("admin:ops", "payment reversed")
    with pytest.raises(ValueError, match="already revoked or ended"):
        revoke(led, "paid-1", ist(2026, 10, 2), audit(ist(2026, 10, 2)))
    with pytest.raises(ValueError, match="no entitlement"):
        revoke(led, "missing", ist(2026, 10, 2), audit(ist(2026, 10, 2)))


def test_revoking_the_base_entitlement_does_not_move_a_stacked_referral_end_date():
    """AC-4: the referral end date shown to the user (9 Nov) is fixed when granted; a later revocation leaves a gap."""
    led = grant_referral(_paid_until_10_oct(), "ref-1", ist(2026, 9, 20), "row-1", audit(ist(2026, 9, 20)))
    led = revoke(led, "paid-1", ist(2026, 9, 25), audit(ist(2026, 9, 25), "chargeback"))
    assert led.grant("ref-1").expiry == ist(2026, 11, 9)
    assert _level(led, ist(2026, 9, 25)) is LIMITED
    assert _level(led, ist(2026, 10, 10)) is PRO


def test_trial_is_ended_early_when_an_already_trialled_client_id_is_connected():
    """AC-4: ADR-039: a running trial ends at the connection instant, as an audited ENDED event."""
    registered = ist(2026, 9, 29, 10)
    led = EntitlementLedger("u").append(trial_grant("trial-1", registered, "reg", audit(registered)))
    connected = ist(2026, 10, 1, 12)
    led = end_trial_early(led, "trial-1", connected, audit(connected, "Client ID already used a trial (ADR-039)"))

    assert _level(led, connected - TICK) is PRO
    assert _level(led, connected) is LIMITED
    (resolved,) = resolve(led)
    assert (resolved.status, resolved.end) == (Status.ENDED, connected)


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
    led = grant_referral(_paid_until_10_oct(), "ref-1", ist(2026, 9, 20), "row-1", audit(ist(2026, 9, 20), "AP report"))
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
        grant_referral(EntitlementLedger("u"), "r", ist(2026, 9, 20), "row", audit(ist(2026, 9, 20)), days=days)
    with pytest.raises(ValueError, match="days"):
        trial_grant("t", ist(2026, 9, 20), "reg", audit(ist(2026, 9, 20)), days=days)


def test_admin_configured_reward_days_and_invalid_stacking_flag():
    """AC-4: the reward day count is configurable (ADR-038); a non-boolean stacking setting is refused."""
    led = grant_referral(_paid_until_10_oct(), "r", ist(2026, 9, 20), "row", audit(ist(2026, 9, 20)), days=45)
    assert led.grant("r").expiry == ist(2026, 10, 10) + timedelta(days=45)
    with pytest.raises(ValueError, match="stacking"):
        grant_referral(_paid_until_10_oct(), "r", ist(2026, 9, 20), "row", audit(ist(2026, 9, 20)), stacking="on")


def test_naive_query_time_is_refused():
    """AC-1: a naive datetime is ambiguous about the instant, so access_at refuses it."""
    from datetime import datetime

    with pytest.raises(ValueError, match="timezone-aware"):
        access_at(_paid_until_10_oct(), datetime(2026, 9, 20))
