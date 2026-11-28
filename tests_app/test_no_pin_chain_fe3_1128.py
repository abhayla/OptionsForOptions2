"""Lane FE3 (28 Nov 2026), coordinator addition (issue 876, the PC's T1-06 of 27 Nov): a paper trade sat about 10
percent in loss against a 5 percent rule for 14 minutes and no alert came. The PC's stored rows: strategy 207, plan
saved and approved at 13:13:33, 27 triggers with 14 on, NO alert style pin, 0 suggestion rows and 0 gate rows for
22 minutes, 0 "check skipped" lines, the worker checking 2 to 3 times a minute.

This is that shape with the worker as a SEPARATE OS process on a real PostgreSQL database (the chain of
``test_plan_stop_worker_chain``): the plan (the whole system rule list, "Loss reaches 5 % of max loss") is accepted
BEFORE the loss begins, the trade has no style pin (automatic style), and the loss is about twice the rule's level
(PATH-94: about 10 percent from 11:41) and stays for 14 minutes.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from test_plan_stop_worker_chain import RELOAD_SECONDS, chain_for  # noqa: F401 - fixture by name


async def test_m_no_style_pin_a_plan_saved_before_the_loss_a_loss_of_twice_the_rule_alerts_and_stays_one_row(
        chain_for, monkeypatch):  # noqa: F811
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False, pin=None)  # no alert style pin: the style is the automatic one
    await c.type_plan(guards={}, t06_percent="5", keep=None)  # approved and saved before the loss
    c.start_worker()
    await c.go_to(0)
    assert await c.plan_alerts() == []
    await asyncio.sleep(RELOAD_SECONDS)  # the plan is in the worker's list (the re-read is every 10 s)
    await c.go_to(1)  # 11:41: the loss is about 10 % (twice the rule's 5 %)
    rows = [r for r in await c.alert_at_once("plan_loss_stop", next_frame=2) if r["rule_id"] == "T-06"]
    print("ROWS", rows)
    assert len(rows) == 1 and rows[0]["threshold"] == Decimal("5"), rows
    await c.go_to(8)
    await c.go_to(15)  # 14 minutes after the loss began
    rows = [r for r in await c.alerts("plan_loss_stop") if r["rule_id"] == "T-06"]
    assert len(rows) == 1 and rows[0]["outcome"] == "open", rows
    log = c.log()
    assert "has no alert preset" not in log, "the style step refused the strategy: no rule was evaluated"
    assert await c.orders_count() == c.orders_at_start
