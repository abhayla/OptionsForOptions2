"""New events vs stored history, and post-dated status changes (REQ-017 AC-3, AC-4; owner decision Q225).

Q225 (owner, 2026-09-29): "a NEW entitlement event is checked against the current settings (caps, clock
skew, no backdating, no post-dating). STORED history is loaded with integrity checks only (order, ids,
references) and is never re-judged by today's settings: lowering the free-day cap from 90 to 30 does not
break a history of 7 + 30 + 30 days that was legal when written. No status change (revoke, early end)
may be dated more than the allowed clock skew after the time it is recorded."

Expected dates are hand-computed from the ADR-023 rules: a 7-day trial from 1 Sep 00:00 IST ends 8 Sep;
a 30-day referral stacked on it runs 8 Sep - 8 Oct; the next 8 Oct - 7 Nov (October has 31 days).
"""

import time
from datetime import timedelta

import pytest

from ofo.entitlements import engine
from ofo.entitlements.engine import access_at, end_trial_early, referral_grant, resolve, revoke, trial_grant
from ofo.entitlements.events import AccessLevel, EntitlementGrant, EntitlementStatusChange, Source, Status
from ofo.entitlements.ledger import EntitlementLedger, StoredHistory, _restore

from . import test_engine as rules
from .helpers import TEST_NOW, TICK, audit, fixed_clock, ist, ledger_for

PRO = AccessLevel.PRO
LIMITED = AccessLevel.LIMITED
FIVE_MIN = timedelta(minutes=5)
ONE_MIN = timedelta(minutes=1)


def _paid(entitlement_id: str, granted_at, reference: str | None = None, recorded_at=None) -> EntitlementGrant:
    return EntitlementGrant(
        entitlement_id, Source.PAID_MONTHLY, granted_at, timedelta(days=30),
        reference or f"razorpay:{entitlement_id}", audit(recorded_at or granted_at),
    )


def _load(history: StoredHistory, **settings) -> EntitlementLedger:
    settings.setdefault("clock", fixed_clock(TEST_NOW))
    return EntitlementLedger.load(history, **settings)


def _seven_plus_thirty_plus_thirty() -> EntitlementLedger:
    """Trial 1 Sep + referrals granted 2 Sep and 3 Sep, legal under a 90-day cap: at 3 Sep 5 trial days
    + 30 queued referral days are unused, so 35 + 30 = 65 <= 90."""
    t0, t1, t2 = ist(2026, 9, 1), ist(2026, 9, 2), ist(2026, 9, 3)
    led = ledger_for("u", max_free_days=90)
    led = led.append(trial_grant("t", t0, "reg", audit(t0)))
    led = led.append(referral_grant("r1", t1, "ref-1", audit(t1)))
    return led.append(referral_grant("r2", t2, "ref-2", audit(t2)))


# ---------------------------------------------------------------- defect 1: post-dated status changes


def test_post_dated_revoke_is_refused_so_a_real_revoke_still_lands():
    """AC-4: a revoke dated 2106 is refused; the real fraud revoke on 3 Oct is then accepted and cuts Pro there."""
    led = ledger_for("u").append(_paid("p", ist(2026, 9, 20)))  # Pro 20 Sep - 20 Oct
    with pytest.raises(ValueError, match="post-dated"):
        revoke(led, "p", ist(2106, 1, 1), audit(ist(2026, 9, 25)))
    led = revoke(led, "p", ist(2026, 10, 3), audit(ist(2026, 10, 3)))
    assert access_at(led, ist(2026, 10, 3) - TICK).level is PRO
    assert access_at(led, ist(2026, 10, 3)).level is LIMITED
    assert led.status_change("p").effective_at == ist(2026, 10, 3)


def test_end_trial_early_five_days_ahead_is_refused():
    """AC-4: ending a trial 5 days after the moment it is recorded is refused; ending it now is accepted."""
    t = ist(2026, 9, 1)
    led = ledger_for("u").append(trial_grant("t", t, "reg", audit(t)))
    recorded = ist(2026, 9, 1, 1)
    with pytest.raises(ValueError, match="post-dated"):
        end_trial_early(led, "t", recorded + timedelta(days=5), audit(recorded))
    ended = end_trial_early(led, "t", recorded, audit(recorded))
    assert access_at(ended, recorded - TICK).level is PRO
    assert access_at(ended, recorded).level is LIMITED


