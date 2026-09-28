"""Mutation tests: flipping each access guard makes the real test suite fail (W-007, Tier A).

Each test replaces ONE guard in ``ofo.entitlements.engine`` with a wrong version (via monkeypatch),
then runs the real tests from ``test_engine`` that protect it and asserts they now FAIL. It also runs
them un-mutated first, so a pass here means "this test detects exactly this mutation", not "this test
was already broken".
"""

from collections.abc import Callable

import pytest

from ofo.entitlements import engine
from ofo.entitlements.events import Status

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
    """AC-4: a referral that ignores the current Pro end (20 Sep -> 20 Oct instead of 10 Oct -> 9 Nov) must fail."""
    _passes_then_fails_under(monkeypatch, "_stacked_start", lambda granted_at, current_end, stacking: granted_at, [
        suite.test_stacked_referral_real_example_pro_until_10_oct_plus_referral_on_20_sep_is_9_nov,
        suite.test_three_stacked_referrals_add_ninety_days,
    ])


def test_stacking_switch_ignored_is_caught(monkeypatch):
    """AC-4: stacking that stays on when the admin switches it off must fail."""
    _passes_then_fails_under(
        monkeypatch, "_stacked_start", lambda granted_at, current_end, stacking: max(granted_at, current_end),
        [suite.test_stacking_off_starts_the_referral_at_its_grant_time],
    )


def test_coverage_chaining_removed_is_caught(monkeypatch):
    """AC-4: stacking on only the first covering entitlement (not the whole unbroken run) must fail at 3 referrals."""
    def one_step(ledger, at):
        ends = [r.end for r in engine.resolve(ledger) if r.end is not None and engine._covers(r.grant.start, r.end, at)]
        return max(ends) if ends else at

    _passes_then_fails_under(monkeypatch, "finite_pro_end", one_step, [
        suite.test_three_stacked_referrals_add_ninety_days,
    ])


def _ignoring(status: Status):
    original = engine._effective_end

    def mutant(grant, change):
        return original(grant, None if change is not None and change.status is status else change)

    return mutant


def test_revocation_ignored_is_caught(monkeypatch):
    """AC-4: a revocation that does not cut access must fail."""
    _passes_then_fails_under(monkeypatch, "_effective_end", _ignoring(Status.REVOKED), [
        suite.test_revocation_is_a_new_audited_event_and_cuts_access_at_its_instant,
        suite.test_revoking_the_base_entitlement_does_not_move_a_stacked_referral_end_date,
    ])


def test_trial_early_end_ignored_is_caught(monkeypatch):
    """AC-4: an ADR-039 early trial end that does not cut access must fail."""
    _passes_then_fails_under(monkeypatch, "_effective_end", _ignoring(Status.ENDED), [
        suite.test_trial_is_ended_early_when_an_already_trialled_client_id_is_connected,
    ])
