"""Mutation tests: flipping each access guard makes the real test suite fail (W-007, Tier A).

Each test replaces ONE guard in ``ofo.entitlements.engine`` with a wrong version (via monkeypatch),
then runs the real tests from ``test_engine`` that protect it and asserts they now FAIL. It runs them
un-mutated first, so a pass here means "this test detects exactly this mutation", not "this test was
already broken".
"""

from collections.abc import Callable
from datetime import timedelta

import pytest

from ofo.entitlements import engine, events, ledger as ledger_module
from ofo.entitlements.events import Placement, Status

from . import test_boundary as boundary
from . import test_engine as suite


# A mutant is "caught" when the protecting test fails: an assertion, a pytest.raises that did not
# raise, an engine refusal the test did not expect (ValueError), or (for the overflow guard) the
# crash the guard exists to prevent. Each case first runs un-mutated and passes, so any of these
# under the mutant is the mutant's doing.
CAUGHT = (AssertionError, pytest.fail.Exception, OverflowError, ValueError)


def _passes_then_fails_under(
    monkeypatch: pytest.MonkeyPatch, name: str, mutant, tests: list[Callable[[], None]], module=engine
):
    for test in tests:
        test()  # baseline: the guard is intact, the test passes
    monkeypatch.setattr(module, name, mutant)
    for test in tests:
        with pytest.raises(CAUGHT):
            test()


def _no_op(*args):
    return None


# ---------------------------------------------------------------- round 3: input-boundary guards


@pytest.mark.parametrize(
    "guard, tests",
    [
        ("_check_unique_id", [boundary.test_duplicate_entitlement_id_is_refused]),
        ("_check_unique_reference", [boundary.test_second_grant_with_same_source_and_reference_is_refused]),
        ("_check_single_trial", [boundary.test_second_trial_in_one_ledger_is_refused]),
        ("_check_not_future", [
            boundary.test_grant_time_far_after_its_recording_is_refused,
            boundary.test_grant_time_skew_is_five_minutes_by_default_and_configurable,
        ]),
        ("_check_not_backdated", [boundary.test_backdated_revocation_is_refused]),
        ("_check_ended_only_for_trial", [boundary.test_ended_is_only_for_a_trial]),
        ("_check_grant_not_backdated", [boundary.test_backdated_open_ended_grant_is_refused]),
        ("_check_recorded_not_future", [
            boundary.test_recorded_at_after_the_clock_is_refused_so_the_ledger_never_freezes,
            boundary.test_default_clock_is_the_real_utc_now,
        ]),
        ("_check_free_day_cap", [
            boundary.test_maximum_accumulated_free_days_cap_of_90,
            boundary.test_free_day_cap_counts_trial_days_and_defaults_to_no_cap,
        ]),
    ],
)
def test_removing_a_ledger_guard_is_caught(monkeypatch, guard, tests):
    """AC-4: each ledger input guard is load-bearing: turning it into a no-op fails its red test."""
    _passes_then_fails_under(monkeypatch, guard, _no_op, tests, module=ledger_module)


def test_removing_the_duration_cap_is_caught(monkeypatch):
    """AC-3: without the 3650-day cap in the grant constructor, an absurd duration is accepted."""
    _passes_then_fails_under(
        monkeypatch, "MAX_DURATION", timedelta.max, [boundary.test_durations_above_ten_years_are_refused],
        module=events,
    )


def test_removing_the_representable_date_guard_is_caught(monkeypatch):
    """AC-1 (round 4, MINOR 3): without the bound check, a grant ending past year 9999 is accepted."""
    _passes_then_fails_under(
        monkeypatch, "_check_representable", _no_op,
        [boundary.test_a_grant_that_would_end_past_the_representable_date_is_refused], module=ledger_module,
    )


