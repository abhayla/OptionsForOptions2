"""#709 item 7 (review MAJOR): the REAL worker path puts the confirming check on each sample it hands the gate.

Two checks fall across a candle close and differ in stage, label and adjustment count; the queued event's record
fields must be the FIRST check's. Deleting the ``dataclasses.replace(spec, sample=ctx)`` in ``_evaluate_and_gate``
leaves ``alert_gate`` tests green (they build the sample by hand), so this drives ``Worker._evaluate_and_gate``.
No database.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from ofo.adjustment import alert_gate
from ofo_app import background, scenario_mode
from ofo_app.routes import adjustment_check as check_route

from tests_app.test_background_settings_cache import FakeDb, _cycle_rig


def _at(hhmmss: str) -> datetime:
    h, m, s = map(int, hhmmss.split(":"))
    return datetime(2026, 11, 17, h, m, s, tzinfo=alert_gate.IST)


def _watched(label: str, count: int) -> SimpleNamespace:
    return SimpleNamespace(user_ref="owner", strategy_id=7, body={"label": label}, is_system=True,
                           tracked=SimpleNamespace(adjustments_used=count))


async def test_the_worker_attaches_the_confirming_check_to_the_event_it_queues(monkeypatch):
    scn = scenario_mode.load("ADJ-02")
    _prov, _now, _calls, _cache, w = _cycle_rig(scn, FakeDb(), n=1)
    w._gate_load[7] = background.GateLoad(alert_gate.GateRows((), 0))
    spec = alert_gate.RuleSpec("T-02", "bool", ())
    holds = iter([True, False])  # the first check reads the rule true, the later one false: it closes the first
    stages = iter(["Early", "Late"])

    async def evaluate(_w, _state, _prefs):
        return SimpleNamespace(values=[], results=[], stage_name=next(stages), memory={})

    monkeypatch.setattr(w, "_evaluate_and_write", evaluate)
    monkeypatch.setattr(background.alert_presets, "style_for", lambda *a: "intraday")
    monkeypatch.setattr(background.alert_presets, "preset_for", lambda *a: alert_gate.INTRADAY)
    monkeypatch.setattr(background.gate_readings, "readings", lambda ev, *, stops: {"T-02": (spec, next(holds))})
    monkeypatch.setattr(background.check, "record_words", lambda body, rid, rv: ("T-02", "ge", body["label"], "u"))
    monkeypatch.setattr(check_route, "cheapest", lambda state: None)
    monkeypatch.setattr(check_route, "t19_record", lambda trigger, cheap: {})
    state = SimpleNamespace(expiry_kind="weekly", days_left=3)
    prefs = SimpleNamespace()
    await w._evaluate_and_gate(_watched("first", 1), _at("10:40:30"), state, prefs, (None, {}))
    await w._evaluate_and_gate(_watched("second", 2), _at("10:41:30"), state, prefs, (None, {}))
    [batch] = w._gate_events[7]
    [event] = batch.events
    assert isinstance(event, alert_gate.Opened)
    f = background.record_fields(event)
    assert (f.stage_name, f.label, f.adjustments) == ("Early", "first", 1)  # the confirming check, not the later one
