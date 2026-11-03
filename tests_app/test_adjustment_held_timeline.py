"""GC-IC1 step 10 fix, REQ-170 AC-4: a crossing the alert gate HOLDS (daily limit, quiet time) is shown on the
Adjustment opportunities timeline as the catalogue's "held: daily limit" / "held: quiet time" with its time, never
dropped, and never looks like an opened opportunity (no Compare link, no Dismiss, not counted as a record).

The Held events come from the real gate (``alert_gate.step`` with a cap of one record, and a close inside the quiet
time); each is stored the way the worker stores it (``playbook_store.record_held``, background.py) and read through
the real route GET /api/adjustment-opportunities. Every test runs in a rolled-back transaction.
"""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from ofo.adjustment import alert_gate as ag
from ofo_app import playbook_store as pb
from ofo_app.db import get_db
from ofo_app.routes.broker import current_user_ref
from test_alert_gate_storage import _strategy, admin, db  # noqa: F401 - fixtures

D = Decimal
OK = 200
DAY = datetime.date(2026, 11, 4)
SPEC = ag.RuleSpec("T-07", "ge", (D("80"),))
SPEC_B = ag.RuleSpec("T-08", "ge", (D("80"),))


def _at(h: int, m: int) -> datetime.datetime:
    return datetime.datetime.combine(DAY, datetime.time(h, m), tzinfo=ag.IST)


def _held_events(events):
    return [e for e in events if isinstance(e, ag.Held)]


async def _inbox(db_conn, user: str) -> dict:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    app = create_app()
    app.dependency_overrides[current_user_ref] = lambda: user
    app.dependency_overrides[get_db] = lambda: db_conn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/adjustment-opportunities")
    assert r.status_code == OK, r.text
    return r.json()


async def _store(db_conn, user, sid, events):
    for e in _held_events(events):
        await pb.record_held(db_conn, user, sid, e.rule_id, trigger_id=e.rule_id, stage="Middle", value=D("85"),
                             threshold=D("80"), reason=e.reason)


async def test_daily_limit_hold_is_on_the_timeline(db):  # noqa: F811
    user, sid = await _strategy(db)
    preset = replace(ag.INTRADAY, daily_cap=1)
    state = ag.initial_state()
    readings = {"T-07": (SPEC, D("85")), "T-08": (SPEC_B, D("85"))}
    state, _ = ag.step(state, now=_at(10, 0), preset=preset, readings=readings)
    state, events = ag.step(state, now=_at(10, 1), preset=preset, readings={})
    held = _held_events(events)
    assert [e.reason for e in held] == ["daily_limit"]  # the gate held the second crossing
    await _store(db, user, sid, events)
    body = await _inbox(db, user)
    assert [h["reason"] for h in body["held"]] == ["daily_limit"]
    h = body["held"][0]
    assert h["text"] == "held: daily limit"
    assert h["strategy_id"] == sid
    assert h["rule_id"] == held[0].rule_id
    assert h["held_at"]
    assert set(h) >= {"id", "strategy_name", "text", "reason", "held_at", "rule_id"}
    assert "can_act" not in h and "has_open" not in h  # never an opened opportunity: no Compare, no Dismiss
    assert body["groups"] == [] and all(c["count"] == 0 for c in body["counts"])  # not counted as a record


async def test_quiet_time_hold_is_on_the_timeline(db):  # noqa: F811
    user, sid = await _strategy(db)
    state, _ = ag.step(ag.initial_state(), now=_at(9, 16), preset=ag.INTRADAY, readings={"T-07": (SPEC, D("85"))})
    state, events = ag.step(state, now=_at(9, 17), preset=ag.INTRADAY, readings={})
    assert [e.reason for e in _held_events(events)] == ["quiet_time"]
    await _store(db, user, sid, events)
    body = await _inbox(db, user)
    assert [(h["reason"], h["text"]) for h in body["held"]] == [("quiet_time", "held: quiet time")]


async def test_held_of_another_user_is_not_shown(db):  # noqa: F811
    user, sid = await _strategy(db)
    await pb.record_held(db, user, sid, "T-07", trigger_id="T-07", stage=None, value=D("85"), threshold=D("80"),
                         reason="daily_limit")
    assert (await _inbox(db, "someone-else"))["held"] == []
    assert len((await _inbox(db, user))["held"]) == 1
