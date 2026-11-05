# ruff: noqa: E501, PLR0913 - long measured-fact comments; keyword-only helper arguments
"""IC e2e paper contract, Stage C2 (ADR-238 (1)(4)(5), ADR-247, REQ-112): every real exit of a paper iron condor on the
weekly path PATH-50 (Wed 4 Nov .. Mon 9 Nov, expiry day), each on a throwaway database with its OWN strategy name.

Per exit: scenario-marked paper iron condor (Stage A seed) -> the shared frame index moves to the exit's frame -> the
record of the exit's rule is open -> the approaches route prepares the exit approach -> the record is acted on -> the basket
is posted at the typed (pre-filled frame mid) prices with the suggestion id -> any leg the approach leaves open is exited
through the tracking exit -> EVERY leg is flat and the history's booked P&L equals the exact Decimal sum of the stored paper
fills (sell = +, buy = -).

Rule ids are written onto the record as the playbook names them (T-07 profit target, T-06 stop, T-09 close for pennies, the
day rule of the 14:30 time exit). The approach builder does not read the record's rule; it reads the frame, so the frame
carries the situation (profit, loss, pennies, expiry day at 14:31).
"""
from __future__ import annotations

import itertools
from decimal import Decimal as D

import pytest
import test_ic_paper_loop_core as core
from httpx import ASGITransport, AsyncClient
from ofo_app import catalogue_store, playbook_store, scenario_mode

OK, CREATED, CONFLICT = 200, 201, 409
PATH = "PATH-50"
F_PROFIT, F_STOP, F_QUIET, F_1420, F_1429, F_1431, F_PENNIES, F_SETTLE = range(8)
TIME_EXIT_RULE = "day.expiry.1430.5"  # the day rule 5 of the time exit (playbook_eval.day_rule_id shape)
_RUN = itertools.count(1)


async def setup(app_engine, monkeypatch, path: str = PATH) -> int:
    run = next(_RUN)
    monkeypatch.setattr(core.seed_mod, "strategy_name", lambda scenario_id: f"C2 {scenario_id} run {run}")
    monkeypatch.setattr(core, "PATH_ID", path)
    await core._db_url(app_engine, monkeypatch)
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    core._reset_engine()
    scn = scenario_mode.load(path)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=core.CATALOGUE_AS_OF, force=True,
                                           reason=f"test: path scenario {path} contracts", actor="test",
                                           max_delist_percent=core.MAX_DELIST)
    await app_engine.dispose()
    sid = await core.seed_mod.seed(path)
    core._reset_engine()
    return sid


async def cleanup() -> None:
    from ofo_app import db as app_db  # noqa: PLC0415
    await app_db.close_db()
    core._reset_engine()
    scenario_mode._loaded.clear()


def client() -> AsyncClient:
    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment of setup
    scenario_mode._loaded.clear()
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


async def prepare(ac: AsyncClient, sid: int, frame: int, approach: str) -> dict:
    check = await ac.get(f"/api/strategies/{sid}/adjustment-check")  # moves the API's scenario to the frame
    assert check.status_code == OK, check.text
    assert scenario_mode.current().frame == frame
    reply = await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})
    assert reply.status_code == OK, reply.text
    return next(a for a in reply.json()["approaches"] if a["id"] == approach)


async def place(ac: AsyncClient, sid: int, frame: int, built: dict, record_id: int) -> None:
    acted = await ac.post(f"/api/adjustment-opportunities/{record_id}/acted-on", json={})
    assert acted.status_code == OK, acted.text
    net = await core._net(sid)
    orders = []
    for t in built["trades"]:
        assert D(t["price"]) == core.mid_of(frame, t["tradingsymbol"]), t
        cid = await core._contract_id(t)
        closes = (net.get(cid, 0) < 0 and t["action"] == "BUY") or (net.get(cid, 0) > 0 and t["action"] == "SELL")
        orders.append({"contract_id": cid, "side": t["action"], "quantity": t["quantity"], "price": t["price"],
                       "kind": "exit" if closes else "open"})
    placed = await ac.post(f"/paper/strategies/{sid}/orders", json={"orders": orders, "suggestion_ids": [record_id]})
    assert placed.status_code == CREATED, placed.text


async def open_legs(ac: AsyncClient, sid: int) -> list[int]:
    tracking = await ac.get(f"/strategies/{sid}/tracking")
    assert tracking.status_code == OK, tracking.text
    return [leg["leg_index"] for leg in tracking.json()["legs"] if leg["exited_at"] is None]


async def sum_of_fills(sid: int) -> D:
    fills = await core._rows("SELECT side, quantity, price FROM public.paper_orders WHERE strategy_id = :s", s=sid)
    return sum((D(q) * D(p) * (1 if side == "SELL" else -1) for side, q, p in fills), D(0))


