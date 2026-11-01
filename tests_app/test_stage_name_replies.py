"""Class "a reply field holding a playbook stage name is typed Identifier" (a stage named "Last day" answered 500 on
every check and opportunities read in that stage).

RCA: the stage name is the user's own words with spaces, an Identifier refuses them. Class: every reply model that
echoes a stage name (CheckStageOut, OpportunityOut.stage; the playbook Test route reuses CheckStageOut). Detection:
each model is built with every stage name of the scenario library and of every system playbook, so a name the type
refuses fails CI, not production."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from ofo.errors.explanations import render_explanation
from ofo_app import adjustment_check as check
from ofo_app.adjustment_check import stage_out
from ofo_app.routes.adjustment_check import CheckStageOut
from ofo_app.routes.adjustment_opportunities import OpportunityOut

ROOT = Path(__file__).resolve().parents[1]


def _names(stages: dict) -> set[str]:
    return {s["name"] for kind in stages.values() for s in kind}


def _all_names() -> list[str]:
    lib = json.loads((ROOT / "tests/fixtures/adjust_scenarios/_playbooks.json").read_text(encoding="utf-8"))
    names = _names(lib["stages"])
    system = json.loads((ROOT / "backend/ofo/adjustment/system_playbooks.json").read_text(encoding="utf-8"))
    for pb in system["playbooks"]:
        names |= _names(pb["body"]["stages"])
    return sorted(names | {"Last day", "Last 2 days"})


def test_the_name_lists_are_not_empty_and_include_a_name_with_a_space():
    names = _all_names()
    assert names and any(" " in n for n in names)


@pytest.mark.parametrize("name", _all_names())
def test_check_stage_reply_accepts_every_stage_name(name):
    out = CheckStageOut.model_validate({"name": render_explanation("adjust_check_stage_name", name=name), "index": 2})
    assert out.model_dump(mode="json") == {"name": name, "index": 2}
    assert CheckStageOut.model_validate(stage_out(name, 2)).model_dump(mode="json")["name"] == name


@pytest.mark.parametrize("name", _all_names())
def test_opportunity_record_accepts_every_stage_name(name):
    row = {"id": 1, "rule_id": "R-1", "trigger_id": "T-19", "stage": check.stage_name_text(name), "value": None,
           "threshold": None, "condition": None, "shown_at": datetime.datetime(2026, 11, 1, tzinfo=datetime.UTC),
           "outcome": "open", "outcome_text": render_explanation("suggestion_outcome_open"), "detail": None,
           "can_act": True}
    assert OpportunityOut.model_validate(row).model_dump(mode="json")["stage"] == name


def test_no_stage_and_an_unusable_name_never_raise():
    assert stage_out(None, None) == {"name": None, "index": None}
    assert str(check.stage_name_text('say "hi"')) == "current"
