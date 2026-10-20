"""ADR-127: the owner's kill switch refuses every basket build at the same gate as ADR-119 (``check_pre_execution``).

One test per entry point (entry, exit, adjustment, Complete, Retry Failed Leg, Close Partial) at Wed 2026-10-21 10:00
IST, market open: with the switch on each is refused with exactly the ADR-127 sentence; with it off the same call is
not. (The condor fixture's own legs have expired by that date; only the switch and market codes are asserted.)
Unknown (None, the switch could not be read) is refused like on (fail closed)."""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

import pytest
from execution_inputs import all_true_context, check, condor_legs
from ofo.engine import Strategy
from ofo.execution import CheckCode
from ofo.execution.context import ExecutionAction, ExecutionContext
from ofo.execution.partial import close_partial_strategy, complete_strategy, retry_failed_leg
from ofo.execution.safety import paused_failures
from ofo.timeutil import IST
from partial_inputs import (
    FakeBroker,
    FakePlanner,
    book_with_three_filled,
    entry_context,
    plan,
    statuses,
    three_positions,
)

OPEN_NOW = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)  # Wednesday, market open
ADR_127 = ("Execution is paused by the platform right now. You can review and save your plan; "
           "no orders can be sent.")


def _check(ctx, catalogue, eligibility):
    return check(Strategy(condor_legs()), ctx, catalogue, eligibility)


def _paused_reasons(result) -> list[str]:
    return [f.reason for f in result.failures if f.code is CheckCode.PLATFORM_PAUSED]


def test_switch_on_refuses_entry_at_market_open_with_exactly_the_adr127_sentence(catalogue, eligibility) -> None:
    result = _check(all_true_context(as_of=OPEN_NOW, market_open=True, platform_paused=True), catalogue, eligibility)
    assert _paused_reasons(result) == [ADR_127]
    assert result.failures[0].code is CheckCode.PLATFORM_PAUSED  # the first failure is the one a user is shown
    assert CheckCode.MARKET_CLOSED not in result.failed_codes  # the market itself is open: only the switch refuses


def test_switch_off_passes_the_same_call(catalogue, eligibility) -> None:
    result = _check(all_true_context(as_of=OPEN_NOW, market_open=True, platform_paused=False), catalogue, eligibility)
    assert CheckCode.PLATFORM_PAUSED not in result.failed_codes
    assert CheckCode.PLATFORM_PAUSED in result.passed
    assert CheckCode.MARKET_CLOSED not in result.failed_codes  # open market + switch off: neither market check fires


def test_switch_unknown_is_refused_like_on(catalogue, eligibility) -> None:
    result = _check(all_true_context(as_of=OPEN_NOW, market_open=True, platform_paused=None), catalogue, eligibility)
    assert _paused_reasons(result) == [ADR_127]


@pytest.mark.parametrize("action", [ExecutionAction.EXIT, ExecutionAction.ADJUSTMENT])
def test_switch_on_refuses_exit_and_adjustment(action, catalogue, eligibility) -> None:
    """An exit is exempt from the margin/data/entitlement checks, never from the kill switch."""
    result = _check(all_true_context(as_of=OPEN_NOW, market_open=True, platform_paused=True, action=action),
                    catalogue, eligibility)
    assert _paused_reasons(result) == [ADR_127]


def test_switch_on_refuses_complete_strategy(catalogue, eligibility) -> None:
    prep = complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book_with_three_filled(),
                             FakePlanner(), entry_context(as_of=OPEN_NOW, market_open=True, platform_paused=True),
                             catalogue, eligibility)
    assert prep.orders == () and CheckCode.PLATFORM_PAUSED in prep.gate.failed_codes


def test_switch_on_refuses_retry_failed_leg(catalogue, eligibility) -> None:
    prep = retry_failed_leg(plan(), "leg-4", FakeBroker(three_positions(), statuses()), book_with_three_filled(),
                            FakePlanner(), entry_context(as_of=OPEN_NOW, market_open=True, platform_paused=True),
                            catalogue, eligibility)
    assert prep.orders == () and CheckCode.PLATFORM_PAUSED in prep.gate.failed_codes


def test_switch_on_refuses_close_partial(catalogue, eligibility) -> None:
    positions = three_positions((D("40.00"), D("80.00"), D("120.00")))
    prep = close_partial_strategy(plan(), FakeBroker(positions, statuses()), book_with_three_filled(), FakePlanner(),
                                  entry_context(as_of=OPEN_NOW, market_open=True, platform_paused=True),
                                  catalogue, eligibility)
    assert prep.orders == () and prep.gate is not None and CheckCode.PLATFORM_PAUSED in prep.gate.failed_codes


def test_the_switch_input_is_required_no_default() -> None:
    """A caller that forgets the switch cannot build a context (finding caller-supplied-verdict-trusted)."""
    fields = {f.name: getattr(all_true_context(), f.name) for f in dataclasses.fields(ExecutionContext)}
    del fields["platform_paused"]
    with pytest.raises(TypeError):
        ExecutionContext(**fields)
    with pytest.raises(ValueError):
        all_true_context(platform_paused="no")  # a string is not a verdict


def test_paused_failures_only_an_explicit_false_passes() -> None:
    assert paused_failures(False) == []
    assert [f.reason for f in paused_failures(True)] == [ADR_127]
    assert [f.reason for f in paused_failures(None)] == [ADR_127]


def test_the_refusal_shows_all_four_parts(catalogue, eligibility) -> None:
    result = _check(all_true_context(as_of=OPEN_NOW, market_open=True, platform_paused=True), catalogue, eligibility)
    assert result.failures[0].text.splitlines() == [
        ADR_127,
        "No order can be sent while execution is paused.",
        "Blocked: Execution of this strategy.",
        "Next step: Review and save your plan now, and come back when execution is on again.",
    ]
