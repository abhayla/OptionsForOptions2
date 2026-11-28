"""Lane FE2 (28 Nov 2026), item 3 (issue #862, Lane Q3's note): a stop typed and crossed inside the same minute is no
longer checked with the old plan first. Spec basis: ADR-330 (44), (47) (a saved stop already crossed alerts at once).

Real case (Lane Q3, case (b)): the loss was Rs 4,608, the plan had no stop, a Rs 1,000 stop was saved; the worker's
re-read (every 10 s, Lane J3) puts the new plan in its list and the FIRST check with it must run at once, whatever the
style's interval (weekly 30 s, monthly 120 s) and the unchanged price say.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from ofo.adjustment import stop_lines as sl
from ofo_app import calc_speeds
from test_background_cycle import (
    DEFAULTS,
    FIRST_ID,
    Calls,
    FakeGate,
    Prov,
    _watched,
    _worker,
    scn,  # noqa: F401 - the module fixture
)
from test_worker_j3 import _rupee_body

CHECKED_TWICE = 2


def _rupee_events(gate: FakeGate) -> list:
    return [e for _s, e in gate.events if sl.RUPEE_LOSS_RULE in repr(e)]


async def test_a_stop_typed_and_crossed_in_the_same_minute_alerts_at_the_next_cycle_after_the_reread(scn):  # noqa: F811
    prov, now, calls, gate = Prov(scn), [scn.clock_at], Calls(), FakeGate()
    long = {**DEFAULTS, **{k: Decimal(600) for k in calc_speeds.BACKGROUND_KEYS.values()}}  # every interval held long
    watched = _watched(scn)  # the plan has no rupee stop
    w = _worker(prov, watched, now, calls, gate_store=gate, settings=lambda _at: long)
    await w.cycle()
    assert len(calls.states) == 1 and _rupee_events(gate) == [], "the old plan: loss crossed, nothing to raise"
    now[0] += datetime.timedelta(seconds=2)  # the same minute
    watched[0] = dataclasses.replace(watched[0], body=_rupee_body("1"))  # the user saves a stop below the loss
    await w.rebuild()  # the worker's re-read (every REBUILD_SECONDS) picks the saved plan up
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()
    print("STATES", len(calls.states), "EVENTS", len(_rupee_events(gate)), "STATUS", w.status.get(FIRST_ID))
    assert len(calls.states) == CHECKED_TWICE, "the first check with the new plan runs at once"
    assert len(_rupee_events(gate)) == 1, "exactly one alert for the stop typed already crossed"


async def test_the_same_plan_is_still_held_inside_the_interval(scn):  # noqa: F811
    """Control: nothing changed, so the interval holds the second check (the lift is not a general bypass)."""
    prov, now, calls, gate = Prov(scn), [scn.clock_at], Calls(), FakeGate()
    long = {**DEFAULTS, **{k: Decimal(600) for k in calc_speeds.BACKGROUND_KEYS.values()}}
    watched = _watched(scn)
    w = _worker(prov, watched, now, calls, gate_store=gate, settings=lambda _at: long)
    await w.cycle()
    now[0] += datetime.timedelta(seconds=2)
    await w.rebuild()
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()
    assert len(calls.states) == 1
