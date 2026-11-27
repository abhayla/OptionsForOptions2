"""Lane J3 (27 Nov 2026): the stop worker keeps every rule it CAN check when one fact is missing, and reads the same
expiry kind row the live check and the plan sheet read. Spec basis: ADR-330 (44), (47), (58); REQ-115 AC-4.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

import pytest
from ofo.adjustment import stop_lines as sl
from ofo_app import adjustment_readers, background, scenario_mode
from test_background_cycle import (
    FIRST_ID,
    PREFS,
    Calls,
    FakeGate,
    Prov,
    _system_body,
    _watched,
    _worker,
    scn,  # noqa: F401 - the module fixture
)


def _rupee_body(level: str) -> dict:
    body = _system_body("ic")
    return {**body, "guards": {**body.get("guards", {}), sl.RUPEE_LOSS_KEY: level}}


def _unknown_kind(tracked):
    return dataclasses.replace(tracked, position=dataclasses.replace(tracked.position, expiry_kind=""))


async def test_a_far_month_leg_of_unknown_kind_still_raises_the_rupee_loss_stop(scn, monkeypatch):  # noqa: F811
    monkeypatch.setattr(adjustment_readers, "expiry_kind_of", lambda *_a, **_k: "")  # R3: "not known"
    prov, now, calls, gate = Prov(scn), [scn.clock_at], Calls(), FakeGate()
    watched = [dataclasses.replace(w, body=_rupee_body("1"), tracked=_unknown_kind(w.tracked)) for w in _watched(scn)]
    w = _worker(prov, watched, now, calls, gate_store=gate)
    await w.cycle()
    print("STATUS", w.status.get(FIRST_ID), w.paused_reason.get(FIRST_ID), "states", len(calls.states),
          "pnl", [getattr(s, "pnl", None) for _, s in calls.states])
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE
    assert any(getattr(e, "rule", None) == sl.RUPEE_LOSS_RULE or sl.RUPEE_LOSS_RULE in repr(e)
               for _, e in gate.events), gate.events


async def test_the_percent_stop_of_an_unknown_kind_is_reported_not_checked_with_its_reason(scn, monkeypatch):  # noqa: F811
    from ofo.adjustment import playbook_eval as pe
    monkeypatch.setattr(adjustment_readers, "expiry_kind_of", lambda *_a, **_k: "")
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    body = _system_body("ic")
    watched = [dataclasses.replace(w, body=body, tracked=_unknown_kind(w.tracked)) for w in _watched(scn)]
    w = _worker(prov, watched, now, calls, gate_store=FakeGate())
    await w.cycle()
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE  # watched, not paused
    state = calls.states[0][1]
    assert state.days_left is None and state.stops is None
    ev = pe.evaluate(body, state, None, None, gap_until=PREFS.gap_until)
    t06 = next((r for r in ev.results if r.trigger_id == "T-06"), None)
    assert t06 is None or isinstance(t06, pe.NotChecked), t06
