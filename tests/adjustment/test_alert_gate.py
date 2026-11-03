"""GC-ALERT1 step 1: the pure alert gate (REQ-170 AC-1..AC-5, ADR-236), proven first on the real 2026-11-02 T-07
paths of strategies 66 and 67 (live system: 30 and 23 records)."""
from __future__ import annotations

import ast
import json
import pathlib
from dataclasses import replace
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


D = Decimal
T07 = ag.RuleSpec("T-07", "ge", (D("80"), D("90")))


def feed(samples, spec=T07, preset=ag.INTRADAY, state=None, day=DAY):
    """samples: [(hh:mm:ss, value)] for one rule; returns (state, events), no flush."""
    state, events = state or ag.initial_state(), []
    for hhmm, value in samples:
        state, ev = ag.step(state, now=at(hhmm, day), preset=preset, readings={spec.rule_id: (spec, value)})
        events += ev
    return state, events


def flush(state, hhmm, preset=ag.INTRADAY, day=DAY):
    return ag.step(state, now=at(hhmm, day), preset=preset, readings={})


def minutes(start: str, n: int, value):
    """One sample at second 30 of each minute from `start` (hh:mm) for n minutes."""
    base = at(start)
    return [((base + timedelta(minutes=i, seconds=30)).time().isoformat(), value) for i in range(n)]


# 2. Wobble inside one candle that ends below the line
def test_wobble_inside_candle_ending_below_gives_no_record():
    state, ev = feed([("10:40:10", D("81")), ("10:40:30", D("79")), ("10:40:50", D("79.5"))])
    state, ev2 = flush(state, "10:41:05")
    assert ev + ev2 == []


# 3. Re-arm: band AND cool-down
def test_rearm_needs_band_and_cooldown():
    samples = [("10:40:30", D("81")), ("10:41:30", D("71")), *minutes("10:42", 5, D("81"))]
    state, ev = feed(samples)
    state, ev2 = flush(state, "10:47:05")
    got = opened(ev + ev2)
    assert [(e.at.time(), e.level, e.worse) for e in got] == [(time(10, 41), 0, None), (time(10, 46), 0, None)]


def test_clear_by_less_than_band_never_reopens():
    _, ev = feed([("10:40:30", D("81")), ("10:41:30", D("72.01")), *minutes("10:42", 30, D("81"))])
    assert len(opened(ev)) == 1


# 4. ADR-236 dismiss
def _opened_then_dismissed():
    state, ev = feed([("10:40:30", D("81")), ("10:41:05", D("81"))])
    assert len(opened(ev)) == 1
    return ag.dismiss(state, "T-07")


def test_dismiss_then_same_level_stays_quiet():
    _, ev = feed(minutes("10:42", 60, D("85")), state=_opened_then_dismissed())
    assert ev == []


def test_dismiss_then_clear_and_recross_before_cooldown_stays_quiet():
    samples = [("10:41:30", D("71")), ("10:42:30", D("81")), ("10:43:30", D("79"))]
    state, ev = feed(samples, state=_opened_then_dismissed())
    _, ev2 = flush(state, "10:44:05")
    assert ev + ev2 == []


def test_dismiss_then_next_level_opens_worse_than_dismissed():
    _, ev = feed([("10:41:30", D("91")), ("10:42:05", D("91"))], state=_opened_then_dismissed())
    assert [(e.level, e.threshold, e.worse, e.at.time()) for e in ev] == [(1, D("90"), "dismissed", time(10, 42))]
    assert ag.WORSE_THAN_DISMISSED == "alert_record_worse_than_dismissed"
    assert ag.WORSE_THAN_LAST == "alert_record_worse_than_last"


def test_dismiss_then_next_level_over_cap_is_held_not_dropped():
    preset = replace(ag.INTRADAY, daily_cap=1)
    state, ev = feed([("10:40:30", D("81")), ("10:41:05", D("81"))], preset=preset)
    assert len(opened(ev)) == 1
    state = ag.dismiss(state, "T-07")
    _, ev = feed([("10:41:30", D("91")), *minutes("10:42", 5, D("91"))], preset=preset, state=state)
    assert [(type(e), e.reason, e.level) for e in ev] == [(ag.Held, ag.HELD_DAILY_LIMIT, 1)]


