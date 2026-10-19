"""REQ-056 AC-12 / ADR-119: every basket build passes ``check_pre_execution``, which reads the calendar itself.

A caller that says ``market_open=True`` on a holiday or outside 09:15-15:30 IST is still refused; one test per entry
point (entry, exit, adjustment, Complete, Retry Failed Leg, Close Partial)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from execution_inputs import all_true_context, check, condor_legs
from partial_inputs import (
    FakeBroker, FakePlanner, book_with_three_filled, entry_context, plan, statuses, three_positions,
)

from ofo.engine import Strategy
from ofo.execution import CheckCode
from ofo.execution.context import ExecutionAction
from ofo.execution.partial import close_partial_strategy, complete_strategy, retry_failed_leg
from ofo.timeutil import IST

HOLIDAY = datetime.datetime(2026, 10, 20, 10, 0, tzinfo=IST)  # Dussehra, NSE closed
BEFORE_OPEN = datetime.datetime(2026, 10, 21, 9, 14, 59, tzinfo=IST)
AT_CLOSE = datetime.datetime(2026, 10, 21, 15, 30, 0, tzinfo=IST)
NO_DATA_YEAR = datetime.datetime(2027, 1, 5, 10, 0, tzinfo=IST)
OPEN_NOW = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)
CLOSED = "Market closed. You can review your plan; execution opens at 09:15 on Wed 21 Oct."
CLOSED_TIMES = [HOLIDAY, BEFORE_OPEN]


def _check(ctx, catalogue, eligibility):  # noqa: ANN001, ANN202
    return check(Strategy(condor_legs()), ctx, catalogue, eligibility)


@pytest.mark.parametrize("when", [HOLIDAY, BEFORE_OPEN, AT_CLOSE])
def test_ac12_entry_refused_though_caller_says_open(when, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: ENTRY at a holiday / 09:14:59 / 15:30:00 is MARKET_CLOSED even with market_open=True."""
    result = _check(all_true_context(as_of=when, market_open=True), catalogue, eligibility)
    assert CheckCode.MARKET_CLOSED in result.failed_codes


def test_ac12_entry_message_names_the_next_trading_day(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: the refusal text is the ADR-119 sentence with the next open date (Dussehra -> Wed 21 Oct)."""
    result = _check(all_true_context(as_of=HOLIDAY, market_open=True), catalogue, eligibility)
    assert [f.reason for f in result.failures if f.code is CheckCode.MARKET_CLOSED] == [CLOSED]


def test_ac12_open_session_passes_the_market_check(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: Wed 21 Oct 10:00 and 09:15:00 sharp with market_open=True do not raise MARKET_CLOSED."""
    for when in (OPEN_NOW, datetime.datetime(2026, 10, 21, 9, 15, 0, tzinfo=IST)):
        result = _check(all_true_context(as_of=when, market_open=True), catalogue, eligibility)
        assert CheckCode.MARKET_CLOSED not in result.failed_codes


def test_ac12_year_without_data_is_unconfirmed_not_open(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: 2027 has no holiday data: blocked with the 'could not confirm' message even with market_open=True."""
    result = _check(all_true_context(as_of=NO_DATA_YEAR, market_open=True), catalogue, eligibility)
    assert [f.reason for f in result.failures if f.code is CheckCode.MARKET_CLOSED] == [
        "We could not confirm that the market is open. Execution is paused until it is confirmed."]


@pytest.mark.parametrize("action", [ExecutionAction.EXIT, ExecutionAction.ADJUSTMENT])
def test_ac12_exit_and_adjustment_refused_on_a_holiday(action, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: an EXIT and an ADJUSTMENT context on Dussehra with market_open=True are refused by the same gate."""
    result = _check(all_true_context(as_of=HOLIDAY, market_open=True, action=action), catalogue, eligibility)
    assert CheckCode.MARKET_CLOSED in result.failed_codes


@pytest.mark.parametrize("when", CLOSED_TIMES)
def test_ac12_complete_strategy_refused(when, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: Complete Strategy prepares nothing outside the session though market_open=True."""
    prep = complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book_with_three_filled(),
                             FakePlanner(), entry_context(as_of=when, market_open=True), catalogue, eligibility)
    assert prep.orders == () and CheckCode.MARKET_CLOSED in prep.gate.failed_codes


@pytest.mark.parametrize("when", CLOSED_TIMES)
def test_ac12_retry_failed_leg_refused(when, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: Retry Failed Leg prepares nothing outside the session though market_open=True."""
    prep = retry_failed_leg(plan(), "leg-4", FakeBroker(three_positions(), statuses()), book_with_three_filled(),
                            FakePlanner(), entry_context(as_of=when, market_open=True), catalogue, eligibility)
    assert prep.orders == () and CheckCode.MARKET_CLOSED in prep.gate.failed_codes


@pytest.mark.parametrize("when", CLOSED_TIMES)
def test_ac12_close_partial_refused(when, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-12: Close Partial (the exit baskets) prepares nothing outside the session though market_open=True."""
    positions = three_positions((D("40.00"), D("80.00"), D("120.00")))
    prep = close_partial_strategy(plan(), FakeBroker(positions, statuses()), book_with_three_filled(), FakePlanner(),
                                  entry_context(as_of=when, market_open=True), catalogue, eligibility)
    assert prep.orders == () and prep.gate is not None and CheckCode.MARKET_CLOSED in prep.gate.failed_codes