@pytest.mark.parametrize("skew", [FIVE_MIN, ONE_MIN, timedelta(0)])
@pytest.mark.parametrize("status", [Status.REVOKED, Status.ENDED])
def test_status_change_post_dating_boundary_is_exactly_the_skew(skew, status):
    """AC-4: effective_at == recorded_at + skew is accepted; one microsecond more is refused (revoke and early end)."""
    t = ist(2026, 9, 1)
    led = ledger_for("u", clock_skew=skew).append(trial_grant("t", t, "reg", audit(t)))
    recorded = ist(2026, 9, 2)
    with pytest.raises(ValueError, match="post-dated"):
        led.append(EntitlementStatusChange("t", status, recorded + skew + TICK, audit(recorded)))
    changed = led.append(EntitlementStatusChange("t", status, recorded + skew, audit(recorded)))
    assert changed.status_change("t").effective_at == recorded + skew


# ---------------------------------------------------------------- defect 2: stored history vs today's settings


def test_history_legal_under_cap_90_loads_under_cap_30_with_exact_access():
    """AC-3: 7 + 30 + 30 days written under max_free_days=90 loads after the cap is lowered to 30; the
    periods resolve to trial 1-8 Sep, referral 8 Sep - 8 Oct, referral 8 Oct - 7 Nov."""
    written = _seven_plus_thirty_plus_thirty()
    loaded = _load(written.stored(), max_free_days=30)
    assert loaded.events == written.events
    assert loaded.max_free_days == 30
    assert [(r.start, r.expiry) for r in resolve(loaded)] == [
        (ist(2026, 9, 1), ist(2026, 9, 8)),
        (ist(2026, 9, 8), ist(2026, 10, 8)),
        (ist(2026, 10, 8), ist(2026, 11, 7)),
    ]
    assert access_at(loaded, ist(2026, 9, 8) - TICK).sources == (Source.TRIAL,)
    assert access_at(loaded, ist(2026, 9, 8)).sources == (Source.REFERRAL,)
    assert access_at(loaded, ist(2026, 11, 7) - TICK).level is PRO
    assert access_at(loaded, ist(2026, 11, 7)).level is LIMITED


def test_a_new_free_grant_on_the_loaded_history_meets_the_new_cap():
    """AC-4: the lowered cap still binds NEW events: at 4 Sep 4 trial + 60 referral days are unused, so a
    new 30-day referral (94 > 30) is refused, while a paid grant (not free) is accepted."""
    loaded = _load(_seven_plus_thirty_plus_thirty().stored(), max_free_days=30)
    at = ist(2026, 9, 4)
    with pytest.raises(ValueError, match="maximum accumulated free days is 30: 64 unused"):
        loaded.append(referral_grant("r3", at, "ref-3", audit(at)))
    assert loaded.append(_paid("p", at)).grant("p").source is Source.PAID_MONTHLY


def test_history_legal_under_skew_5_min_loads_under_skew_1_min():
    """AC-3: a grant 3 min after its recording and a revoke 3 min before its recording (legal under a
    5-minute skew) load after the skew is lowered to 1 minute; new events then meet the 1-minute skew."""
    rec = ist(2026, 9, 1)
    led = ledger_for("u").append(_paid("p", rec + timedelta(minutes=3), recorded_at=rec))
    revoke_rec = ist(2026, 9, 10)
    led = revoke(led, "p", revoke_rec - timedelta(minutes=3), audit(revoke_rec))
    loaded = _load(led.stored(), clock_skew=ONE_MIN)
    assert access_at(loaded, rec + timedelta(minutes=3) - TICK).level is LIMITED
    assert access_at(loaded, rec + timedelta(minutes=3)).level is PRO
    assert access_at(loaded, revoke_rec - timedelta(minutes=3) - TICK).level is PRO
    assert access_at(loaded, revoke_rec - timedelta(minutes=3)).level is LIMITED
    late = ist(2026, 9, 11)
    with pytest.raises(ValueError, match="more than 0:01:00 after"):
        loaded.append(_paid("p2", late + timedelta(minutes=3), recorded_at=late))


