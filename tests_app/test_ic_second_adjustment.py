"""IC e2e paper contract, Stage C1 (design decision 14): the second adjustment and the T-18 limit, on one path scenario.

PATH-40 (PATH-01's condor, spot drifting up): the REAL background worker raises T-01 at frame 6 -> A-01 is placed on
paper with the suggestion id (adjustment 1) -> the drift raises a new record -> a second adjustment is placed on it
(adjustment 2 = the plan's max_adjustments) -> the worker raises exactly one T-18 record -> the approaches route offers
only exit and reduce approaches and the check reply carries the T-19 cost-vs-premium-left line. Counted from the DB.
"""
from __future__ import annotations

import datetime
import json

import test_ic_paper_loop_core as core
from httpx import ASGITransport, AsyncClient
from ofo.adjustment.offered import EXIT_REDUCE
from ofo_app import background, catalogue_store, scenario_mode, strategy_alert_style_store
from ofo_app import db as app_db
from ofo_app.routes.outcome import load_charge_rates

PATH = "PATH-40"
OK, CREATED = 200, 201
LAST_FRAME = 17
FIRST_CROSSING = 6
MAX_ADJUSTMENTS = 2
ROLLS_FIRST = ("A-01", "A-05", "A-02", "A-06", "A-04", "A-11")


async def _setup(app_engine, monkeypatch, name: str) -> int:
    monkeypatch.setattr(core.seed_mod, "strategy_name", lambda _scenario_id: name)
    monkeypatch.setattr(core, "PATH_ID", PATH)
    await core._db_url(app_engine, monkeypatch)
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    core._reset_engine()
    scn = scenario_mode.load(PATH)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=core.CATALOGUE_AS_OF,
                                           force=True, reason="test: path scenario PATH-40 contracts", actor="test",
                                           max_delist_percent=core.MAX_DELIST)
    await app_engine.dispose()
    sid = await core.seed_mod.seed(PATH)
    core._reset_engine()
    async with core._engine().connect() as conn:
        await strategy_alert_style_store.set_pin(conn, "owner", sid, "intraday")
        await conn.commit()
    return sid


def _worker(scn, now):
    def settings(_at):
        return core.registry_defaults()

    async def preferences(_u):
        return core.from_values(core.registry_defaults())

    async def user_values(_u):
        return core.registry_defaults()
    provider, before_cycle = background.scenario_worker_parts(scn, app_db.get_sessionmaker())
    return core._Draining(provider_for=lambda _o: provider,
                          lister=lambda: background.owner_lister(provider, rates_of=load_charge_rates),
                          clock=lambda: now[0], settings=settings, preferences=preferences, user_values=user_values,
                          before_cycle=before_cycle)


async def _records(sid: int) -> list[tuple]:
    """The trigger records; situation notes (sit.S-12, raised at frame 0) are not crossings."""
    rows = await core._rows("SELECT id, rule_id, outcome FROM public.adjustment_suggestions WHERE strategy_id = :s "
                            "ORDER BY id", s=sid)
    return [r for r in rows if not str(r[1]).startswith("sit.")]


async def _run_frame(worker, now, k: int) -> None:
    await core._move(k)
    start = datetime.datetime.fromisoformat(core.frame_doc(k)["clock"]["ist"])
    now[0] = start
    # #662: the real role re-reads its monitors (the tracked legs and adjustments_used) on its own task every
    # REBUILD_SECONDS (background.Worker.run -> _rebuild_loop); cycle() alone reads them only at the first cycle, so
    # the C1 run checked the ENTRY position with adjustments_used 0 on every frame (no T-18 could open). Frames are a
    # minute apart, so the real role has re-read them before each frame: so does this test.
    if worker.monitors:
        await worker.rebuild()
    for s in range(core.CYCLES_PER_FRAME):
        now[0] = start + datetime.timedelta(seconds=s)
        await worker.cycle()
    assert worker.errors == [], worker.errors


async def _advance_until(worker, now, sid: int, k: int, seen: int) -> int:
    """Run frames from ``k`` until the strategy has more than ``seen`` records; returns that frame."""
    while k <= LAST_FRAME:
        await _run_frame(worker, now, k)
        if len(await _records(sid)) > seen:
            return k
        k += 1
    raise AssertionError(f"no new record by frame {LAST_FRAME}: {await _records(sid)}")


async def _adjust(ac, sid: int, record_id: int, frame: int, wanted: tuple[str, ...]) -> str:
    """Prepare the approaches at ``frame`` and place the first wanted one that has trades; returns its id."""
    check = await ac.get(f"/api/strategies/{sid}/adjustment-check")  # moves the API's scenario to the frame
    assert check.status_code == OK, check.text
    assert scenario_mode.current().frame == frame
    prepared = await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})
    assert prepared.status_code == OK, prepared.text
    by_id = {a["id"]: a for a in prepared.json()["approaches"]}
    pick = next((i for i in wanted if i in by_id and by_id[i]["trades"] and by_id[i]["refusal"] is None), None)
    assert pick is not None, {i: (bool(a["trades"]), a["refusal"]) for i, a in by_id.items()}
    acted = await ac.post(f"/api/adjustment-opportunities/{record_id}/acted-on", json={})
    assert acted.status_code == OK, acted.text
    net = await core._net(sid)
    orders = []
    for t in by_id[pick]["trades"]:
        cid = await core._contract_id(t)
        closes = (net.get(cid, 0) < 0 and t["action"] == "BUY") or (net.get(cid, 0) > 0 and t["action"] == "SELL")
        orders.append({"contract_id": cid, "side": t["action"], "quantity": t["quantity"], "price": t["price"],
                       "kind": "exit" if closes else "open"})
    placed = await ac.post(f"/paper/strategies/{sid}/orders", json={"orders": orders, "suggestion_ids": [record_id]})
    assert placed.status_code == CREATED, placed.text
    return pick


