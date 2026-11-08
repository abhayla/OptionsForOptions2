# ruff: noqa: E501, PLR0913 - long measured-fact comments; keyword-only helper arguments
"""IC e2e paper contract, Stage B3 (design decisions 5, 6, 15): each of the 14 trade approaches, prepared and placed on
paper with its suggestion id, leaves the stored paper legs EXACTLY equal to the legs the approach built (its After legs).

Per approach, on a throwaway database: a scenario-marked paper iron condor (Stage A seed) -> the shared frame index moves
to a frame where the approach applies -> the approaches route prepares it -> the record is acted on -> the basket is posted
at the typed prices with the suggestion id (scenario mode, own scenario) -> the stored net paper legs per contract are
compared with the After legs (strike, side, lots, expiry) and the link on the record is read back.
"""
from __future__ import annotations

import datetime
import itertools
from decimal import Decimal as D

import pytest
import test_ic_paper_loop_core as core
from _scenario_catalogue import load_library
from httpx import ASGITransport, AsyncClient
from ofo_app import background, playbook_store, scenario_mode
from ofo_app import db as app_db

OK, CREATED, CONFLICT = 200, 201, 409
# approach -> (path, frame where it applies; PATH-01 frame 6 = a call-side test, PATH-31 = expiry day after the time exit)
WHERE = dict.fromkeys(("A-01", "A-02", "A-04", "A-05", "A-06", "A-11", "A-24", "A-25", "A-26", "A-28", "A-29", "A-31"), ("PATH-01", 6))
# the system playbook's roll debit limit (Rs 500 or 10% of max profit = Rs 1,145.30 here) refuses A-02, A-05 and A-06 from
# frame 3 on (measured: debits Rs 1,150 to 1,850); frame 2 is the one frame where all three roll inside it
WHERE |= dict.fromkeys(("A-02", "A-05", "A-06"), ("PATH-01", 2))
WHERE |= {"A-27": ("PATH-31", 2), "A-35": ("PATH-31", 2)}
APPROACHES = ["A-01", "A-02", "A-04", "A-05", "A-06", "A-11", "A-24", "A-25", "A-26", "A-27", "A-28", "A-29", "A-31",
              "A-35"]


_RUN = itertools.count(1)


async def _setup(app_engine, monkeypatch, path: str) -> int:
    run = next(_RUN)  # the database is shared by the tests of a run and the seed is idempotent by name: one name per test
    monkeypatch.setattr(core.seed_mod, "strategy_name", lambda scenario_id: f"B3 {scenario_id} run {run}")
    monkeypatch.setattr(core, "PATH_ID", path)
    await core._db_url(app_engine, monkeypatch)
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    core._reset_engine()
    await load_library(app_engine)  # the whole library's list, once per database
    await app_engine.dispose()  # from here on ONE engine (the app's) holds every connection
    sid = await core.seed_mod.seed(path)
    core._reset_engine()
    return sid


async def _unit(sid: int) -> int:
    """Shares per lot of the seeded strategy (from its first order and lots)."""
    return 1  # quantity in the paper orders is shares; lots*lot is taken from the prepared trades instead


async def _place(approach: str, path: str, frame: int, *, only_first: bool = False, link: bool = True,
                 sid: int) -> dict:
    await core._move(frame)
    async with core._engine().begin() as conn:
        record = await playbook_store.open_suggestion(conn, "owner", sid, "T-01", trigger_id="T-01", stage=None,
                                                      value=D("0.5"), threshold=D("0.5"))
    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment of _setup
    scenario_mode._loaded.clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        check = await ac.get(f"/api/strategies/{sid}/adjustment-check")  # moves the API's scenario to the frame
        assert check.status_code == OK, check.text
        assert scenario_mode.current().frame == frame
        prepared = await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})
        assert prepared.status_code == OK, prepared.text
        built = next(a for a in prepared.json()["approaches"] if a["id"] == approach)
        assert built["refusal"] is None and built["trades"] and built["after_legs"] is not None, built
        acted = await ac.post(f"/api/adjustment-opportunities/{record.id}/acted-on", json={})
        assert acted.status_code == OK, acted.text
        net = await core._net(sid)
        orders = []
        for t in built["trades"]:
            assert D(t["price"]) == core.mid_of(frame, t["tradingsymbol"]), t  # the app pre-fills the frame's mid
            cid = await core._contract_id(t)
            closes = (net.get(cid, 0) < 0 and t["action"] == "BUY") or (net.get(cid, 0) > 0 and t["action"] == "SELL")
            orders.append({"contract_id": cid, "side": t["action"], "quantity": t["quantity"], "price": t["price"],
                           "kind": "exit" if closes else "open"})
        sent = orders[:1] if only_first else orders
        body = {"orders": sent, "suggestion_ids": [record.id] if link else []}
        placed = await ac.post(f"/paper/strategies/{sid}/orders", json=body)
        assert placed.status_code == CREATED, placed.text
    return {"built": built, "record": record.id, "before": net, "sent": len(sent)}


async def _expected(built: dict) -> dict[int, int]:
    """The net open shares per contract the approach's After legs stand for."""
    lot = built["trades"][0]["quantity"] // built["trades"][0]["lots"]
    want: dict[int, int] = {}
    for leg in built["after_legs"]:
        cid = await core._contract_id(leg)
        want[cid] = want.get(cid, 0) + (1 if leg["side"] == "BUY" else -1) * leg["lots"] * lot
    return want


async def _stored(sid: int) -> dict[int, int]:
    return {c: n for c, n in (await core._net(sid)).items() if n != 0}


