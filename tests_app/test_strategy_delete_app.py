"""REQ-070 AC-6 (W-156, part 28b): delete a never-executed draft: hidden from every read, kept for audit, Undo.

Spec basis (quoted): REQ-070 AC-6 "Only a strategy that never sent a basket can be deleted: the user confirms, Undo is
offered, the draft is hidden from every list and kept on the server with its history for audit; a strategy that ever
sent a basket cannot be deleted and shows \"Can't delete: orders were sent\" instead of Delete (ADR-118)."; ADR-118
"Deleting never erases history or audit rows".

Sensibull: no history/restore screen in the study; delete = soft delete at catalogue-raw.md 270-273, screens 270-272.

Real PostgreSQL only (ADR-048); every test rolls back. The raw SELECTs below run as the application role, which holds
SELECT on both tables and passes through none of the store's filters.
"""

from __future__ import annotations

import pytest
from ofo_app import execution_plan_store as plans
from ofo_app import strategy_store as store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_execution_plan_store import _close, _order, _Tx
from test_strategy_followups import _ConnMaker
from test_strategy_store import WING, _app, _body, _client, _history_rows, _saved_in, _user, _with_draft

RAW_ROW = text("SELECT id, revision, updated_at, deleted_at FROM public.strategies WHERE id = :id")
REFUSAL_TEXT = "Can't delete: orders were sent"
NOT_FOUND_CODE = "USER_INPUT_003"
CONFLICT_CODE = "STRATEGY_VALIDATION_409"
DELETE_REFUSED_CODE = "STRATEGY_VALIDATION_432"
INSUFFICIENT_PRIVILEGE = "42501"
MISSING_ID = 987654321
STALE_REVISION = 9


