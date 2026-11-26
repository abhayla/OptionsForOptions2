"""P8 (ADR-330 (9)): what a plan changed against its playbook; pure functions."""
from __future__ import annotations

import copy

from ofo.adjustment import plan_diff

BOOK = {
    "schema": 1, "strategy_type": "ic", "stages": {"monthly": 1},
    "triggers": {"T-01": {"on": True, "monthly": ["1.5"]}, "T-02": {"on": True, "monthly": ["2"]}},
    "rules": [{"id": "T-01", "any_of": ["T-01"]}],
    "guards": {"hide_oi_below": "3"},
}
EMPTY = {"changed": [], "switched_off": []}


def test_identical_is_empty():
    assert plan_diff.diff(copy.deepcopy(BOOK), BOOK) == EMPTY
    assert plan_diff.subset_of(copy.deepcopy(BOOK), BOOK)


def test_value_changed_is_listed():
    plan = copy.deepcopy(BOOK)
    plan["triggers"]["T-01"]["monthly"] = ["2.5"]
    plan["guards"]["hide_oi_below"] = "2"
    assert plan_diff.diff(plan, BOOK) == {"changed": ["guards.hide_oi_below", "triggers.T-01"], "switched_off": []}


def test_switched_off_is_listed_not_changed():
    plan = copy.deepcopy(BOOK)
    plan["triggers"]["T-02"]["on"] = False
    assert plan_diff.diff(plan, BOOK) == {"changed": [], "switched_off": ["triggers.T-02"]}


def test_a_condition_removed_from_the_plan_is_switched_off():
    plan = copy.deepcopy(BOOK)
    del plan["guards"]["hide_oi_below"]
    assert plan_diff.diff(plan, BOOK)["switched_off"] == ["guards.hide_oi_below"]


def test_an_added_condition_is_refused_naming_it():
    plan = copy.deepcopy(BOOK)
    plan["triggers"]["T-99"] = {"on": True, "monthly": ["1"]}
    assert not plan_diff.subset_of(plan, BOOK)
    assert plan_diff.added(plan, BOOK) == ["triggers.T-99"]


def test_the_sheets_own_levels_and_plan_settings_are_not_conditions():
    plan = copy.deepcopy(BOOK)
    plan["guards"].update({"loss_stop_rupees": "5000.00", "time_exit": "15:00", "profit_target_rupees": "100"})
    plan["settings"] = {"other.carry_gap_percent": "1"}
    assert plan_diff.subset_of(plan, BOOK)
    assert plan_diff.diff(plan, BOOK) == EMPTY


def test_reset_equals_the_playbook_body_and_is_a_copy():
    plan = copy.deepcopy(BOOK)
    plan["triggers"]["T-01"]["on"] = False
    plan["triggers"]["T-99"] = {"on": True}
    got = plan_diff.reset(plan, BOOK)
    assert got == BOOK
    assert got is not BOOK
    assert got["triggers"] is not BOOK["triggers"]
    assert plan_diff.diff(got, BOOK) == EMPTY
