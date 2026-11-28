# ruff: noqa: F811 - the imported fixture is used as a test argument
"""Lane R1 stage 1 (28 Nov 2026; ADR-330 (58), owner: "the tag never changes"): the position tag is a STORED fact
(``strategy_position_tags``, migration 0063), written once and never updated; ``kinds_of`` reads it. Real PostgreSQL,
rolled back. Spec basis: ADR-330 (73), (58). Answer states: draft (no tag), paper, real by Execute, real by held
entry, an order with no tag stored yet."""
from __future__ import annotations

import datetime

import pytest
from _migration_replay import round_trip_sql
from ofo.marketdata.kite_provider import IST
from ofo_app import strategy_store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_exit_door_real_fd3 import _held_book, _sent_basket
from test_paper_adjustment_limit import _book
from test_paper_save_paths_fx2 import db  # noqa: F401 - fixture

MIGRATION = "0063_position_tags.py"
AT = datetime.datetime(2026, 11, 27, 11, 0, tzinfo=IST)
_TAG = text("SELECT tag FROM public.strategy_position_tags WHERE strategy_id = :i")
_ORDER = text("INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at) "
              "VALUES (:s, :c, :side, 65, 39.15, :kind, :at)")
_RECORD = text("INSERT INTO public.real_action_records (user_ref, strategy_id, action, legs) "
               "VALUES (:u, :s, :action, CAST('[]' AS JSONB))")


async def _tag(db, sid: int):
    return (await db.execute(_TAG, {"i": sid})).scalar()


async def _kind(db, sid: int) -> str:
    return (await strategy_store.kinds_of(db, [sid]))[sid]


async def test_a_draft_has_no_tag_and_reads_none(db):
    from test_strategy_tracking import _setup  # noqa: PLC0415
    _a, draft, *_ = await _setup(db)
    assert await _kind(db, draft.id) == "none"
    assert await _tag(db, draft.id) is None


async def test_the_first_paper_order_stores_paper_once(db):
    _app, stored, _ids = await _book(db, max_adjustments=2)
    assert await _tag(db, stored.id) == "paper"
    assert await _kind(db, stored.id) == "paper"


async def test_a_sent_basket_stores_real_when_first_read_and_keeps_it(db):
    _app, stored, _ids = await _sent_basket(db)
    assert await _tag(db, stored.id) is None  # nothing wrote it yet
    assert await _kind(db, stored.id) == "real"
    assert await _tag(db, stored.id) == "real"
    assert await _kind(db, stored.id) == "real"


async def test_an_order_with_no_tag_and_no_derivation_fails_closed(db, monkeypatch):
    """An unreadable claim (a database refusal) is never read as a kind: the read raises."""
    _app, stored, _ids = await _sent_basket(db)

    async def refused(*_a, **_k):
        raise DBAPIError("x", {}, Exception("no"))
    monkeypatch.setattr(strategy_store, "claim_tag", refused)
    with pytest.raises(DBAPIError):
        await strategy_store.kinds_of(db, [stored.id])


@pytest.mark.parametrize("kind", ["open", "add", "exit", "stop", "settle"])
async def test_the_tag_never_flips_on_a_stored_paper_order_of_any_kind(db, kind):
    """The guard test: a real strategy, then every kind of stored order row: kind and tag unchanged."""
    _app, stored, ids = await _sent_basket(db)
    assert await _kind(db, stored.id) == "real"
    await db.execute(_ORDER, {"s": stored.id, "c": ids[0], "side": "SELL", "kind": kind, "at": AT})
    assert await _kind(db, stored.id) == "real"
    assert await _tag(db, stored.id) == "real"


@pytest.mark.parametrize("action", ["open", "add", "exit", "stop", "stop_fired"])
async def test_the_tag_never_flips_on_a_stored_record_of_any_action(db, action):
    _app, stored, _ids = await _sent_basket(db)
    assert await _kind(db, stored.id) == "real"
    await db.execute(_RECORD, {"u": stored.user_ref, "s": stored.id, "action": action})
    assert await _kind(db, stored.id) == "real"
    assert await _tag(db, stored.id) == "real"


async def test_a_held_entry_is_real_though_its_basket_stored_paper_first(db):
    _app, stored, _ids = await _held_book(db)
    assert await _tag(db, stored.id) == "paper"  # written once at the first paper order, in the same transaction
    assert await _kind(db, stored.id) == "real"  # a held entry (ADR-292) is a real position
    assert await _tag(db, stored.id) == "paper"  # and the stored tag is untouched


