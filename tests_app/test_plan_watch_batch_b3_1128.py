"""Lane B3 (28 Nov 2026) I-48 / I-08: GET /api/plan-watch for nine running rows reads orders, contracts and settings
ONCE for the whole batch, and a row never shows another row's figures.

Real case (plan rows I-48, I-08): the Positions page asked for nine running trades; each row cost about 25 statements
(about 2.7 s a row over the tunnel), and the builder ended "not available" while the answer existed.
"""
from __future__ import annotations

from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from ofo_app import paper_store, paper_trigger_store
from test_adjustment_check import (
    _planned,
    _seeded,
    app_db_url,  # noqa: F401 - the fixture of the check tests
    seed_mod,
)

ROWS = 9
BASE_LEVEL = 23400  # row k arms its index exit at BASE_LEVEL + 10 * k: every row's figures differ


async def seed_rows(app_engine, monkeypatch, n: int = ROWS) -> list[int]:
    """n distinct running strategies of the ONE active scenario (the seed is idempotent per name, so each row gets
    its own name), each with its own plan and armed triggers at its own levels."""
    ids = [await _seeded(app_engine, monkeypatch, "ADJ-01")]
    original = seed_mod.strategy_name
    for k in range(1, n):
        monkeypatch.setattr(seed_mod, "strategy_name", lambda _scenario_id, k=k: f"B3 row {k}")
        sid = await seed_mod.seed("ADJ-01")
        await _planned(app_engine, sid)
        ids.append(sid)
    monkeypatch.setattr(seed_mod, "strategy_name", original)
    for k, sid in enumerate(ids):
        async with app_engine.begin() as conn:
            await paper_trigger_store.add(conn, sid, paper_trigger_store.NewTrigger(
                "conditional_exit", "above", Decimal(BASE_LEVEL + 10 * k), underlying="NIFTY"))
            orders = await paper_store.load(conn, sid)
            shorts = sorted({o.order.contract_id for o in orders if o.order.side == "SELL"})[:2]
            for cid in shorts:
                await paper_trigger_store.add(conn, sid, paper_trigger_store.NewTrigger(
                    "leg_stop", "above", Decimal(90 + k), contract_id=cid))
    return ids


async def test_seed_rows_makes_nine_distinct_strategies(app_db_url, monkeypatch):  # noqa: F811
    ids = await seed_rows(app_db_url, monkeypatch)
    assert len(set(ids)) == ROWS


async def _batch_and_singles(ids: list[int], single_for: list[int] | None = None) -> tuple[dict, dict[int, dict], int]:
    """(the batch body, each row's single-route body, the statements the ONE batch request ran)."""
    from ofo_app import db as app_db  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    from sqlalchemy import event  # noqa: PLC0415
    from test_adjustment_check import _reset_engine  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    count = [0]
    event.listen(app_db.get_engine().sync_engine, "before_cursor_execute",
                 lambda *_a: count.__setitem__(0, count[0] + 1))
    query = ",".join(str(i) for i in ids)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await ac.get(f"/api/plan-watch?strategy_ids={query}")  # warm: imports, caches
        count[0] = 0
        r = await ac.get(f"/api/plan-watch?strategy_ids={query}")
        statements = count[0]
        assert r.status_code == 200, r.text  # noqa: PLR2004
        singles = {}
        for sid in single_for or ids:
            s = await ac.get(f"/api/strategies/{sid}/plan-watch")
            assert s.status_code == 200, s.text  # noqa: PLR2004
            singles[sid] = s.json()
    await app_db.close_db()
    return r.json(), singles, statements


#: Statements a batch of nine running rows may run. MEASURED on this test's rows: 219 before the batch reads (24 a
#: row), 162 after (the duplicate screen-isolation read gone, trigger contracts and position kinds read once for all
#: rows, the expiry kind read once). What is left is per row: orders and traded contracts (``read_tracked``), the plan,
#: the facts and the records; batching those needs ``adjustment_readers.py`` (see RESULTS, "For the owner lane").
#: Lowered with each fix, never raised.
BATCH9_CEILING = 162


async def test_nine_rows_statement_ceiling_and_each_row_its_own(app_db_url, monkeypatch):  # noqa: F811
    ids = await seed_rows(app_db_url, monkeypatch)
    body, singles, statements = await _batch_and_singles(ids)
    assert [i["strategy_id"] for i in body["items"]] == ids
    for k, item in enumerate(body["items"]):
        assert item["state"] == "ok", item
        assert item["watch"] == singles[item["strategy_id"]], f"row {k}: the batch differs from its single route"
        index_exit = next(x for x in item["watch"]["lines"] if x["kind"] == "index_exit")
        assert index_exit["fires_at"] == f"{BASE_LEVEL + 10 * k}.00", f"row {k} shows another row's level"
    assert statements <= BATCH9_CEILING, f"batch of {ROWS}: {statements} statements, ceiling {BATCH9_CEILING}"


async def test_a_failed_shared_read_fails_no_row_and_a_failed_row_is_its_own_refusal(app_db_url, monkeypatch):  # noqa: F811
    """I-08: the shared read failing (here: one row's triggers cannot be read) never turns the other rows into a
    refusal; that row alone is refused, with the catalogue sentence and a status, never an empty "not available"."""
    from ofo_app.routes import plan_watch  # noqa: PLC0415
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415
    ids = await seed_rows(app_db_url, monkeypatch)
    bad = ids[4]
    real = paper_trigger_store.list_for

    async def flaky(conn, sid):
        if sid == bad:
            raise SQLAlchemyError("simulated: triggers of one row unreadable")
        return await real(conn, sid)

    monkeypatch.setattr(plan_watch.paper_trigger_store, "list_for", flaky)
    body, singles, _statements = await _batch_and_singles(ids, single_for=[i for i in ids if i != bad])
    for item in body["items"]:
        if item["strategy_id"] == bad:
            assert item["state"] == "refused" and item["watch"] is None, item
            assert item["refusal"] and item["status"] >= 400, item  # noqa: PLR2004
        else:
            assert item["state"] == "ok", item
            assert item["watch"] == singles[item["strategy_id"]]
