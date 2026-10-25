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

from sqlalchemy import text

from ofo_app import strategy_store as store
from test_strategy_store import WING, _history_rows, _saved_in, _user, _with_draft

RAW_ROW = text("SELECT id, revision, updated_at, deleted_at FROM public.strategies WHERE id = :id")


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