def test_raw_reference_comparison_is_caught(monkeypatch):
    """AC-4 (round 4, MINOR 1): comparing references raw (no strip/casefold, per source) lets duplicates through."""
    def raw(grant):
        return grant.source.value, grant.reference

    for variant in ("alice ", "ALICE"):
        _passes_then_fails_under(
            monkeypatch, "_reference_key", raw,
            [lambda: boundary.test_references_are_normalised_before_the_duplicate_check(variant)],
            module=ledger_module,
        )
        monkeypatch.undo()
    _passes_then_fails_under(
        monkeypatch, "_reference_key", raw,
        [boundary.test_one_payment_reference_grants_once_across_monthly_and_annual], module=ledger_module,
    )


def test_truncate_keeping_banked_time_is_caught(monkeypatch):
    """AC-4: a revocation that leaves banked days in place (still "30 days saved") must fail."""
    original = engine._truncate

    def keeps_banked(segments, banked, change):
        return original(segments, banked, change)[0], banked

    _passes_then_fails_under(monkeypatch, "_truncate", keeps_banked, [
        boundary.test_revoking_a_banked_referral_cancels_its_saved_days,
        boundary.test_ending_a_banked_trial_cancels_its_remaining_days,
    ])


def test_ending_only_a_running_trial_is_caught(monkeypatch):
    """AC-4: refusing to end a banked trial (the pre-round-3 rule) must fail caveat 9's test."""
    def running_only(resolved, at):
        return any(engine._covers(s, e, at) for s, e in resolved.segments)

    _passes_then_fails_under(monkeypatch, "_owes_pro", running_only, [
        boundary.test_ending_a_banked_trial_cancels_its_remaining_days,
    ])


def test_status_expiring_one_tick_late_is_caught(monkeypatch):
    """AC-3: a status that stays ACTIVE at exactly the expiry instant must fail (half-open, like access)."""
    original = engine.ResolvedEntitlement.status_at

    def late(self, at):
        return original(self, at - boundary.TICK)

    monkeypatch.setattr(engine.ResolvedEntitlement, "status_at", late)
    with pytest.raises(CAUGHT):
        boundary.test_status_is_evaluated_at_the_query_time()


# ---------------------------------------------------------------- engine guards


def test_interval_end_made_inclusive_is_caught(monkeypatch):
    """AC-1: [start, end] instead of [start, end) must fail the boundary tests (Pro at exactly end is wrong)."""
    def inclusive_end(start, end, at):
        return start <= at and (end is None or at <= end)

    _passes_then_fails_under(monkeypatch, "_covers", inclusive_end, [
        suite.test_trial_boundaries_seven_days_from_registration,
        suite.test_stacked_referral_real_example_pro_until_10_oct_plus_referral_on_20_sep_is_9_nov,
    ])


def test_interval_start_made_exclusive_is_caught(monkeypatch):
    """AC-1: (start, end) instead of [start, end) must fail: Pro begins AT registration."""
    def exclusive_start(start, end, at):
        return start < at and (end is None or at < end)

    _passes_then_fails_under(monkeypatch, "_covers", exclusive_start, [
        suite.test_trial_boundaries_seven_days_from_registration,
    ])


def test_stacking_removed_is_caught(monkeypatch):
    """AC-4 rule 2: a period that ignores the current Pro end (overlapping it) must fail."""
    _passes_then_fails_under(monkeypatch, "_chain_start", lambda granted_at, cursor: granted_at, [
        suite.test_stacked_referral_real_example_pro_until_10_oct_plus_referral_on_20_sep_is_9_nov,
        suite.test_three_stacked_referrals_add_ninety_days,
        suite.test_rule2_paid_bought_during_trial_starts_when_the_trial_ends,
    ])


def test_stacking_switch_ignored_is_caught(monkeypatch):
    """AC-4: a referral that stays stacked when the admin switches stacking off must fail."""
    _passes_then_fails_under(monkeypatch, "_placement", lambda stacking: Placement.STACKED, [
        suite.test_stacking_off_runs_the_referral_from_its_grant_time_and_may_overlap,
    ])


