"""Plan stop to alert ROW, with the worker as a SEPARATE OS process on a real PostgreSQL database (Lane Q3, 27 Nov 2026).

The PC's own run of 27 Nov (tree 206a9f0) lost alerts the in-memory chain test could see only in part. Here the chain is
the product's own: the plan saved through ``playbook_store.accept_plan``, the scenario worker as its own process
(``python -m ofo_app.background``, ``OFO_SCENARIO=PATH-nn``, ``APP_ENV=test``), the prices of a scripted path, and the
answer read back from ``public.adjustment_suggestions`` (kind, rule, the level, how many rows) and from
``public.paper_orders`` (nothing else is placed). Paths PATH-90 to PATH-96 (tests/fixtures/adjust_paths) are the
scripted tracks: one iron condor (PATH-10's legs), 1-minute frames from 11:40 on Fri 6 Nov 2026; the loss on the
"23350" frames is Rs 4,608 (entry at 11:20, credit Rs 2,450, max loss Rs 23,550). The worker's clock is the scenario's: it stands still
inside a frame, so a row that exists after a frame's wait was raised at THAT frame's check, and a row that only comes at
the next frame came at the next candle close.

Spec basis: ADR-330 (3), (44), (47); REQ-170 AC-5; REQ-115 AC-4. Cases (a) to (j) of the Q3 brief.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from decimal import Decimal

import _worker_chain as wc
import pytest

pytestmark = pytest.mark.real_preferences  # the true database read, not the conftest defaults

LOSS_STOP = {"loss_stop_rupees": "1000"}
RELOAD_SECONDS = 20  # the worker process rebuilds its monitors from the database about every 10 s


@pytest.fixture
async def chain_for(monkeypatch, tmp_path: pathlib.Path):
    made: list[tuple[wc.Chain, str, str]] = []

    async def make(path_id: str) -> wc.Chain:
        app_url, admin_url = await asyncio.to_thread(wc.make_database)  # the admin helper runs its own loop
        chain = wc.Chain(path_id, app_url, tmp_path)
        made.append((chain, app_url, admin_url))
        return chain
    yield make
    for chain, app_url, admin_url in made:
        await chain.close()
        await asyncio.to_thread(wc.drop_database, app_url, admin_url)


def only(rows: list[dict], rule: str, kind: str, level: str) -> None:
    """Exactly this one row: the rule, the kind and the level (the threshold the user typed)."""
    assert [(r["rule_id"], r["kind"]) for r in rows] == [(rule, kind)], rows
    assert rows[0]["threshold"] == Decimal(level), rows


async def nothing_else(c: wc.Chain, kinds: set[str]) -> None:
    rows = await c.plan_alerts()
    assert {r["kind"] for r in rows} <= kinds, ("another plan alert was raised", rows)
    assert await c.orders_count() == c.orders_at_start, "an order was placed: nothing but the alert may happen"


async def test_a_loss_stop_crossed_on_a_fresh_trade_raises_its_alert(chain_for, monkeypatch):
    """(a) A Rs 1,000 stop; the trade entered 11:20; at 11:42 the loss is Rs 4,608: the row is there at that check."""
    c = await chain_for("PATH-90")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards=LOSS_STOP)
    c.start_worker()
    await c.go_to(0)
    await c.go_to(1)
    assert await c.plan_alerts() == [], "no alert before the stop is crossed"
    await c.go_to(2)
    rows = await c.alert_at_once("plan_rupee_loss", next_frame=3)
    only(rows, "plan.rupee_loss", "plan_rupee_loss", "1000")
    await c.go_to(3)
    only(await c.alerts("plan_rupee_loss"), "plan.rupee_loss", "plan_rupee_loss", "1000")  # once, not once per tick
    await nothing_else(c, {"plan_rupee_loss"})


async def test_b_a_loss_stop_already_crossed_when_the_plan_is_saved_raises_its_alert(chain_for, monkeypatch):
    """(b) The trade sits at a loss of Rs 4,608 with a plan that has no stop; the Rs 1,000 stop is then typed and
    saved (real cases #207, #209: never alerted). The next check raises the row."""
    c = await chain_for("PATH-90")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards={})  # a plan with no stop
    c.start_worker()
    await c.go_to(0)
    await c.go_to(2)
    assert await c.plan_alerts() == []
    await c.type_plan(guards=LOSS_STOP)
    await asyncio.sleep(RELOAD_SECONDS)  # the worker reloads the saved plan (its rebuild) BEFORE the next prices
    await c.go_to(3)  # the next minute's prices: the first check with the saved plan
    rows = await c.alert_at_once("plan_rupee_loss", next_frame=4)
    only(rows, "plan.rupee_loss", "plan_rupee_loss", "1000")
    await nothing_else(c, {"plan_rupee_loss"})


