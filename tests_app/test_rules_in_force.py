"""GC-ICFIX u113 (ADR-295, ADR-252): the plan card's target and stop are read from the SAME body and per-stage values the live
check uses (``settings_in_force.rule_of``). Real numbers: the iron condor system playbook, T-07 weekly 50/50/80, monthly 50/50/75,
T-06 50/50/40. No database: the function takes the resolved body."""
from __future__ import annotations

import copy
import json
import pathlib
from decimal import Decimal as D

from ofo_app import adjustment_check as check
from ofo_app import settings_in_force as sif

SEED = pathlib.Path(__file__).resolve().parent.parent / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
IC = next(e["body"] for e in json.loads(SEED.read_text(encoding="utf-8"))["playbooks"] if e["strategy_type"] == "ic")


def _resolved(body, plan=False):
    return check.Resolved("plan" if plan else "system", check.with_plan_target(body) if plan else body, 1, None, not plan,
                          saved_before_adr247=False)


def test_the_real_iron_condor_rows_per_stage_weekly_and_monthly():
    r = _resolved(IC)
    assert sif.rule_of(r, "T-07", "weekly") == sif.RuleInForce(True, (("Early", D(50)), ("Middle", D(50)), ("Last day", D(80))))
    assert sif.rule_of(r, "T-07", None).stages[-1] == ("Last day", D(80))  # no kind -> the weekly row
    assert sif.rule_of(r, "T-07", "monthly") == sif.RuleInForce(True, (("Early", D(50)), ("Middle", D(50)), ("Last 2 days", D(75))))
    assert sif.rule_of(r, "T-06", "weekly") == sif.RuleInForce(True, (("Early", D(50)), ("Middle", D(50)), ("Last day", D(40))))


def test_a_rule_that_is_off_has_no_number():
    body = copy.deepcopy(IC)
    body["triggers"]["T-07"]["on"] = False
    assert sif.rule_of(_resolved(body), "T-07", "weekly") == sif.RuleInForce(False, ())
    del body["triggers"]["T-06"]  # absent = nothing acts on it
    assert sif.rule_of(_resolved(body), "T-06", "weekly") == sif.RuleInForce(False, ())


def test_a_typed_target_follows_the_min_rule_of_the_check():
    body = copy.deepcopy(IC)
    body["guards"]["profit_target_pct_of_max_profit"] = "90"  # above the last stage's 80: last = min(90, 80)
    assert [v for _, v in sif.rule_of(_resolved(body, plan=True), "T-07", "weekly").stages] == [D(90), D(90), D(80)]
    body["guards"]["profit_target_pct_of_max_profit"] = "60"
    assert [v for _, v in sif.rule_of(_resolved(body, plan=True), "T-07", "weekly").stages] == [D(60), D(60), D(60)]


def test_unreadable_answers_fail_closed():
    none = check.Resolved("none", None, None, None, False, saved_before_adr247=False)
    assert sif.rule_of(none, "T-07", "weekly") is None
    for edit in (lambda b: b["triggers"]["T-07"].update(on="yes"), lambda b: b["triggers"]["T-07"].update(weekly=["50", "x", "80"]),
                 lambda b: b["triggers"]["T-07"].update(weekly=["50", "50"]), lambda b: b.update(triggers="bad"),
                 lambda b: b["triggers"]["T-07"].update(weekly=["", "", ""])):
        body = copy.deepcopy(IC)
        edit(body)
        assert sif.rule_of(_resolved(body), "T-07", "weekly") is None