async def _timeline_orders(record: int) -> list[list[int]]:
    rows = await core._rows("SELECT timeline FROM public.adjustment_suggestions WHERE id = :r", r=record)
    return [sorted(e["order_ids"]) for e in rows[0][0] if e.get("event") == "orders_placed"]


async def _run(app_engine, monkeypatch, approach: str, **kw) -> tuple[dict, dict, dict, int]:
    path, frame = WHERE[approach]
    sid = await _setup(app_engine, monkeypatch, path)
    try:
        done = await _place(approach, path, frame, sid=sid, **kw)
        return done, await _expected(done["built"]), await _stored(sid), sid
    finally:
        pass


async def _cleanup() -> None:
    await app_db.close_db()
    core._reset_engine()
    scenario_mode._loaded.clear()


@pytest.mark.parametrize("approach", APPROACHES)
async def test_the_stored_paper_legs_equal_the_built_after_legs(approach, app_engine, monkeypatch):
    try:
        done, want, stored, sid = await _run(app_engine, monkeypatch, approach)
        assert stored == want, (approach, stored, want)
        # the link: the record names exactly the orders its basket placed (attack 1: no suggestion id, no link)
        newest = [i for (i,) in await core._rows("SELECT id FROM public.paper_orders WHERE strategy_id = :s "
                                                 "ORDER BY id DESC LIMIT :n", s=sid, n=done["sent"])]
        assert await _timeline_orders(done["record"]) == [sorted(newest)]
    finally:
        await _cleanup()


async def test_diagnose_a35_time_exit_source(app_engine, monkeypatch):
    """A-35's refusal on the real route: which playbook body the route resolves, its stored versions, the check clock."""
    import json  # noqa: PLC0415

    from ofo.adjustment import playbook_eval as pe  # noqa: PLC0415
    from ofo_app import adjustment_check  # noqa: PLC0415
    sid = await _setup(app_engine, monkeypatch, "PATH-31")
    try:
        versions = await core._rows("SELECT version, reason, body::jsonb->'guards'->>'time_exit' "
                                    "FROM public.system_playbook_versions WHERE strategy_type = 'ic' ORDER BY version")
        await core._move(2)
        from ofo_app.main import create_app  # noqa: PLC0415
        scenario_mode._loaded.clear()
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as ac:
            assert (await ac.get(f"/api/strategies/{sid}/adjustment-check")).status_code == OK
            reply = (await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})).json()
        a35 = next(a for a in reply["approaches"] if a["id"] == "A-35")
        async with core._engine().connect() as conn:
            pb = await playbook_store.active_for(conn, "owner", "ic")
            plan = await playbook_store.plan_for(conn, "owner", sid)
        guards = adjustment_check.guards_of_body(pb.body)
        facts = {"versions(version, reason, time_exit)": [list(v) for v in versions],
                 "active_for ic: version/status": [pb.version, pb.status], "plan_for": None if plan is None else plan.playbook_id,
                 "guards time_exit via active_for": dict(pb.body.get("guards", {})).get("time_exit"),
                 "exit_inputs": repr(pe.exit_inputs(pb.body, guards, pe.StrategyState(
                     stops=None, expiry_kind="weekly", days_left=0, hhmm="15:00", tighten_percent=None))),
                 "spot": reply["spot"]["value"], "spot_at": str(reply["spot"]["at"]),
                 "a35 refusal": (a35["refusal"] or {}).get("what_happened"), "a35 trades": bool(a35["trades"])}
        print("A35-FACTS " + json.dumps(facts, default=str))
        assert facts["guards time_exit via active_for"] == "14:30", facts
    finally:
        await _cleanup()


async def test_a_basket_without_the_suggestion_id_changes_the_legs_but_names_no_orders(app_engine, monkeypatch):
    """Attack 1: the legs equal the After legs, yet the record carries no link, so the link assertion would fail."""
    try:
        done, want, stored, _sid = await _run(app_engine, monkeypatch, "A-05", link=False)
        assert stored == want
        assert await _timeline_orders(done["record"]) == []
    finally:
        await _cleanup()


async def test_a_partial_basket_leaves_legs_that_differ_from_the_after_legs(app_engine, monkeypatch):
    """Attack 4: only the first leg of A-05's basket is placed; the comparison detects it."""
    try:
        _done, want, stored, _sid = await _run(app_engine, monkeypatch, "A-05", only_first=True)
        assert stored != want
    finally:
        await _cleanup()


async def test_a_paper_order_on_a_strategy_of_another_scenario_is_refused(app_engine, monkeypatch):
    """Attack 5: the Stage A guard still holds - the API runs PATH-01, so a PATH-31 strategy cannot be traded."""
    path_other = "PATH-31"
    sid = await _setup(app_engine, monkeypatch, "PATH-01")
    try:
        other = await core.seed_mod.seed(path_other)
        core._reset_engine()
        from ofo_app.main import create_app  # noqa: PLC0415
        scenario_mode._loaded.clear()
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as ac:
            await ac.get(f"/api/strategies/{sid}/adjustment-check")
            net = await core._net(other)
            cid = next(iter(net))
            r = await ac.post(f"/paper/strategies/{other}/orders",
                              json={"orders": [{"contract_id": cid, "side": "BUY", "quantity": 75, "price": "1.00",
                                                "kind": "open"}]})
            assert r.status_code == CONFLICT, r.text
    finally:
        await _cleanup()


_ = (background, datetime)  # kept: imports the core proof's own modules loaded the same way
