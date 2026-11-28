"""Lane FE2 (28 Nov 2026), coordinator hand-over 2 (from Lane FD2). Spec basis: REQ-115 AC-4 ("Monitoring paused" while
nothing can be checked), REQ-049, ADR-330 (44), (58), (13).

(1) A trade whose expiry kind is not known and whose EVERY exit rule answers "not checked" is published as
``status paused, reason expiry_kind_unknown`` (the screen words it; REQ-115: never shown as watched with no exit that
can run). A trade that still has an exit the evaluation CAN run (a typed rupee stop, Lane J3) stays watched.
(2) Once per cycle the worker publishes the value of every rule it evaluated through ``rule_readings.publish`` (the
pages' "Now <value> as of <time>").
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal

from ofo.adjustment import stop_lines as sl
from ofo_app import background, monitoring_state, rule_readings
from test_background_cycle import (  # noqa: F401
    DEFAULTS,
    FIRST_ID,
    Calls,
    FakeGate,
    Prov,
    _system_body,
    _watched,
    _worker,
    scn,
)
from test_monitoring_state import _Client, _fresh
from test_worker_j3 import _rupee_body, _state_without_kind


async def _published(scn, monkeypatch, body, unknown: bool):  # noqa: F811
    if unknown:
        _state_without_kind(monkeypatch)
    client = _Client()
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    watched = [dataclasses.replace(w, body=body) for w in _watched(scn)]
    w = _worker(prov, watched, now, calls, gate_store=FakeGate(), want_client=client)
    await w.cycle()
    await monitoring_state.ExitsPublisher(client, "m").publish([], {}, now[0])  # a live monitor's report exists
    return w, client, now[0]


async def test_an_unknown_kind_with_no_exit_that_can_run_is_published_paused_expiry_kind_unknown(scn, monkeypatch):  # noqa: F811
    w, client, now = await _published(scn, monkeypatch, _system_body("ic"), unknown=True)
    got = (await monitoring_state.read_states(client, [FIRST_ID], now, heartbeat=_fresh))[FIRST_ID]
    print("PUBLISHED", got, w.status[FIRST_ID], w.paused_reason.get(FIRST_ID))
    assert (got.status, got.reason) == (monitoring_state.PAUSED, "expiry_kind_unknown"), got


async def test_an_unknown_kind_with_a_rupee_stop_stays_watched(scn, monkeypatch):  # noqa: F811
    w, client, now = await _published(scn, monkeypatch, _rupee_body("1"), unknown=True)
    got = (await monitoring_state.read_states(client, [FIRST_ID], now, heartbeat=_fresh))[FIRST_ID]
    assert got.status == monitoring_state.ACTIVE, got
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE


async def test_a_known_kind_is_never_published_as_expiry_kind_unknown(scn, monkeypatch):  # noqa: F811
    _w, client, now = await _published(scn, monkeypatch, _system_body("ic"), unknown=False)
    got = (await monitoring_state.read_states(client, [FIRST_ID], now, heartbeat=_fresh))[FIRST_ID]
    assert got.reason != "expiry_kind_unknown", got


async def test_the_worker_publishes_the_value_of_every_rule_it_evaluated_once_per_cycle(scn, monkeypatch):  # noqa: F811
    w, client, now = await _published(scn, monkeypatch, _rupee_body("1"), unknown=False)
    got = await rule_readings.read(client, now)
    print("RULE VALUES", got)
    value, at = got[(FIRST_ID, sl.RUPEE_LOSS_RULE)]
    assert isinstance(value, Decimal) and value > 0 and at == now
    assert w is not None


async def test_a_strategy_that_left_the_list_is_no_longer_in_the_rule_values(scn, monkeypatch):  # noqa: F811
    w, client, now = await _published(scn, monkeypatch, _rupee_body("1"), unknown=False)
    w.monitors.clear()
    w._clock = lambda: now.replace(microsecond=1)  # a later cycle
    await w.cycle()
    got = await rule_readings.read(client, now)
    assert all(sid != FIRST_ID for sid, _r in got), got


# ---- second Opus review: F1 and F3 ----------------------------------------------------------------------------

async def test_review_f1_a_fresh_read_does_not_undo_the_kind_pause_but_clears_any_other(scn):  # noqa: F811
    """The worker wakes every second and checks every 10 s: a fresh price read in a cycle that runs no check must
    not turn a trade paused for its unknown expiry kind into "watched" (only a check clears it); any other pause is
    cleared by a fresh read as before."""
    w = _worker(Prov(scn), _watched(scn), [scn.clock_at], Calls())
    w.status[FIRST_ID] = background.MonitoringStatus.PAUSED
    w.paused_reason[FIRST_ID] = background.PriceState.EXPIRY_KIND_UNKNOWN
    w._owed[FIRST_ID] = background.PriceState.EXPIRY_KIND_UNKNOWN  # FE3 F1: the debt lives in ``_owed``
    w._fresh_read(FIRST_ID)
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[FIRST_ID] is background.PriceState.EXPIRY_KIND_UNKNOWN
    w._owed.pop(FIRST_ID)
    w.paused_reason[FIRST_ID] = background.PriceState.LEG_MISSING
    w._fresh_read(FIRST_ID)
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE and FIRST_ID not in w.paused_reason


async def test_review_f1_a_check_that_finds_an_exit_that_can_run_clears_the_kind_pause(scn, monkeypatch):  # noqa: F811
    w, _client, _now = await _published(scn, monkeypatch, _system_body("ic"), unknown=True)
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    state = dataclasses.replace(w._gate_ctx[FIRST_ID].state, days_left=3)  # the kind became known
    w._note_rules(w.monitors[0], state, {sl.RUPEE_LOSS_RULE: (None, Decimal(5))})
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE and FIRST_ID not in w.paused_reason


async def test_review_f3_a_value_of_an_unwatched_trade_is_not_republished(scn, monkeypatch):  # noqa: F811
    import datetime  # noqa: PLC0415
    w, client, now = await _published(scn, monkeypatch, _rupee_body("1"), unknown=False)
    assert (FIRST_ID, sl.RUPEE_LOSS_RULE) in await rule_readings.read(client, now)
    w._provider_for(w.monitors[0].feed_owner).health = background.DataHealth.STALE  # the feed goes stale
    later = now + datetime.timedelta(seconds=66)
    w._clock = lambda: later
    await w.cycle()
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    got = await rule_readings.read(client, later)
    assert (FIRST_ID, sl.RUPEE_LOSS_RULE) not in got, got
