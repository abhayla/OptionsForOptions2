"""IC e2e paper contract, Stage A CORE proof (design decisions 1-7).

One scenario-marked paper iron condor (path scenario PATH-01, built from ADJ-02, 10 frames) on a throwaway database:
paper entry at frame 0 -> the shared frame index moves frame by frame -> the REAL background worker (no screen open,
the scenario's own fed provider, the frame read before every cycle) writes 0 T-01 records up to frame 5 and exactly 1
at frame 6 -> A-01 is prepared at frame 6 through the app's own approaches route -> its paper orders are placed through
the app (scenario mode, own scenario: allowed) at frame 6 mids, linked to the record (legs changed) -> paper exit of
every open leg -> the stored fills' signed total equals the history's booked P&L. Everything counted from the database.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
from decimal import Decimal as D

from httpx import ASGITransport, AsyncClient
from ofo.adjustment.preferences import from_values
from ofo.settings import calc as settings_calc
from ofo.settings import defaults as registry_defaults
from ofo.timeutil import IST
from ofo_app import background, catalogue_store, scenario_mode, strategy_alert_style_store
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
MAX_DELIST = settings_calc.max_delist_percent(registry_defaults())
PATH_ID = "PATH-01"
CROSS_FRAME = 6
CYCLES_PER_FRAME = 75  # past one 1-minute candle close (intraday style) at one-second cycles
OK, CREATED = 200, 201


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


async def _db_url(app_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", PATH_ID)
    _reset_engine()


class _Draining(background.Worker):
    async def cycle(self) -> None:
        await super().cycle()
        await self.drain_writes()


def frame_doc(k: int) -> dict:
    return json.loads(scenario_mode.frame_path(PATH_ID, k).read_text(encoding="utf-8"), parse_float=D)


def mid_of(k: int, symbol: str) -> D:
    """The frame's mid of a contract: (bid + ask) / 2 snapped to the 0.05 tick (the prepared basket's pre-fill)."""
    row = next(r for c in frame_doc(k)["market"]["chains"] for r in c["rows"] if r["tradingsymbol"] == symbol)
    mid = (D(str(row["bid"])) + D(str(row["ask"]))) / 2
    return (mid / D("0.05")).quantize(D(1)) * D("0.05")


def _engine():
    """THE one engine of this test: the app's own (pool 2, no overflow), shared with the worker and the API (the role
    has CONNECTION LIMIT 5 and other sessions hold some)."""
    return app_db.get_engine()


async def _rows(sql: str, **params) -> list:
    async with _engine().connect() as conn:
        return list((await conn.execute(text(sql), params)).all())


async def _move(k: int) -> None:
    async with _engine().begin() as conn:
        await scenario_mode.write_frame(conn, PATH_ID, k)


async def test_core_path_frames_raise_one_record_adjusted_exited_and_totalled_on_paper(app_engine, monkeypatch):
    await _db_url(app_engine, monkeypatch)
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    try:
        await _core(app_engine)
    finally:
        await app_db.close_db()
        _reset_engine()
        scenario_mode._loaded.clear()


async def _contract_id(symbol_row: dict) -> int:
    rows = await _rows("SELECT id FROM public.catalogue_contracts WHERE name = 'NIFTY' AND instrument_type = :t "
                       "AND strike = :k AND expiry = :e AND NOT retired AND NOT delisted",
                       t=symbol_row["type"], k=D(symbol_row["strike"]),
                       e=datetime.date.fromisoformat(str(symbol_row["expiry"])))
    assert len(rows) == 1, (symbol_row, rows)
    return int(rows[0][0])


async def _net(sid: int) -> dict[int, int]:
    rows = await _rows("SELECT contract_id, sum(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) "
                       "FROM public.paper_orders WHERE strategy_id = :s GROUP BY contract_id", s=sid)
    return {int(c): int(n) for c, n in rows}


async def _core(app_engine) -> None:  # noqa: PLR0915 - one readable walk of the proof
    scn = scenario_mode.load(PATH_ID)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=CATALOGUE_AS_OF, force=True,
                                           reason="test: path scenario PATH-01 contracts", actor="test",
                                           max_delist_percent=MAX_DELIST)
    await app_engine.dispose()  # from here on ONE engine (the app's) holds every connection
    sid = await seed_mod.seed(PATH_ID)  # paper entry at frame 0 (the base position's entry fills)
    _reset_engine()
    assert await _rows("SELECT scenario_id FROM public.strategies WHERE id = :s", s=sid) == [(PATH_ID,)]
    entry_orders = (await _rows("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s", s=sid))[0][0]
    async with _engine().connect() as conn:
        await strategy_alert_style_store.set_pin(conn, "owner", sid, "intraday")
        await conn.commit()
    now = [scn.clock_at]

    def settings(_at):
        return registry_defaults()

    async def preferences(_u):
        return from_values(registry_defaults())

    async def user_values(_u):
        return registry_defaults()
    provider, before_cycle = background.scenario_worker_parts(scn, app_db.get_sessionmaker())  # the process wiring
    assert provider is scn.provider  # the scenario feed: no KiteProvider built for the worker
    worker = _Draining(provider_for=lambda _o: provider, lister=lambda: background.owner_lister(provider),
                       clock=lambda: now[0], settings=settings, preferences=preferences, user_values=user_values,
                       before_cycle=before_cycle)
    t01_at: dict[int, int] = {}
    total_at: dict[int, int] = {}
    for k in range(CROSS_FRAME + 1):
        await _move(k)
        start = datetime.datetime.fromisoformat(frame_doc(k)["clock"]["ist"])
        for s in range(CYCLES_PER_FRAME):
            now[0] = start + datetime.timedelta(seconds=s)
            await worker.cycle()
        assert scn.frame == k and str(scn.provider.underlying_quote("NIFTY").ltp) == str(frame_doc(k)["market"]["spot"])
        t01_at[k] = len(await _rows("SELECT id FROM public.adjustment_suggestions "
                                    "WHERE strategy_id = :s AND rule_id = 'T-01'", s=sid))
        total_at[k] = len(await _rows("SELECT id FROM public.adjustment_suggestions WHERE strategy_id = :s", s=sid))
    assert worker.errors == [], worker.errors
    # contract Proof: ONE record in total, 0 of any rule through frame 5 (PATH-01's legs make T-01 the only crossing)
    assert all(total_at[k] == 0 for k in range(CROSS_FRAME)), total_at
    assert total_at[CROSS_FRAME] == 1 and t01_at[CROSS_FRAME] == 1, (total_at, t01_at)
    all_records = await _rows("SELECT id, outcome, rule_id FROM public.adjustment_suggestions WHERE strategy_id = :s",
                              s=sid)
    record = all_records[0]
    assert (record[1], record[2]) == ("open", "T-01")  # T-01 IS that record

    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment above
    scenario_mode._loaded.clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        check = await ac.get(f"/api/strategies/{sid}/adjustment-check")  # moves the API's scenario to frame 6
        assert check.status_code == OK, check.text
        assert scenario_mode.current().frame == CROSS_FRAME
        r = await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})
        assert r.status_code == OK, r.text
        a01 = next(a for a in r.json()["approaches"] if a["id"] == "A-01")
        assert a01["trades"], a01
        acted = await ac.post(f"/api/adjustment-opportunities/{record[0]}/acted-on", json={})
        assert acted.status_code == OK, acted.text
        net = await _net(sid)
        orders = []
        for t in a01["trades"]:
            assert D(t["price"]) == mid_of(CROSS_FRAME, t["tradingsymbol"]), t  # the app pre-fills frame 6 mid
            cid = await _contract_id(t)
            closes = (net.get(cid, 0) < 0 and t["action"] == "BUY") or (net.get(cid, 0) > 0 and t["action"] == "SELL")
            orders.append({"contract_id": cid, "side": t["action"], "quantity": t["quantity"],
                           "price": t["price"],  # the PREPARED basket's own pre-filled price, sent as typed
                           "kind": "exit" if closes else "open"})
        before = (await _rows("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s", s=sid))[0][0]
        placed = await ac.post(f"/paper/strategies/{sid}/orders", json={"orders": orders,
                                                                        "suggestion_ids": [record[0]]})
        assert placed.status_code == CREATED, placed.text
        new = (await _rows("SELECT id, price FROM public.paper_orders WHERE strategy_id = :s ORDER BY id",
                           s=sid))[before:]
        assert [format(p, "f") for _i, p in new] == [o["price"] for o in orders]  # fill = frame 6 mid (REQ-109 AC-1)
        timeline = (await _rows("SELECT timeline FROM public.adjustment_suggestions WHERE id = :r", r=record[0]))[0][0]
        placed_events = [e for e in timeline if e.get("event") == "orders_placed"]
        assert [sorted(e["order_ids"]) for e in placed_events] == [sorted(i for i, _p in new)]  # linked
        assert await _net(sid) != net  # the paper legs changed
        tracking = await ac.get(f"/strategies/{sid}/tracking")
        assert tracking.status_code == OK, tracking.text
        legs = [leg["leg_index"] for leg in tracking.json()["legs"] if leg["exited_at"] is None]  # every open leg
        exit_r = await ac.post(f"/strategies/{sid}/tracking/exit", json={"legs": legs})
        assert exit_r.status_code == OK, exit_r.text
        history = await ac.get(f"/api/strategies/{sid}/adjustment-history")
        assert history.status_code == OK, history.text
    fills = await _rows("SELECT side, quantity, price FROM public.paper_orders WHERE strategy_id = :s", s=sid)
    cash = sum((D(q) * D(p) * (1 if side == "SELL" else -1) for side, q, p in fills), D(0))
    assert set((await _net(sid)).values()) == {0}  # every leg exited
    booked = D(history.json()["totals"]["booked"])
    assert booked == cash, (history.json()["totals"], cash)
    print(f"CORE-PROOF strategy={sid} marker={PATH_ID} t01_by_frame={t01_at} records_all={len(all_records)} "
          f"total_by_frame={total_at} rules={sorted(r[2] for r in all_records)} entry_orders={entry_orders} "
          f"a01_orders={len(new)} fills={len(fills)} booked={booked} sum_of_fills={cash}")
