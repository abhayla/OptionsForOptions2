"""GC-ADJ2 item 1 (REQ-161/REQ-162): a shown adjustment condition reads in words, from the evaluated body's own label
and unit through the catalogue; never a trigger id with bare numbers."""
from __future__ import annotations

import copy
import re
from decimal import Decimal as D

import pytest
from ofo.adjustment.playbook_eval import Flag, body_from_fixture
from ofo_app.routes.adjustment_check import result_out
from test_adjust_scenarios import PLAYBOOKS

T01 = "Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)"


def _flag(tid: str, value: str, threshold: str, cmp: str) -> Flag:
    return Flag(rule_id=tid, trigger_id=tid, cmp=cmp, value=D(value), threshold=D(threshold), stage_name="Middle")


def _condition(body, flag):
    return result_out(flag, "w", None, body)["condition"]


def test_adj02_conditions_read_in_words_with_units_and_no_trigger_id():
    body = body_from_fixture(PLAYBOOKS, "ic")
    out = {t: _condition(body, _flag(t, v, th, c)) for t, v, th, c in (
        ("T-01", "0.34159", "0.5", "le"), ("T-03", "0.4103", "0.35", "ge"), ("T-09", "2.7", "3", "le"))}
    assert out["T-01"] == T01
    assert out["T-03"] == "Tested short's delta reaches: 0.4103 delta (rule 0.3500 delta)"
    assert out["T-09"] == "A short leg's premium falls below Rs (close for pennies): 2.7000 Rs (rule 3.0000 Rs)"
    for line in out.values():
        assert not re.search(r"\bT-\d", line) and "at or below" not in line and "at or above" not in line


def test_an_edited_label_is_shown_as_edited():
    body = copy.deepcopy(body_from_fixture(PLAYBOOKS, "ic"))
    body["triggers"]["T-01"]["label"] = "Close to a short strike"
    assert _condition(body, _flag("T-01", "0.3416", "0.5", "le")) == "Close to a short strike: 0.3416 % (rule 0.5000 %)"


@pytest.mark.parametrize("label", [None, "", '"quoted"', "x" * 121, " padded "])
def test_a_trigger_without_a_usable_label_shows_its_id(label):
    body = copy.deepcopy(body_from_fixture(PLAYBOOKS, "ic"))
    body["triggers"]["T-01"]["label"] = label
    assert _condition(body, _flag("T-01", "0.3416", "0.5", "le")) in (
        "T-01: 0.3416 % (rule 0.5000 %)", "T-01: 0.3416 (rule 0.5000)")


def test_plan_target_and_stop_say_what_the_numbers_are():
    from ofo_app.routes.adjustment_plan import _values
    ic = _values(body_from_fixture(PLAYBOOKS, "ic"))
    assert ic["target_words"] == "50 % of max profit"
    assert ic["stop_words"] == "50 % of max loss or 4 % of margin, whichever comes first"
    assert _values(body_from_fixture(PLAYBOOKS, "strangle"))["stop_words"] == "50 % of max loss"
    assert _values({"guards": {}})["target_words"] is None and _values({})["stop_words"] is None


def test_no_body_shows_the_id():
    assert _condition(None, _flag("T-01", "0.3416", "0.5", "le")) == "T-01: 0.3416 (rule 0.5000)"