async def test_c_a_loss_stop_crossed_at_entry_is_raised_after_the_five_minutes_never_swallowed(chain_for, monkeypatch):
    """(c) ADR-330 (47): the trade is entered at 11:40 with the loss already Rs 4,608 (PATH-96). The 5-minute period
    delays the alert; when it ends and the level is still crossed the alert is raised (11:46 is past 11:45)."""
    c = await chain_for("PATH-96")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards=LOSS_STOP)
    c.start_worker()
    await c.go_to(0)
    early = await c.alerts()  # observed, not asserted: the 5-minute period may hold it
    print("Q3-OBSERVED (c) rows at 11:40, entry minute:", [r["kind"] for r in early])
    await c.go_to(6)  # 11:46: six minutes after entry
    rows = await c.alert_at_once("plan_rupee_loss", next_frame=7)
    only(rows, "plan.rupee_loss", "plan_rupee_loss", "1000")
    await c.go_to(8)
    only(await c.alerts("plan_rupee_loss"), "plan.rupee_loss", "plan_rupee_loss", "1000")
    await nothing_else(c, {"plan_rupee_loss"})


async def test_d_the_daily_alert_cap_used_up_does_not_hold_the_plan_exit(chain_for, monkeypatch):
    """(d) Weekly style: the daily cap is 4. PATH-10 (spot sweeping up from 11:40) raises the playbook's own alerts;
    with the cap used, the Rs 9,000 stop crosses at frame 17 (loss Rs 9,782): it must still alert (real case #200)."""
    c = await chain_for("PATH-10")
    await c.seed(monkeypatch, plan=False, pin="weekly")
    await c.type_plan(guards={"loss_stop_rupees": "9000"}, keep=None)
    c.start_worker()
    for k in range(0, 17):
        await c.go_to(k, settle=5)
    others = [r for r in await c.alerts() if r["kind"] != "plan_rupee_loss"]
    assert len(others) >= 4, ("the cap of 4 is not used up before the crossing", [r["kind"] for r in others])
    assert await c.alerts("plan_rupee_loss") == [], "not crossed yet"
    await c.go_to(17)
    rows = await c.alert_at_once("plan_rupee_loss", next_frame=18)
    only(rows, "plan.rupee_loss", "plan_rupee_loss", "9000")
    assert await c.orders_count() == c.orders_at_start


async def test_e_a_rupee_loss_stop_that_dips_back_before_the_candle_close_still_alerts_at_once(chain_for, monkeypatch):
    """(e) PATH-91: the loss is Rs 4,608 at 11:42 and gone at 11:43. The alert is there at the 11:42 check and stays."""
    c = await chain_for("PATH-91")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards=LOSS_STOP)
    c.start_worker()
    await c.go_to(0)
    await c.go_to(2)
    rows = await c.alert_at_once("plan_rupee_loss", next_frame=3)
    only(rows, "plan.rupee_loss", "plan_rupee_loss", "1000")
    await c.go_to(3)  # the loss is gone: the alert is actionable (ADR-330 (3)) and does not lapse
    await c.go_to(4)
    rows = await c.alerts("plan_rupee_loss")
    only(rows, "plan.rupee_loss", "plan_rupee_loss", "1000")
    assert rows[0]["outcome"] == "open", rows
    await nothing_else(c, {"plan_rupee_loss"})


async def test_f_a_profit_target_raises_its_alert(chain_for, monkeypatch):
    """(f) Rs 1,500 target; the profit is about Rs 20 at ATM IV 0.10 and about Rs 2,100 from 11:42, IV 0.06 (PATH-92)."""
    c = await chain_for("PATH-92")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards={"profit_target_rupees": "1500"})
    c.start_worker()
    await c.go_to(0)
    await c.go_to(1)
    assert await c.plan_alerts() == []
    await c.go_to(2)
    rows = await c.alert_at_once("plan_rupee_profit", next_frame=3)
    only(rows, "plan.rupee_profit", "plan_rupee_profit", "1500")
    await nothing_else(c, {"plan_rupee_profit"})


async def test_g_a_time_exit_raises_its_alert_at_its_time(chain_for, monkeypatch):
    """(g) Time exit 11:43 on Fri 6 Nov (flat prices, PATH-93): nothing at 11:42, the alert at the 11:43 check (real
    case 27 Nov: set for 11:03, came at 11:05, the candle close)."""
    c = await chain_for("PATH-93")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards={}, time_exit="11:43", keep=("T-10b",))
    c.start_worker()
    await c.go_to(0)
    await c.go_to(2)
    assert await c.plan_alerts() == [], "before the time: nothing"
    await c.go_to(3)
    rows = await c.alert_at_once("plan_time_exit", next_frame=4)
    assert [r["kind"] for r in rows] == ["plan_time_exit"], rows
    await nothing_else(c, {"plan_time_exit"})


