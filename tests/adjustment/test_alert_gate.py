"""GC-ALERT1 step 1: the pure alert gate (REQ-170 AC-1..AC-5, ADR-236), proven first on the real 2026-11-02 T-07
paths of strategies 66 and 67 (live system: 30 and 23 records)."""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "alert_discipline" / "gclive3_2026-11-02_t07.json").read_text("utf-8")
)
PRESETS = {"intraday": ag.INTRADAY, "weekly": ag.WEEKLY, "monthly": ag.MONTHLY}
DAY = date(2026, 11, 2)


def at(hhmm: str, day: date = DAY) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), tzinfo=ag.IST)


def opened(events):
    return [e for e in events if isinstance(e, ag.Opened)]


def held(events):
    return [e for e in events if isinstance(e, ag.Held)]


def run(preset, samples, spec):
    """samples: [(datetime, value)]; one step per sample, then one empty flush step later the same session."""
    state, events = ag.initial_state(), []
    for now, value in samples:
        state, ev = ag.step(state, now=now, preset=preset, readings={spec.rule_id: (spec, value)})
        events += ev
    state, ev = ag.step(state, now=samples[-1][0] + timedelta(hours=3), preset=preset, readings={})
    return state, events + ev


# 1. Replay of the real fixture
@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: str(c["strategy_id"]))
@pytest.mark.parametrize("style", ["intraday", "weekly", "monthly"])
def test_replay_real_fixture_gives_expected_records(case, style):
    spec = ag.RuleSpec(case["rule"], "ge", (Decimal(str(case["threshold"])),))
    samples = [(at(t), Decimal(str(v))) for t, v in case["minute_closes_ist"]]
    _, events = run(PRESETS[style], samples, spec)
    assert len(opened(events)) == case["expected_records"][style]
    assert len(case["live_records_ist"]) == case["live_record_count"]


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: str(c["strategy_id"]))
def test_replay_without_gate_crosses_many_times(case):
    thr = Decimal(str(case["threshold"]))
    values = [Decimal(str(v)) for _, v in case["minute_closes_ist"]]
    pairs = zip([None, *values[:-1]], values, strict=True)
    raw = sum(1 for prev, cur in pairs if cur >= thr and (prev is None or prev < thr))
    assert raw > 1
