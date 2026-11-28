"""ADR-330 (57): the one read-only line of a closed trade: what the plan was and how the trade ended, built by the
server ("Plan: stop Rs 300, target Rs 800. Closed by your exit at 11:23."). Real case 27 Nov: settled trade 173.
Every ending and every answer state of the plan: stated, not set, not available, no plan, no closing record."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.timeutil import IST
from ofo.tracking.plan_final import NOT_SHOWN, PlanLevels, plan_final_line

D = Decimal
AT = datetime.datetime(2026, 11, 27, 11, 23, tzinfo=IST)
TODAY = datetime.date(2026, 11, 27)
BOTH = PlanLevels(D("300"), D("800"))


def line(plan=BOTH, ending="exit", at=AT, today=TODAY):
    return str(plan_final_line(plan, ending, at, today))


def test_the_owner_example_word_for_word():
    assert line() == "Plan: stop Rs 300, target Rs 800. Closed by your exit at 11:23."


@pytest.mark.parametrize(("ending", "how"), [("exit", "your exit"), ("stop", "your stop"),
                                             ("settle", "expiry settlement")])
def test_every_ending_is_named(ending, how):
    assert line(ending=ending).endswith(f"Closed by {how} at 11:23.")


def test_time_is_the_closing_order_in_ist_whatever_zone_it_arrives_in():
    utc = datetime.datetime(2026, 11, 27, 5, 53, tzinfo=datetime.UTC)
    assert line(at=utc).endswith("at 11:23.")


def test_a_trade_closed_on_an_earlier_day_names_the_day():
    assert line(at=datetime.datetime(2026, 11, 24, 15, 30, tzinfo=IST), ending="settle").endswith(
        "Closed by expiry settlement on 24 Nov at 15:30.")


def test_large_levels_use_indian_grouping():
    assert line(PlanLevels(D("1234567"), D("80000"))).startswith("Plan: stop Rs 12,34,567, target Rs 80,000.")


def test_a_level_the_plan_does_not_set_says_no_stop_or_no_target():
    assert line(PlanLevels(D("300"), None)).startswith("Plan: stop Rs 300, no target.")
    assert line(PlanLevels(None, D("800"))).startswith("Plan: no stop, target Rs 800.")
    assert line(PlanLevels(None, None)).startswith("Plan: no stop, no target.")


def test_a_level_that_cannot_be_worked_out_prints_no_number_and_is_not_called_unset():
    got = line(PlanLevels(NOT_SHOWN, D("800")))
    assert got.startswith("Plan: stop not available, target Rs 800.")
    assert "no stop" not in got


def test_no_plan_at_all_says_so_and_still_says_how_it_ended():
    assert line(None) == "No plan was set for this trade. Closed by your exit at 11:23."


def test_no_closing_record_says_how_it_ended_is_not_recorded_and_invents_nothing():
    assert line(ending=None, at=None) == "Plan: stop Rs 300, target Rs 800. How this trade ended is not recorded."
    assert line(None, None, None) == "No plan was set for this trade. How this trade ended is not recorded."


def test_an_ending_without_a_time_does_not_print_a_time():
    assert line(at=None) == "Plan: stop Rs 300, target Rs 800. Closed by your exit."


def test_a_naive_time_is_refused_not_guessed():
    with pytest.raises(ValueError):
        plan_final_line(BOTH, "exit", datetime.datetime(2026, 11, 27, 11, 23), TODAY)  # noqa: DTZ001 - the naive time is the case


def test_an_unknown_ending_is_refused():
    with pytest.raises(ValueError):
        plan_final_line(BOTH, "plan_stop", AT, TODAY)
