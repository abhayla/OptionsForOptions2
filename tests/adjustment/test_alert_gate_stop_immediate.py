"""GC-ICFIX issue 9 (REQ-170 AC-5, ADR-237): a stop (risk) rule is raised on the first check that sees it beyond its
line, on every alert style; every other rule keeps the candle-close wait. One crossing is still one record."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment import stop_lines as sl

DAY = date(2026, 11, 2)
D = Decimal
STYLES = [ag.INTRADAY, ag.WEEKLY, ag.MONTHLY]
STOPS = [sl.TRIGGER_MAX_LOSS, sl.TRIGGER_MARGIN, sl.CREDIT_RULE]


def at(hhmm: str) -> datetime:
    return datetime.combine(DAY, time.fromisoformat(hhmm), tzinfo=ag.IST)


def _read(rule_id: str, value: str):
    return {rule_id: (ag.RuleSpec(rule_id, "ge", (D("10"),)), D(value))}


@pytest.mark.parametrize("preset", STYLES)
@pytest.mark.parametrize("rule_id", STOPS)
def test_stop_beyond_its_line_is_raised_mid_candle(preset, rule_id):
    state, ev = ag.step(ag.initial_state(), now=at("10:40:30"), preset=preset, readings=_read(rule_id, "11"))
    assert [(type(e), e.rule_id, e.at) for e in ev] == [(ag.Opened, rule_id, at("10:40:30"))]


@pytest.mark.parametrize("preset", STYLES)
@pytest.mark.parametrize("rule_id", ["T-03", "T-07", "T-99"])
def test_other_rule_and_unknown_kind_keep_the_candle_wait(preset, rule_id):
    state, ev = ag.step(ag.initial_state(), now=at("10:40:30"), preset=preset, readings=_read(rule_id, "11"))
    assert ev == []
    _, later = ag.step(state, now=at("11:59:59"), preset=preset, readings={})
    assert [type(e) for e in later] == [ag.Opened]


@pytest.mark.parametrize("preset", STYLES)
def test_a_stop_already_raised_is_not_raised_twice(preset):
    state, opened = ag.initial_state(), []
    for hhmm in ("10:40:30", "10:40:40", "10:41:10", "11:59:59", "12:00:10"):
        state, ev = ag.step(state, now=at(hhmm), preset=preset, readings=_read("T-06", "11"))
        opened += [e for e in ev if isinstance(e, ag.Opened)]
    assert len(opened) == 1


def test_a_worse_level_of_a_raised_stop_escalates_at_once():
    spec = ag.RuleSpec("T-06", "ge", (D("10"), D("20")))
    state, ev = ag.step(ag.initial_state(), now=at("10:40:30"), preset=ag.WEEKLY, readings={"T-06": (spec, D("11"))})
    state, worse = ag.step(state, now=at("10:40:40"), preset=ag.WEEKLY, readings={"T-06": (spec, D("21"))})
    assert [(type(e), e.level, e.worse) for e in ev + worse] == [(ag.Opened, 0, None), (ag.Opened, 1, "last")]


def test_a_stop_below_its_line_still_waits_and_opens_nothing():
    state, ev = ag.step(ag.initial_state(), now=at("10:40:30"), preset=ag.INTRADAY, readings=_read("T-06", "9"))
    _, later = ag.step(state, now=at("10:42:10"), preset=ag.INTRADAY, readings={})
    assert ev == [] and later == []
