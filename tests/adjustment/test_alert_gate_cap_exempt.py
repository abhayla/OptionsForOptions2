"""GC-TRACK1 k22 (issues 57 + 60, ADR-267 and its amendment): a user's level watch and a day rule are never held by
the daily alert cap and do not count toward it; every other rule still is (fail closed)."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment.cap_scope import cap_exempt, count_capped

DAY = date(2026, 11, 2)
D = Decimal
PRESET = replace(ag.INTRADAY, daily_cap=2, quiet_until=time(0, 0))
AUTO = ("T-01", "T-02")
CAP = 2


def at(hhmm: str) -> datetime:
    return datetime.combine(DAY, time.fromisoformat(hhmm), tzinfo=ag.IST)


def _spec(rule_id: str) -> ag.RuleSpec:
    return ag.RuleSpec(rule_id, "ge", (D("10"),))


def _cross(rule_id):
    """Two automatic rules fill the cap at the 10:41 close; then `rule_id` crosses at the 10:43 close."""
    state, events = ag.initial_state(), []
    for hhmm, auto_v, other_v in (("10:40:30", D("1"), D("1")), ("10:41:30", D("11"), D("1")),
                                  ("10:42:30", D("11"), D("1")), ("10:43:30", D("11"), D("11")),
                                  ("10:44:05", D("11"), D("11"))):
        readings = {r: (_spec(r), auto_v) for r in AUTO}
        readings[rule_id] = (_spec(rule_id), other_v)
        state, ev = ag.step(state, now=at(hhmm), preset=PRESET, readings=readings)
        events += ev
    return state, [e for e in events if e.rule_id == rule_id]


@pytest.mark.parametrize("rule_id", ["watch.level.above", "watch.level.below", "day.after.1500.exit",
                                     "day:after:1500:exit"])
def test_exempt_rule_opens_when_cap_used_and_is_not_counted(rule_id):
    state, got = _cross(rule_id)
    assert [type(e) for e in got] == [ag.Opened]
    assert state.opened_today == CAP


@pytest.mark.parametrize("rule_id", ["T-03", "sit.S-03", "watch.x", "daily.x"])
def test_other_rule_still_held_by_cap(rule_id):
    state, got = _cross(rule_id)
    assert [(type(e), e.reason) for e in got] == [(ag.Held, ag.HELD_DAILY_LIMIT)]
    assert state.opened_today == CAP


@pytest.mark.parametrize("rule_id", ["", None, 5])
def test_empty_or_non_string_id_is_capped(rule_id):
    assert cap_exempt(rule_id) is False


def test_count_capped_skips_only_exempt_ids_and_fails_closed():
    ids = ["watch.level.above", "day.after.1500.exit", "day:x", "T-01", "sit.S-03", "", None, 5]
    assert count_capped(ids) == 5  # noqa: PLR2004 - T-01, sit.S-03, "", None, 5


def _restored_cross(stored, rule_id):
    state = ag.restore(ag.GateRows((), count_capped(stored)), DAY, {})
    ev = []
    for hhmm, v in (("10:40:30", D("1")), ("10:41:30", D("11")), ("10:42:30", D("11"))):
        state, ev = ag.step(state, now=at(hhmm), preset=PRESET, readings={rule_id: (_spec(rule_id), v)})
    return state, [e for e in ev if e.rule_id == rule_id]


def test_restore_with_two_exempt_records_still_opens_an_automatic_rule():
    state, _ = _restored_cross(["watch.level.above", "day.after.1500.exit"], "T-01")
    assert state.opened_today == 1
    assert state.rule("T-01").record is not None


def test_restore_with_two_automatic_and_one_watch_still_holds_the_next_automatic():
    state, _ = _restored_cross(["T-01", "T-02", "watch.level.above"], "T-03")
    assert state.opened_today == CAP
    assert state.rule("T-03").hold is not None and state.rule("T-03").hold.reason == ag.HELD_DAILY_LIMIT
