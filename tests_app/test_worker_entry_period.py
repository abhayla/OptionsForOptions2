"""The worker hands the strategy's entry time to the gate: a plan exit crossed at entry waits 5 minutes, then alerts.

Case A-G #207 (27 Nov 2026): accepted 13:13:33, loss past its Rs 80 stop from 13:14. Spec basis: ADR-330 (47) ("the
5-minute period after entry delays an alert whose level is already crossed at entry and never swallows it"),
REQ-170 AC-5.
"""
from __future__ import annotations

import asyncio
import collections
import datetime
from decimal import Decimal
from types import SimpleNamespace

from ofo.adjustment import alert_gate
from ofo.adjustment import stop_lines as sl
from ofo_app import background

IST = alert_gate.IST
ENTERED = datetime.datetime(2026, 11, 27, 13, 13, 33, tzinfo=IST)


def _at(hhmm: str) -> datetime.datetime:
    return datetime.datetime.combine(ENTERED.date(), datetime.time.fromisoformat(hhmm), tzinfo=IST)


def _worker():
    w = background.Worker.__new__(background.Worker)
    w._gate, w._gate_body, w._paused_at, w._gate_events = {}, {}, {}, {}
    w._write_wake = SimpleNamespace(set=lambda: None)
    w._restored = lambda sid, now, readings: alert_gate.initial_state()
    return w


def _step(w, watched, hhmm: str) -> list:
    spec = alert_gate.RuleSpec(sl.RUPEE_LOSS_RULE, "ge", (Decimal(80),))
    asyncio.run(w._gate_step(watched, _at(hhmm), alert_gate.WEEKLY, {sl.RUPEE_LOSS_RULE: (spec, Decimal(199))}))
    queue = w._gate_events.get(207, collections.deque())
    return [e for batch in queue for e in batch.events]


def test_207_the_worker_delays_the_stop_five_minutes_after_entry_then_raises_it():
    w = _worker()
    watched = SimpleNamespace(strategy_id=207, body={}, tracked=SimpleNamespace(entered_at=ENTERED))
    for hhmm in ("13:14:44", "13:15:44", "13:17:44"):
        assert _step(w, watched, hhmm) == []
    events = _step(w, watched, "13:18:44")
    assert [(type(e).__name__, e.at) for e in events] == [("Opened", _at("13:18:44"))]


def test_an_unknown_entry_time_holds_nothing():
    w = _worker()
    watched = SimpleNamespace(strategy_id=207, body={}, tracked=SimpleNamespace(entered_at=None))
    assert [e.at for e in _step(w, watched, "13:14:44")] == [_at("13:14:44")]