async def test_h_a_5_percent_loss_stop_saved_while_the_loss_is_10_percent_alerts_and_is_held_14_minutes(
        chain_for, monkeypatch):
    """(h) The PC's T1-06 of 27 Nov 13:28 (a stop already crossed when the plan is accepted): rule "Loss reaches 5 % of
    max loss" typed and saved while the loss is about 10 % (about Rs 2,400 of the condor's Rs 23,550 max loss), PATH-94
    from 11:41. The alert is there at the first check after the save and is still one row 14 minutes later."""
    c = await chain_for("PATH-94")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards={}, keep=None)  # a plan with no stop, every system rule on
    c.start_worker()
    await c.go_to(0)
    await c.go_to(1)  # 11:41: the loss is already about 10 %
    assert await c.plan_alerts() == []
    await c.type_plan(guards={}, t06_percent="5", keep=None)  # the PC's plan: the whole system rule list, 5 % typed
    await asyncio.sleep(RELOAD_SECONDS)
    await c.go_to(2)
    rows = [r for r in await c.alert_at_once("plan_loss_stop", next_frame=3) if r["rule_id"] == "T-06"]
    assert len(rows) == 1, rows
    assert rows[0]["threshold"] == Decimal("5"), rows
    await c.go_to(8)
    await c.go_to(15)  # 14 minutes after the loss began
    rows = [r for r in await c.alerts("plan_loss_stop") if r["rule_id"] == "T-06"]
    assert len(rows) == 1 and rows[0]["outcome"] == "open", rows
    assert [r["kind"] for r in await c.plan_alerts()] == ["plan_loss_stop"], ("one plan alert only", await c.plan_alerts())
    assert await c.orders_count() == c.orders_at_start


async def test_i_a_trade_that_cannot_be_priced_claims_no_trigger_and_is_paused(chain_for, monkeypatch):
    """(i) REQ-115 AC-4 / ADR-330 (44): from 11:42 the prices are 600 s old (PATH-95; the loss would be Rs 4,608).
    No alert row claims the stop; the worker's own minute line reads the strategy's prices as not fresh (its
    "Monitoring paused" state is held in the worker process only: see RESULTS, For lane J2)."""
    c = await chain_for("PATH-95")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards=LOSS_STOP)
    c.start_worker()
    for k in (0, 1, 2, 3, 4, 5):
        await c.go_to(k)
    assert await c.plan_alerts() == [], ("an alert claimed a trigger on prices that cannot be used", await c.alerts())
    assert await c.orders_count() == c.orders_at_start
    reads = re.findall(r"minute 11:4[2-5] [^\n]* reads (\{[^}]*\})", c.log())
    assert reads, c.log()[-1500:]
    assert all("FRESH" not in r for r in reads[-2:]), ("the strategy's prices were read as fresh", reads)
    print("Q3-OBSERVED (i) reads of the stale minutes:", reads)


async def test_j_exiting_the_last_leg_closes_the_trades_open_alerts_as_closed_by_system(chain_for, monkeypatch):
    """(j) ADR-330 (3): an open plan alert; every leg is exited; the worker closes the alert, answer
    ``closed_by_system``, and nothing but the exit orders the test placed is on the trade."""
    from decimal import Decimal as D  # noqa: PLC0415

    from ofo_app import paper_store  # noqa: PLC0415
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415
    c = await chain_for("PATH-90")
    await c.seed(monkeypatch, plan=False)
    await c.type_plan(guards=LOSS_STOP)
    c.start_worker()
    await c.go_to(0)
    await c.go_to(2)
    rows = await c.alert_at_once("plan_rupee_loss", next_frame=3)
    assert rows[0]["outcome"] == "open", rows
    legs = await c.legs()
    exits = [paper_store.NewOrder(cid, "SELL" if side == "BUY" else "BUY", qty, D(str(price)), "exit",
                                  wc.scenario_time(c.path_id, 3)) for cid, side, qty, price in legs]
    async with get_sessionmaker()() as db:  # what the Exit button's last leg stores (no real order, paper only)
        await paper_store.place(db, "owner", c.sid, exits)
        await db.commit()
    await c.go_to(4, settle=12)
    await c.go_to(5, settle=12)
    rows = await c.alerts("plan_rupee_loss")
    assert len(rows) == 1, rows
    assert rows[0]["outcome"] != "open", ("the alert is still open", rows)
    assert rows[0]["answer"] == "closed_by_system", rows
    assert await c.orders_count() == c.orders_at_start + len(exits), "only the test's exit orders are on the trade"
