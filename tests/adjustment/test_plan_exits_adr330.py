"""ADR-330 (47), owner 27 Nov 2026 16:25 IST: ALL the plan exits alert on the first check past their level or time.

Loss stop (percent or rupee), 2x-credit stop, profit target (percent or rupee) and time exit: none waits for the candle
close, none is held by the quiet time after the open, none by the daily cap. Only adjustment suggestions keep candle,
quiet time and cap. The 5-minute period after entry delays an alert whose level is already crossed at entry and never
swallows it: when the period ends and it is still crossed, it is raised (case A-G #207: accepted 13:13:33, crossed from
13:14, expect the alert at the first check at or after 13:18:33).
Spec basis: ADR-330 (47), REQ-170 AC-5, ADR-267 amendment, F-71.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.cap_scope import cap_exempt, count_capped
from test_playbook_eval import body_of, load

D = Decimal
DAY = date(2026, 11, 27)
EXITS = ("T-06", "T-16", sl.CREDIT_RULE, sl.RUPEE_LOSS_RULE, "T-07", sl.RUPEE_PROFIT_RULE)
ALL_EXITS = (*EXITS, sl.TRIGGER_TIME_EXIT)
FULL_CAP = 99
ENTERED = datetime.combine(DAY, time(13, 13, 33), tzinfo=ag.IST)


def at(hhmm: str) -> datetime:
    return datetime.combine(DAY, time.fromisoformat(hhmm), tzinfo=ag.IST)


def _spec(rule_id: str) -> ag.RuleSpec:
    if rule_id == sl.TRIGGER_TIME_EXIT:
        return ag.RuleSpec(rule_id, "bool", ())
    return ag.RuleSpec(rule_id, "ge", (D("80"),))


def _past(rule_id: str):
    return True if rule_id == sl.TRIGGER_TIME_EXIT else D("199")


def _clear(rule_id: str):
    return False if rule_id == sl.TRIGGER_TIME_EXIT else D("10")


def _opened(events, rule_id=None):
    return [e for e in events if isinstance(e, ag.Opened) and (rule_id is None or e.rule_id == rule_id)]


# ---- one set -------------------------------------------------------------------------------------------------------

def test_one_set_of_the_plans_own_exits():
    assert frozenset(ALL_EXITS) == sl.PLAN_EXIT_RULES
    assert sl.LOSS_STOP_RULES < sl.PLAN_EXIT_RULES  # a loss stop is still a loss stop
    assert all(sl.is_plan_exit(r) for r in ALL_EXITS)
    assert not any(sl.is_plan_exit(r) for r in ("T-03", "T-01", "sit.S-03", None, 7))
    assert not sl.is_loss_stop("T-07") and not sl.is_loss_stop(sl.TRIGGER_TIME_EXIT)


def test_plan_exit_rule_ids_reads_every_exit_trigger_under_any_id():
    body = {"rules": [{"id": "R-TGT", "any_of": ["T-03", "T-07"]}, {"id": "R-TIME", "all_of": ["T-10b"]},
                      {"id": "R-STOP", "any_of": ["T-16"]}, {"id": "R-ADJ", "any_of": ["T-03", "T-01"]}]}
    ids = sl.plan_exit_rule_ids(body)
    assert {"R-TGT", "R-TIME", "R-STOP"} <= ids and "R-ADJ" not in ids and ids >= sl.PLAN_EXIT_RULES
    assert sl.plan_exit_rule_ids(None) == sl.PLAN_EXIT_RULES  # unreadable body: the fixed set, never fewer
    assert "R-TGT" not in sl.loss_stop_rule_ids(body)  # a profit target is not a loss stop


@pytest.mark.parametrize("rule_id", ALL_EXITS)
def test_cap_exempt_for_every_plan_exit_and_the_restart_count(rule_id):
    assert cap_exempt(rule_id)
    assert count_capped(["T-03", rule_id, "R-TGT"], stops=frozenset({"R-TGT"})) == 1


def test_never_held_at_entry_covers_every_plan_exit():
    assert sl.plan_exit_rule_ids(None) <= pe.never_held({"rules": [], "triggers": {}})


# ---- the first check past the level ----------------------------------------------------------------------------------

@pytest.mark.parametrize("style", [ag.INTRADAY, ag.WEEKLY, ag.MONTHLY])
@pytest.mark.parametrize("rule_id", ALL_EXITS)
def test_plan_exit_opens_at_the_first_check_not_the_candle_close(rule_id, style):
    """09:16:44 is inside the first candle and inside the quiet time; the cap is used up."""
    state = replace(ag.initial_state(), day=DAY, opened_today=FULL_CAP)
    new, events = ag.step(state, now=at("09:16:44"), preset=style, readings={rule_id: (_spec(rule_id), _past(rule_id))})
    assert [(e.rule_id, e.at) for e in _opened(events)] == [(rule_id, at("09:16:44"))]
    assert not [e for e in events if isinstance(e, ag.Held)] and new.opened_today == FULL_CAP


@pytest.mark.parametrize("rule_id", ALL_EXITS)
def test_plan_exit_in_a_paused_candle_opens_at_the_next_live_check(rule_id):
    gate = ag.pause(ag.initial_state(), at("13:13:40"))
    _, events = ag.step(gate, now=at("13:13:44"), preset=ag.WEEKLY,
                       readings={rule_id: (_spec(rule_id), _past(rule_id))})
    assert [e.at for e in _opened(events, rule_id)] == [at("13:13:44")]


def test_time_exit_opens_once_with_no_flood():
    """T-10b reads False, then True from 11:03: ONE record at the first check past 11:03, nothing after."""
    spec, gate, events = _spec(sl.TRIGGER_TIME_EXIT), ag.initial_state(), []
    t = at("10:58:30")
    while t <= at("11:40:30"):
        gate, out = ag.step(gate, now=t, preset=ag.WEEKLY, readings={"T-10b": (spec, t >= at("11:03:00"))})
        events += out
        t += timedelta(minutes=1)
    assert [(type(e).__name__, e.at) for e in events if not isinstance(e, ag.Lapsed)] == [("Opened", at("11:03:30"))]


def test_adjustment_rules_keep_candle_close_quiet_time_and_cap():
    spec = ag.RuleSpec("T-03", "ge", (D("0.3"),))
    mid_state, mid = ag.step(ag.initial_state(), now=at("10:01:10"), preset=ag.WEEKLY,
                             readings={"T-03": (spec, D("0.4"))})
    assert not mid  # a mid-candle sample opens nothing
    _, close = ag.step(mid_state, now=at("10:05:10"), preset=ag.WEEKLY, readings={})
    assert [e.at for e in _opened(close)] == [at("10:05:00")]  # the close opens it
    s, _ = ag.step(ag.initial_state(), now=at("09:22:10"), preset=ag.WEEKLY, readings={"T-03": (spec, D("0.4"))})
    _, quiet = ag.step(s, now=at("09:26:00"), preset=ag.WEEKLY, readings={})
    assert [(type(e), e.reason) for e in quiet] == [(ag.Held, ag.HELD_QUIET_TIME)]
    s0 = replace(ag.initial_state(), day=DAY, opened_today=FULL_CAP)
    s, _ = ag.step(s0, now=at("11:01:10"), preset=ag.WEEKLY, readings={"T-03": (spec, D("0.4"))})
    _, capped = ag.step(s, now=at("11:05:10"), preset=ag.WEEKLY, readings={})
    assert [(type(e), e.reason) for e in capped] == [(ag.Held, ag.HELD_DAILY_LIMIT)]


# ---- the 5-minute period after entry: delays, never swallows -----------------------------------------------------

def test_entry_period_end_is_entry_plus_five_minutes():
    assert ag.entry_period_end(ENTERED) == at("13:18:33")
    assert ag.entry_period_end(None) is None
    assert ag.entry_period_end(datetime(2026, 11, 27, 13, 13, 33)) is None  # noqa: DTZ001  # no zone: no guess, no hold


def _run(rule_id, values, entered=ENTERED, preset=ag.WEEKLY):
    """Minute checks at :44 from 13:13:44; ``values`` maps a check's HH:MM to the reading (default: past the level)."""
    spec, gate, events, t = _spec(rule_id), ag.initial_state(), [], at("13:13:44")
    until = ag.entry_period_end(entered)
    while t <= at("13:25:44"):
        v = values.get(t.strftime("%H:%M"), _past(rule_id))
        gate, out = ag.step(gate, now=t, preset=preset, readings={rule_id: (spec, v)}, entry_hold_until=until)
        events += out
        t += timedelta(minutes=1)
    return events


