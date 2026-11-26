"""ADR-330 (31): a delete and its Undo each leave one strategy_history entry ("Deleted" / "Restored").

Spec basis (quoted): ADR-330 (31) "A delete and its Undo are recorded in the strategy's history as "Deleted" and
"Restored" entries with their times (real case 26 Nov: drafts 182 and 183 were deleted and came back through Undo with
no trace)."; ADR-330 (8) "Every rule of a single delete applies to each row" (a bulk delete and a bulk Undo write one
entry per strategy); REQ-070 AC-8; ADR-292 (delete / undelete).

Real PostgreSQL only (ADR-048); every test rolls back. The entry is written inside the same savepoint as the delete or
the undelete: all or nothing.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from ofo_app import strategy_store as store
from sqlalchemy import text
from test_execution_plan_store import _new_strategy, _Tx
from test_strategy_bulk_delete import URL, _items
from test_strategy_delete_app import RAW_ROW, _revision
from test_strategy_followups import _ConnMaker
from test_strategy_store import _app, _client, _history_rows

DELETED = [{"kind": "deleted"}]
UNDELETED = [{"kind": "undeleted"}]
BULK = 3


def _kinds(rows: list[tuple]) -> list[list[dict]]:
    return [json.loads(r[1]) for r in rows]


async def test_core_a_delete_and_its_undo_write_one_entry_each(app_engine):
    async with _Tx(app_engine) as tx:
        sid, revision = tx.strategy_id, await _revision(tx.conn, tx.strategy_id)
        before = await _history_rows(tx.conn, sid)
        await store.delete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        after_delete = await _history_rows(tx.conn, sid)
        assert _kinds(after_delete[len(before):]) == [DELETED]
        await store.undelete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        assert _kinds((await _history_rows(tx.conn, sid))[len(before):]) == [DELETED, UNDELETED]
        raw = (await tx.conn.execute(RAW_ROW, {"id": sid})).one()
        assert raw.deleted_at is None and raw.revision == revision  # the strategy itself is unchanged


async def test_each_entry_holds_the_definition_that_was_current_and_a_database_time(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        current = (await tx.conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :i"),
                                         {"i": sid})).scalar_one()
        await store.delete_draft(tx.conn, tx.user, sid, expected_revision=await _revision(tx.conn, sid))
        row = (await tx.conn.execute(text("SELECT definition::text AS d, at, clock_timestamp() AS now "
                                          "FROM public.strategy_history WHERE strategy_id = :i"), {"i": sid})).one()
        assert json.loads(row.d) == json.loads(current)
        assert row.at is not None and row.at <= row.now


async def test_a_refused_delete_writes_no_entry(app_engine):
    """Every answer state of delete_draft that raises leaves the history as it was."""
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        revision = await _revision(tx.conn, sid)
        before = await _history_rows(tx.conn, sid)
        with pytest.raises(store.StrategyStoreError) as stale:
            await store.delete_draft(tx.conn, tx.user, sid, expected_revision=revision + 5)
        assert stale.value.code == store.REVISION_CONFLICT
        with pytest.raises(store.StrategyStoreError) as missing:
            await store.delete_draft(tx.conn, tx.user, 987654321, expected_revision=1)
        assert missing.value.code == store.NOT_FOUND
        await store.delete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        with pytest.raises(store.StrategyStoreError) as hidden:  # already hidden: not found, no second entry
            await store.delete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        assert hidden.value.code == store.NOT_FOUND
        assert len(await _history_rows(tx.conn, sid)) == len(before) + 1


async def test_a_refused_undo_writes_no_entry(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        revision = await _revision(tx.conn, sid)
        with pytest.raises(store.StrategyStoreError) as visible:  # a visible strategy is not undeleted
            await store.undelete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        assert visible.value.code == store.NOT_FOUND
        await store.delete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        with pytest.raises(store.StrategyStoreError) as stale:
            await store.undelete_draft(tx.conn, tx.user, sid, expected_revision=revision + 5)
        assert stale.value.code == store.REVISION_CONFLICT
        assert _kinds(await _history_rows(tx.conn, sid)) == [DELETED]


async def test_a_history_write_that_fails_rolls_the_delete_back(app_engine, monkeypatch):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        revision = await _revision(tx.conn, sid)
        before = await _history_rows(tx.conn, sid)

        async def broken(*_a, **_k):
            raise RuntimeError("history is down")

        monkeypatch.setattr(store, "_write_history", broken)
        with pytest.raises(RuntimeError, match="history is down"):
            await store.delete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        assert (await tx.conn.execute(RAW_ROW, {"id": sid})).one().deleted_at is None
        assert [s.id for s in await store.list_strategies(tx.conn, tx.user)] == [sid]
        assert await _history_rows(tx.conn, sid) == before


async def test_a_history_write_that_fails_rolls_the_undo_back(app_engine, monkeypatch):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        revision = await _revision(tx.conn, sid)
        await store.delete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        before = await _history_rows(tx.conn, sid)

        async def broken(*_a, **_k):
            raise RuntimeError("history is down")

        monkeypatch.setattr(store, "_write_history", broken)
        with pytest.raises(RuntimeError, match="history is down"):
            await store.undelete_draft(tx.conn, tx.user, sid, expected_revision=revision)
        assert (await tx.conn.execute(RAW_ROW, {"id": sid})).one().deleted_at is not None  # still hidden
        assert await _history_rows(tx.conn, sid) == before


async def test_bulk_delete_of_three_writes_three_entries_and_bulk_undo_three_more(app_engine):
    async with _Tx(app_engine) as tx:
        ids = [tx.strategy_id] + [await _new_strategy(tx.conn, tx.user, catalogue=False) for _ in range(BULK - 1)]
        items = await _items(tx.conn, ids)
        base = {i: len(await _history_rows(tx.conn, i)) for i in ids}
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": items})).json()
            assert sorted(d["id"] for d in out["deleted"]) == sorted(ids)
            for i in ids:
                assert _kinds((await _history_rows(tx.conn, i))[base[i]:]) == [DELETED]
            for d in out["deleted"]:
                back = await ac.post(f"/strategies/{d['id']}/undelete", params={"expected_revision": d["revision"]})
                assert back.status_code == HTTPStatus.OK, back.text
        for i in ids:
            assert _kinds((await _history_rows(tx.conn, i))[base[i]:]) == [DELETED, UNDELETED]


async def test_a_kept_row_of_a_bulk_delete_gets_no_entry(app_engine):
    async with _Tx(app_engine) as tx:
        stale = await _new_strategy(tx.conn, tx.user, catalogue=False)
        items = await _items(tx.conn, [tx.strategy_id, stale])
        items[1]["expected_revision"] += 5
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": items})).json()
        assert [d["id"] for d in out["deleted"]] == [tx.strategy_id] and out["kept"][0]["id"] == stale
        assert _kinds(await _history_rows(tx.conn, tx.strategy_id)) == [DELETED]
        assert await _history_rows(tx.conn, stale) == []


async def test_another_users_strategy_is_untouched(app_engine):
    async with _Tx(app_engine) as tx:
        stranger = await _new_strategy(tx.conn, "test-someone-else-0057", catalogue=False)
        revision = await _revision(tx.conn, stranger)
        with pytest.raises(store.StrategyStoreError) as refused:
            await store.delete_draft(tx.conn, tx.user, stranger, expected_revision=revision)
        assert refused.value.code == store.NOT_FOUND
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": [{"id": stranger, "expected_revision": revision}]})).json()
        assert out["deleted"] == [] and out["kept"][0]["reason"] == "not_found"
        with pytest.raises(store.StrategyStoreError):
            await store.undelete_draft(tx.conn, tx.user, stranger, expected_revision=revision)
        assert (await tx.conn.execute(RAW_ROW, {"id": stranger})).one().deleted_at is None
        assert await _history_rows(tx.conn, stranger) == []


async def test_the_history_route_lists_both_entries_with_their_times_and_labels(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        revision = await _revision(tx.conn, sid)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            assert (await ac.delete(f"/strategies/{sid}", params={"expected_revision": revision})).status_code == 200
            assert (await ac.post(f"/strategies/{sid}/undelete", params={"expected_revision": revision})
                    ).status_code == 200
            answer = await ac.get(f"/strategies/{sid}/history")
            assert answer.status_code == HTTPStatus.OK, answer.text
            entries = answer.json()["entries"]
            assert [e["change_summary"]["what_happened"] if isinstance(e["change_summary"], dict)
                    else e["change_summary"] for e in entries] == ["Deleted", "Restored"]
            assert all(e["at"] for e in entries) and entries[0]["at"] <= entries[1]["at"]
            assert [e["restorable"] for e in entries] == [False, False]  # a delete is not a configuration
            # Restore is refused on them as on a rename (HISTORY_NOT_FOUND), never a silent no-op
            refused = await ac.post(f"/strategies/{sid}/restore/{entries[0]['seq']}",
                                    params={"expected_revision": revision})
            assert refused.status_code != HTTPStatus.OK


def test_the_two_items_render_and_the_kinds_are_closed():
    from ofo.strategy import stored_form as sf

    assert sf.render_summary(sf.summary_text(DELETED)) == "Deleted"
    assert sf.render_summary(sf.summary_text(UNDELETED)) == "Restored"
    assert sf.delete_summary() == sf.summary_text(DELETED) and sf.undelete_summary() == sf.summary_text(UNDELETED)
    for bad in ('[{"kind":"deleted","x":1}]', '[{"kind":"nonsense"}]', '[{"kind":"deleted","seq":1}]'):
        assert sf.render_summary(bad) == "this change could not be shown"
