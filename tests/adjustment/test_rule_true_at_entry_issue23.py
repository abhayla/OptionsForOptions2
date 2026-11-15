"""GC-ICFIX issue 23: what a rule that is already true at entry does, pinned from the three user-test trades.

Pure evaluator tests, no database. Built on ADJ-42 (iron condor body) with the trades' own numbers from the user-test
notes (ISSUES.md lines 66, 194, 221). Every behaviour below is a decision, not a fault:
- trade 138 (spot 25,185, short CE 25,200, delta 0.49): level rules true at entry are held, grey line, no alert (F-71,
  ADR-258); they flag after a check finds them clear.
- trade 142 (T-03 0.4008 at the check): the baseline is the fill's own value (ADR-283 (1)); a fill value of
  0.3490 (under the 0.35 limit of this body) is not true at entry, so 0.4008 at the check flags;
  0.4008 at the fill is held.
- trades 142 / 143 (clock rule 13:56 passed 2 minutes after entry): the clock rule is never "already true" (ADR-283 (2))
  and acts on expiry day only (ADR-310).

Spec basis: ADR-258, ADR-283 (1)-(2), ADR-296, ADR-310; finding level-trigger-true-at-entry-by-design (F-71).
"""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal as D

from ofo.adjustment.playbook_eval import AlreadyTrue, Flag, NotChecked, ShortLeg
from test_adjust_scenarios import load
from test_playbook_eval import body_of, entry_of, evaluate, state_of

GAP = "09:30"


def _short(strike, delta, kind="CE"):
    return ShortLeg(D(strike), D(delta), D("90"), kind)


def _kind(ev, rid):
    return next((type(r).__name__ for r in ev.results if r.rule_id == rid), None)


def _t138():
    """Trade 138: spot 25,185, the only short is the 25,200 CE at delta 0.49 (15 points, 0.0596 %), at entry and now."""
    sc = load("ADJ-42")
    state = replace(state_of(sc), spot=D("25185"), shorts=(_short("25200", "0.49"),))
    return body_of(sc), state


def test_138_level_rules_true_at_entry_are_held_with_no_alert():
    body, state = _t138()
    ev = evaluate(body, state, {}, state)
    assert (_kind(ev, "T-01"), _kind(ev, "T-03")) == ("AlreadyTrue", "AlreadyTrue"), ev.results
    assert not [r for r in ev.results if isinstance(r, Flag)]
    assert ev.memory["T-01"] == {"held_at_entry": True, "seen_clear": False}


def test_138_held_rules_stay_quiet_on_the_next_check_and_flag_only_after_a_clear():
    body, state = _t138()
    first = evaluate(body, state, {}, state)
    again = evaluate(body, state, first.memory, state)  # the next check, same market: still held, no alert
    assert (_kind(again, "T-01"), _kind(again, "T-03")) == ("AlreadyTrue", "AlreadyTrue")
    far = replace(state, spot=D("24900"), shorts=(_short("25200", "0.10"),))  # a check that finds both clear
    cleared = evaluate(body, far, again.memory, state)
    assert {"T-01", "T-03"} <= set(cleared.clear)
    back = evaluate(body, state, cleared.memory, state)  # back on the strike: now a real crossing
    assert (_kind(back, "T-01"), _kind(back, "T-03")) == ("Flag", "Flag")


def _t142(entry_delta):
    """Trade 142: delta 0.4008 at the check (this body's T-03 limit is 0.35); the fill's own is ``entry_delta``."""
    sc = load("ADJ-42")
    body = body_of(sc)
    state = replace(state_of(sc), shorts=(_short("25200", "0.4008"),))
    entry = replace(entry_of(sc), shorts=(_short("25200", entry_delta),))
    return body, state, entry


def test_142_t03_is_judged_on_the_fills_own_delta_below_the_limit_it_flags():
    body, state, entry = _t142("0.3490")
    ev = evaluate(body, state, {}, entry)
    flag = next(r for r in ev.results if r.rule_id == "T-03")
    assert isinstance(flag, Flag) and (flag.value, flag.threshold) == (D("0.4008"), D("0.35")), flag
    assert ev.memory["T-03"] == {"held_at_entry": False, "seen_clear": False}


def test_142_t03_at_or_above_the_limit_at_the_fill_is_held():
    body, state, entry = _t142("0.4008")
    ev = evaluate(body, state, {}, entry)
    assert _kind(ev, "T-03") == "AlreadyTrue" and ev.memory["T-03"]["held_at_entry"] is True


def test_142_t03_with_no_computable_fill_value_is_not_held_never_the_first_check():
    body, state, entry = _t142("0.3490")
    unknown = replace(entry, shorts=(ShortLeg(D("25200"), None, None, "CE"),))
    ev = evaluate(body, state, {}, unknown)
    assert _kind(ev, "T-03") == "Flag" and ev.memory["T-03"]["held_at_entry"] is False


def test_142_143_the_clock_rule_past_its_time_at_entry_waits_before_expiry_day_and_warns_on_it():
    """143: NIFTY 17 Nov expiry, clock rule 13:56 already past at entry. The day before: waiting, no alert; on expiry
    day past the time: a Flag, never 'already true', even when the entry was also past the time."""
    sc = load("ADJ-14")
    expiry = datetime.date(2026, 11, 17)
    body = body_of(sc)

    def at(day, hhmm):
        s = replace(state_of(sc), today=day, expiry=expiry, hhmm=hhmm, days_left=(expiry - day).days)
        return s, replace(entry_of(sc), today=day, expiry=expiry, hhmm="13:56")

    state, entry = at(datetime.date(2026, 11, 16), "13:58")
    ev = evaluate(body, state, {}, entry)
    t10b = next(r for r in ev.results if r.trigger_id == "T-10b" and not r.rule_id.startswith("day."))
    assert isinstance(t10b, NotChecked) and t10b.code == "adjust_trigger_waits_expiry_day"
    state, entry = at(expiry, "14:45")
    t10b = next(r for r in evaluate(body, state, {}, entry).results
                if r.trigger_id == "T-10b" and not r.rule_id.startswith("day."))
    assert isinstance(t10b, Flag) and not isinstance(t10b, AlreadyTrue)
