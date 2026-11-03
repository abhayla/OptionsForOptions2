"""GC-IC1 step 1a (REQ-159 AC-4, REQ-170, ADR-216): the iron condor's expiry-day rule (14:30, close a spread whose
short is within 0.3% of spot, action 5 "Prepare an exit for review") is a rule the evaluator reports, a yes/no gate
reading, and opens a record only through ``alert_gate.step``. Pure: no DB, no clock read."""
from __future__ import annotations

import copy
import dataclasses
import datetime
import json
import pathlib
import re
from decimal import Decimal as D

import pytest
from ofo.adjustment import alert_gate, gate_readings
from ofo.adjustment import playbook_eval as pe
from ofo.strategy.settings_value import IDENTIFIER_PATTERN
from ofo.timeutil import IST

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED = ROOT / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
GAP = "09:30"
RID = "day.expiry.1430.5"  # the iron condor's switched-on expiry close rule (id from its content, B3)


def _ic() -> dict:
    rows = json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]
    return copy.deepcopy(next(r["body"] for r in rows if r["strategy_type"] == "ic"))


def _state(spot: str | None = "23400", hhmm: str | None = "14:30", days_left: int | None = 0,
           far_ltp: str | None = "1.95", **kw) -> pe.StrategyState:
    shorts = (pe.ShortLeg(D(22600), D("0.01"), None if far_ltp is None else D(far_ltp)),
              pe.ShortLeg(D(23450), D("0.40"), D("60")))
    return pe.StrategyState(expiry_kind="weekly", days_left=days_left, hhmm=hhmm,
                            spot=None if spot is None else D(spot), shorts=kw.pop("shorts", shorts),
                            prices_fresh=kw.pop("prices_fresh", True), **kw)


def _day(ev: pe.Evaluation) -> list:
    return [r for r in ev.results if r.rule_id == RID]


def _value(ev: pe.Evaluation):
    return next((v for v in ev.values if v.rule_id == RID), None)


def _reading(ev: pe.Evaluation):
    got = gate_readings.readings(ev).get(RID)
    return None if got is None else got[1]


def test_the_seeded_ic_rule_carries_its_a27_limit():
    rule = _ic()["day_rules"][5]
    assert rule == {"on": True, "when": "expiry", "at": "14:30", "action": 5, "close_if_short_within_pct": "0.3"}


def test_core_at_1430_on_expiry_day_a_short_within_03_pct_flags_and_names_a28_and_a27():
    ev = pe.evaluate(_ic(), _state(), gap_until=GAP)
    flags = _day(ev)
    assert len(flags) == 1 and isinstance(flags[0], pe.Flag), flags
    v = _value(ev)
    assert v.fired is True and v.yes_no is True and v.approaches == ("A-28", "A-27")
    assert v.threshold == D("0.3") and v.cmp == "le"
    spec, reading = gate_readings.readings(ev)[RID]
    assert spec.cmp == "bool" and spec.ladder == () and reading is True


def test_attack1_at_1429_there_is_no_reading():
    ev = pe.evaluate(_ic(), _state(hhmm="14:29"), gap_until=GAP)
    assert _day(ev) == [] and _value(ev) is None and _reading(ev) is None and RID not in ev.clear


def test_attack2_the_day_before_expiry_there_is_no_reading():
    ev = pe.evaluate(_ic(), _state(days_left=1), gap_until=GAP)
    assert _day(ev) == [] and _reading(ev) is None and RID not in ev.clear


def test_attack4_no_spot_reads_none_never_true_or_false():
    ev = pe.evaluate(_ic(), _state(spot=None), gap_until=GAP)
    assert _reading(ev) is None and RID not in ev.clear and _value(ev) is None
    assert [type(r).__name__ for r in _day(ev)] == ["NotChecked"]


def test_withheld_prices_read_none():
    ev = pe.evaluate(_ic(), _state(prices_fresh=False), gap_until=GAP)
    assert _reading(ev) is None and [r.code for r in _day(ev)] == [f"{pe.P}withheld_stale"]


def test_no_clock_and_no_days_left_are_not_checked():
    assert [r.code for r in _day(pe.evaluate(_ic(), _state(hhmm=None), gap_until=GAP))] == [f"{pe.P}missing_clock"]
    assert [r.code for r in _day(pe.evaluate(_ic(), _state(days_left=None), gap_until=GAP))] == \
        [f"{pe.P}missing_days_left"]


def test_no_short_leg_is_not_checked():
    ev = pe.evaluate(_ic(), _state(shorts=()), gap_until=GAP)
    assert [r.code for r in _day(ev)] == [f"{pe.P}no_short_leg"] and _reading(ev) is None


