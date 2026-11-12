"""GC-TRACK1 k22 (issues 57 + 60, ADR-267 and its amendment): a user's level watch and a day rule are never held by
the daily alert cap and do not count toward it; every other rule still is (fail closed)."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag

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
    assert ag._cap_exempt(rule_id) is False