async def booked(ac: AsyncClient, sid: int) -> D:
    history = await ac.get(f"/api/strategies/{sid}/adjustment-history")
    assert history.status_code == OK, history.text
    return D(history.json()["totals"]["booked"])


async def run_exit(app_engine, monkeypatch, *, frame: int, rule: str, approach: str, all_legs: bool) -> tuple[D, D, int]:
    """One exit end to end; returns (history booked, sum of fills, legs the approach alone left open)."""
    sid = await setup(app_engine, monkeypatch)
    try:
        await core._move(frame)
        async with core._engine().begin() as conn:
            record = await playbook_store.open_suggestion(conn, "owner", sid, rule, trigger_id=rule, stage=None,
                                                          value=D("0.5"), threshold=D("0.5"))
        async with client() as ac:
            built = await prepare(ac, sid, frame, approach)
            assert built["refusal"] is None and built["trades"], built
            await place(ac, sid, frame, built, record.id)
            left = len([n for n in (await core._net(sid)).values() if n != 0])
            if all_legs:
                assert left == 0, (approach, left)  # attack 1: the exit itself leaves no leg open
            legs = await open_legs(ac, sid)
            if legs:
                assert not all_legs
                done = await ac.post(f"/strategies/{sid}/tracking/exit", json={"legs": legs})
                assert done.status_code == OK, done.text
            assert await open_legs(ac, sid) == []
            assert set((await core._net(sid)).values()) == {0}  # every leg flat in the stored fills
            return await booked(ac, sid), await sum_of_fills(sid), left
    finally:
        await cleanup()


@pytest.mark.parametrize("approach", ["A-24", "A-31"])
async def test_profit_target_t07_closes_every_leg_and_history_equals_the_fills(approach, app_engine, monkeypatch):
    got, cash, _left = await run_exit(app_engine, monkeypatch, frame=F_PROFIT, rule="T-07", approach=approach,
                                      all_legs=True)
    assert got == cash and cash > 0, (got, cash)  # attack 2: exact; a profit target ends in a profit


async def test_stop_t06_a31_closes_every_leg_and_history_equals_the_fills(app_engine, monkeypatch):
    got, cash, _left = await run_exit(app_engine, monkeypatch, frame=F_STOP, rule="T-06", approach="A-31", all_legs=True)
    assert got == cash and cash < 0, (got, cash)  # a stop ends in a loss


async def test_time_exit_1431_a35_closes_every_leg_and_history_equals_the_fills(app_engine, monkeypatch):
    got, cash, _left = await run_exit(app_engine, monkeypatch, frame=F_1431, rule=TIME_EXIT_RULE, approach="A-35",
                                      all_legs=True)
    assert got == cash, (got, cash)


async def test_close_for_pennies_t09_a27_closes_the_shorts_then_every_leg_and_history_equals_the_fills(app_engine,
                                                                                                          monkeypatch):
    got, cash, left = await run_exit(app_engine, monkeypatch, frame=F_PENNIES, rule="T-09", approach="A-27",
                                     all_legs=False)
    assert left == 2, left  # A-27 closes the two shorts; the two bought wings are exited next
    assert got == cash, (got, cash)


@pytest.mark.parametrize(("frame", "builds"), [(F_1420, False), (F_1429, False), (F_1431, True)])
async def test_a35_on_the_real_route_is_refused_naming_1430_before_it_and_built_after_it(frame, builds, app_engine,
                                                                                           monkeypatch):
    sid = await setup(app_engine, monkeypatch)
    try:
        await core._move(frame)
        async with client() as ac:
            a35 = await prepare(ac, sid, frame, "A-35")
        if builds:
            assert a35["refusal"] is None and a35["trades"], a35
        else:
            assert a35["trades"] == [] or not a35["trades"], a35
            assert a35["refusal"] is not None and "14:30" in a35["refusal"]["what_happened"], a35["refusal"]
    finally:
        await cleanup()


async def test_an_exit_on_a_strategy_of_another_scenario_is_refused(app_engine, monkeypatch):
    """Attack 5: the API runs PATH-50; a PATH-01 strategy cannot be exited (409), and it stays open."""
    await setup(app_engine, monkeypatch)
    try:
        other = await core.seed_mod.seed("PATH-01")
        core._reset_engine()
        async with client() as ac:
            await ac.get(f"/api/strategies/{other}/adjustment-check")
            r = await ac.post(f"/strategies/{other}/tracking/exit", json={"legs": [0]})
            assert r.status_code == CONFLICT, r.text
        assert any(n != 0 for n in (await core._net(other)).values())
    finally:
        await cleanup()
