"""Lane RA2 item 2 (issue 876): ``alert_gate.silent_reason`` says why a rule past its line raised nothing at a
check, for the worker's log (a closed word; no price, no figure). Real case: the PC's strategy 207, a 5 percent of
max loss line (T-06) crossed with the plan saved a minute earlier: the first check past it opens its record; every
later check past the line has an open record, so it is "alert_already_open"; inside the first 5 minutes after entry
it is "entry_hold"."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from ofo.adjustment import alert_gate as ag
from ofo.adjustment.stop_lines import is_plan_exit_rule

DAY = date(2026, 11, 27)
D = Decimal
SPEC = ag.RuleSpec("T-06", "ge", (D("5"),))
T14 = ag.RuleSpec("T-14", "ge", (D("5"),))


def at(hhmm: str) -> datetime:
    return datetime.combine(DAY, time.fromisoformat(hhmm), tzinfo=ag.IST)


def test_a_rule_inside_its_line_or_unread_has_no_reason():
    state, _ = ag.step(ag.initial_state(), now=at("13:14:10"), preset=ag.INTRADAY, readings={"T-06": (SPEC, D("1"))})
    assert ag.silent_reason(state, "T-06", SPEC, D("1"), now=at("13:14:10")) is None
    assert ag.silent_reason(state, "T-06", SPEC, None, now=at("13:14:10")) is None


def test_a_plan_loss_stop_past_its_line_with_its_alert_open_is_alert_already_open():
    assert is_plan_exit_rule("T-06")
    clear = {"T-06": (SPEC, D("1"))}
    state, events = ag.step(ag.initial_state(), now=at("13:14:10"), preset=ag.INTRADAY, readings=clear)
    state, events = ag.step(state, now=at("13:20:10"), preset=ag.INTRADAY, readings={"T-06": (SPEC, D("9"))})
    assert [type(e) for e in events] == [ag.Opened], "the stop opens at the first check past its line"
    state, events = ag.step(state, now=at("13:21:10"), preset=ag.INTRADAY, readings={"T-06": (SPEC, D("9"))})
    assert events == []
    assert ag.silent_reason(state, "T-06", SPEC, D("9"), now=at("13:21:10")) == "alert_already_open"


def test_a_stop_inside_the_five_minutes_after_entry_that_never_read_clear_is_entry_hold():
    entered = at("13:14:00")
    hold = ag.entry_period_end(entered)
    state, events = ag.step(ag.initial_state(), now=at("13:15:10"), preset=ag.INTRADAY,
                            readings={"T-06": (SPEC, D("9"))}, entry_hold_until=hold)
    assert events == []
    assert ag.silent_reason(state, "T-06", SPEC, D("9"), now=at("13:15:10"), entry_hold_until=hold) == "entry_hold"
    assert hold == entered + timedelta(minutes=5)


def test_a_rule_judged_on_a_candle_close_waits_for_it():
    state, events = ag.step(ag.initial_state(), now=at("13:15:10"), preset=ag.INTRADAY,
                            readings={"T-14": (T14, D("9"))})
    assert events == []
    assert ag.silent_reason(state, "T-14", T14, D("9"), now=at("13:15:10")) == "waiting_for_candle_close"
