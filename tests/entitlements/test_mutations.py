"""Mutation tests: flipping each access guard makes the real test suite fail (W-007, Tier A).

Each test replaces ONE guard in ``ofo.entitlements.engine`` with a wrong version (via monkeypatch),
then runs the real tests from ``test_engine`` that protect it and asserts they now FAIL. It runs them
un-mutated first, so a pass here means "this test detects exactly this mutation", not "this test was
already broken".
"""

from collections.abc import Callable

import pytest

from ofo.entitlements import engine
from ofo.entitlements.events import Placement, Status

from . import test_engine as suite


def _passes_then_fails_under(monkeypatch: pytest.MonkeyPatch, name: str, mutant, tests: list[Callable[[], None]]):
    for test in tests:
        test()  # baseline: the guard is intact, the test passes
    monkeypatch.setattr(engine, name, mutant)
    for test in tests:
        with pytest.raises(AssertionError):
            test()


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