def test_sequencing_fixed_at_natural_end_leaves_a_gap_and_is_caught(monkeypatch):
    """AC-4 rule 5: continuing the chain from where a revoked period WOULD have ended opens a Limited gap; must fail."""
    def from_natural_end(previous, natural, kept):
        return natural[-1][1] if natural else previous

    _passes_then_fails_under(monkeypatch, "_next_cursor", from_natural_end, [
        suite.test_rule5_revoking_paid_pulls_the_stacked_referral_forward,
        suite.test_rule5_adr039_trial_end_pulls_a_queued_paid_period_forward,
    ])


def test_banked_days_consumed_during_direct_pro_is_caught(monkeypatch):
    """AC-4 rule 3: referral days that run down during Direct Customer Pro (instead of being banked) must fail."""
    original = engine._consume

    def ignore_open_ended(start, duration, open_ended):
        return original(start, duration, [])

    _passes_then_fails_under(monkeypatch, "_consume", ignore_open_ended, [
        suite.test_rule3_referral_days_are_banked_during_direct_pro_and_start_when_it_ends,
        suite.test_rule3_a_running_referral_pauses_while_direct_pro_is_in_force,
    ])


def _ignoring(status: Status):
    original = engine._truncate

    def mutant(segments, banked, change):
        return original(segments, banked, None if change is not None and change.status is status else change)

    return mutant


def test_revocation_ignored_is_caught(monkeypatch):
    """AC-4: a revocation that does not cut access must fail."""
    _passes_then_fails_under(monkeypatch, "_truncate", _ignoring(Status.REVOKED), [
        suite.test_revocation_is_a_new_audited_event_and_cuts_access_at_its_instant,
        suite.test_rule5_revoking_paid_pulls_the_stacked_referral_forward,
        suite.test_rule3_referral_days_are_banked_during_direct_pro_and_start_when_it_ends,
    ])


def test_trial_early_end_ignored_is_caught(monkeypatch):
    """AC-4: an ADR-039 early trial end that does not cut access must fail."""
    _passes_then_fails_under(monkeypatch, "_truncate", _ignoring(Status.ENDED), [
        suite.test_trial_is_ended_early_when_an_already_trialled_client_id_is_connected,
        suite.test_rule5_adr039_trial_end_pulls_a_queued_paid_period_forward,
    ])


# ---------------------------------------------------------------- round 5: new vs stored (owner decision Q225)

from . import test_stored_history as stored  # noqa: E402


def test_removing_the_post_dating_guard_is_caught(monkeypatch):
    """AC-4: without the post-dating bound, a revoke dated 2106 and a trial end 5 days ahead are accepted."""
    tests = [
        stored.test_post_dated_revoke_is_refused_so_a_real_revoke_still_lands,
        stored.test_end_trial_early_five_days_ahead_is_refused,
        *[lambda s=s, st=st: stored.test_status_change_post_dating_boundary_is_exactly_the_skew(s, st)
          for s in (stored.FIVE_MIN, stored.ONE_MIN) for st in (Status.REVOKED, Status.ENDED)],
    ]
    _passes_then_fails_under(monkeypatch, "_check_change_not_postdated", _no_op, tests, module=ledger_module)


def test_post_dating_bound_one_tick_loose_is_caught(monkeypatch):
    """AC-4: a bound of skew + 1 microsecond (off by one) lets the +skew+1us change in."""
    real = ledger_module._check_change_not_postdated
    tests = [lambda: stored.test_status_change_post_dating_boundary_is_exactly_the_skew(stored.FIVE_MIN, Status.REVOKED)]
    _passes_then_fails_under(
        monkeypatch, "_check_change_not_postdated", lambda change, skew: real(change, skew + boundary_tick()),
        tests, module=ledger_module,
    )


def boundary_tick():
    from .helpers import TICK

    return TICK


