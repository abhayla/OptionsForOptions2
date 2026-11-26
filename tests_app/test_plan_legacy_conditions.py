# ruff: noqa: E501, PLR2004 - exact status codes are the assertion
"""P8 round 2 (ADR-330 (9), ADR-250/ADR-247): a plan saved before a later playbook version removed a condition stays
editable; only a condition NEW in this save is refused. Reset keeps the sheet levels and the plan settings (LP-5 (a)).
Real PostgreSQL; the plan is the iron condor seed body (pre-0040: it holds guards.stop_line_pct_of_margin)."""
from __future__ import annotations

import copy
import json

from ofo_app import playbook_store as store
from ofo_app import system_playbook_store as sys_store
from test_adjustment_plan_customise import USER, _call, _plan_row, _seeded, app_db_url, plan_path, rules_path  # noqa: F401

MARGIN = "stop_line_pct_of_margin"


async def _legacy_plan(engine, sid: int) -> dict:
    """Stores the pre-0040 ic body (the seed version) as this trade's plan, pointing at the current ic playbook."""
    async with engine.connect() as conn:
        seed = next(v for v in await sys_store.history(conn, "ic") if v.reason == "seed")
        active = await store.active_for(conn, USER, "ic")
    assert MARGIN in seed.body["guards"] and MARGIN not in active.body["guards"]
    async with engine.begin() as conn:
        await conn.execute(store._UPSERT_PLAN, {"strategy_id": sid, "playbook_id": active.id, "type": "ic",
                                               "body": store._dump(seed.body), "stop_base": None})
    return seed.body


async def test_a_plan_saved_before_adr247_stays_editable_and_a_new_condition_is_still_refused(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    async with app_db_url.connect() as conn:
        active = await store.active_for(conn, USER, "ic")
    await _legacy_plan(app_db_url, sid)
    status, out = await _call("PUT", plan_path(sid), json={"playbook_id": active.id, "target": "55"})
    assert status == 200, out
    kept = json.loads((await _plan_row(app_db_url, sid)).body)
    assert MARGIN in kept["guards"] and kept["guards"]["profit_target_pct_of_max_profit"] == "55"
    status, read = await _call("GET", rules_path(sid))
    assert status == 200
    mine = copy.deepcopy(read["body"])
    mine["triggers"]["T-01"]["weekly"][1] = "0.31"
    status, out = await _call("PUT", rules_path(sid), json={"body": mine})
    assert status == 200, out
    # a key neither the stored plan nor the playbook has: refused, the plan unchanged, the key not echoed (F5)
    before = (await _plan_row(app_db_url, sid)).body
    new = copy.deepcopy(mine)
    new["guards"]["brand_new_guard_xyz"] = {"on": True}
    status, out = await _call("PUT", rules_path(sid), json={"body": new})
    assert status == 422, out
    assert "brand_new_guard_xyz" not in json.dumps(out)
    assert (await _plan_row(app_db_url, sid)).body == before
