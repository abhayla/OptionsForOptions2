# ruff: noqa: F811
"""Lane B1b (coordinator, issue 876, the two cases nobody had tried; Lane RA2's list):
(a) the loss arrives within five minutes of entry: Lane RA's tests (c) and (l) in test_plan_stop_worker_chain.py already
    run it (PATH-96 enters at 11:40 with the loss already past the stops; the alert comes at 11:46, after the entry
    period): green on this head, so (a) is NOT reproduced.
(b) the worker restarts AFTER the loss has begun (rule state ``seen_clear`` and ``held_at_entry`` across a
    restart): the test below. Real case shape: the PC's #207 (plan accepted 13:13:33, one second after the entry;
    rupee stop 80 and the
    per-stage T-06 row [50, 5, 40], the whole rule list on), the worker (a separate OS process, real PostgreSQL) stopped
    and started while the loss is already past both levels and inside the entry period."""
from __future__ import annotations

from test_plan_stop_worker_chain import chain_for, only  # noqa: F401 - fixture by name


async def test_t106_b_a_restart_after_the_loss_began_still_raises_the_alert_when_the_entry_period_ends(
        chain_for, monkeypatch):
    c = await chain_for("PATH-96")
    await c.seed(monkeypatch, plan=False, pin="weekly")
    await c.type_plan(guards={"loss_stop_rupees": "80"}, t06_stages=["50", "5", "40"], keep=None)
    c.start_worker()
    await c.go_to(0)  # 11:40: entered with the loss already past both levels (inside the entry period)
    await c.go_to(2)  # the loss has begun and goes on
    c.stop_worker()  # the restart AFTER the loss began
    c.start_worker()
    await c.go_to(3)
    await c.go_to(6)  # 11:46: past the 5-minute entry period
    rows = await c.alert_at_once("plan_rupee_loss", next_frame=7)
    print("(b) NOT REPRODUCED" if rows else "(b) REPRODUCED", [(r["rule_id"], r["kind"]) for r in rows])
    assert rows, "no plan alert after a restart that came after the loss began\n" + c.log()[-1500:]
    only(rows, "plan.rupee_loss", "plan_rupee_loss", "80")