def test_dismiss_the_worse_one_then_same_worse_level_stays_quiet():
    state, ev = feed([("10:41:30", D("91")), ("10:42:05", D("91"))], state=_opened_then_dismissed())
    assert len(opened(ev)) == 1
    _, ev = feed(minutes("10:42", 30, D("92")), state=ag.dismiss(state, "T-07"))
    assert ev == []


# 5. Escalation without dismiss
def test_escalation_without_dismiss_is_worse_than_last_and_ignores_cooldown():
    _, ev = feed([("10:40:30", D("81")), ("10:41:30", D("90")), ("10:42:05", D("90"))])
    got = [(e.level, e.worse, e.at.time()) for e in opened(ev)]
    assert got == [(0, None, time(10, 41)), (1, "last", time(10, 42))]


def test_jump_two_levels_at_once_gives_one_record_at_the_higher_level():
    spec = ag.RuleSpec("T-03", "ge", (D("0.30"), D("0.35"), D("0.40")))
    _, ev = feed([("10:40:30", D("0.29")), ("10:41:30", D("0.41")), ("10:42:05", D("0.41"))], spec=spec)
    assert [(e.level, e.threshold, e.worse) for e in ev] == [(2, D("0.40"), None)]
    _, ev = feed([("10:40:30", D("0.31")), ("10:41:30", D("0.45")), ("10:42:05", D("0.45"))], spec=spec)
    assert [(e.level, e.worse) for e in ev] == [(0, None), (2, "last")]


# 6. Daily cap per strategy, reset next day
def test_daily_cap_six_opened_one_held_then_next_day_resets():
    specs = [ag.RuleSpec(f"R{i}", "ge", (D("1"),)) for i in range(1, 8)]
    readings = {s.rule_id: (s, D("2")) for s in specs}
    state, ev = ag.step(ag.initial_state(), now=at("10:40:30"), preset=ag.INTRADAY, readings=readings)
    state, ev = ag.step(state, now=at("10:41:30"), preset=ag.INTRADAY, readings=readings)
    assert [e.rule_id for e in opened(ev)] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert [(e.rule_id, e.reason) for e in held(ev)] == [("R7", ag.HELD_DAILY_LIMIT)]
    state, ev = ag.step(state, now=at("10:42:30"), preset=ag.INTRADAY, readings=readings)
    assert ev == []  # episode consumed: no repeated Held
    nxt = DAY + timedelta(days=1)
    state, ev = ag.step(state, now=at("10:40:30", nxt), preset=ag.INTRADAY, readings=readings)
    state, ev = ag.step(state, now=at("10:41:30", nxt), preset=ag.INTRADAY, readings=readings)
    assert [(type(e), e.rule_id) for e in ev] == [(ag.Opened, "R7")]
    assert state.opened_today == 1


# 7. Quiet time after the open
def test_quiet_time_intraday_held_then_opens_after():
    _, ev = feed(minutes("09:15", 7, D("81")))
    assert [(type(e), e.at.time()) for e in ev] == [(ag.Held, time(9, 16)), (ag.Opened, time(9, 21))]
    assert held(ev)[0].reason == ag.HELD_QUIET_TIME


def test_quiet_time_weekly_held_until_0930():
    _, ev = feed(minutes("09:20", 16, D("81")), preset=ag.WEEKLY)
    assert [(type(e), e.at.time()) for e in ev] == [(ag.Held, time(9, 25)), (ag.Opened, time(9, 35))]


# 8. None values
def test_candle_with_only_none_has_no_close():
    state, ev = feed([("10:40:10", None), ("10:40:40", None)])
    state, ev2 = flush(state, "10:41:05")
    assert ev + ev2 == []
    assert state.rule("T-07").pending is None


def test_none_never_clears():
    samples = [("10:40:30", D("81")), *minutes("10:41", 10, None), *minutes("10:51", 5, D("81"))]
    _, ev = feed(samples)
    assert len(opened(ev)) == 1


