"""I-59 (test plan 28 Nov 2026): two alerts fired at a plan's time exit and neither said it was the time exit. With
the plan's whole system rule list on and a time exit typed, the check at that time raises ONE exit alert, of kind
``plan_time_exit``, and its text says it is the time exit. Chain as ``test_plan_stop_worker_chain.py`` (g): the worker
as its own process on PATH-93 (flat prices), time exit 11:43 on Fri 6 Nov 2026.
Spec basis: ADR-330 (3) (one open alert per rule), (7) (time exit), (47) (a plan exit is its own alert).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from test_adjustment_opportunities import _call
from test_plan_stop_worker_chain import chain_for  # noqa: F401 - the fixture is used by name

pytestmark = pytest.mark.real_preferences
OK = 200


LAST_FRAME = 9  # PATH-93 has ten frames, one a minute from 11:40; the time exit is 11:43 (frame 3)


async def _all(c) -> list[dict]:
    """Every alert row of the strategy with its id (the harness's ``alerts()`` does not select it)."""
    sql = text("SELECT id, rule_id, kind FROM public.adjustment_suggestions WHERE strategy_id = :s ORDER BY id")
    async with c.engine.connect() as conn:
        return [dict(r) for r in (await conn.execute(sql, {"s": c.sid})).mappings().all()]


async def _ids(c) -> set[int]:
    return {r["id"] for r in await _all(c)}


async def test_the_time_exit_raises_one_alert_and_its_words_say_time_exit(chain_for, monkeypatch):  # noqa: F811
    c = await chain_for("PATH-93")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards={}, time_exit="11:43", keep=None)  # the whole system rule list on, as a user's plan is
    c.start_worker()
    await c.go_to(0)
    await c.go_to(2)
    known = await _ids(c)  # whatever the plan's other rules raised before the time: not the time exit's
    assert [r for r in await c.plan_alerts() if r["kind"] == "plan_time_exit"] == [], "before the time: no time exit"
    await c.go_to(3)  # 11:43: the time exit
    await c.alert_at_once("plan_time_exit", next_frame=4)
    exits = [r for r in await _all(c) if r["id"] not in known]
    assert [r["kind"] for r in exits] == ["plan_time_exit"], f"another alert fired with the time exit: {exits}"
    exit_id = exits[0]["id"]
    for frame in range(4, LAST_FRAME + 1):  # every later candle close: still ONE row, never a second alert
        await c.go_to(frame)
        later = [r for r in await _all(c) if r["id"] not in known]
        assert [(r["id"], r["kind"]) for r in later] == [(exit_id, "plan_time_exit")], (frame, later)
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK
    texts = [a["text"] for a in active["alerts"] if a["id"] == exit_id]
    assert len(texts) == 1 and "time exit" in texts[0].lower(), texts
    assert await c.orders_count() == c.orders_at_start  # the alert exits nothing
