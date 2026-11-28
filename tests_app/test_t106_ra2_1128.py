"""Lane RA2 item 2 (issue 876, check T1-06 of 27 Nov; Lane FE3 and FE4 did NOT reproduce it): the PC's stored facts,
words and counts: strategy 207; plan saved 13:13:33 and approved; 27 triggers, 13 on; loss rules on T-06 (percent of
max loss) and T-14; guards: a rupee loss stop (plan.rupee_loss) and a percent-of-max-loss stop line, whichever first;
rule state held_at_entry false, seen_clear true; between 13:14 and 13:36 0 suggestion rows and 0 gate rows; the worker
checked it 2 to 3 times a minute; its log has no per-strategy per-rule line; the worker restarted during the window.
New in this shape against FE4's test: the guards together, the T-14 rule, held_at_entry false with seen_clear true, and
the restart. The worker is a SEPARATE OS process (``_worker_chain``) on a real PostgreSQL database.

Test 1 builds that shape and reports whether the alert comes (reproduced or not). Test 2 pins the worker log line this
lane adds: whenever a loss rule is true and nothing is alerted, the worker says which strategy, which rule and why
(never a price or a figure of the feed), so the next silence is explained by the log. Spec basis: REQ-115, ADR-016 to
ADR-019 (a missed alert is never silent), ADR-330 (44), (47).
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from test_plan_stop_worker_chain import RELOAD_SECONDS, chain_for  # noqa: F401 - fixture by name

SILENT = "loss rule true, nothing alerted"


async def test_t106_the_pcs_207_shape_with_both_guards_t14_and_a_worker_restart_alerts(chain_for, monkeypatch):  # noqa: F811
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False, pin=None)
    await c.type_plan(guards={"loss_stop_rupees": "80"}, t06_stages=["50", "5", "40"], keep=None)
    c.start_worker()
    await c.go_to(0)  # one minute before the loss: the rules read clear (seen_clear is stored true)
    await asyncio.sleep(RELOAD_SECONDS)
    assert await c.plan_alerts() == []
    c.stop_worker()  # the worker restarts during the window
    c.start_worker()
    await c.go_to(1)  # the loss begins
    rows = await c.plan_alerts()
    for _ in range(3):
        if rows:
            break
        await c.go_to(c.frame + 1)
        rows = await c.plan_alerts()
    print("REPRODUCED" if not rows else "NOT REPRODUCED", [(r["rule_id"], r["kind"], r["threshold"]) for r in rows])
    assert rows, "no plan alert after the restart with the PC's shape\n" + c.log()[-1500:]
    assert {r["rule_id"] for r in rows} & {"T-06", "plan.rupee_loss"}, rows


async def test_t106_an_open_alert_with_the_loss_still_true_says_so_in_the_log(chain_for, monkeypatch):  # noqa: F811
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False, pin=None)
    await c.type_plan(guards={}, t06_percent="5", keep=None)
    c.start_worker()
    await c.go_to(0)
    await asyncio.sleep(RELOAD_SECONDS)
    await c.go_to(1)
    rows = [r for r in await c.alert_at_once("plan_loss_stop", next_frame=2) if r["rule_id"] == "T-06"]
    assert len(rows) == 1 and rows[0]["threshold"] == Decimal("5"), rows
    await c.go_to(3)  # the loss goes on past the line; the alert is open, so nothing new is raised
    await c.go_to(4)
    log = c.log()
    line = next((ln for ln in log.splitlines() if SILENT in ln and f"strategy {c.sid}" in ln and "T-06" in ln), None)
    print("LOG LINE", line)
    assert line is not None and "alert_already_open" in line, log[-2000:]
    assert log.count(f"strategy {c.sid} {SILENT}: T-06 alert_already_open") == 1, "told once per change, not per check"
    for word in ("price", "ltp", "Decimal", "24"):  # no price and no figure of the feed in the line
        assert word not in line.split(SILENT, 1)[1], line
