"""ADR-330 (8) bulk delete, ADR-292 / ADR-293 (S-01, S-03, S-02 of the 26 Nov 2026 plan).

Spec basis (quoted): ADR-330 (8) "Every rule of a single delete applies to each row (ADR-292, ADR-293): a strategy that
cannot be deleted today ... is skipped and named in the result, as in '12 deleted, 2 kept: they have open positions'."
ADR-330 (8), running paper strategies: "a RUNNING paper strategy is deleted in a bulk delete, exactly as a single delete
allows today". ADR-292: a strategy held at the broker is never deleted.

Real PostgreSQL only (ADR-048); every test rolls back. S-02 (a delete while another connection holds the row
lock) needs committed rows the app role cannot remove, so it is NOT written here: see the item's report.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from ofo_app import strategy_store as store
from sqlalchemy import text
from test_execution_plan_store import _new_strategy, _Tx
from test_strategy_delete_app import RAW_ROW, _paper_order, _revision, _send_basket
from test_strategy_followups import _ConnMaker
from test_strategy_store import _app, _client

HELD_TEXT = "This strategy is marked as held at your broker, so it cannot be deleted."
SENT_TEXT = "Orders were already sent for this strategy, so it cannot be deleted."
CHANGED_TEXT = "This strategy was changed by another action after you opened it."
NOT_FOUND_TEXT = "The page or action you asked for is not available here."
FAILED_TEXT = "This strategy could not be deleted because of an unexpected error, so it was left as it is."
TOO_MANY_CODE = "STRATEGY_VALIDATION_514"
LIMIT = 200
URL = "/strategies/bulk-delete"
DELETED = 12
RUNNING = 3


async def _held(conn, strategy_id: int) -> None:
    await _paper_order(conn, strategy_id)
    await conn.execute(text("INSERT INTO public.strategy_held_entries (strategy_id, entry_at, broker_text) "
                            "VALUES (:s, now(), NULL)"), {"s": strategy_id})


async def _items(conn, ids: list[int]) -> list[dict]:
    return [{"id": i, "expected_revision": await _revision(conn, i)} for i in ids]


async def _fourteen(tx: _Tx) -> tuple[list[int], int, int]:
    """Real-shaped rows of one user: 12 deletable (3 running on paper orders), 1 held at the broker, 1 with a real
    basket. Returns (ids in order, held id, basket id)."""
    ids = [tx.strategy_id]
    for _ in range(DELETED + 1):
        ids.append(await _new_strategy(tx.conn, tx.user, catalogue=False))
    for sid in ids[1:1 + RUNNING]:
        await _paper_order(tx.conn, sid)
    held, basket = ids[-2], ids[-1]
    await _held(tx.conn, held)
    await _send_basket(tx.conn, tx.user, basket, "open")
    assert len(ids) == DELETED + 2
    return ids, held, basket


async def test_core_twelve_deleted_two_kept_with_reasons(app_engine):
    """Core: 14 strategies = 12 deletable (3 running paper) + 1 held + 1 real basket -> 12 deleted, 2 kept."""
    async with _Tx(app_engine) as tx:
        ids, held, basket = await _fourteen(tx)
        body = {"items": await _items(tx.conn, ids)}
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            answer = await ac.post(URL, json=body)
            assert answer.status_code == HTTPStatus.OK, answer.text
            out = answer.json()
            assert sorted(d["id"] for d in out["deleted"]) == sorted(ids[:DELETED])
            assert {d["id"]: d["revision"] for d in out["deleted"]} == {i["id"]: i["expected_revision"]
                                                                        for i in body["items"][:DELETED]}
            assert {k["id"]: (k["reason"], k["text"]["what_happened"]) for k in out["kept"]} == {
                held: ("held_at_broker", HELD_TEXT), basket: ("orders_sent", SENT_TEXT)}
            assert out["summary_text"]["what_happened"] == "12 deleted, 2 kept: see each row"
            assert sorted(s["id"] for s in (await ac.get("/strategies")).json()["strategies"]) == sorted([held, basket])
        for sid in ids[:DELETED]:
            assert (await tx.conn.execute(RAW_ROW, {"id": sid})).one().deleted_at is not None


async def test_summary_text_forms(app_engine):
    """'3 deleted' when none kept; one shared reason names its sentence; '0 deleted, 2 kept: ...' when none deleted."""
    async with _Tx(app_engine) as tx:
        two = [await _new_strategy(tx.conn, tx.user, catalogue=False) for _ in range(2)]
        for sid in two:
            await _held(tx.conn, sid)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            none_deleted = (await ac.post(URL, json={"items": await _items(tx.conn, two)})).json()
            assert none_deleted["deleted"] == [] and len(none_deleted["kept"]) == len(two)
            assert none_deleted["summary_text"]["what_happened"] == f"0 deleted, 2 kept: {HELD_TEXT}"
            plain = [tx.strategy_id] + [await _new_strategy(tx.conn, tx.user, catalogue=False) for _ in range(2)]
            none_kept = (await ac.post(URL, json={"items": await _items(tx.conn, plain)})).json()
            assert none_kept["kept"] == [] and none_kept["summary_text"]["what_happened"] == "3 deleted"


async def test_empty_and_over_the_limit_are_refused(app_engine):
    async with _Tx(app_engine) as tx, _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
        assert (await ac.post(URL, json={"items": []})).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        many = {"items": [{"id": i + 1, "expected_revision": 1} for i in range(LIMIT + 1)]}
        refused = await ac.post(URL, json=many)
        assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert refused.json()["code"] == TOO_MANY_CODE and "200" in refused.json()["what_happened"]
        exactly = {"items": [{"id": i + 1, "expected_revision": 1} for i in range(LIMIT)]}
        assert (await ac.post(URL, json=exactly)).status_code == HTTPStatus.OK  # the limit itself is allowed


async def test_duplicate_ids_are_processed_once(app_engine):
    async with _Tx(app_engine) as tx:
        item = (await _items(tx.conn, [tx.strategy_id]))[0]
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": [item, item, item]})).json()
            assert out["deleted"] == [{"id": tx.strategy_id, "revision": item["expected_revision"]}]
            assert out["kept"] == [] and out["summary_text"]["what_happened"] == "1 deleted"


async def test_another_users_and_an_already_hidden_id_are_kept_not_found(app_engine):
    async with _Tx(app_engine) as tx:
        stranger = await _new_strategy(tx.conn, "test-someone-else", catalogue=False)
        gone = await _new_strategy(tx.conn, tx.user, catalogue=False)
        items = await _items(tx.conn, [stranger, gone, tx.strategy_id])
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            hidden = await ac.delete(f"/strategies/{gone}", params={"expected_revision": items[1]["expected_revision"]})
            assert hidden.status_code == HTTPStatus.OK
            out = (await ac.post(URL, json={"items": items})).json()
            assert [d["id"] for d in out["deleted"]] == [tx.strategy_id]
            assert {k["id"]: (k["reason"], k["text"]["what_happened"]) for k in out["kept"]} == {
                stranger: ("not_found", NOT_FOUND_TEXT), gone: ("not_found", NOT_FOUND_TEXT)}
        assert (await tx.conn.execute(RAW_ROW, {"id": stranger})).one().deleted_at is None


async def test_a_stale_revision_is_kept_changed(app_engine):
    async with _Tx(app_engine) as tx:
        other = await _new_strategy(tx.conn, tx.user, catalogue=False)
        items = await _items(tx.conn, [tx.strategy_id, other])
        items[0]["expected_revision"] += 5
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": items})).json()
            assert [d["id"] for d in out["deleted"]] == [other]
            assert [(k["id"], k["reason"], k["text"]["what_happened"]) for k in out["kept"]] == [
                (tx.strategy_id, "changed", CHANGED_TEXT)]
            assert out["summary_text"]["what_happened"] == f"1 deleted, 1 kept: {CHANGED_TEXT}"
        assert (await tx.conn.execute(RAW_ROW, {"id": tx.strategy_id})).one().deleted_at is None


async def test_one_item_raising_is_failed_the_others_deleted_and_the_error_logged(app_engine, monkeypatch, caplog):
    """Savepoint per item: the failing item first WRITES its hide, then raises; its write must be undone."""
    async with _Tx(app_engine) as tx:
        boom = await _new_strategy(tx.conn, tx.user, catalogue=False)
        real = store.delete_draft

        async def flaky(conn, user_ref, strategy_id, *, expected_revision):
            await real(conn, user_ref, strategy_id, expected_revision=expected_revision)
            if strategy_id == boom:
                raise RuntimeError("disk on fire")

        monkeypatch.setattr(store, "delete_draft", flaky)
        items = await _items(tx.conn, [boom, tx.strategy_id])
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            with caplog.at_level(logging.ERROR):
                out = (await ac.post(URL, json={"items": items})).json()
        assert [d["id"] for d in out["deleted"]] == [tx.strategy_id]
        assert [(k["id"], k["reason"], k["text"]["what_happened"]) for k in out["kept"]] == [
            (boom, "failed", FAILED_TEXT)]
        assert (await tx.conn.execute(RAW_ROW, {"id": boom})).one().deleted_at is None
        assert (await tx.conn.execute(RAW_ROW, {"id": tx.strategy_id})).one().deleted_at is not None
        assert "bulk delete: strategy" in caplog.text and "RuntimeError: disk on fire" in caplog.text  # with traceback


async def test_undo_per_deleted_id_restores_exactly_those(app_engine):
    """Undo of a batch = the existing undelete route, once per deleted id (no new route)."""
    async with _Tx(app_engine) as tx:
        ids, _held_id, _basket = await _fourteen(tx)
        items = await _items(tx.conn, ids)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            out = (await ac.post(URL, json={"items": items})).json()
            for d in out["deleted"]:
                back = await ac.post(f"/strategies/{d['id']}/undelete", params={"expected_revision": d["revision"]})
                assert back.status_code == HTTPStatus.OK
            assert sorted(s["id"] for s in (await ac.get("/strategies")).json()["strategies"]) == sorted(ids)


async def test_list_rows_carry_held_at_broker_from_one_batched_read(app_engine):
    async with _Tx(app_engine) as tx:
        held = await _new_strategy(tx.conn, tx.user, catalogue=False)
        await _held(tx.conn, held)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            rows = {s["id"]: s["held_at_broker"] for s in (await ac.get("/strategies")).json()["strategies"]}
        assert rows == {tx.strategy_id: False, held: True}


async def test_single_delete_of_a_held_strategy_says_held_not_orders_sent(app_engine):
    """S-03: before the fix a held strategy's refusal read 'Orders were already sent'."""
    async with _Tx(app_engine) as tx:
        await _held(tx.conn, tx.strategy_id)
        revision = await _revision(tx.conn, tx.strategy_id)
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            refused = await ac.delete(f"/strategies/{tx.strategy_id}", params={"expected_revision": revision})
        assert refused.status_code == HTTPStatus.CONFLICT
        assert refused.json()["what_happened"] == HELD_TEXT
