"""GC-IC1 step 1b (REQ-159 AC-4, REQ-170, S-06): the before-weekend and before-holiday day rules (15:00, action 0
"Run the carry check") are yes/no readings through step 1a's day-rule path (``day_answers``) and ``gate_readings``:
True from ``at`` on a matching day, no reading before it or on another day, NotChecked "holiday list not known" when
the year has no holiday data. Pure: no DB, no clock read; dates and the holiday table are passed in."""
from __future__ import annotations

import copy
import dataclasses
import datetime
import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.adjustment import gate_readings
from ofo.adjustment import playbook_eval as pe
from ofo.errors import render

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED = ROOT / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
GAP = "09:30"
WEEKEND = "day:beforeWeekend:0"
HOLIDAY = "day:beforeHoliday:1"
FRI = datetime.date(2026, 10, 30)  # a session; Saturday 31 Oct follows
WED = datetime.date(2026, 10, 28)  # Thursday 29 Oct is a normal session
MON_BEFORE_HOLIDAY = datetime.date(2026, 11, 23)  # Tuesday 24 Nov: Prakash Gurpurb (NSE F&O list)
HOLIDAY_ITSELF = datetime.date(2026, 11, 24)
LAST_2026 = datetime.date(2026, 12, 31)  # Thursday: Friday 1 Jan 2027 has no holiday data
#: a test table: Friday 6 Nov 2026 listed as a holiday, so Thursday 5 Nov is before a holiday AND before a weekend
THU_BEFORE_FRI_HOLIDAY = datetime.date(2026, 11, 5)
TABLE_FRI_HOLIDAY = {2026: frozenset({datetime.date(2026, 11, 6)})}


def _ic() -> dict:
    rows = json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]
    return copy.deepcopy(next(r["body"] for r in rows if r["strategy_type"] == "ic"))


def _state(today: datetime.date = FRI, hhmm: str | None = "15:00", holidays=None, **kw) -> pe.StrategyState:
    shorts = (pe.ShortLeg(D(23200), D("0.15"), D("40")), pe.ShortLeg(D(23800), D("0.15"), D("40")))
    return pe.StrategyState(expiry_kind="weekly", days_left=4, hhmm=hhmm, spot=D("23500"), shorts=shorts,
                            prices_fresh=True, carry_days=pe.carry_day_kinds(today, holidays), **kw)


def _reading(ev: pe.Evaluation, rid: str):
    got = gate_readings.readings(ev).get(rid)
    return None if got is None else got[1]


def _result(ev: pe.Evaluation, rid: str) -> list:
    return [r for r in ev.results if r.rule_id == rid]


def test_the_seeded_ic_carry_rules_are_switched_on_at_1500_action_0():
    rules = _ic()["day_rules"]
    assert rules[0] == {"on": True, "when": "beforeWeekend", "at": "15:00", "action": 0}
    assert rules[1] == {"on": True, "when": "beforeHoliday", "at": "15:00", "action": 0}


@pytest.mark.parametrize(("today", "holidays", "kinds"), [
    (FRI, None, {"beforeWeekend"}),
    (WED, None, set()),
    (MON_BEFORE_HOLIDAY, None, {"beforeHoliday"}),
    (HOLIDAY_ITSELF, None, set()),  # the day is a holiday itself: no carry day
    (datetime.date(2026, 10, 31), None, set()),  # Saturday
    (THU_BEFORE_FRI_HOLIDAY, TABLE_FRI_HOLIDAY, {"beforeWeekend", "beforeHoliday"}),
])
def test_carry_day_kinds_from_the_calendar(today, holidays, kinds):
    assert pe.carry_day_kinds(today, holidays) == frozenset(kinds)


def test_carry_day_kinds_year_missing_is_not_known():
    assert pe.carry_day_kinds(LAST_2026) is None  # 1 Jan 2027: no data, never assumed a session
    assert pe.carry_day_kinds(datetime.date(2027, 1, 4)) is None


