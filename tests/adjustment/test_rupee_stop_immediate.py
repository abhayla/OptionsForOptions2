"""The plan's rupee loss stop acts on the first check past its line, not at the candle close (REQ-170 AC-5, #202).

Real case 2026-11-27 (paper trade A-E #202): entered 11:54:20, plan approved, Stop Rs 50 typed 12:01:21 (guards
``loss_stop_rupees`` "50", T-06 in the rules). Loss before charges Rs 46.60 at 12:10:27, Rs 85.75 at 12:13:44; Alerts >
Active unchanged at 12:10, 12:13 and 12:18; no alert row for #202. The gate's stop fast path
(``stop_lines.is_stop_rule``) named only the % stop lines (T-06, T-16, the 2x-credit line), so the rupee stop -- the
plan's ONE loss stop when typed (ADR-330 (5)(a)) -- waited for the style's candle close and had to be past its line on
the LAST check of that candle: a loss that crosses and dips back before the close opened nothing, close after close.
Spec basis: REQ-170 AC-5 ("a stop-loss ... acts on the live price at once"), ADR-330 (5)(a), ADR-237.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment import gate_readings
from ofo.adjustment import stop_lines as sl
from test_playbook_eval import body_of, evaluate, load, state_of

D = Decimal
DAY = date(2026, 11, 27)
#: every loss stop of a plan: the % of max loss, % of margin and 2x-credit lines and the typed rupee level
LOSS_STOPS = (sl.TRIGGER_MAX_LOSS, sl.TRIGGER_MARGIN, sl.CREDIT_RULE, sl.RUPEE_LOSS_RULE)
CANDLE_MINUTES, LAST_MINUTE = 5, 4  # the weekly candle; its last minute check (12:14:44, 12:19:44, ...)
STYLES = {"intraday": ag.INTRADAY, "weekly": ag.WEEKLY, "monthly": ag.MONTHLY}


def at(hhmm: str) -> datetime:
    return datetime.combine(DAY, time.fromisoformat(hhmm), tzinfo=ag.IST)


def _body_202() -> dict:
    body = copy.deepcopy(body_of(load("ADJ-01")))
    body["status"] = "approved"
    body.setdefault("guards", {})[sl.RUPEE_LOSS_KEY] = "50"
    assert any(r["id"] == sl.TRIGGER_MAX_LOSS for r in body["rules"])  # T-06 in the rules, as on #202
    return body


def _run(preset: ag.Preset, loss_at) -> list:
    """The worker's minute checks from 12:01:44 to 12:30:44 through the real evaluator and the one readings function."""
    body, base = _body_202(), state_of(load("ADJ-01"))
    gate, memory, events, t = ag.initial_state(), {}, [], at("12:01:44")
    while t <= at("12:30:44"):
        ev = evaluate(body, replace(base, pnl=-loss_at(t)), memory, None)
        memory = ev.memory
        readings = {k: v for k, v in gate_readings.readings(ev, stops=frozenset()).items() if k == sl.RUPEE_LOSS_RULE}
        gate, out = ag.step(gate, now=t, preset=preset, readings=readings)
        events += out
        t += timedelta(minutes=1)
    return events


def _loss_202(t: datetime) -> Decimal:
    if t < at("12:10:27"):
        return D("20")
    return D("46.60") if t < at("12:13:44") else D("85.75")


def _loss_dips(t: datetime) -> Decimal:
    """Past Rs 50 from 12:13:44, but back under it on the last minute check of every 5-minute candle (12:14:44,
    12:19:44, ...): a weekly or monthly close then never sees it past the line, though the loss was past it for 4 of
    every 5 checks."""
    if t < at("12:13:44"):
        return D("46.60")
    return D("47.10") if t.minute % CANDLE_MINUTES == LAST_MINUTE else D("85.75")


def test_rupee_loss_is_a_stop_rule():
    assert sl.is_stop_rule(sl.RUPEE_LOSS_RULE)
    assert frozenset(LOSS_STOPS) == sl.LOSS_STOP_RULES
    assert not any(sl.is_stop_rule(r) for r in (sl.RUPEE_PROFIT_RULE, "T-07", sl.TRIGGER_TIME_EXIT, None, 6))


@pytest.mark.parametrize("style", STYLES)
def test_202_rupee_stop_opens_at_the_first_check_past_rs_50(style):
    events = _run(STYLES[style], _loss_202)
    assert [(type(e), e.rule_id, e.at, e.value) for e in events] == [
        (ag.Opened, sl.RUPEE_LOSS_RULE, at("12:13:44"), D("85.75"))]


@pytest.mark.parametrize("style", STYLES)
def test_rupee_stop_touched_then_left_before_the_close_still_opens_once(style):
    events = _run(STYLES[style], _loss_dips)
    opened = [e for e in events if isinstance(e, ag.Opened)]
    assert [(e.at, e.value) for e in opened] == [(at("12:13:44"), D("85.75"))]


@pytest.mark.parametrize("rule_id", LOSS_STOPS)
def test_every_loss_stop_is_on_the_fast_path(rule_id):
    _, ev = ag.step(ag.initial_state(), now=at("12:13:44"), preset=ag.WEEKLY,
                    readings={rule_id: (ag.RuleSpec(rule_id, "ge", (D("50"),)), D("85.75"))})
    assert [(type(e), e.at) for e in ev] == [(ag.Opened, at("12:13:44"))]


@pytest.mark.parametrize("rule_id", ["T-03", "T-14"])  # ADR-330 (47): targets and the time exit are on the fast path
def test_targets_time_exit_and_adjustments_keep_the_candle_wait(rule_id):
    state, ev = ag.step(ag.initial_state(), now=at("12:13:44"), preset=ag.WEEKLY,
                        readings={rule_id: (ag.RuleSpec(rule_id, "ge", (D("50"),)), D("85.75"))})
    assert ev == []
    _, later = ag.step(state, now=at("12:15:01"), preset=ag.WEEKLY, readings={})
    assert [(type(e), e.at) for e in later] == [(ag.Opened, at("12:15:00"))]