def test_attack5_exactly_03_pct_fires_and_03001_does_not():
    # spot 30000, a short at 30090: 90 / 30000 = exactly 0.3%; the rule at 0.3001% must not stand for 0.3%
    exact = (pe.ShortLeg(D(30090), None, D(50)),)
    ev = pe.evaluate(_ic(), _state(spot="30000", shorts=exact), gap_until=GAP)
    assert _value(ev).fired is True and _value(ev).value == D("0.3")
    beyond = (pe.ShortLeg(D("30090.03"), None, D(50)),)  # 90.03 / 30000 = 0.3001%
    ev = pe.evaluate(_ic(), _state(spot="30000", shorts=beyond), gap_until=GAP)
    assert _value(ev).fired is False and _reading(ev) is False and RID in ev.clear


def test_case_b_04_pct_away_reads_false_and_records_a_clear():
    ev = pe.evaluate(_ic(), _state(spot="23356.55"), gap_until=GAP)
    assert _reading(ev) is False and RID in ev.clear and _day(ev) == []


def test_a27_boundary_at_or_below_rs2_as_t09_ltp_200_named_205_not_and_absent_not():
    assert _value(pe.evaluate(_ic(), _state(far_ltp="2.00"), gap_until=GAP)).approaches == ("A-28", "A-27")
    assert _value(pe.evaluate(_ic(), _state(far_ltp="2.05"), gap_until=GAP)).approaches == ("A-28",)
    assert _value(pe.evaluate(_ic(), _state(far_ltp=None), gap_until=GAP)).approaches == ("A-28",)


def test_a27_limit_is_t09_of_the_current_stage_not_hard_coded():
    body = _ic()
    body["triggers"]["T-09"]["weekly"][2] = "1.5"  # the Last day stage (days left 0)
    assert _value(pe.evaluate(body, _state(far_ltp="1.95"), gap_until=GAP)).approaches == ("A-28",)
    assert _value(pe.evaluate(body, _state(far_ltp="1.50"), gap_until=GAP)).approaches == ("A-28", "A-27")
    body["triggers"]["T-09"]["weekly"][2] = "3"
    assert _value(pe.evaluate(body, _state(far_ltp="2.50"), gap_until=GAP)).approaches == ("A-28", "A-27")
    body["triggers"]["T-09"]["on"] = False  # T-09 off: A-27 is never named (no default)
    assert _value(pe.evaluate(body, _state(far_ltp="0.05"), gap_until=GAP)).approaches == ("A-28",)
    del body["triggers"]["T-09"]  # T-09 absent: not named
    assert _value(pe.evaluate(body, _state(far_ltp="0.05"), gap_until=GAP)).approaches == ("A-28",)


def test_b2_a_body_saved_before_1a_names_a27_through_t09():
    """GC-IC1 1a review B2: the pre-1a system iron condor (37824fb9 system_playbooks.json playbooks[2]) has no
    second key; A-27 is named through its T-09 weekly Last day threshold (Rs 2, le)."""
    body = json.loads((pathlib.Path(__file__).parent / "pre1a_ic_body.json").read_text(encoding="utf-8"))
    assert "buy_back_short_below_rs" not in json.dumps(body)
    v = _value(pe.evaluate(body, _state(), gap_until=GAP))
    assert v.fired is True and v.approaches == ("A-28", "A-27")


def test_b3_reordering_day_rules_keeps_every_id():
    body = _ic()
    before = {a.rule_id for a in pe.day_answers(body, _state())}
    body["day_rules"].reverse()
    assert {a.rule_id for a in pe.day_answers(body, _state())} == before == {RID}


def test_long_legs_are_never_read_as_shorts():
    # only ShortLeg rows are read: a long wing at 23400 (spot) must not make the rule fire
    shorts = (pe.ShortLeg(D(22600), None, D(1)), pe.ShortLeg(D(24000), None, D(1)))
    ev = pe.evaluate(_ic(), _state(spot="23400", shorts=shorts), gap_until=GAP)
    assert _value(ev).fired is False


@pytest.mark.parametrize("change", [
    {"at": None}, {"at": "2:30"}, {"close_if_short_within_pct": None}, {"close_if_short_within_pct": "abc"},
    {"close_if_short_within_pct": 0.3},
])
def test_malformed_rule_is_not_checked_with_a_reason_never_true(change):
    body = _ic()
    for k, val in change.items():
        if val is None:
            body["day_rules"][5].pop(k, None)
        else:
            body["day_rules"][5][k] = val
    if isinstance(change.get("close_if_short_within_pct"), float):
        ev_results = pe.day_answers(body, _state())  # evaluate refuses a float body outright (fail closed)
        assert [a.reason for a in ev_results] == [pe.DAY_RULE_INCOMPLETE]
        return
    ev = pe.evaluate(body, _state(), gap_until=GAP)
    rid = pe.day_rule_id(body["day_rules"][5])  # a malformed time is part of the id
    assert [r.code for r in ev.results if r.rule_id == rid] == [pe.DAY_RULE_INCOMPLETE]
    assert gate_readings.readings(ev).get(rid, (None, None))[1] is None  # NotChecked reads None, never True
    assert pe.reason_text(pe.DAY_RULE_INCOMPLETE)


