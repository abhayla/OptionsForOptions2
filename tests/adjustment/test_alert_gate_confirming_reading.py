"""GC-ICFIX: a stored alert carries the number of the sample that CONFIRMED the firing, not of the next check.

A yes/no rule (T-02, situation, level watch, day, combined, clock) gates on True / False, so its record had no number
of its own and the store copied the LATEST check's (a record opened at the close of candle 1 showed candle 2's figure).
The reading now travels with the pending sample (RuleSpec.shown_value / shown_threshold) and out on the event.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from ofo.adjustment import alert_gate as ag
from ofo.adjustment import gate_readings
from ofo.adjustment.playbook_eval import RuleValue
from ofo.adjustment.stop_lines import RULE_OF_LINE

D = Decimal
DAY = date(2026, 11, 2)


def at(hhmm: str, day: date = DAY) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), tzinfo=ag.IST)


def _t02(shown: str | None, thr: str | None = "0") -> ag.RuleSpec:
    return ag.RuleSpec("T-02", "bool", (), shown_value=None if shown is None else D(shown),
                       shown_threshold=None if thr is None else D(thr))


def _step(state, hhmm, spec, value, day=DAY):
    return ag.step(state, now=at(hhmm, day), preset=ag.INTRADAY, readings={spec.rule_id: (spec, value)})


def test_the_record_carries_the_confirming_samples_reading_not_the_later_checks():
    state, _ = _step(ag.initial_state(), "10:40:30", _t02("-500"), True)  # candle 10:40-10:41 reads -500
    state, ev = _step(state, "10:41:30", _t02("1816.75"), False)  # the later check: profit again
    [o] = [e for e in ev if isinstance(e, ag.Opened)]
    assert (o.at.time(), o.value, o.shown_value, o.shown_threshold) == (time(10, 41), True, D("-500"), D("0"))


def test_a_confirming_sample_with_no_number_stores_none_never_the_later_number():
    state, _ = _step(ag.initial_state(), "10:40:30", _t02(None, None), True)
    _, ev = _step(state, "10:41:30", _t02("1816.75"), True)
    [o] = [e for e in ev if isinstance(e, ag.Opened)]
    assert (o.shown_value, o.shown_threshold) == (None, None)


def test_a_rule_that_fires_and_closes_within_one_step_carries_that_samples_reading():
    # a stop rule is judged at once (REQ-170 AC-5), in the very step that takes the sample
    spec = ag.RuleSpec(next(iter(RULE_OF_LINE.values())), "bool", (), shown_value=D("-42"), shown_threshold=D("0"))
    _, ev = _step(ag.initial_state(), "10:40:30", spec, True)
    [o] = [e for e in ev if isinstance(e, ag.Opened)]
    assert o.shown_value == D("-42")


def test_a_held_close_carries_the_reading_too():
    state, _ = _step(ag.initial_state(), "09:16:30", _t02("-7"), True)  # before the 09:20 quiet time
    _, ev = _step(state, "09:17:30", _t02("9"), True)
    [h] = [e for e in ev if isinstance(e, ag.Held)]
    assert h.shown_value == D("-7")


def test_a_pending_sample_from_a_previous_day_closes_with_its_own_reading():
    state, _ = _step(ag.initial_state(), "15:29:30", _t02("-3"), True)
    day2 = date(2026, 11, 3)
    _, ev = ag.step(state, now=at("09:30:30", day2), preset=ag.INTRADAY, readings={})
    [o] = [e for e in ev if isinstance(e, ag.Opened)]
    assert (o.at.date(), o.shown_value) == (DAY, D("-3"))


def test_a_decimal_rule_is_unchanged_its_event_value_is_the_number():
    spec = ag.RuleSpec("T-07", "ge", (D("80"),))
    state, _ = _step(ag.initial_state(), "10:40:30", spec, D("81"))
    _, ev = _step(state, "10:41:30", spec, D("79"))
    [o] = [e for e in ev if isinstance(e, ag.Opened)]
    assert (o.value, o.threshold, o.shown_value) == (D("81"), D("80"), None)


def test_gate_readings_put_the_numbers_of_a_yes_no_rule_on_its_spec():
    v = RuleValue("T-02", "T-02", D("-500"), D("0"), "lt", True)
    spec, value = gate_readings.reading(v)
    assert (value, spec.shown_value, spec.shown_threshold) == (True, D("-500"), D("0"))
    clock = RuleValue("T-10b", "T-10b", "14:00", "14:30", "ge", False)
    spec, _ = gate_readings.reading(clock)
    assert (spec.shown_value, spec.shown_threshold) == (None, None)


# ---- GC-ICFIX round 2: a held ladder row keeps its rung; an opened record's limit is the confirming sample's ---


def test_a_held_ladder_rule_carries_the_rung_of_its_own_sample():
    spec = ag.RuleSpec("T-07", "ge", (D("80"), D("90")))
    state, _ = _step(ag.initial_state(), "09:16:30", spec, D("85"))  # before the 09:20 quiet time
    _, ev = _step(state, "09:17:30", spec, D("85"))
    [h] = [e for e in ev if isinstance(e, ag.Held)]
    assert (h.level, h.threshold) == (0, D("80"))


def test_a_restored_held_ladder_row_ends_by_the_band_after_a_restart():
    spec = ag.RuleSpec("T-07", "ge", (D("80"),))
    state, _ = _step(ag.initial_state(), "09:16:30", spec, D("85"))
    _, ev = _step(state, "09:17:30", spec, D("85"))
    [h] = [e for e in ev if isinstance(e, ag.Held)]
    capped = ag.restore(ag.GateRows((), 0), DAY, {})
    restored = ag.restore_held(capped, "T-07", h.reason, h.threshold, spec)
    assert restored.rule("T-07").hold.threshold == D("80")
    restored, _ = _step(restored, "10:40:30", spec, D("60"))  # well inside the band (80 - 20% of 80 = 64)
    restored, _ = _step(restored, "10:41:30", spec, D("60"))
    assert restored.rule("T-07").hold is None


def test_an_opened_ladder_record_carries_the_limit_of_its_own_sample():
    first = ag.RuleSpec("T-07", "ge", (D("80"), D("90")))
    moved = ag.RuleSpec("T-07", "ge", (D("85"), D("90")))  # the stage moved on before the next check
    state, _ = _step(ag.initial_state(), "10:40:30", first, D("81"))
    _, ev = _step(state, "10:41:30", moved, D("81"))
    [o] = [e for e in ev if isinstance(e, ag.Opened)]
    assert o.limit == D("80")


def test_an_opened_yes_no_record_carries_its_samples_number_as_the_limit():
    state, _ = _step(ag.initial_state(), "10:40:30", _t02("-500", "0"), True)
    _, ev = _step(state, "10:41:30", _t02("9", "1"), True)
    [o] = [e for e in ev if isinstance(e, ag.Opened)]
    assert o.limit == D("0")
