"""Lane B3 (28 Nov 2026) I-48 / I-08: GET /api/plan-watch for nine running rows reads orders, contracts and settings
ONCE for the whole batch, and a row never shows another row's figures.

Real case (plan rows I-48, I-08): the Positions page asked for nine running trades; each row cost about 25 statements
(about 2.7 s a row over the tunnel), and the builder ended "not available" while the answer existed.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
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
        for sid in ids if single_for is None else single_for:
            s = await ac.get(f"/api/strategies/{sid}/plan-watch")
            assert s.status_code == 200, s.text  # noqa: PLR2004
            singles[sid] = s.json()
    await app_db.close_db()
    return r.json(), singles, statements


#: Queries one plan-watch batch answer may run, WHATEVER the number of rows. MEASURED: 219 for nine rows (24 a row)
#: before any batch read; 162 with shared trigger, contract and kind reads; 136 with orders and traded contracts
#: read once;
#: 12 with every table of the check path read for all rows in ONE statement and the per-row statements answered from
#: memory (``plan_watch_prefetch``): 3 request settings, 1 combined read, orders 1, contracts 2, kinds 1, the expiry
#: kind of the first row 3 (savepoint, catalogue, release), the ADR-247 time 1. Lowered with each fix, never raised.
BATCH_QUERY_CEILING = 12
#: The owner's PC, real database link, 28 Nov (PC round 2, W-02): the API log said 11.8 s of database time over 88
#: queries, so a query costs about 134 ms of link. A test proves cost by COUNTING work
#: (tests/test_no_wall_clock_asserts.py): the
#: link is modelled as this constant per query, no sleep and no clock.
LINK_S_PER_QUERY = Decimal("0.134")
PAGE_BUDGET_S = Decimal(2)  # the plan's target for one answer of nine strategies
MISSING_ID_EXTRA = 5  # queries the row of one id that is not the user's may cost on its own (its refusal), measured
WRITE_AND_REREAD = 2


async def test_nine_rows_each_row_its_own_and_a_fixed_number_of_queries(app_db_url, monkeypatch):  # noqa: F811
    ids = await seed_rows(app_db_url, monkeypatch)
    body, singles, statements = await _batch_and_singles(ids)
    assert [i["strategy_id"] for i in body["items"]] == ids
    for k, item in enumerate(body["items"]):
        assert item["state"] == "ok", item
        assert item["watch"] == singles[item["strategy_id"]], f"row {k}: the batch differs from its single route"
        index_exit = next(x for x in item["watch"]["lines"] if x["kind"] == "index_exit")
        assert index_exit["fires_at"] == f"{BASE_LEVEL + 10 * k}.00", f"row {k} shows another row's level"
    assert statements <= BATCH_QUERY_CEILING, f"batch of {ROWS}: {statements} queries, ceiling {BATCH_QUERY_CEILING}"
    assert statements * LINK_S_PER_QUERY < PAGE_BUDGET_S, f"{statements} queries on the real link: too slow"


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




async def test_the_query_count_does_not_grow_with_the_number_of_rows(app_db_url, monkeypatch):  # noqa: F811
    """The defect class of PC round 2 W-02: a per-row read costs a link round trip per row. Three rows and nine rows run
    the SAME number of queries (red before: 24 a row, 219 for nine)."""
    ids = await seed_rows(app_db_url, monkeypatch)
    _b, _s, three = await _batch_and_singles(ids[:3], single_for=[])
    _b, _s, nine = await _batch_and_singles(ids, single_for=[])
    assert three == nine, f"3 rows: {three} queries, 9 rows: {nine}"


def test_every_statement_copy_equals_the_stores_own():
    """``plan_watch_prefetch.ORIGINAL`` matches a per-row statement by its text; a store that rewords one must fail
    here, so the saving is never silently lost (and never applied to a different statement)."""
    from ofo_app import (  # noqa: PLC0415
        entry_facts_store,
        paper_trigger_store,
        playbook_store,
        scenario_guard,
        strategy_pause_store,
    )
    from ofo_app import plan_watch_prefetch as pf  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415
    stores = {
        "marker": text(scenario_guard._MARKER), "owns": playbook_store._OWNS_STRATEGY,
        "pause": strategy_pause_store._LATEST, "facts": entry_facts_store._SELECT,
        "baskets": entry_facts_store._SELECT_BASKETS, "rule_state": playbook_store._SELECT_STATE,
        "plan": playbook_store._SELECT_PLAN, "open": playbook_store._OPEN_OF_STRATEGY,
        "dismissed": playbook_store._LATEST_DISMISSED, "triggers": paper_trigger_store._FOR,
        "adr247": playbook_store._ADR247_SAVED_AT,
    }
    assert set(stores) == set(pf.ORIGINAL)
    for name, statement in stores.items():
        assert pf.norm(statement) == pf.ORIGINAL[name], name


async def test_one_id_the_user_does_not_own_does_not_cost_the_whole_saving(app_db_url, monkeypatch):  # noqa: F811
    """Opus review F1 (real case: a Positions list holding a strategy deleted meanwhile, or a missing id): the removal
    of an unowned id used to raise inside the prefetch, which dropped EVERY shared read (71 queries for 3 rows)."""
    ids = await seed_rows(app_db_url, monkeypatch)
    _b, _s, three = await _batch_and_singles(ids[:3], single_for=[])
    body, _s, with_missing = await _batch_and_singles([*ids[:3], 987654], single_for=[])
    assert [i["state"] for i in body["items"]] == ["ok", "ok", "ok", "refused"]
    assert with_missing <= three + MISSING_ID_EXTRA, f"3 rows: {three} queries, with one missing id: {with_missing}"


class _Real:
    """A session double: records what reaches the database."""

    def __init__(self):
        self.reached = []

    async def execute(self, statement, params=None, *args, **kwargs):
        self.reached.append(str(getattr(statement, "text", statement)))
        raise RuntimeError("the database")  # a stand-in answer is not needed: the test only looks at who was asked


async def test_a_statement_that_is_not_a_read_drops_the_memory():
    """Opus review F2: a write on the check path (the stop-base backfill) is followed by a re-read of the same table;
    that re-read must see the write, not the request-start memory."""
    from ofo_app import plan_watch_prefetch as pf  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415
    plan = text(pf.ORIGINAL["plan"])
    pre = pf.Prefetch("owner", {"plan": {1: ["memory"]}})
    db = _Real()
    restore = pf.install(db, pre)
    assert (await db.execute(plan, {"strategy_id": 1, "user_ref": "owner"})).all() == ["memory"]
    with pytest.raises(RuntimeError):
        await db.execute(text("UPDATE public.strategy_adjustment_plans SET stop_base = NULL"), {})
    with pytest.raises(RuntimeError):  # now the plan read goes to the database
        await db.execute(plan, {"strategy_id": 1, "user_ref": "owner"})
    assert len(db.reached) == WRITE_AND_REREAD  # the write and the re-read
    restore()
    assert db.execute.__func__ is _Real.execute  # the class's own method is back


async def test_the_adr247_memo_is_kept_per_parameters():
    """Opus review F4: the cut-off time is the same for every row of one request, but a different ``reason`` is a
    different question."""
    from ofo_app import plan_watch_prefetch as pf  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    class Result:
        def __init__(self, value):
            self.value = value

        def all(self):
            return [(self.value,)]

    class Real:
        def __init__(self):
            self.asked = []

        async def execute(self, statement, params=None, *args, **kwargs):
            self.asked.append(params["reason"])
            return Result(params["reason"])

    db, pre = Real(), pf.Prefetch("owner", {})
    pf.install(db, pre)
    statement = text(pf.ORIGINAL["adr247"])
    first = (await db.execute(statement, {"reason": "A"})).scalar()
    again = (await db.execute(statement, {"reason": "A"})).scalar()
    other = (await db.execute(statement, {"reason": "B"})).scalar()
    assert (first, again, other) == ("A", "A", "B") and db.asked == ["A", "B"]
