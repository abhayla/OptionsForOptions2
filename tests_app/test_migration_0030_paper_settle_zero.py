"""GC-TP step 5b (REQ-109 AC-7): migration 0030 lets a paper `settle` order carry a price of 0 (an option expiring out
of the money) and settles a contract once per strategy (a unique index).

Spec basis (quoted): REQ-109 AC-7 "settles with a "settle" order at its intrinsic value from the official closing value
of its index that day". Real PostgreSQL only; every test rolls back. The round trip runs as the owner (admin_engine).
"""

from __future__ import annotations

import pytest
from _migration_replay import round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_migration_0028_paper_orders import _contracts, _privileges, _scalar
from test_strategy_store import _user, _with_draft

MIGRATION = "0030_paper_settle_zero.py"


async def _state(conn) -> dict:
    return {
        "check": await _scalar(conn, "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                                     "WHERE conname = 'paper_orders_price_check'"),
        "index": await _scalar(conn, "SELECT count(*) FROM pg_indexes WHERE indexname = 'paper_orders_settle_once'"),
        "grants": await _privileges(conn, "paper_orders"),
    }


async def _zero_settle(conn) -> None:
    _, stored = await _with_draft(conn, _user())
    contract = (await _contracts(conn))[0]
    await conn.execute(text("INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, "
                            "placed_at) VALUES (:s, :c, 'SELL', 65, 10.00, 'open', now()), "
                            "(:s, :c, 'BUY', 65, 0, 'settle', now())"), {"s": stored.id, "c": contract})


async def test_upgrade_relaxes_the_check_for_settle_only_and_adds_the_index_downgrade_restores(admin_engine):
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await _state(conn)
            assert "kind = 'settle'::text" in head["check"] and "price = (0)::numeric" in head["check"]
            assert head["index"] == 1
            for sql in down:
                await conn.execute(text(sql))
            before = await _state(conn)
            assert before["check"] == "CHECK ((price > (0)::numeric))"
            assert before["index"] == 0
            assert before["grants"] == head["grants"]  # no grant moves
            for sql in up:
                await conn.execute(text(sql))
            assert await _state(conn) == head
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_while_a_zero_price_settle_exists(admin_engine):
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _zero_settle(conn)
            with pytest.raises(DBAPIError, match=r"OF030|a paper settle order at a price of 0 exists"):
                async with conn.begin_nested():
                    for sql in own_down:
                        await conn.execute(text(sql))
            assert (await _state(conn))["index"] == 1
        finally:
            await trans.rollback()