# 9. le and bool rules
def test_le_rule_t01_symmetric():
    spec = ag.RuleSpec("T-01", "le", ag.ladder_for("le", D("0.75"), [D("0.5"), D("0.3")]))
    samples = [("10:40:30", D("0.74")), ("10:41:30", D("0.80")), ("10:42:30", D("0.74")),
               ("10:43:30", D("0.83")), *minutes("10:44", 3, D("0.70")), ("10:47:30", D("0.45")),
               ("10:48:05", None)]
    _, ev = feed(samples, spec=spec)
    assert [(e.at.time(), e.level, e.worse) for e in opened(ev)] == [
        (time(10, 41), 0, None), (time(10, 46), 0, None), (time(10, 48), 1, "last")]


def test_bool_rule_t02_symmetric():
    spec = ag.RuleSpec("T-02", "bool", ())
    samples = [("10:40:30", True), ("10:41:30", True), ("10:42:30", False), *minutes("10:43", 4, True)]
    _, ev = feed(samples, spec=spec)
    assert [(e.at.time(), e.level, e.threshold, e.value) for e in opened(ev)] == [
        (time(10, 41), 0, None, True), (time(10, 46), 0, None, True)]


# Ladder helper
def test_ladder_for():
    assert ag.ladder_for("ge", D("50"), [D("40")]) == (D("50"),)
    assert ag.ladder_for("ge", D("0.30"), [D("0.35"), D("0.40")]) == (D("0.30"), D("0.35"), D("0.40"))
    assert ag.ladder_for("le", D("0.75"), [D("0.5"), D("0.3")]) == (D("0.75"), D("0.5"), D("0.3"))
    assert ag.ladder_for("bool", None, []) == ()


# Answer states of a reading: stated, absent, not readable (None), empty readings map
def test_absent_rule_gives_no_sample_and_last_seen_value_is_the_close():
    state, _ = feed([("10:40:10", D("81"))])
    state, ev = ag.step(state, now=at("10:40:40"), preset=ag.INTRADAY, readings={})
    assert ev == []
    _, ev = ag.step(state, now=at("10:41:10"), preset=ag.INTRADAY, readings={})
    assert [(e.at.time(), e.value) for e in opened(ev)] == [(time(10, 41), D("81"))]


def test_not_readable_none_keeps_the_last_value_seen_in_the_candle():
    state, _ = feed([("10:40:10", D("81")), ("10:40:40", None)])
    _, ev = flush(state, "10:41:10")
    assert [e.value for e in opened(ev)] == [D("81")]


def test_empty_readings_still_process_due_closes():
    state, _ = feed([("10:40:10", D("81"))])
    _, ev = ag.step(state, now=at("10:55:00"), preset=ag.INTRADAY, readings={})
    assert [e.at.time() for e in ev] == [time(10, 41)]


def test_naive_now_fails_closed():
    with pytest.raises(ValueError, match="timezone-aware"):
        ag.step(ag.initial_state(), now=datetime(2026, 11, 2, 10, 40), preset=ag.INTRADAY, readings={})  # noqa: DTZ001


