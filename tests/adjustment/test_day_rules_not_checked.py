"""GC-IC1 step 10 fix (REQ-159 AC-4): a switched-on day rule whose (kind, action) pair the worker does not act on is
answered NotChecked with a named reason (never silent), from ONE table of acting pairs. Pure: no DB."""
from __future__ import annotations

import copy
import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.adjustment import playbook_eval as pe

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED = ROOT / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
NOT_ACTED = (("weekday", 1), ("afterBreak", 2), ("beforeExpiry", 3), ("monthlyWeek", 6), ("dom", 1), ("date", 2),
             ("event", 1), ("away", 1), ("expiry", 1), ("expiry", 3), ("expiry", 6), ("beforeWeekend", 1))


def _ic() -> dict:
    rows = json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]
    return copy.deepcopy(next(r["body"] for r in rows if r["strategy_type"] == "ic"))


def _state() -> pe.StrategyState:
    shorts = (pe.ShortLeg(D(22600), D("0.01"), D("1.95")), pe.ShortLeg(D(23450), D("0.40"), D("60")))
    return pe.StrategyState(expiry_kind="weekly", days_left=3, hhmm="09:30", spot=D("23400"), shorts=shorts,
                            prices_fresh=True)


def _with(rule: dict) -> dict:
    body = _ic()
    body["day_rules"] = [rule]
    return body


@pytest.mark.parametrize(("when", "action"), NOT_ACTED)
def test_a_switched_on_rule_the_worker_cannot_act_on_is_not_checked_with_a_reason(when, action):
    rule = {"on": True, "when": when, "at": "09:30", "action": action}
    answers = pe.day_answers(_with(rule), _state())
    assert [(a.rule_id, a.hit, a.reason) for a in answers] == [(pe.day_rule_id(rule), None, pe.DAY_RULE_NOT_CHECKED)]
    ev = pe.evaluate(_with(rule), _state(), gap_until="09:30")
    got = [r for r in ev.results if r.rule_id == pe.day_rule_id(rule)]
    assert len(got) == 1 and isinstance(got[0], pe.NotChecked) and got[0].code == pe.DAY_RULE_NOT_CHECKED
    assert pe.reason_text(pe.DAY_RULE_NOT_CHECKED)


def test_a_switched_off_rule_is_silent():
    rule = {"on": False, "when": "afterBreak", "at": "09:30", "action": 2}
    assert pe.day_answers(_with(rule), _state()) == ()


def test_the_acting_pairs_are_the_one_table_and_do_not_answer_not_checked():
    assert {("expiry", 5), ("expiry", 4), ("beforeWeekend", 0), ("beforeHoliday", 0)} == pe.ACTING_DAY_PAIRS
    for when, action in sorted(pe.ACTING_DAY_PAIRS):
        rule = {"on": True, "when": when, "at": "09:30", "action": action, "percent": "20"}
        assert pe.day_rule_acts(rule)
        assert all(a.reason != pe.DAY_RULE_NOT_CHECKED for a in pe.day_answers(_with(rule), _state()))


def test_every_switched_on_rule_of_every_system_playbook_acts():
    rows = json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]
    for row in rows:
        for rule in row["body"]["day_rules"]:
            assert pe.day_rule_acts(rule) or not rule["on"], (row["strategy_type"], rule)


def test_ic_system_playbook_switched_on_rules_all_still_act():
    on = [r for r in _ic()["day_rules"] if r["on"]]
    assert {(r["when"], r["action"]) for r in on} == {("beforeWeekend", 0), ("beforeHoliday", 0), ("expiry", 5)}
    assert all(pe.day_rule_acts(r) for r in on)
    assert all(a.reason != pe.DAY_RULE_NOT_CHECKED for a in pe.day_answers(_ic(), _state()))
