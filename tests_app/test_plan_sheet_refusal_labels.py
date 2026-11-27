"""27 Nov 10:28 / 10:59: a plan-sheet refusal names the box as the sheet prints it, never the code word.

RCA: every plan-sheet refusal went through ``playbook_body_invalid`` ("The playbook value {field} is not valid.") with
the raw field name ("time_exit"). Class: every refusal of a plan-sheet box; the one place that words them is
``ofo_app.routes.adjustment_plan._refused`` with the sheet's own labels (``PLAN_SHEET_LABEL_TEXT``)."""
from __future__ import annotations

import datetime

import pytest
from ofo.errors.explanations import PLAN_SHEET_LABEL_TEXT
from ofo_app.routes import adjustment_plan as route
from ofo_app.routes.adjustment_plan import PlanIn, TimeExitIn

TODAY, LAST = datetime.date(2026, 11, 27), datetime.date(2026, 12, 29)


def _said(exc: Exception) -> str:
    return route._refused(exc).message.what_happened


def test_a_time_exit_date_in_the_past_says_so_with_the_box_label():
    with pytest.raises(Exception) as caught:
        route.check_time_exit_day({"at": "15:15", "on": "2026-11-26"}, TODAY, LAST)
    assert _said(caught.value) == "Time exit date is in the past."


def test_a_time_exit_date_after_the_last_expiry_uses_the_label_not_the_code_word():
    with pytest.raises(Exception) as caught:
        route.check_time_exit_day({"at": "15:15", "on": "2027-01-05"}, TODAY, LAST)
    assert _said(caught.value) == "Time exit date is not valid."


@pytest.mark.parametrize(("box", "label"), [("target", "Target"), ("stop", "Stop"), ("target_rupees", "Target (Rs)"),
                                            ("stop_rupees", "Stop (Rs)"), ("max_adjustments", "Max adjustments"),
                                            ("time_exit", "Time exit")])
def test_every_sheet_box_names_its_catalogue_label(box, label):
    assert PLAN_SHEET_LABEL_TEXT[box] == label  # the refusal's words are the sheet's own label
    assert _said(route._bad(box)) == f"{label} is not valid."


def test_the_date_box_label_is_the_catalogues():
    assert PLAN_SHEET_LABEL_TEXT["time_exit_on"].startswith("Time exit date")


def test_a_bad_clock_text_names_the_time_exit_box():
    with pytest.raises(Exception) as caught:
        route.with_overrides({"guards": {}}, PlanIn(playbook_id=1, time_exit=TimeExitIn(at="25:99", on="")))
    assert _said(caught.value) == "Time exit is not valid."