def test_switched_off_rule_gives_nothing():
    body = _ic()
    body["day_rules"][5]["on"] = False
    ev = pe.evaluate(body, _state(), gap_until=GAP)
    assert _day(ev) == [] and _reading(ev) is None


def test_tighten_rule_unchanged_and_not_reported_as_a_day_rule():
    body = _ic()
    ev = pe.evaluate(body, _state(tighten_percent=D(20)), gap_until=GAP)
    assert [r.rule_id for r in ev.results if pe.is_day_rule_id(r.rule_id)] == [RID]


def _step(gs, at: datetime.datetime, ev: pe.Evaluation | None):
    preset = alert_gate.INTRADAY
    return alert_gate.step(gs, now=at, preset=preset, readings={} if ev is None else gate_readings.readings(ev))


def test_attack3_the_gate_opens_one_record_per_episode_across_checks():
    gs = alert_gate.initial_state()
    day = datetime.datetime(2026, 11, 3, tzinfo=IST)
    opened = []
    for minute, hhmm in ((29, "14:29"), (30, "14:30"), (31, "14:31"), (32, "14:32"), (33, "14:33"), (34, "14:34"),
                         (35, "14:35")):
        ev = pe.evaluate(_ic(), _state(hhmm=hhmm), gap_until=GAP)
        gs, events = _step(gs, day.replace(hour=14, minute=minute, second=1), ev)
        opened += [e for e in events if isinstance(e, alert_gate.Opened) and e.rule_id == RID]
    assert len(opened) == 1 and opened[0].at == day.replace(hour=14, minute=31), opened


def test_day_rule_action_names_action_5():
    assert pe.day_rule_action(_ic(), RID) == pe.DAY_ACTION_PREPARE_EXIT
    assert pe.day_rule_action(_ic(), "day.expiry.99") is None and pe.day_rule_action(_ic(), "T-01") is None


# ---- step 2 / 4: the generator cases, read through the scenario state the screen tests use ----------------------
@pytest.mark.parametrize(("case", "hhmm"), [("ADJ-51", "14:30"), ("ADJ-51", "14:29"), ("ADJ-52", "14:30")])
def test_generator_case_matches_its_engine_free_expected_block(case, hhmm):
    from test_adjust_scenarios import load  # noqa: PLC0415 - the scenario library's loader
    from test_playbook_eval import body_of, state_of  # noqa: PLC0415 - the scenario state the screen tests use
    sc = load(case)
    want = sc["expected"]["day_close"]
    state = dataclasses.replace(state_of(sc), hhmm=hhmm)
    ev = pe.evaluate(body_of(sc), state, gap_until=GAP)
    got = gate_readings.readings(ev).get(want["rule_id"])
    if hhmm < want["at"]:
        assert got is None  # before its time: no reading at all
        return
    assert got[1] is want["fires"]
    v = next(x for x in ev.values if x.rule_id == want["rule_id"])
    assert list(v.approaches) == want["approaches"]
    assert format(v.value.quantize(D("0.0001")), "f") == want["nearest_short_pct"]


def test_t01_and_the_day_rule_share_one_measure():
    shorts = (pe.ShortLeg(D(22600), None, D(1)), pe.ShortLeg(D(23450), None, D(60)))
    assert pe.short_gap_pct(D(23400), shorts) == (D(5000), D(23400))
    assert pe.short_premium(shorts) == D(1)


# ---- GC-IC1 review A1: a day rule id is always inside the Identifier pattern -----------------------------------------
@pytest.mark.parametrize("at", ["2:30 pm", "14.30", "", None, 1430, "14:30 ", "9:5"])
def test_a_malformed_time_never_makes_an_id_outside_the_identifier_pattern(at):
    rule = {"on": True, "when": "expiry", "at": at, "action": 5}
    rid = pe.day_rule_id(rule)
    assert re.fullmatch(IDENTIFIER_PATTERN, rid)
    assert rid == pe.DAY_RULE_UNNAMEABLE
    assert pe.day_rule_action({"day_rules": [rule]}, rid) is None  # never names a rule


@pytest.mark.parametrize("rule", [{"at": "14:30", "action": 5}, {"when": "a b", "at": "14:30", "action": 5},
                                  {"when": "expiry", "at": "14:30"}, {"when": "expiry", "at": "14:30", "action": "5"}])
def test_a_missing_or_odd_kind_or_action_also_fails_closed(rule):
    assert pe.day_rule_id(rule) == pe.DAY_RULE_UNNAMEABLE


def test_a_good_rule_keeps_its_id():
    assert pe.day_rule_id({"when": "expiry", "at": "14:30", "action": 5}) == "day.expiry.1430.5"