async def _run(app_engine, monkeypatch, name: str, *, to_limit: bool) -> None:
    sid = await _setup(app_engine, monkeypatch, name)  # one strategy name per test (the DB is shared)
    try:
        await _scenario(sid, to_limit=to_limit)
    finally:
        await app_db.close_db()
        core._reset_engine()
        scenario_mode._loaded.clear()


async def test_two_adjustments_are_placed_acted_on_and_counted(app_engine, monkeypatch):
    """Proven (c1c.log): T-01 at frame 6 -> A-01 (used 1) -> a new record -> second adjustment (used 2 = the max)."""
    await _run(app_engine, monkeypatch, "C1 two adjusts", to_limit=False)


async def test_limit_raises_one_t18_record_and_offers_only_exit_reduce_with_t19(app_engine, monkeypatch):
    await _run(app_engine, monkeypatch, "C1 limit", to_limit=True)


async def _scenario(sid: int, *, to_limit: bool) -> None:
    scn = scenario_mode.load(PATH)
    entry_orders = (await core._rows("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s", s=sid))[0][0]
    now = [scn.clock_at]
    worker = _worker(scn, now)
    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment above
    scenario_mode._loaded.clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # crossing 1: T-01 only, nothing before it; adjustment 1 = A-01 on that record
        k1 = await _advance_until(worker, now, sid, 0, 0)
        records = await _records(sid)
        assert [r[1] for r in records] == ["T-01"] and k1 == FIRST_CROSSING, (k1, records)
        used = (await ac.get(f"/api/strategies/{sid}/adjustment-history")).json()["totals"]["adjustments_used"]
        assert used == 0, used  # attack 1: the entry batch is not an adjustment
        assert await _adjust(ac, sid, records[0][0], k1, ("A-01",)) == "A-01"
        used = (await ac.get(f"/api/strategies/{sid}/adjustment-history")).json()["totals"]["adjustments_used"]
        assert used == 1, used
        # crossing 2: the drift raises a new record; adjustment 2 is placed on it
        k2 = await _advance_until(worker, now, sid, k1 + 1, len(records))
        records = await _records(sid)
        assert k2 > k1 and records[-1][1] != "T-18", (k2, records)  # the limit is not reached yet
        used = (await ac.get(f"/api/strategies/{sid}/adjustment-history")).json()["totals"]["adjustments_used"]
        assert used == 1, used
        second = await _adjust(ac, sid, records[-1][0], k2, ROLLS_FIRST)
        used = (await ac.get(f"/api/strategies/{sid}/adjustment-history")).json()["totals"]["adjustments_used"]
        assert used == MAX_ADJUSTMENTS, (second, used)
        assert (await core._rows("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s", s=sid))[0][0] \
            > entry_orders
        if not to_limit:
            return
        # crossing 3: the limit. Exactly one T-18 record, however many cycles and frames follow
        before = len(await _records(sid))
        k3 = k2
        await _run_frame(worker, now, k3)
        for k in range(k3 + 1, min(k3 + 3, LAST_FRAME) + 1):
            if not [r for r in await _records(sid) if r[1] == "T-18"]:
                await _run_frame(worker, now, k)
                k3 = k
        t18 = [r for r in await _records(sid) if r[1] == "T-18"]
        held = await core._rows("SELECT rule_id, reason FROM public.adjustment_held_crossings WHERE strategy_id = :s",
                                s=sid)  # a T-18 held by the daily cap / quiet time is named, never silent
        assert len(t18) == 1, (k3, await _records(sid), held)
        assert len(await _records(sid)) >= before
        for k in range(k3 + 1, min(k3 + 3, LAST_FRAME) + 1):  # attack 3: more frames never raise T-18 a second time
            await _run_frame(worker, now, k)
        assert [r[1] for r in await _records(sid)].count("T-18") == 1
        check = await ac.get(f"/api/strategies/{sid}/adjustment-check")
        assert check.status_code == OK, check.text
        prepared = await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})
        assert prepared.status_code == OK, prepared.text
        ids = [a["id"] for a in prepared.json()["approaches"]]
        assert ids and set(ids) <= EXIT_REDUCE, ids  # attack 2: no third roll offered
        text = json.dumps(check.json(), default=str)
        assert "T-19" in text and "T-18" in text, text[:3000]  # T-19: the cost-vs-premium-left line is in the reply
        print(f"C1-PROOF strategy={sid} frames={k1},{k2},{k3} second={second} records={await _records(sid)} "
              f"offered={ids} used={used}")
