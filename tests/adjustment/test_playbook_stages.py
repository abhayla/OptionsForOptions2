"""GC-ADJ2 step 2: the stage gap / overlap check and the unknown-key check (REQ-159 AC-1, B4 (c)), on the real
function, with the 12 shipped system bodies as the population that must pass."""
from __future__ import annotations

import copy
import json
import pathlib

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import playbook_stages as ps
from ofo.adjustment.playbook_types import TYPE_KEYS
from ofo.errors import render

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "adjust_scenarios" / "_playbooks.json").read_text("utf-8"))


def _body(weekly: list[tuple[str, int, int | None]]) -> dict:
    body = copy.deepcopy(pe.body_from_fixture(FIXTURE, "ic"))
    body["stages"]["weekly"] = [{"name": n, "from": f, "to": t} for n, f, t in weekly]
    return body


@pytest.mark.parametrize("key", TYPE_KEYS)
def test_every_shipped_system_body_passes(key):
    body = pe.body_from_fixture(FIXTURE, key)
    ps.check_keys(body)
    ps.check_stages(body)


def test_overlap_names_the_days_and_the_stages():
    with pytest.raises(ps.StageProblem) as caught:
        ps.check_stages(_body([("Early", 5, None), ("Near", 2, 4), ("Last", 0, 4)]))
    assert caught.value.template == ps.OVERLAP
    assert render(caught.value.template, **caught.value.slots).what_happened == (
        "Days 2 to 4 are in both Last and Near (weekly expiries).")  # the stage starting earlier is named first


def test_gap_names_the_days():
    with pytest.raises(ps.StageProblem) as caught:
        ps.check_stages(_body([("Early", 7, None), ("Near", 2, 4), ("Last", 0, 1)]))
    assert caught.value.template == ps.GAP
    assert render(caught.value.template, **caught.value.slots).what_happened == (
        "Days 5 to 6 are in no stage (weekly expiries).")


def test_gap_before_the_first_stage_and_after_a_closed_last_stage():
    with pytest.raises(ps.StageProblem) as first:
        ps.check_stages(_body([("Early", 5, None), ("Near", 2, 4)]))
    assert (first.value.slots["from_day"], first.value.slots["to_day"]) == (0, 1)
    with pytest.raises(ps.StageProblem) as last:
        ps.check_stages(_body([("Near", 0, 4), ("Early", 5, 9)]))
    assert (last.value.slots["from_day"], last.value.slots["to_day"]) == (10, ps.OPEN_END)


def test_monthly_kind_is_checked_too():
    body = copy.deepcopy(pe.body_from_fixture(FIXTURE, "ic"))
    body["stages"]["monthly"][1]["to"] = 8  # day 9 left in no stage
    with pytest.raises(ps.StageProblem) as caught:
        ps.check_stages(body)
    assert caught.value.slots["expiry"] == "monthly"
    assert (caught.value.slots["from_day"], caught.value.slots["to_day"]) == (9, 9)


@pytest.mark.parametrize("weekly", [
    [("Early", 5, None), ("Near", 4, 2), ("Last", 0, 1)],  # to below from
    [("Early", 5, None), ("Near", 2, 4), ("Last", -1, 1)],  # negative day
])
def test_a_stage_with_impossible_days_is_invalid_naming_the_field(weekly):
    with pytest.raises(ps.StageProblem) as caught:
        ps.check_stages(_body(weekly))
    assert caught.value.template == ps.INVALID
    assert caught.value.slots["field"].startswith("stages.weekly.")


def test_a_stage_name_the_catalogue_cannot_quote_is_invalid_not_a_crash():
    with pytest.raises(ps.StageProblem) as caught:
        ps.check_stages(_body([("Early ", 5, None), ("Near", 2, 4), ("Last", 0, 1)]))
    assert caught.value.slots == {"field": "stages.weekly.0.name"}


def test_unknown_stage_key_and_unknown_body_key_are_refused():
    body = _body([("Early", 5, None), ("Near", 2, 4), ("Last", 0, 1)])
    body["stages"]["weekly"][0]["colour"] = "red"
    with pytest.raises(ps.StageProblem):
        ps.check_stages(body)
    extra = pe.body_from_fixture(FIXTURE, "ic")
    extra["surprise"] = 1
    with pytest.raises(ps.StageProblem) as caught:
        ps.check_keys(extra)
    assert caught.value.slots == {"field": "body"}