def test_loaded_ledger_ignores_the_clock_for_stored_events_but_not_for_new_ones():
    """AC-4: stored events recorded after a (misset) clock still load; a new event after it is refused."""
    t = ist(2026, 9, 1)
    written = ledger_for("u").append(_paid("p", t))
    early_clock = fixed_clock(ist(2020, 1, 1))
    loaded = EntitlementLedger.load(written.stored(), clock=early_clock)
    assert loaded.events == written.events
    with pytest.raises(ValueError, match="after the ledger clock"):
        loaded.append(_paid("p2", ist(2026, 9, 2)))


def test_new_events_after_load_follow_the_stored_order():
    """AC-4: the loaded index carries the last recorded time, so a new event recorded before it is refused."""
    loaded = _load(_seven_plus_thirty_plus_thirty().stored())
    earlier = ist(2026, 9, 2, 12)
    with pytest.raises(ValueError, match="recorded_at order"):
        loaded.append(_paid("p", earlier))
    with pytest.raises(ValueError, match="already granted"):
        loaded.append(_paid("r1", ist(2026, 9, 4)))


# ---------------------------------------------------------------- the load path is not a back door


def test_stored_history_cannot_be_built_or_edited_by_a_caller():
    """AC-4: a StoredHistory comes only from a ledger: construction, subclassing and edits are refused."""
    with pytest.raises(TypeError):
        StoredHistory("u", ())
    history = _seven_plus_thirty_plus_thirty().stored()
    with pytest.raises(AttributeError):
        history.events = ()
    with pytest.raises(AttributeError):
        del history.events

    class Forged(StoredHistory):
        def __init__(self, user_id, events):
            object.__setattr__(self, "user_id", user_id)
            object.__setattr__(self, "events", events)

    with pytest.raises(ValueError, match="load takes a StoredHistory"):
        EntitlementLedger.load(Forged("u", history.events))


@pytest.mark.parametrize("raw", ["tuple", "list", "ledger"])
def test_load_refuses_raw_events(raw):
    """AC-4: load never takes a raw event sequence (or a ledger), so a caller cannot slip a new event in."""
    led = _seven_plus_thirty_plus_thirty()
    value = {"tuple": led.events, "list": list(led.events), "ledger": led}[raw]
    with pytest.raises(ValueError, match="load takes a StoredHistory"):
        EntitlementLedger.load(value)


def test_a_new_event_cannot_skip_the_policy_by_riding_on_stored_history():
    """AC-4: stored events + a post-dated revoke or an over-cap referral, fed back in, get the NEW-event checks.

    The constructor replays its events as NEW ones (under the 90-day cap they were written with; at 4 Sep
    4 + 60 unused + 30 new = 94 > 90); a loaded ledger applies the lowered 30-day cap to the new event."""
    written = _seven_plus_thirty_plus_thirty()
    rec = ist(2026, 9, 4)
    post_dated = EntitlementStatusChange("r1", Status.REVOKED, ist(2106, 1, 1), audit(rec))
    over_cap = referral_grant("r3", rec, "ref-3", audit(rec))
    for smuggled, message in ((post_dated, "post-dated"), (over_cap, "maximum accumulated free days")):
        with pytest.raises(ValueError, match=message):
            ledger_for("u", written.stored().events + (smuggled,), max_free_days=90)
        with pytest.raises(ValueError, match=message):
            _load(written.stored(), max_free_days=30).append(smuggled)
    # the only public path from stored history to a ledger is load(StoredHistory), and it adds nothing
    assert _load(written.stored()).events == written.events


# ---------------------------------------------------------------- integrity checks on stored history


def _corrupt(*events) -> StoredHistory:
    """What the store adapter would hand over if the store were corrupted (the adapter is not built yet)."""
    return _restore("u", tuple(events))


T0, T1, T2 = ist(2026, 9, 1), ist(2026, 9, 2), ist(2026, 9, 3)