def test_core_friday_1500_reads_true_through_the_gate():
    ev = pe.evaluate(_ic(), _state(), gap_until=GAP)
    flags = _result(ev, WEEKEND)
    assert len(flags) == 1 and isinstance(flags[0], pe.Flag), flags
    spec, reading = gate_readings.readings(ev)[WEEKEND]
    assert spec.cmp == "bool" and spec.ladder == () and reading is True
    assert _reading(ev, HOLIDAY) is None and _result(ev, HOLIDAY) == []


def test_friday_1459_no_reading():
    ev = pe.evaluate(_ic(), _state(hhmm="14:59"), gap_until=GAP)
    assert _reading(ev, WEEKEND) is None and _result(ev, WEEKEND) == [] and WEEKEND not in ev.clear


def test_wednesday_1500_no_reading_and_no_false_clear():
    ev = pe.evaluate(_ic(), _state(WED), gap_until=GAP)
    for rid in (WEEKEND, HOLIDAY):
        assert _reading(ev, rid) is None and _result(ev, rid) == [] and rid not in ev.clear


def test_monday_before_a_listed_holiday_reads_the_holiday_rule_only():
    ev = pe.evaluate(_ic(), _state(MON_BEFORE_HOLIDAY), gap_until=GAP)
    assert _reading(ev, HOLIDAY) is True and _reading(ev, WEEKEND) is None


def test_attack1_year_missing_never_fires_and_says_holiday_list_not_known():
    ev = pe.evaluate(_ic(), _state(LAST_2026), gap_until=GAP)
    for rid in (WEEKEND, HOLIDAY):
        got = _result(ev, rid)
        assert len(got) == 1 and isinstance(got[0], pe.NotChecked), got
        assert got[0].code == pe.HOLIDAY_LIST_UNKNOWN
        assert _reading(ev, rid) is None
    assert "holiday list is not known" in render(pe.HOLIDAY_LIST_UNKNOWN).what_happened


def test_year_missing_before_1500_is_silent():
    ev = pe.evaluate(_ic(), _state(LAST_2026, hhmm="14:59"), gap_until=GAP)
    assert _result(ev, WEEKEND) == [] and _result(ev, HOLIDAY) == []


def test_attack2_thursday_before_a_friday_holiday_reads_both_rules_one_each():
    ev = pe.evaluate(_ic(), _state(THU_BEFORE_FRI_HOLIDAY, holidays=TABLE_FRI_HOLIDAY), gap_until=GAP)
    assert _reading(ev, WEEKEND) is True and _reading(ev, HOLIDAY) is True
    assert len(_result(ev, WEEKEND)) == 1 and len(_result(ev, HOLIDAY)) == 1


def test_no_clock_is_not_checked():
    ev = pe.evaluate(_ic(), _state(hhmm=None), gap_until=GAP)
    got = _result(ev, WEEKEND)
    assert len(got) == 1 and got[0].code == f"{pe.P}missing_clock"


def test_carry_due_only_from_the_time_on_a_matching_day():
    body = _ic()
    assert pe.carry_due(body, _state()) is True
    assert pe.carry_due(body, _state(hhmm="14:59")) is False
    assert pe.carry_due(body, _state(WED)) is False
    assert pe.carry_due(body, _state(LAST_2026)) is False


def test_carry_figures_ride_on_the_rule_value():
    figs = pe.CarryFigures(D("-1234.50"), D("-2345.60"), margin=D("100000"))
    ev = pe.evaluate(_ic(), dataclasses.replace(_state(), carry=figs), gap_until=GAP)
    v = next(v for v in ev.values if v.rule_id == WEEKEND)
    assert v.carry == figs and v.yes_no is True and v.fired is True


def test_attack4_the_gate_opens_once_and_holds_across_five_checks():
    body = _ic()
    ev = pe.evaluate(body, _state(), gap_until=GAP)
    readings = gate_readings.readings(ev)
    assert readings[WEEKEND][1] is True
    opened = sum(1 for rid, (_s, r) in readings.items() if rid == WEEKEND and r is True)
    assert opened == 1
    # the same reading on five later checks stays True: the gate is edge-triggered (alert_gate.step), see the worker
    for minute in range(1, 6):
        later = pe.evaluate(body, _state(hhmm=f"15:{minute:02d}"), gap_until=GAP)
        assert _reading(later, WEEKEND) is True
