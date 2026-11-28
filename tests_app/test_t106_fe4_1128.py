"""Lane FE4 (28 Nov 2026), issue 876 / check T1-06 of 27 Nov: a paper trade sat about 10 percent in loss against a 5
percent rule for 14 minutes and no alert came. Stored facts from the PC (words and counts only): strategy 207; plan
saved 13:13:33 and approved; 27 triggers, 14 on; NO alert style pin; from 13:14 to 13:36 0 suggestion rows and 0 gate
rows; the worker checked it 2 to 3 times a minute; 0 "check skipped" lines.

This is that shape, the worker a SEPARATE OS process on a real PostgreSQL database (``_worker_chain``): the approved
plan (the system rule list, "Loss reaches 5 % of max loss") is saved ONE minute (one frame) before the loss begins; the
trigger list is 27 with 13 on (the PC stored 14); no style pin; the loss is twice the rule's level (PATH-94: about 10 %
from 11:41) and is held 15 minutes. Spec basis: REQ-115, ADR-016 to ADR-019 (a missed alert is never silent), ADR-330
(44), (47).
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from test_plan_stop_worker_chain import RELOAD_SECONDS, chain_for  # noqa: F401 - fixture by name


async def test_t106_an_approved_plan_13_of_27_triggers_no_pin_a_loss_twice_the_rule_for_15_minutes_alerts(
        chain_for, monkeypatch):  # noqa: F811
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False, pin=None)  # no alert style pin
    await c.type_plan(guards={}, t06_percent="5", keep=None)  # approved and saved one minute before the loss
    from ofo_app import playbook_store  # noqa: PLC0415
    async with c.engine.begin() as conn:
        plan = await playbook_store.active_for(conn, "owner", "ic")
    triggers = plan.body["triggers"]
    on = [k for k, v in triggers.items() if isinstance(v, dict) and v.get("on")]
    print("TRIGGERS", len(triggers), "ON", len(on))
    # the system list here has 27 triggers and 13 on (the PC stored 14 on: one more trigger set on by hand; which one is
    # not in the stored facts). The list is pinned so a change of the shipped list is seen.
    assert (len(triggers), len(on)) == (27, 13), (len(triggers), len(on), sorted(on))
    c.start_worker()
    await c.go_to(0)  # 11:40, one minute before the loss
    assert await c.plan_alerts() == []
    await asyncio.sleep(RELOAD_SECONDS)
    await c.go_to(1)  # 11:41: the loss is about 10 %
    rows = [r for r in await c.alert_at_once("plan_loss_stop", next_frame=2) if r["rule_id"] == "T-06"]
    print("ROWS", rows)
    assert len(rows) == 1 and rows[0]["threshold"] == Decimal("5"), rows
    await c.go_to(8)
    await c.go_to(16)  # 15 minutes after the loss began
    rows = [r for r in await c.alerts("plan_loss_stop") if r["rule_id"] == "T-06"]
    assert len(rows) == 1 and rows[0]["outcome"] == "open", rows
    log = c.log()
    assert "has no alert preset" not in log and "no_preset" not in log, log[-1500:]
    assert await c.orders_count() == c.orders_at_start


async def test_t106_b_the_pcs_per_stage_row_50_5_40_alerts_at_the_middle_stage_with_no_pin(chain_for, monkeypatch):  # noqa: F811
    """Review F1: the first test types 5 in every stage, so a wrong stage or row would still read 5. The PC's stored
    row was weekly [50, 5, 40]: 5 only in the middle stage. A wrong stage compares against 50 and stays silent."""
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False, pin=None)
    await c.type_plan(guards={}, t06_stages=["50", "5", "40"], keep=None)
    c.start_worker()
    await c.go_to(0)
    await asyncio.sleep(RELOAD_SECONDS)
    await c.go_to(1)
    rows = [r for r in await c.alert_at_once("plan_loss_stop", next_frame=2) if r["rule_id"] == "T-06"]
    print("ROWS", rows)
    assert len(rows) == 1 and rows[0]["threshold"] == Decimal("5"), rows


async def test_t106_c_the_pcs_rupee_guard_of_80_alerts_with_no_pin(chain_for, monkeypatch):  # noqa: F811
    """Review F2: with the PC's real guard (loss_stop_rupees 80) and row, a plan alert comes (the rupee row); the
    harness shows an alert on the PC's plan shape, so the PC's silence is not explained by the shape alone."""
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False, pin=None)
    await c.type_plan(guards={"loss_stop_rupees": "80"}, t06_stages=["50", "5", "40"], keep=None)
    c.start_worker()
    await c.go_to(0)
    await asyncio.sleep(RELOAD_SECONDS)
    await c.go_to(1)
    await c.go_to(2)
    rows = await c.plan_alerts()
    print("PLAN ALERTS", rows)
    assert rows, "no plan alert at all with the PC's guards"


async def test_t106_d_ra_the_pcs_corrected_shape_both_loss_guards_13_on_seen_clear_loss_beyond_both_held_15_min(
        chain_for, monkeypatch):  # noqa: F811
    """Lane RA (coordinator, 16:25 IST, issue 876 corrected facts): 27 triggers, 13 on; loss rules on: T-06 (percent of
    max loss, 5) and the rupee loss stop (``plan.rupee_loss``, Rs 80; the harness's PATH-94 loss is beyond both); the
    rules read clear before the loss began (the loss starts one frame after the plan is saved: ``seen_clear``); the loss
    is held 15 minutes; the worker is a separate OS process. Reproduced or not: the assertions say it. Every loss row
    that exists is ONE row per rule (no duplicate, nothing placed)."""
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False, pin=None)
    await c.type_plan(guards={"loss_stop_rupees": "80"}, t06_percent="5", keep=None)
    c.start_worker()
    await c.go_to(0)  # 11:40: the rules read clear
    assert await c.plan_alerts() == []
    await asyncio.sleep(RELOAD_SECONDS)
    await c.go_to(1)  # 11:41: the loss is beyond both levels
    await c.go_to(2)
    first = await c.plan_alerts()
    print("PLAN ALERTS AT ONCE", [(r["rule_id"], r["kind"]) for r in first])
    assert first, "REPRODUCED: no plan alert at all with both loss guards and the loss beyond both"
    await c.go_to(8)
    await c.go_to(16)  # 15 minutes after the loss began
    rows = [r for r in await c.plan_alerts() if r["outcome"] == "open"]
    rules = sorted(r["rule_id"] for r in rows)
    print("OPEN ROWS", rules)
    assert len(rules) == len(set(rules)), rules  # one row per rule
    assert rules, "REPRODUCED: the alert did not stay open"
    assert await c.orders_count() == c.orders_at_start
    assert "loss rule evaluated, no alert" not in c.log() or "already_true" not in c.log() or rows, c.log()[-800:]
