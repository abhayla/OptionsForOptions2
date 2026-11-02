
"""GC-ALERT1 wire-a: the gate's Lapsed event (ADR-237 (4)) and its restore from stored rows (ADR-237 (5)).

Spec basis: ADR-237 (4) "an open record lapses when a close clears its line by the re-arm band ... not at the first
close back under the line"; ADR-237 (5) "the gate state is rebuilt on worker start ... 'Cleared' is not stored: after a
restart a rule counts as not yet cleared (quiet; an escalation still opens)"; ADR-236 (worded by the dismissed flag).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from test_alert_gate import DAY, FIXTURE, PRESETS, at, opened, run

D = Decimal
T07 = ag.RuleSpec("T-07", "ge", (D("80"),))
T03 = ag.RuleSpec("T-03", "ge", (D("0.30"), D("0.35"), D("0.40")))


def lapsed(events):
    return [e for e in events if isinstance(e, ag.Lapsed)]


def steps(state, preset, samples, spec):
    events = []
    for now, value in samples:
        state, ev = ag.step(state, now=now, preset=preset, readings={spec.rule_id: (spec, value)})
        events += ev
    return state, events


# ---- Lapsed --------------------------------------------------------------------------------------------------------

def test_lapse_only_when_the_close_clears_the_band_not_at_the_first_close_under_the_line():
    # intraday 1-min candles; 80 % line, band 10 % -> lapses at or below 72 %
    samples = [(at("10:40"), D("81")), (at("10:41"), D("79")), (at("10:42"), D("75")), (at("10:43"), D("72")),
               (at("10:44"), D("70"))]
    _, events = steps(ag.initial_state(), ag.INTRADAY, samples, T07)
    assert [e.at for e in opened(events)] == [at("10:41")]
    assert lapsed(events) == [ag.Lapsed("T-07", at("10:44"), D("72"))]  # the 10:43 candle's close, seen at 10:44


def test_lapse_is_emitted_once_per_record():
    samples = [(at("10:40"), D("81")), (at("10:41"), D("70")), (at("10:42"), D("60")), (at("10:43"), D("50")),
               (at("10:44"), D("50"))]
    _, events = steps(ag.initial_state(), ag.INTRADAY, samples, T07)
    assert len(lapsed(events)) == 1


def test_a_dismissed_record_does_not_lapse():
    state, _ = steps(ag.initial_state(), ag.INTRADAY, [(at("10:40"), D("81")), (at("10:41"), D("81"))], T07)
    state = ag.dismiss(state, "T-07")
    _, events = steps(state, ag.INTRADAY, [(at("10:42"), D("60")), (at("10:43"), D("60"))], T07)
    assert lapsed(events) == []


def test_a_yes_no_rule_lapses_at_its_first_false_close():
    spec = ag.RuleSpec("T-02", "bool", ())
    samples = [(at("10:40"), True), (at("10:41"), False), (at("10:42"), False)]
    _, events = steps(ag.initial_state(), ag.INTRADAY, samples, spec)
    assert len(opened(events)) == 1
    assert lapsed(events) == [ag.Lapsed("T-02", at("10:42"), False)]


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: str(c["strategy_id"]))
@pytest.mark.parametrize("style", ["intraday", "weekly", "monthly"])
def test_real_fixture_every_lapse_is_beyond_the_band_and_follows_its_own_record(case, style):
    preset = PRESETS[style]
    thr = D(str(case["threshold"]))
    spec = ag.RuleSpec(case["rule"], "ge", (thr,))
    _, events = run(preset, [(at(t), D(str(v))) for t, v in case["minute_closes_ist"]], spec)
    band_line = thr - preset.rearm_fraction * thr
    open_now = False
    for e in events:
        if isinstance(e, ag.Opened):
            open_now = True
        elif isinstance(e, ag.Lapsed):
            assert open_now and e.value <= band_line
            open_now = False


# ---- restore ---------------------------------------------------------------------------------------------------------

def _rows(*rows: ag.GateRow, today: int = 0) -> ag.GateRows:
    return ag.GateRows(rows, today)


def test_restore_then_same_level_stays_quiet():
    row = ag.GateRow("T-07", at("10:41"), D("80"), dismissed=False, open=True)
    state = ag.restore(_rows(row, today=1), DAY, {"T-07": T07})
    _, events = steps(state, ag.INTRADAY, [(at("11:00"), D("85")), (at("11:30"), D("85")), (at("11:31"), D("85"))],
                      T07)
    assert opened(events) == []  # not cleared after a restart: quiet


def test_restore_then_escalation_opens_worded_by_the_dismissed_flag():
    for dismissed, worse in ((True, "dismissed"), (False, "last")):
        row = ag.GateRow("T-03", at("10:00"), D("0.30"), dismissed=dismissed, open=not dismissed)
        state = ag.restore(_rows(row), DAY, {"T-03": T03})
        _, events = steps(state, ag.WEEKLY, [(at("11:00"), D("0.36")), (at("11:05"), D("0.36"))], T03)
        assert [(e.level, e.threshold, e.worse) for e in opened(events)] == [(1, D("0.35"), worse)]


def test_restore_with_todays_cap_used_holds_the_next_crossing():
    state = ag.restore(_rows(today=ag.WEEKLY.daily_cap), DAY, {})
    _, events = steps(state, ag.WEEKLY, [(at("11:00"), D("0.31")), (at("11:05"), D("0.31"))], T03)
    assert opened(events) == []
    assert [(e.reason, e.level) for e in events if isinstance(e, ag.Held)] == [(ag.HELD_DAILY_LIMIT, 0)]


def test_restore_cap_resets_on_a_new_day():
    state = ag.restore(_rows(today=ag.WEEKLY.daily_cap), DAY, {})
    nxt = DAY + timedelta(days=1)
    _, events = steps(state, ag.WEEKLY, [(at("11:00", nxt), D("0.31")), (at("11:05", nxt), D("0.31"))], T03)
    assert len(opened(events)) == 1


def test_restored_final_record_never_lapses_but_clears():
    row = ag.GateRow("T-07", at("10:41"), D("80"), dismissed=False, open=False)  # already lapsed in the store
    state = ag.restore(_rows(row), DAY, {"T-07": T07})
    samples = [(at("11:00"), D("60")), (at("11:01"), D("60")), (at("11:10"), D("81")), (at("11:11"), D("81"))]
    _, events = steps(state, ag.INTRADAY, samples, T07)
    assert lapsed(events) == []
    assert [e.at for e in opened(events)] == [at("11:11")]  # cleared by the band and past the cool-down: re-armed


def test_restore_stored_threshold_less_severe_than_the_current_line_is_below_level_zero():
    # recorded in Early at 0.30; the stage moved on and the current ladder starts at 0.35: a crossing is worse
    row = ag.GateRow("T-03", at("10:00"), D("0.30"), dismissed=False, open=True)
    spec = ag.RuleSpec("T-03", "ge", (D("0.35"), D("0.40")))
    state = ag.restore(_rows(row), DAY, {"T-03": spec})
    _, events = steps(state, ag.WEEKLY, [(at("11:00"), D("0.36")), (at("11:05"), D("0.36"))], spec)
    assert [(e.level, e.worse) for e in opened(events)] == [(0, "last")]


def test_restore_refuses_a_negative_count_and_a_naive_time():
    with pytest.raises(ValueError, match="negative"):
        ag.restore(_rows(today=-1), DAY, {})
    naive = ag.GateRow("T-07", at("10:41").replace(tzinfo=None), D("80"), dismissed=False, open=True)
    with pytest.raises(ValueError, match="timezone"):
        ag.restore(_rows(naive), DAY, {"T-07": T07})