async def test_a_second_claim_never_changes_the_stored_tag(db):
    _app, stored, _ids = await _book(db, max_adjustments=2)
    assert await strategy_store.claim_tag(db, stored.id, "real") == "paper"
    assert await _tag(db, stored.id) == "paper"


@pytest.mark.parametrize("sql", ["UPDATE public.strategy_position_tags SET tag = 'real' WHERE strategy_id = :s",
                                 "DELETE FROM public.strategy_position_tags WHERE strategy_id = :s",
                                 "UPDATE public.real_action_records SET reason = 'x' WHERE strategy_id = :s",
                                 "DELETE FROM public.real_action_records WHERE strategy_id = :s"])
async def test_the_app_role_cannot_update_or_delete_a_tag_or_a_record(db, sql):
    _app, stored, _ids = await _sent_basket(db)
    await _kind(db, stored.id)
    await db.execute(_RECORD, {"u": stored.user_ref, "s": stored.id, "action": "exit"})
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql), {"s": stored.id})


async def test_the_owner_cannot_change_them_either_the_guard_refuses(admin_engine):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _app, stored, _ids = await _sent_basket(conn)
            await _kind(conn, stored.id)
            await conn.execute(_RECORD, {"u": stored.user_ref, "s": stored.id, "action": "exit"})
            for sql in ("UPDATE public.strategy_position_tags SET tag = 'paper' WHERE strategy_id = :s",
                        "UPDATE public.real_action_records SET action = 'add' WHERE strategy_id = :s"):
                with pytest.raises(DBAPIError, match="insert-only"):
                    async with conn.begin_nested():
                        await conn.execute(text(sql), {"s": stored.id})
        finally:
            await trans.rollback()


async def test_a_record_has_no_broker_column_and_one_stop_fired_per_trigger(db):
    cols = {r[0] for r in await db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'real_action_records'"))}
    assert cols == {"id", "user_ref", "strategy_id", "action", "legs", "reason", "trigger_id", "request_key",
                    "stored_at", "created_at"}
    _app, stored, _ids = await _sent_basket(db)
    fired = text("INSERT INTO public.real_action_records (user_ref, strategy_id, action, legs, trigger_id) "
                 "VALUES (:u, :s, 'stop_fired', CAST('[]' AS JSONB), 7)")
    await db.execute(fired, {"u": stored.user_ref, "s": stored.id})
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(fired, {"u": stored.user_ref, "s": stored.id})


async def test_the_migration_round_trips_and_refuses_a_downgrade_with_a_record(admin_engine):
    from _migration_replay import recorded  # noqa: PLC0415
    own_down = recorded(MIGRATION, "downgrade")
    _, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1]
    exists = text("SELECT to_regclass('public.real_action_records') IS NOT NULL")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _app, stored, _ids = await _sent_basket(conn)
            await conn.execute(_RECORD, {"u": stored.user_ref, "s": stored.id, "action": "exit"})
            with pytest.raises(DBAPIError, match="refusing downgrade"):
                async with conn.begin_nested():
                    for sql in own_down:
                        await conn.execute(text(sql))
        finally:
            await trans.rollback()
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            assert (await conn.execute(exists)).scalar() is False
            for sql in up:
                await conn.execute(text(sql))
            assert (await conn.execute(exists)).scalar() is True
        finally:
            await trans.rollback()


async def test_the_backfill_rule_matches_the_old_derivation(db):
    """held -> real; a paper order -> paper; a plan only -> real (the claim's SQL is the migration's)."""
    _app, held, _ = await _held_book(db)
    _a, paper, _i = await _book(db, max_adjustments=2)
    _b, sent, _j = await _sent_basket(db)
    for sid, want in ((held.id, "real"), (paper.id, "paper"), (sent.id, "real")):
        got = (await db.execute(text(
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM public.strategy_held_entries h WHERE h.strategy_id = :s) "
            "THEN 'real' "
            "WHEN EXISTS (SELECT 1 FROM public.paper_orders o WHERE o.strategy_id = :s) THEN 'paper' "
            "WHEN EXISTS (SELECT 1 FROM public.execution_plans p WHERE p.strategy_id = :s) THEN 'real' END"),
            {"s": sid})).scalar()
        assert got == want