def test_load_re_applying_the_current_policy_is_caught(monkeypatch):
    """AC-3: if load re-judged stored events by today's settings, the 90->30 cap and 5->1 min skew histories break."""
    def strict_integrity(index, event):
        ledger_module._check_event_type(event)
        ledger_module._check_order(index, event)
        # a load that re-applies the policy: grant skew at the (lowered) 1-minute setting
        if isinstance(event, events.EntitlementGrant):
            ledger_module._check_not_future(event, timedelta(minutes=1))
        real_integrity(index, event)

    real_integrity = ledger_module._check_integrity
    tests = [stored.test_history_legal_under_skew_5_min_loads_under_skew_1_min]
    _passes_then_fails_under(monkeypatch, "_check_integrity", strict_integrity, tests, module=ledger_module)


def test_load_through_the_new_event_path_is_caught(monkeypatch):
    """AC-3: a load that replays stored events through append (the round-4 behaviour) fails the cap-lowering test."""
    def load_via_append(cls, history, *, clock_skew=ledger_module.DEFAULT_CLOCK_SKEW, clock=ledger_module.utc_now,
                        max_free_days=None):
        return cls(history.user_id, history.events, clock_skew=clock_skew, clock=clock, max_free_days=max_free_days)

    tests = [
        stored.test_history_legal_under_cap_90_loads_under_cap_30_with_exact_access,
        stored.test_history_legal_under_skew_5_min_loads_under_skew_1_min,
    ]
    _passes_then_fails_under(
        monkeypatch, "load", classmethod(load_via_append), tests, module=ledger_module.EntitlementLedger
    )


def test_load_skipping_integrity_is_caught(monkeypatch):
    """AC-3: a load with no integrity checks accepts a corrupted store (duplicate id)."""
    def no_integrity_load(cls, history, *, clock_skew=ledger_module.DEFAULT_CLOCK_SKEW, clock=ledger_module.utc_now,
                          max_free_days=None):
        empty = cls(history.user_id, clock_skew=clock_skew, clock=clock, max_free_days=max_free_days)
        index = ledger_module._Index()
        for event in history.events:
            index = index.with_event(event)
        return empty._with(history.events, index)

    duplicate = lambda: stored.test_corrupted_stored_history_is_refused_on_load(  # noqa: E731
        lambda: stored._corrupt(stored._paid("a", stored.T0), stored._paid("a", stored.T1, "other")), "already granted"
    )
    _passes_then_fails_under(
        monkeypatch, "load", classmethod(no_integrity_load), [duplicate], module=ledger_module.EntitlementLedger
    )


def test_removing_the_stored_history_type_check_is_caught(monkeypatch):
    """AC-4: without the type check, load takes a forged subclass or any object with user_id/events, such as a
    ledger built from new events (the back door). A raw tuple would still crash, so it is not the killing case."""
    tests = [
        stored.test_stored_history_cannot_be_built_or_edited_by_a_caller,
        lambda: stored.test_load_refuses_raw_events("ledger"),
    ]
    _passes_then_fails_under(monkeypatch, "_check_stored_history", _no_op, tests, module=ledger_module)


def test_stored_history_made_constructible_is_caught(monkeypatch):
    """AC-4: if a caller could construct a StoredHistory, it could hand load any events it liked."""
    def open_init(self, user_id, events):
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "events", tuple(events))

    tests = [stored.test_stored_history_cannot_be_built_or_edited_by_a_caller]
    _passes_then_fails_under(monkeypatch, "__init__", open_init, tests, module=ledger_module.StoredHistory)


def test_stored_history_made_mutable_is_caught(monkeypatch):
    """AC-4: if a StoredHistory's events could be reassigned, a ledger's stored history could be extended."""
    tests = [stored.test_stored_history_cannot_be_built_or_edited_by_a_caller]
    _passes_then_fails_under(
        monkeypatch, "__setattr__", object.__setattr__, tests, module=ledger_module.StoredHistory
    )
