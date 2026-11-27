"""A plan's loss stop is never held or dropped without an alert (REQ-170 AC-5, ADR-267 amendment 2; Lane J 2026-11-27).

Four gaps found by the Tier A reviews and the live case A-G #207 (2026-11-27: plan approved 13:13:33, Stop Rs 80 typed,
T-06 weekly stages 50 / 5 / 40, loss about Rs 199 from about 13:14; no alert row for 19 minutes):
1. quiet time after the open held every loss stop (weekly to 09:30, monthly to 09:45);
2. a candle that saw a pause (stale feed, missing leg, failed check) took no sample, so the stop fast path did not see
   the next LIVE check either: a pause in every candle kept a stop silent for good;
3. the gate keyed on the rule id, so a rule that carries T-06 / T-16 under another id (a mixed any/all rule, or a
   single-trigger rule with its own id) missed the fast path, the quiet-time and the cap exemption;
4. F-71 "held at entry": a stop already true at the starting point answered "already true" (no reading) until a check
   found it false, so a stop that never clears never alerted.
Spec basis: REQ-170 AC-5 ("a stop-loss ... acts on the live price at once"), ADR-267 + amendment 2 ("no crossing is ever
dropped without trace"), ADR-016..019 (never a stale price as live), ADR-330 (5)(a), F-71.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment import gate_readings
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.cap_scope import cap_exempt, count_capped
from test_playbook_eval import body_of, evaluate, load, state_of

D = Decimal
DAY = date(2026, 11, 27)
LOSS_STOPS = sorted(sl.LOSS_STOP_RULES)
CAPPED_OF_FOUR = 2  # T-03 and T-07 count; the two stop rules do not
FULL_CAP = 99  # a count far past every preset's daily cap
STYLES = {"weekly": ag.WEEKLY, "monthly": ag.MONTHLY, "intraday": ag.INTRADAY}


def at(hhmm: str) -> datetime:
    return datetime.combine(DAY, time.fromisoformat(hhmm), tzinfo=ag.IST)


def _stop_spec(rule_id: str, *, loss_stop: bool = False) -> ag.RuleSpec:
    return ag.RuleSpec(rule_id, "ge", (D("80"),), loss_stop=loss_stop)


def _opened(events, rule_id):
    return [e for e in events if isinstance(e, ag.Opened) and e.rule_id == rule_id]


# ---- gap 1: quiet time ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("style", ["weekly", "monthly", "intraday"])
@pytest.mark.parametrize("rule_id", LOSS_STOPS)
def test_loss_stop_is_not_held_by_quiet_time(style, rule_id):
    """A stop crossed at 09:15:44 opens at 09:15:44, not when the quiet time ends (09:30:44 weekly)."""
    _, events = ag.step(ag.initial_state(), now=at("09:15:44"), preset=STYLES[style],
                        readings={rule_id: (_stop_spec(rule_id), D("199"))})
    assert [(e.rule_id, e.at) for e in _opened(events, rule_id)] == [(rule_id, at("09:15:44"))]
    assert not [e for e in events if isinstance(e, ag.Held)]


@pytest.mark.parametrize("rule_id", ["T-07", sl.RUPEE_PROFIT_RULE, "T-03"])
def test_other_rules_keep_quiet_time(rule_id):
    state, events = ag.step(ag.initial_state(), now=at("09:16:44"), preset=ag.WEEKLY,
                            readings={rule_id: (ag.RuleSpec(rule_id, "ge", (D("1"),)), D("2"))})
    _, events = ag.step(state, now=at("09:20:44"), preset=ag.WEEKLY, readings={})
    assert [(type(e).__name__, e.reason) for e in events] == [("Held", ag.HELD_QUIET_TIME)]


# ---- gap 2: a pause in the candle ----------------------------------------------------------------------------------

@pytest.mark.parametrize("style", ["weekly", "monthly"])
def test_stop_opens_at_the_next_live_check_after_a_pause(style):
    """A pause at 13:26:10 (one stale read); the next live check at 13:26:44 is past the line: it opens then."""
    state = ag.pause(ag.initial_state(), at("13:26:10"))
    _, events = ag.step(state, now=at("13:26:44"), preset=STYLES[style],
                        readings={sl.RUPEE_LOSS_RULE: (_stop_spec(sl.RUPEE_LOSS_RULE), D("199"))})
    assert [e.at for e in _opened(events, sl.RUPEE_LOSS_RULE)] == [at("13:26:44")]


def test_a_paused_candle_still_has_no_close_for_other_rules():
    """The pause rule stands for every other rule (and for the stop's own candle close): no sample, no close."""
    state = ag.pause(ag.initial_state(), at("13:26:10"))
    spec = ag.RuleSpec("T-03", "ge", (D("0.30"),))
    state, events = ag.step(state, now=at("13:26:44"), preset=ag.WEEKLY, readings={"T-03": (spec, D("0.40"))})
    _, later = ag.step(state, now=at("13:30:44"), preset=ag.WEEKLY, readings={})
    assert events == [] and later == []
    assert state.rule(sl.RUPEE_LOSS_RULE).pending is None


def test_stop_in_a_paused_candle_is_judged_live_only():
    """A stop not past its line in a paused candle opens nothing and clears nothing (no close to judge)."""
    state = ag.pause(ag.initial_state(), at("13:26:10"))
    state, events = ag.step(state, now=at("13:26:44"), preset=ag.WEEKLY,
                            readings={sl.RUPEE_LOSS_RULE: (_stop_spec(sl.RUPEE_LOSS_RULE), D("40"))})
    assert events == [] and state.rule(sl.RUPEE_LOSS_RULE).pending is None


# ---- gap 3: classify by trigger, not only rule id -------------------------------------------------------------------

def _mixed_body() -> dict:
    body = copy.deepcopy(body_of(load("ADJ-01")))
    body["status"] = "approved"
    body["rules"] = [r for r in body["rules"] if r["id"] not in ("T-06", "T-03")]
    body["rules"].append({"id": "R-LOSS", "any_of": ["T-03", "T-06"]})
    body["rules"].append({"id": "MYSTOP", "any_of": ["T-16"]})
    return body


def test_loss_stop_rule_ids_reads_the_triggers():
    ids = sl.loss_stop_rule_ids(_mixed_body())
    assert {"R-LOSS", "MYSTOP"} <= ids
    assert ids >= sl.LOSS_STOP_RULES
    assert "T-07" not in ids and "T-10b" not in ids and "T-01" not in ids
    assert sl.loss_stop_rule_ids(None) == sl.LOSS_STOP_RULES  # an unreadable body: the fixed set, never fewer


def test_one_place_decides_the_stop_for_gate_and_store():
    stops = sl.loss_stop_rule_ids(_mixed_body())
    assert sl.is_loss_stop("R-LOSS", stops) and sl.is_loss_stop("T-06", frozenset())
    assert cap_exempt("R-LOSS", loss_stop=True) and not cap_exempt("R-LOSS")
    # the store's restart count reads the same function: the mixed stop rule is not counted
    assert count_capped(["R-LOSS", "MYSTOP", "T-03", "T-07"], stops) == CAPPED_OF_FOUR


def test_mixed_stop_rule_reading_carries_the_stop_flag():
    body, base = _mixed_body(), state_of(load("ADJ-01"))
    ev = evaluate(body, replace(base, pnl=D("-20000")), {}, None)
    readings = gate_readings.readings(ev, sl.loss_stop_rule_ids(body))
    spec, value = readings["R-LOSS"]
    assert spec.loss_stop and value is True
    assert not readings["T-07"][0].loss_stop


def test_mixed_stop_rule_opens_at_once_in_quiet_time_and_past_the_cap():
    spec = ag.RuleSpec("R-LOSS", "bool", (), loss_stop=True)
    state = replace(ag.initial_state(), day=DAY, opened_today=FULL_CAP)
    _, events = ag.step(state, now=at("09:16:44"), preset=ag.WEEKLY, readings={"R-LOSS": (spec, True)})
    assert [e.at for e in _opened(events, "R-LOSS")] == [at("09:16:44")]
    state = replace(ag.initial_state(), day=DAY, opened_today=FULL_CAP)
    new, events = ag.step(state, now=at("11:16:44"), preset=ag.WEEKLY, readings={"R-LOSS": (spec, True)})
    assert _opened(events, "R-LOSS") and new.opened_today == FULL_CAP  # not counted


# ---- gap 4: held at entry --------------------------------------------------------------------------------------------

def test_loss_stops_are_never_held_at_entry():
    body = _mixed_body()
    assert sl.loss_stop_rule_ids(body) <= pe.never_held(body)


def _body_207() -> dict:
    """A-G #207's plan: approved, Stop Rs 80 typed, T-06 weekly 50 / 5 / 40 (Middle 5 %)."""
    body = copy.deepcopy(body_of(load("ADJ-01")))
    body["status"] = "approved"
    body["triggers"]["T-06"]["weekly"] = ["50", "5", "40"]
    body.setdefault("guards", {})[sl.RUPEE_LOSS_KEY] = "80"
    return body


def test_207_stop_true_at_entry_still_alerts():
    """The loss was past Rs 80 at the starting point: the stop is a Flag at the first check, never "already true"."""
    body, base = _body_207(), state_of(load("ADJ-01"))
    entry = replace(base, pnl=D("-199"))
    ev = evaluate(body, replace(base, pnl=D("-199")), {}, entry)
    kinds = {r.rule_id: type(r).__name__ for r in ev.results}
    assert kinds[sl.RUPEE_LOSS_RULE] == "Flag"
    assert gate_readings.readings(ev)[sl.RUPEE_LOSS_RULE][1] == D("199")


def test_207_minute_checks_with_a_pause_every_candle_open_the_rupee_stop_at_once():
    """#207 from 13:13:44: minute checks, loss Rs 199, one paused read in every 5-minute candle before its
    first live check (13:13:10, 13:15:10, 13:20:10, ...). Before the fix no check in any candle took a sample, so no
    row came at all (as on #207); now the first live check past Rs 80 opens it."""
    body, base = _body_207(), state_of(load("ADJ-01"))
    gate, memory, events, t = ag.initial_state(), {}, [], at("13:13:44")
    while t <= at("13:33:44"):
        mark = t.replace(second=10)
        if t.minute % 5 == 0 or t == at("13:13:44"):  # this candle's paused read, before its first live check
            gate = ag.pause(gate, mark)
        ev = evaluate(body, replace(base, pnl=D("-199")), memory, None)
        memory = ev.memory
        gate, out = ag.step(gate, now=t, preset=ag.WEEKLY,
                            readings=gate_readings.readings(ev, sl.loss_stop_rule_ids(body)))
        events += out
        t += timedelta(minutes=1)
    assert [e.at for e in _opened(events, sl.RUPEE_LOSS_RULE)] == [at("13:13:44")]


def test_207_first_check_in_a_paused_candle_opens_the_stop():
    body, base = _body_207(), state_of(load("ADJ-01"))
    ev = evaluate(body, replace(base, pnl=D("-199")), {}, None)
    gate = ag.pause(ag.initial_state(), at("13:13:40"))
    _, events = ag.step(gate, now=at("13:13:44"), preset=ag.WEEKLY,
                        readings=gate_readings.readings(ev, sl.loss_stop_rule_ids(body)))
    assert [e.at for e in _opened(events, sl.RUPEE_LOSS_RULE)] == [at("13:13:44")]



# ---- a worker restart (coordinator 13:58: #207 still silent after the 13:33:30 restart) ------------------------------

HELD_MEMORY = {"held_at_entry": True, "seen_clear": False}  # an adjustment_rule_state row as the old code left it


@pytest.mark.parametrize("rule_id", [sl.RUPEE_LOSS_RULE, sl.TRIGGER_MAX_LOSS, sl.CREDIT_RULE])
def test_stored_held_at_entry_row_of_a_stop_is_ignored(rule_id):
    """A stored held_at_entry=true / seen_clear=false row for a stop answers a Flag, never "already true"."""
    body, base = _body_207(), state_of(load("ADJ-01"))
    ev = evaluate(body, replace(base, pnl=D("-199")), {rule_id: dict(HELD_MEMORY)}, None)
    kinds = {r.rule_id: type(r).__name__ for r in ev.results}
    assert kinds.get(rule_id, "Flag") != "AlreadyTrue"
    assert kinds[sl.RUPEE_LOSS_RULE] == "Flag"


def test_time_exit_is_never_held_at_entry():
    assert sl.TRIGGER_TIME_EXIT in pe.never_held(_body_207())


def test_207_restart_at_13_33_30_opens_the_stop_at_the_first_live_check():
    """#207: no alert row stored, rule memory as the old code left it (held at entry, never seen clear), worker
    restarted 13:33:30; the loss Rs 199 never came back inside Rs 80. The first live check opens the stop."""
    body, base = _body_207(), state_of(load("ADJ-01"))
    memory = {rid: dict(HELD_MEMORY) for rid in (sl.RUPEE_LOSS_RULE, sl.TRIGGER_MAX_LOSS, "T-07", "T-03")}
    ev = evaluate(body, replace(base, pnl=D("-199")), memory, None)
    readings = gate_readings.readings(ev, sl.loss_stop_rule_ids(body))
    gate = ag.restore(ag.GateRows((), 0), DAY, {rid: spec for rid, (spec, _v) in readings.items()})
    _, events = ag.step(gate, now=at("13:33:44"), preset=ag.WEEKLY, readings=readings)
    assert [e.at for e in _opened(events, sl.RUPEE_LOSS_RULE)] == [at("13:33:44")]
