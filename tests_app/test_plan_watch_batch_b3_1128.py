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
#: rows, the expiry kind read once), 136 after the orders and traded contracts are read once too (``Prefetched`` in
#: ``read_tracked``). What is left is per row: the plan, the facts and the records (``run_check``, not this lane's).
#: Lowered with each fix, never raised.
BATCH9_CEILING = 136


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


async def test_a_failed_shared_read_fails_no_row_and_a_failed_row_is_its_own_refusal(
        app_db_url, monkeypatch):  # noqa: F811
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


async def _batch_only(ids: list[int], *, other_user: str | None = None, single: bool = False) -> dict:
    from ofo_app import db as app_db  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    from ofo_app.routes.broker import current_user_ref  # noqa: PLC0415
    from test_adjustment_check import _reset_engine  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    if other_user is not None:
        app.dependency_overrides[current_user_ref] = lambda: other_user
    query = ",".join(str(i) for i in ids)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/api/plan-watch?strategy_ids={query}")
        assert r.status_code == 200, r.text  # noqa: PLR2004
        out = {"batch": r.json()}
        if single:
            s = await ac.get(f"/api/strategies/{ids[0]}/plan-watch")
            out["single"] = {"status": s.status_code, "body": s.json()}
    await app_db.close_db()
    return out


async def test_a_real_position_in_a_batch_gets_no_paper_stop_line(app_db_url, monkeypatch):  # noqa: F811
    """ADR-330 (64), Opus review M4: a real (or unknown) position keeps its armed rows stored but shows them as
    "not applicable", with no price and no distance, in the batch exactly as in the single route."""
    from ofo_app import position_kind, strategy_store  # noqa: PLC0415
    ids = await seed_rows(app_db_url, monkeypatch, 3)
    real = strategy_store.kinds_of

    async def kinds(conn, strategy_ids):
        out = await real(conn, strategy_ids)
        return {sid: (position_kind.REAL if sid == ids[1] else k) for sid, k in out.items()}

    monkeypatch.setattr(strategy_store, "kinds_of", kinds)
    out = await _batch_only(ids)
    by = {i["strategy_id"]: i for i in out["batch"]["items"]}
    armed_real = [x for x in by[ids[1]]["watch"]["lines"] if x["section"] == "armed"]
    assert armed_real and all(x["state"] == "not_applicable" and x["now"] is None and x["distance_rs"] is None
                              for x in armed_real)
    armed_paper = [x for x in by[ids[0]]["watch"]["lines"] if x["section"] == "armed"]
    assert armed_paper and all(x["state"] != "not_applicable" for x in armed_paper)


async def test_another_users_strategy_with_armed_triggers_is_refused_as_the_single_route_refuses(
        app_db_url, monkeypatch):  # noqa: F811
    """Opus review M4: the batch prefetches triggers by id; a strategy that is not the caller's must answer the same
    refusal as the single route and show nothing of those triggers (no lines, no watch)."""
    ids = await seed_rows(app_db_url, monkeypatch, 3)
    out = await _batch_only(ids, other_user="someone-else", single=True)
    for item in out["batch"]["items"]:
        assert item["state"] == "refused" and item["watch"] is None and item["status"] >= 400, item  # noqa: PLR2004
    first = out["batch"]["items"][0]
    assert first["status"] == out["single"]["status"], (first, out["single"])
    for key in ("code", "error_class", "impact"):  # the error reference differs per request, the rest is the same
        assert first["refusal"][key] == out["single"]["body"][key]


async def test_a_release_that_fails_does_not_turn_the_batch_into_a_500(app_db_url, monkeypatch):  # noqa: F811
    """Opus review M2: ``release_connection`` raising after the shared reads is logged; each row answers on its own."""
    from ofo_app.routes import plan_watch_batch  # noqa: PLC0415
    ids = await seed_rows(app_db_url, monkeypatch, 3)

    async def broken(_db):
        raise RuntimeError("simulated: the connection could not be released")

    monkeypatch.setattr(plan_watch_batch, "release_connection", broken)
    out = await _batch_only(ids, single=False)
    assert [i["state"] for i in out["batch"]["items"]] == ["ok", "ok", "ok"]


def _same(tracked):
    """The Tracked without its two ``taken_at`` stamps (the clock at each call; everything else is the book)."""
    import dataclasses  # noqa: PLC0415
    if tracked is None:
        return None
    fixed = {k: (None if getattr(tracked, k) is None else dataclasses.replace(getattr(tracked, k), taken_at=None))
             for k in ("stop_base", "entry_stop_base")}
    return dataclasses.replace(tracked, **fixed)


async def test_read_tracked_gives_the_same_book_with_and_without_the_batch_reads(app_db_url, monkeypatch):  # noqa: F811
    """I-48, the reader half: ``prefetched`` is read cost only. For every row the Tracked it returns equals the one the
    unaided reader returns, and a row the batch did not read (absent from ``orders``) is read by the row itself."""
    from ofo_app import paper_book, tracked_contracts  # noqa: PLC0415
    from ofo_app.adjustment_readers import Prefetched, read_tracked  # noqa: PLC0415
    ids = await seed_rows(app_db_url, monkeypatch, 3)
    async with app_db_url.connect() as conn:
        orders = await paper_book.load_owned_many(conn, "owner", ids)
        found = {c.contract_id: c for c in await tracked_contracts.resolve(
            conn, sorted({o.order.contract_id for rows in orders.values() for o in rows}))}
        shared = Prefetched(orders, found)
        for sid in ids:
            assert _same(await read_tracked(sid, None, db=conn, prefetched=shared)) == _same(
                await read_tracked(sid, None, db=conn))
        partial = Prefetched({ids[0]: orders[ids[0]]}, {})  # rows 1 and 2 not read by the batch: read by themselves
        for sid in ids:
            assert _same(await read_tracked(sid, None, db=conn, prefetched=partial)) == _same(
                await read_tracked(sid, None, db=conn))
        assert await read_tracked(987654, None, db=conn, prefetched=shared) is None  # not found stays not found
