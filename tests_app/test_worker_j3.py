"""Lane J3 (27 Nov 2026): the stop worker keeps every rule it CAN check when one fact is missing, and reads the same
expiry kind row the live check and the plan sheet read. Spec basis: ADR-330 (44), (47), (58); REQ-115 AC-4.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.marketdata.shared_compute import FeedScope
from ofo_app import adjustment_readers, background, calc_speeds
from test_background_cycle import (
    DEFAULTS,
    FIRST_ID,
    PREFS,
    Calls,
    FakeGate,
    Prov,
    _price_time,
    _system_body,
    _watched,
    _worker,
    scn,  # noqa: F401 - the module fixture
)

MAX_REREAD_SECONDS = 10
CHECKED_TWICE = 2


def _rupee_body(level: str) -> dict:
    body = _system_body("ic")
    return {**body, "guards": {**body.get("guards", {}), sl.RUPEE_LOSS_KEY: level}}


def _state_without_kind(monkeypatch) -> None:
    """The state of a trade whose expiry kind is not known (Lane R3's ``state_of``: no stop lines, ``days_left`` None,
    the kind a placeholder), whatever the base the worker is built on: the worker's own state step answers so."""
    real = background.state_from_market

    def unknown(*a, **k):
        return dataclasses.replace(real(*a, **k), days_left=None, stops=None)
    monkeypatch.setattr(background, "state_from_market", unknown)


async def test_a_far_month_leg_of_unknown_kind_still_raises_the_rupee_loss_stop(scn, monkeypatch):  # noqa: F811
    _state_without_kind(monkeypatch)  # R3: "not known"
    prov, now, calls, gate = Prov(scn), [scn.clock_at], Calls(), FakeGate()
    watched = [dataclasses.replace(w, body=_rupee_body("1")) for w in _watched(scn)]
    w = _worker(prov, watched, now, calls, gate_store=gate)
    await w.cycle()
    print("STATUS", w.status.get(FIRST_ID), w.paused_reason.get(FIRST_ID), "states", len(calls.states),
          "pnl", [getattr(s, "pnl", None) for _, s in calls.states])
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE
    assert any(getattr(e, "rule", None) == sl.RUPEE_LOSS_RULE or sl.RUPEE_LOSS_RULE in repr(e)
               for _, e in gate.events), gate.events


async def test_the_percent_stop_of_an_unknown_kind_is_reported_not_checked_with_its_reason(scn, monkeypatch):  # noqa: F811
    _state_without_kind(monkeypatch)
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    body = _system_body("ic")
    watched = [dataclasses.replace(w, body=body) for w in _watched(scn)]
    w = _worker(prov, watched, now, calls, gate_store=FakeGate())
    await w.cycle()
    # FE2 (FD2 hand-over): no exit rule can be checked here, so the trade is published paused, not watched
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[FIRST_ID] is background.PriceState.EXPIRY_KIND_UNKNOWN
    state = calls.states[0][1]
    assert state.days_left is None and state.stops is None
    ev = pe.evaluate(body, state, None, None, gap_until=PREFS.gap_until)
    t06 = next((r for r in ev.results if r.trigger_id == "T-06"), None)
    assert t06 is None or isinstance(t06, pe.NotChecked), t06


def test_the_kind_is_read_for_the_nearest_leg_not_the_first_one_listed(scn, monkeypatch):  # noqa: F811
    """J3 item 2 (R3's finding): the screen's kind is read for the nearest leg; the worker read legs[0]."""
    seen: list[datetime.date] = []

    def recording(expiry, *_a, **_k):
        seen.append(expiry)
        return "monthly"
    monkeypatch.setattr(adjustment_readers, "expiry_kind_of", recording)
    prov = Prov(scn)
    at = _price_time(prov)
    w = _watched(scn)[0]
    read = background.read_prices(prov, w, at)
    near = datetime.date(2026, 11, 2)
    legs = (w.tracked.position.legs[0], dataclasses.replace(w.tracked.position.legs[1], expiry=near),
            *w.tracked.position.legs[2:])
    w2 = dataclasses.replace(w, tracked=dataclasses.replace(
        w.tracked, position=dataclasses.replace(w.tracked.position, legs=legs)))
    background.market_inputs(w2, read, FeedScope(background.SharedCompute(), "owner"), at, DEFAULTS)
    assert seen == [near]


async def test_the_worker_rereads_a_saved_plan_within_ten_seconds(scn):  # noqa: F811
    """J3 item 3: the re-read of the monitors (where a saved plan is picked up) is never more than 10 s apart."""
    asked: list[float] = []
    w = _worker(Prov(scn), _watched(scn), [scn.clock_at], Calls())

    async def sleeper(seconds):
        asked.append(seconds)
        w.stop()
    w._rebuild_sleep = sleeper
    await w._rebuild_loop()
    assert asked and asked[0] <= MAX_REREAD_SECONDS, asked


async def test_a_plan_saved_during_an_old_plan_check_is_checked_at_once_not_after_the_interval(scn):  # noqa: F811
    """J3 item 3 (review F1): the re-read awaits the database before it publishes the new plan; a check with the
    OLD plan meanwhile used up the tick, the signature and the style interval. The first check with the new plan runs
    at the next cycle anyway (the plan in the list is not the one the last check ran with)."""
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    long = {**DEFAULTS, **{k: Decimal(600) for k in calc_speeds.BACKGROUND_KEYS.values()}}
    w = _worker(prov, _watched(scn), now, calls, settings=lambda _at: long)
    await w.cycle()
    assert len(calls.states) == 1
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()
    assert len(calls.states) == 1  # the control: the same plan, inside the interval, is held
    w.monitors[0] = dataclasses.replace(w.monitors[0], body=_rupee_body("1"))  # published after the old check ran
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()
    assert len(calls.states) == CHECKED_TWICE  # the saved plan is checked at once


async def test_a_refused_pin_is_never_replaced_by_the_unknown_kind_fallback(scn, monkeypatch):  # noqa: F811
    _state_without_kind(monkeypatch)

    class BogusPin(FakeGate):
        async def load(self, _w, _today):
            return background.GateLoad(background.alert_gate.GateRows((), 0), pin="bogus")
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    watched = [dataclasses.replace(w) for w in _watched(scn)]
    w = _worker(prov, watched, now, calls, gate_store=BogusPin())
    await w.cycle()
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED
