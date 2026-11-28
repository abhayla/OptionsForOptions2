"""Lane TF item 3 (I-80, database half): bulk delete, its Undo, Dismiss and the 30 second hold.

What tests_app/test_strategy_bulk_delete.py and tests_app/test_history_delete_entries.py already prove: 12 deleted /
2 kept with reasons (3 of the 12 running on paper), the summary forms, stale and foreign ids, one failing item, Undo of
a whole batch through the per-id route, and the Deleted / Restored history entries of a 3-row batch.

What they do not: the server side of the 30 second hold and of Dismiss (both are on-screen; the server must not
expire an Undo and must keep everything a Dismiss leaves behind), a partial Undo, a repeated Undo, a stale Undo, and a
running trade through delete and Undo (ADR-330 (8): a running paper trade is deleted like any other; ADR-293 (1) and
(2): kept on the server with its history and paper records, the worker stops tracking it, Undo brings all back).
Real case: 27 Nov T2-09, "Dismiss, 30 s hold" not run on the screen; 25 Nov 09:50 "T1123-C9 pm 4lot" deleted while
running.

Real PostgreSQL as the ofo_app role; every test rolls back."""
from __future__ import annotations

import asyncio
from http import HTTPStatus

from ofo_app import strategy_store as store
from sqlalchemy import text
from test_execution_plan_store import _new_strategy, _Tx
from test_strategy_bulk_delete import URL, _items
from test_strategy_delete_app import RAW_ROW, _paper_order, _revision
from test_strategy_followups import _ConnMaker
from test_strategy_store import _app, _client, _history_rows

HOLD_SECONDS = 30  # the on-screen wait before the Undo line goes (ADR-330 (8)); the server has no such wait
PAST_HOLD = HOLD_SECONDS + 1
THREE = 3
TWO = 2
CONFLICT = HTTPStatus.CONFLICT


async def _undo(ac, item: dict):
    return await ac.post(f"/strategies/{item['id']}/undelete", params={"expected_revision": item["revision"]})


async def _three(tx) -> list[int]:
    return [tx.strategy_id] + [await _new_strategy(tx.conn, tx.user, catalogue=False) for _ in range(THREE - 1)]


async def _orders(conn, strategy_id: int) -> int:
    return int((await conn.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s"),
                                   {"s": strategy_id})).scalar_one())


async def _listed(conn, user: str) -> set[int]:
    return {s.id for s in await store.list_strategies(conn, user)}


async def test_an_undo_after_the_thirty_second_hold_is_still_accepted(app_engine):
    """The result line (Undo, Dismiss) stays on screen; the server never expires the Undo. 31 real seconds."""
    async with _Tx(app_engine) as tx:
        ids = await _three(tx)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": await _items(tx.conn, ids)})).json()
            await asyncio.sleep(PAST_HOLD)
            for d in out["deleted"]:
                back = await _undo(ac, d)
                assert back.status_code == HTTPStatus.OK, back.text
            assert sorted(s["id"] for s in (await ac.get("/strategies")).json()["strategies"]) == sorted(ids)


async def test_dismiss_leaves_everything_on_the_server_deleted_but_kept(app_engine):
    """Dismiss is a screen action only (no route): after the answer, with no further call, every deleted row is hidden
    from the list but still stored with its history entry and its paper orders (ADR-293 (1): kept for audit)."""
    async with _Tx(app_engine) as tx:
        ids = await _three(tx)
        await _paper_order(tx.conn, ids[1])
        base = {i: len(await _history_rows(tx.conn, i)) for i in ids}
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": await _items(tx.conn, ids)})).json()
            assert len(out["deleted"]) == THREE and out["kept"] == []
            assert (await ac.get("/strategies")).json()["strategies"] == []
        for i in ids:
            assert (await tx.conn.execute(RAW_ROW, {"id": i})).one().deleted_at is not None  # the row is still there
            assert len(await _history_rows(tx.conn, i)) == base[i] + 1  # its "Deleted" entry
        assert await _orders(tx.conn, ids[1]) == 1  # the paper record is kept


async def test_a_partial_undo_restores_only_the_chosen_rows(app_engine):
    async with _Tx(app_engine) as tx:
        ids = await _three(tx)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": await _items(tx.conn, ids)})).json()
            first, second, third = out["deleted"]
            assert (await _undo(ac, first)).status_code == HTTPStatus.OK
            assert (await _undo(ac, third)).status_code == HTTPStatus.OK
            assert sorted(s["id"] for s in (await ac.get("/strategies")).json()["strategies"]) == sorted(
                [first["id"], third["id"]])
        assert (await tx.conn.execute(RAW_ROW, {"id": second["id"]})).one().deleted_at is not None


async def test_a_second_undo_of_the_same_row_is_refused_and_writes_no_second_entry(app_engine):
    """A double click on Undo: the second answer is the "not available" refusal of a visible row, no extra entry."""
    async with _Tx(app_engine) as tx:
        [sid] = [tx.strategy_id]
        base = len(await _history_rows(tx.conn, sid))
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            [only] = (await ac.post(URL, json={"items": await _items(tx.conn, [sid])})).json()["deleted"]
            assert (await _undo(ac, only)).status_code == HTTPStatus.OK
            again = await _undo(ac, only)
            assert HTTPStatus.BAD_REQUEST <= again.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, again.text
        assert len(await _history_rows(tx.conn, sid)) == base + TWO  # Deleted, Restored: nothing more
        assert (await tx.conn.execute(RAW_ROW, {"id": sid})).one().deleted_at is None


async def test_an_undo_with_a_stale_revision_is_refused_and_the_row_stays_deleted(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            [only] = (await ac.post(URL, json={"items": await _items(tx.conn, [sid])})).json()["deleted"]
            back = await ac.post(f"/strategies/{sid}/undelete", params={"expected_revision": only["revision"] + 5})
            assert back.status_code == CONFLICT, back.text
            assert (await ac.get("/strategies")).json()["strategies"] == []
        assert (await tx.conn.execute(RAW_ROW, {"id": sid})).one().deleted_at is not None
        assert await _revision(tx.conn, sid) == only["revision"]  # the refused Undo changed nothing


async def test_a_running_paper_trade_is_deleted_leaves_the_worker_list_and_comes_back_with_its_orders(app_engine):
    """ADR-330 (8) + ADR-293 (1)(2): deleted like any draft (not kept), its paper orders stay, the list the worker
    reads (``strategy_store.list_strategies``, background.owner_lister) drops it, Undo brings it and its orders back."""
    async with _Tx(app_engine) as tx:
        running = await _new_strategy(tx.conn, tx.user, catalogue=False)
        await _paper_order(tx.conn, running)
        plain = tx.strategy_id
        assert {running, plain} <= await _listed(tx.conn, tx.user)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": await _items(tx.conn, [running, plain])})).json()
            assert sorted(d["id"] for d in out["deleted"]) == sorted([running, plain]) and out["kept"] == []
            assert not {running, plain} & await _listed(tx.conn, tx.user)  # the worker would stop tracking it
            assert await _orders(tx.conn, running) == 1  # the paper record is not removed
            back = next(d for d in out["deleted"] if d["id"] == running)
            assert (await _undo(ac, back)).status_code == HTTPStatus.OK
        assert running in await _listed(tx.conn, tx.user) and plain not in await _listed(tx.conn, tx.user)
        assert await _orders(tx.conn, running) == 1  # the same single order, none added by delete or Undo