@pytest.mark.parametrize(
    "history, message",
    [
        (lambda: _corrupt(_paid("a", T1), _paid("b", T0)), "recorded_at order"),
        (lambda: _corrupt(_paid("a", T0), _paid("a", T1, "other")), "already granted"),
        (lambda: _corrupt(_paid("a", T0, " Pay-1 "), _paid("b", T1, "pay-1")), "one fact grants once"),
        (lambda: _corrupt(trial_grant("t1", T0, "reg-1", audit(T0)), trial_grant("t2", T1, "reg-2", audit(T1))),
         "already has a trial"),
        (lambda: _corrupt(EntitlementStatusChange("x", Status.REVOKED, T0, audit(T0))), "no entitlement 'x'"),
        (lambda: _corrupt(_paid("a", T0), EntitlementStatusChange("a", Status.REVOKED, T1, audit(T1)),
                          EntitlementStatusChange("a", Status.REVOKED, T2, audit(T2))), "already revoked or ended"),
        (lambda: _corrupt(_paid("a", T0), EntitlementStatusChange("a", Status.ENDED, T1, audit(T1))),
         "ENDED is only a trial"),
        (lambda: _corrupt(_paid("a", T0), "not an event"), "not an entitlement event"),
        (lambda: _corrupt(*[
            EntitlementGrant(f"a{i}", Source.PAID_ANNUAL, T0, timedelta(days=3650), f"pay-{i}", audit(T0))
            for i in range(800)
        ]), "past the last representable date"),
    ],
    ids=["order", "duplicate-id", "duplicate-reference", "second-trial", "unknown-target", "double-change",
         "ended-not-trial", "not-an-event", "overflow"],
)
def test_corrupted_stored_history_is_refused_on_load(history, message):
    """AC-3: load keeps every integrity check (order, ids, references, one trial, change targets, dates)."""
    with pytest.raises(ValueError, match=message):
        _load(history())


def test_load_of_1000_stored_events_is_fast():
    """AC-4: loading re-checks each event against an index, not the whole history (1,000 events well under 1 s)."""
    stored = _restore("u", tuple(_paid(f"p{i}", T0 + timedelta(seconds=i)) for i in range(1000)))
    started = time.perf_counter()
    loaded = _load(stored)
    assert time.perf_counter() - started < 1.0
    assert len(loaded.events) == 1000


# ---------------------------------------------------------------- ADR-023 rule 1-5 examples through load


RULE_EXAMPLES = [
    rules.test_trial_boundaries_seven_days_from_registration,
    rules.test_stacked_referral_real_example_pro_until_10_oct_plus_referral_on_20_sep_is_9_nov,
    rules.test_three_stacked_referrals_add_ninety_days,
    rules.test_rule2_paid_bought_during_trial_starts_when_the_trial_ends,
    rules.test_rule2_a_grant_after_a_gap_starts_at_its_grant_time,
    rules.test_stacking_off_runs_the_referral_from_its_grant_time_and_may_overlap,
    rules.test_rule3_referral_days_are_banked_during_direct_pro_and_start_when_it_ends,
    rules.test_rule3_a_running_referral_pauses_while_direct_pro_is_in_force,
    rules.test_rule5_revoking_paid_pulls_the_stacked_referral_forward,
    rules.test_rule5_adr039_trial_end_pulls_a_queued_paid_period_forward,
    rules.test_revocation_is_a_new_audited_event_and_cuts_access_at_its_instant,
    rules.test_trial_is_ended_early_when_an_already_trialled_client_id_is_connected,
]


@pytest.mark.parametrize("example", RULE_EXAMPLES, ids=lambda f: f.__name__)
def test_adr023_rule_examples_hold_when_every_ledger_is_stored_and_reloaded(monkeypatch, example):
    """AC-3: each ADR-023 rule 1-5 example passes with every ledger reloaded from its stored history after
    each append, and the reload under the strictest settings (skew 0, cap 1 day) resolves identically."""
    real_append = EntitlementLedger.append
    reloads = []

    def append_then_reload(self, event):
        appended = real_append(self, event)
        strict = EntitlementLedger.load(appended.stored(), clock_skew=timedelta(0), clock=appended.clock,
                                        max_free_days=1)
        assert resolve(strict) == resolve(appended)
        reloads.append(event)
        return EntitlementLedger.load(appended.stored(), clock_skew=appended.clock_skew, clock=appended.clock,
                                      max_free_days=appended.max_free_days)

    monkeypatch.setattr(EntitlementLedger, "append", append_then_reload)
    example()
    assert reloads, "the example appended nothing, so it proved nothing about load"
    assert engine.EntitlementLedger is EntitlementLedger