# 10. No I/O
def test_gate_module_makes_no_io():
    src = (ROOT / "backend" / "ofo" / "adjustment" / "alert_gate.py").read_text("utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods, "scan found no imports: parser broken"
    assert not mods & {"ofo_app", "sqlalchemy", "redis", "asyncio", "time", "os", "socket", "pathlib", "io"}
    for banned in (".now(", ".today(", ".utcnow(", "open("):
        assert banned not in src


# GC-ALERT1 step 5 review round 2, finding 2: a candle that saw a pause has no close
def test_pause_drops_the_pending_candle_so_its_close_opens_nothing():
    state, ev = feed([("10:00:20", D("82"))])
    state = ag.pause(state, at("10:00:25"))
    assert state.rule("T-07").pending is None
    state, ev2 = flush(state, "10:01:00")
    assert ev + ev2 == []


def test_a_sample_after_the_pause_in_the_same_candle_gives_no_close():
    state, _ = feed([("10:00:20", D("82"))])
    state = ag.pause(state, at("10:00:25"))
    state, ev = feed([("10:00:40", D("85"))], state=state)  # the feed came back inside the paused candle
    assert state.rule("T-07").pending is None
    state, ev2 = flush(state, "10:01:05")
    assert ev + ev2 == []
    state, ev3 = feed([("10:01:30", D("85"))], state=state)  # the next candle was fully watched: it opens
    state, ev4 = flush(state, "10:02:00")
    assert [(e.rule_id, e.at) for e in opened(ev3 + ev4)] == [("T-07", at("10:02:00"))]


def test_a_pause_never_lapses_an_open_record():
    state, ev = feed([("10:00:30", D("82"))])
    state, ev2 = flush(state, "10:01:00")
    assert len(opened(ev + ev2)) == 1
    state, _ = feed([("10:01:10", D("60"))], state=state)  # would clear by the band at the 10:02 close
    state = ag.pause(state, at("10:01:20"))
    state, ev3 = flush(state, "10:02:00")
    assert ev3 == [] and state.rule("T-07").record.final is False


def test_a_pause_keeps_the_close_of_a_candle_that_ended_before_it():
    state, _ = feed([("10:00:30", D("82"))])
    state = ag.pause(state, at("10:01:02"))  # the 10:00 candle ended at 10:01:00, fully watched; not yet closed
    state, ev = flush(state, "10:01:03")
    assert [(e.rule_id, e.at) for e in opened(ev)] == [("T-07", at("10:01:00"))]


def test_pause_keeps_the_latest_instant_and_needs_an_aware_time():
    state = ag.pause(ag.pause(ag.initial_state(), at("10:00:40")), at("10:00:10"))
    assert state.paused_at == at("10:00:40")
    with pytest.raises(ValueError, match="timezone-aware"):
        ag.pause(state, datetime(2026, 11, 2, 10, 0))  # noqa: DTZ001 - the naive time the gate must refuse


# #638 / attack 2: the daily cap resets on the IST day, never the UTC day (05:30 IST is midnight UTC)
def _capped_at_one(day: date):
    preset = replace(ag.INTRADAY, daily_cap=1, quiet_until=time(0, 0))
    return preset, replace(ag.initial_state(), day=day, opened_today=1)


def test_the_cap_resets_at_ist_midnight():
    preset, state = _capped_at_one(DAY)
    state, ev = ag.step(state, now=at("23:58:30"), preset=preset, readings={"T-07": (T07, D("81"))})
    state, ev2 = ag.step(state, now=at("23:59:05"), preset=preset, readings={})
    assert [e.reason for e in held(ev + ev2)] == ["daily_limit"] and opened(ev + ev2) == []
    nxt = DAY + timedelta(days=1)
    state, ev = ag.step(state, now=at("00:00:30", nxt), preset=preset, readings={"T-07": (T07, D("81"))})
    state, ev2 = ag.step(state, now=at("00:01:05", nxt), preset=preset, readings={})
    assert [(e.at, e.level) for e in opened(ev + ev2)] == [(at("00:01", nxt), 0)]
    assert (state.day, state.opened_today) == (nxt, 1)


def test_the_cap_does_not_reset_at_utc_midnight():
    preset, state = _capped_at_one(DAY)
    state, ev = ag.step(state, now=at("05:28:30"), preset=preset, readings={"T-07": (T07, D("81"))})
    state, ev2 = ag.step(state, now=at("05:30:30"), preset=preset, readings={"T-07": (T07, D("81"))})
    state, ev3 = ag.step(state, now=at("05:31:05"), preset=preset, readings={})
    assert opened(ev + ev2 + ev3) == [] and [e.reason for e in held(ev + ev2 + ev3)] == ["daily_limit"]
    assert (state.day, state.opened_today) == (DAY, 1)


# #639 item 2: a dismiss matches the stored record, never the rule
def test_a_dismiss_of_another_record_leaves_the_gate_record_alone():
    state, _ = feed([("10:40:30", D("81")), ("10:41:05", D("81"))])
    state = ag.with_record_id(state, "T-07", 42)
    assert ag.is_dismissed(ag.dismiss(state, "T-07", 41), "T-07") is False  # an older record's dismiss
    assert ag.is_dismissed(ag.dismiss(state, "T-07", 42), "T-07") is True