async def test_core_delete_hides_and_keeps_history(app_engine):
    """Core: save, edit once (one history entry), delete: gone from the list, row and entry still in the database,
    Undo brings back the same id, revision and updated_at."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, user := _user())
            edited = await store.update(conn, user, stored.id, await _saved_in(conn, user, ids, WING),
                                        expected_revision=1)
            assert len(await _history_rows(conn, stored.id)) == 1
            before = (edited.id, edited.revision, edited.updated_at)
            await store.delete_draft(conn, user, stored.id, expected_revision=edited.revision)
            assert await store.list_strategies(conn, user) == []
            raw = (await conn.execute(RAW_ROW, {"id": stored.id})).one()
            assert raw.deleted_at is not None
            assert len(await _history_rows(conn, stored.id)) == 1
            back = await store.undelete_draft(conn, user, stored.id, expected_revision=edited.revision)
            assert (back.id, back.revision, back.updated_at) == before
            assert [s.id for s in await store.list_strategies(conn, user)] == [stored.id]
        finally:
            await trans.rollback()


async def _record_plan(tx: _Tx, close: str | None) -> None:
    number = await plans.next_plan_number(tx.conn, tx.user, tx.strategy_id)
    await plans.record_plan(tx.conn, tx.user, tx.strategy_id, number, "ENTRY",
                            (_order(tx.strategy_id, number, "SELL", "7.00"),))
    if close is not None:
        await _close(tx.conn, tx.user, tx.strategy_id, number, close)


async def _revision(conn, strategy_id: int) -> int:
    return int((await conn.execute(text("SELECT revision FROM public.strategies WHERE id = :id"),
                                   {"id": strategy_id})).scalar_one())


@pytest.mark.parametrize("close", [None, "nothing_placed", "filled"], ids=["open plan", "closed empty", "closed filled"])
async def test_a_draft_with_a_plan_row_of_any_status_is_never_deleted_and_says_so(app_engine, close):
    """Attack 1: ANY plan row (open or closed) refuses; the list says can_delete false; the row stays visible."""
    async with _Tx(app_engine) as tx:
        await _record_plan(tx, close)
        revision = await _revision(tx.conn, tx.strategy_id)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            listed = (await ac.get("/strategies")).json()["strategies"]
            assert [(s["id"], s["can_delete"]) for s in listed] == [(tx.strategy_id, False)]
            refused = await ac.delete(f"/strategies/{tx.strategy_id}", params={"expected_revision": revision})
            assert (refused.status_code, refused.json()["code"]) == (409, DELETE_REFUSED_CODE), refused.text
            assert refused.json()["what_happened"] == REFUSAL_TEXT
            assert (await ac.get(f"/strategies/{tx.strategy_id}")).status_code == 200
        raw = (await tx.conn.execute(RAW_ROW, {"id": tx.strategy_id})).one()
        assert raw.deleted_at is None


async def test_a_draft_with_a_version_row_is_never_deleted(app_engine):
    async with _Tx(app_engine) as tx:
        definition = (await tx.conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :id"),
                                            {"id": tx.strategy_id})).scalar_one()
        await tx.conn.execute(store._INSERT_VERSION, {
            "id": tx.strategy_id, "n": 1, "state": "active", "based_on": None, "definition": definition,
            "version": 1, "confirmed_at": store._now(), "reconciled_at": store._now()})
        assert [(s.id, s.can_delete) for s in await store.list_strategies(tx.conn, tx.user)] == [(tx.strategy_id, False)]
        with pytest.raises(store.StrategyStoreError) as err:
            await store.delete_draft(tx.conn, tx.user, tx.strategy_id, expected_revision=1)
        assert err.value.code == store.DELETE_AFTER_BASKET


async def test_a_draft_with_no_plan_and_no_version_lists_can_delete_true(app_engine):
    async with _Tx(app_engine) as tx:
        assert [(s.id, s.can_delete) for s in await store.list_strategies(tx.conn, tx.user)] == [(tx.strategy_id, True)]


async def test_an_unreadable_plan_table_refuses_the_delete_and_leaves_the_row_visible(app_engine, monkeypatch):
    """Attack 5: the decision query raises -> DELETE_AFTER_BASKET, nothing hidden."""
    async with _Tx(app_engine) as tx:
        monkeypatch.setattr(store, "_CAN_DELETE", text("SELECT 1 / 0"))
        with pytest.raises(store.StrategyStoreError) as err:
            await store.delete_draft(tx.conn, tx.user, tx.strategy_id, expected_revision=1)
        assert err.value.code == store.DELETE_AFTER_BASKET
        assert [s.id for s in await store.list_strategies(tx.conn, tx.user)] == [tx.strategy_id]


async def test_delete_over_the_api_hides_from_every_reader_and_keeps_the_rows(app_engine):
    """Attack 2 (list, load, update, history, restore, rename, delete again, tracking, plan creation, the reconcile
    reader's list) plus Undo."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, first = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                edited = await ac.put(f"/strategies/{first.id}", json=_body(ids, wing=WING, expected_revision=1))
                again = await ac.put(f"/strategies/{first.id}", json=_body(ids, expected_revision=2))
                assert (edited.status_code, again.status_code) == (200, 200), again.text
                revision = again.json()["revision"]
                assert len(await _history_rows(conn, first.id)) == 2
                gone = await ac.delete(f"/strategies/{first.id}", params={"expected_revision": revision})
                assert (gone.status_code, gone.json()) == (200, {"id": first.id, "revision": revision}), gone.text
                assert (await ac.get("/strategies")).json()["strategies"] == []
                for call in (ac.get(f"/strategies/{first.id}"), ac.get(f"/strategies/{first.id}/history"),
                             ac.put(f"/strategies/{first.id}", json=_body(ids, expected_revision=revision)),
                             ac.post(f"/strategies/{first.id}/restore/1", params={"expected_revision": revision}),
                             ac.patch(f"/strategies/{first.id}/name",
                                      json={"name": "x", "expected_revision": revision}),
                             ac.delete(f"/strategies/{first.id}", params={"expected_revision": revision}),
                             ac.get(f"/strategies/{first.id}/tracking")):
                    answer = await call
                    assert answer.status_code == 404, (str(answer.request.url), answer.text)
                for reader in (plans.next_plan_number, plans.owned_strategy):  # the order path: "not yours"
                    with pytest.raises(plans.PlanStoreError) as err:
                        await reader(conn, user, first.id)
                    assert err.value.code == plans.NOT_FOUND
                count = text("SELECT count(*) FROM public.execution_plans WHERE strategy_id = :id")
                assert (await conn.execute(count, {"id": first.id})).scalar_one() == 0
                assert len(await _history_rows(conn, first.id)) == 2
                assert await store.list_strategies(conn, user) == []  # reconcile_attribution reads this list
                back = await ac.post(f"/strategies/{first.id}/undelete", params={"expected_revision": revision})
                assert (back.status_code, back.json()["id"]) == (200, first.id), back.text
                assert [s["id"] for s in (await ac.get("/strategies")).json()["strategies"]] == [first.id]
                again_undo = await ac.post(f"/strategies/{first.id}/undelete", params={"expected_revision": revision})
                assert again_undo.status_code == 404
        finally:
            await trans.rollback()


async def test_other_users_and_missing_and_stale_revisions_write_nothing(app_engine):
    """Attack 3."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, first = await _with_draft(conn, _user())
            async with _client(_app(_ConnMaker(conn), _user())) as stranger:
                for call in (stranger.delete(f"/strategies/{first.id}", params={"expected_revision": 1}),
                             stranger.post(f"/strategies/{first.id}/undelete", params={"expected_revision": 1}),
                             stranger.delete(f"/strategies/{MISSING_ID}", params={"expected_revision": 1})):
                    assert (await call).status_code == 404
            async with _client(_app(_ConnMaker(conn), first.user_ref)) as ac:
                stale = await ac.delete(f"/strategies/{first.id}", params={"expected_revision": STALE_REVISION})
                assert (stale.status_code, stale.json()["code"]) == (409, CONFLICT_CODE), stale.text
                assert len((await ac.get("/strategies")).json()["strategies"]) == 1
                await ac.delete(f"/strategies/{first.id}", params={"expected_revision": 1})
                stale_undo = await ac.post(f"/strategies/{first.id}/undelete",
                                           params={"expected_revision": STALE_REVISION})
                assert stale_undo.status_code == 409, stale_undo.text
                assert await store.list_strategies(conn, first.user_ref) == []
        finally:
            await trans.rollback()


async def test_delete_then_save_as_makes_a_new_id_and_the_deleted_one_stays_hidden(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, first = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                await ac.delete(f"/strategies/{first.id}", params={"expected_revision": 1})
                copy = await ac.post("/strategies", json=_body(ids))
                assert copy.status_code == 201 and copy.json()["id"] != first.id, copy.text
                assert [s["id"] for s in (await ac.get("/strategies")).json()["strategies"]] == [copy.json()["id"]]
        finally:
            await trans.rollback()


async def test_a_hidden_draft_is_not_tracked_and_undo_tracks_it_again(app_engine):
    """Q6 (pending owner): delete stops tracking in the same transaction; Undo restores it."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, first = await _with_draft(conn, user := _user())
            await conn.execute(text("INSERT INTO public.strategy_tracking (strategy_id, strategy_revision, "
                                    "price_health, prices_at) VALUES (:id, 1, 'available', now())"), {"id": first.id})
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                assert [s["tracked"] for s in (await ac.get("/strategies")).json()["strategies"]] == [True]
                await ac.delete(f"/strategies/{first.id}", params={"expected_revision": 1})
                assert (await ac.get("/strategies")).json()["strategies"] == []
                assert (await ac.get(f"/strategies/{first.id}/tracking")).status_code == 404
                await ac.post(f"/strategies/{first.id}/undelete", params={"expected_revision": 1})
                assert [s["tracked"] for s in (await ac.get("/strategies")).json()["strategies"]] == [True]
        finally:
            await trans.rollback()


async def test_q4_a_rename_entry_is_shown_but_is_not_a_restore_target(app_engine):
    """Q4 (pending owner)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, first = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                renamed = await ac.patch(f"/strategies/{first.id}/name", json={"name": "Wider", "expected_revision": 1})
                assert renamed.status_code == 200, renamed.text
                entries = (await ac.get(f"/strategies/{first.id}/history")).json()["entries"]
                assert len(entries) == 1
                refused = await ac.post(f"/strategies/{first.id}/restore/{entries[0]['seq']}",
                                        params={"expected_revision": 1})
                assert (refused.status_code, refused.json()["code"]) == (404, NOT_FOUND_CODE), refused.text
        finally:
            await trans.rollback()


async def test_q5_history_stays_readable_after_a_basket_and_restore_keeps_its_refusal(app_engine):
    """Q5 (pending owner): REQ-070 AC-5 history readable; ADR-019 restore refused, on the same executed strategy."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, first = await _with_draft(conn, user := _user())
            edited = await store.update(conn, user, first.id, await _saved_in(conn, user, ids, WING),
                                        expected_revision=1)
            number = await plans.next_plan_number(conn, user, first.id)
            await plans.record_plan(conn, user, first.id, number, "ENTRY", (_order(first.id, number, "SELL", "7.00"),))
            await _close(conn, user, first.id, number, "filled")
            assert len(await store.history(conn, user, first.id)) == 1
            with pytest.raises(store.StrategyStoreError) as err:
                await store.restore(conn, user, first.id, 1, expected_revision=edited.revision)
            assert err.value.code == store.RESTORE_AFTER_EXECUTION
        finally:
            await trans.rollback()


async def test_the_app_role_cannot_insert_a_row_born_hidden(app_engine):
    async with _Tx(app_engine) as tx:
        point = await tx.conn.begin_nested()
        with pytest.raises(DBAPIError) as err:
            await tx.conn.execute(text(
                "INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version, deleted_at) "
                "SELECT user_ref, underlying, definition, definition_schema_version, now() FROM public.strategies "
                "WHERE id = :id"), {"id": tx.strategy_id})
        await point.rollback()
        assert getattr(err.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE
