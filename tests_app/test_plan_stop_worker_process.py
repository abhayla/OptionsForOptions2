"""Plan stop to alert with the worker as a SEPARATE OS process on a real database (Lane Q2, leftover 3 of the gap-4
file).

The product already starts the scenario worker as its own process: ``python -m ofo_app.background`` with
OFO_SCENARIO and
APP_ENV=test (``background._serve_scenario``): the scenario's fed provider (recorded prices), the scenario's own
clock (a
market minute, so the worker does not skip the check), the real gate and the real store. This test seeds ADJ-01
through the
app's own stores, types the plan's rupee stop, starts that process, and reads the stored alert rows.
Spec basis: REQ-170 AC-5, ADR-330 (5), (47), ADR-267 amendment 2.
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import time

import pytest
from ofo_app import playbook_store
from sqlalchemy import text
from test_adjustment_check import _seeded, app_db_url  # noqa: F401 - the fixture of the check tests

WORKER_SECONDS = 25  # how long the worker process is left to check (its first cycle is within seconds)


async def _alerts(engine, sid: int, rule: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM public.adjustment_suggestions WHERE strategy_id = :s "
                                            "AND rule_id = :r"), {"s": sid, "r": rule})).scalar_one())


async def _type_rupee_stop(engine, sid: int, level: str) -> None:
    async with engine.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
        body = copy.deepcopy(system.body)
        body.setdefault("guards", {})["loss_stop_rupees"] = level
        await playbook_store.accept_plan(conn, "owner", sid, system.id, body)


def _run_worker(engine) -> str:
    env = dict(os.environ, DATABASE_URL=engine.url.render_as_string(hide_password=False), APP_ENV="test",
               OFO_SCENARIO="ADJ-01")
    proc = subprocess.Popen([sys.executable, "-m", "ofo_app.background"], env=env, cwd=os.environ.get("PWD"),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(WORKER_SECONDS)
    proc.terminate()
    out, _ = proc.communicate(timeout=20)
    return out


@pytest.mark.xfail(strict=True, reason="ADJ-01 never ticks in the separate worker ('check skipped: not_ticked'); "
                                       "a PATH-xx scenario with write_frame is the next step (RESULTS)")
async def test_a_rupee_stop_already_crossed_raises_one_alert_in_the_separate_worker(
        app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _type_rupee_stop(app_db_url, sid, "1")  # a Rs 1 stop: crossed by any losing trade
    out = _run_worker(app_db_url)
    assert "not_ticked" not in out, out[-600:]  # the worker must have checked, not skipped
    assert await _alerts(app_db_url, sid, "plan.rupee_loss") == 1