@pytest.mark.parametrize("rule_id", ALL_EXITS)
def test_207_crossed_at_entry_is_delayed_then_raised_never_swallowed(rule_id):
    """Accepted 13:13:33, past the level from 13:14: no alert before 13:18:33, ONE alert at the first check after."""
    events = _run(rule_id, {})
    assert [(type(e).__name__, e.at) for e in events] == [("Opened", at("13:18:44"))]


@pytest.mark.parametrize("rule_id", ALL_EXITS)
def test_crossed_after_a_clear_check_is_raised_at_once(rule_id):
    """A level seen clear after entry and then crossed is a new crossing: no delay."""
    events = _run(rule_id, {"13:14": _clear(rule_id), "13:15": _past(rule_id)})
    assert [(type(e).__name__, e.at) for e in events] == [("Opened", at("13:15:44"))]


@pytest.mark.parametrize("rule_id", ALL_EXITS)
def test_crossed_at_entry_and_clear_again_before_the_period_ends_raises_nothing(rule_id):
    clear = {f"13:{m}": _clear(rule_id) for m in range(14, 26)}
    clear["13:14"] = _past(rule_id)
    assert not _opened(_run(rule_id, clear))


def test_adjustment_rules_ignore_the_entry_hold():
    spec = ag.RuleSpec("T-03", "ge", (D("0.3"),))
    gate, events, t = ag.initial_state(), [], at("13:13:44")
    while t <= at("13:25:44"):
        gate, out = ag.step(gate, now=t, preset=ag.WEEKLY, readings={"T-03": (spec, D("0.4"))},
                            entry_hold_until=at("13:18:33"))
        events += out
        t += timedelta(minutes=1)
    assert [e.at for e in _opened(events)] == [at("13:15:00")]  # its own candle close, as before


def test_207_body_rules_are_plan_exits():
    body = copy.deepcopy(body_of(load("ADJ-01")))
    assert {"T-06", "T-07"} <= sl.plan_exit_rule_ids(body)
