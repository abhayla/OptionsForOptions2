"""I-59 (test plan 28 Nov 2026): two alerts fired at a plan's time exit and neither said it was the time exit. With
the plan's whole system rule list on and a time exit typed, the check at that time raises ONE exit alert, of kind
``plan_time_exit``, and its text says it is the time exit. Chain as ``test_plan_stop_worker_chain.py`` (g): the worker
as its own process on PATH-93 (flat prices), time exit 11:43 on Fri 6 Nov 2026.
Spec basis: ADR-330 (3) (one open alert per rule), (7) (time exit), (47) (a plan exit is its own alert).
"""
from __future__ import annotations

import pytest
from test_adjustment_opportunities import _call
from test_plan_stop_worker_chain import chain_for  # noqa: F401 - the fixture is used by name

pytestmark = pytest.mark.real_preferences
OK = 200


async def test_the_time_exit_raises_one_alert_and_its_words_say_time_exit(chain_for, monkeypatch):  # noqa: F811
    c = await chain_for("PATH-93")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards={}, time_exit="11:43", keep=None)  # the whole system rule list on, as a user's plan is
    c.start_worker()
    await c.go_to(0)
    await c.go_to(2)
    before = {r["rule_id"] for r in await c.alerts()}
    await c.go_to(3)  # 11:43: the time exit
    await c.alert_at_once("plan_time_exit", next_frame=4)
    rows = [r for r in await c.alerts() if r["rule_id"] not in before and r["outcome"] == "open"]
    print("ROWS", [(r["rule_id"], r["kind"], r["threshold"], r["value"]) for r in rows])
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK
    mine = [a for a in active["alerts"] if a["strategy_id"] == c.sid and a["kind"] != "situation"]
    print("ACTIVE", [(a["kind"], a["text"]) for a in mine])
    exits = [r for r in rows if r["kind"] == "plan_time_exit"]
    assert len(exits) == 1, rows
    assert [r["kind"] for r in rows] == ["plan_time_exit"], f"another alert fired with the time exit: {rows}"
    texts = [a["text"] for a in mine if a["kind"] == "plan_time_exit"]
    assert len(texts) == 1 and "time exit" in texts[0].lower(), texts
