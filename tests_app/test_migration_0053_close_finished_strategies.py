"""Migration 0053 (GC-ICFIX; ADR-259, REQ-109 AC-7): a strategy fully exited or settled BEFORE 0049 made the store
write 'closed' still reads 'draft' (shown as "Running"); the settle job never revisits it (nothing left to settle).
0053 stores 'closed' for exactly those rows, by the same rule as ``paper_store.place``: at least one reducing order and
a net quantity of 0 on every contract. Rows with real broker orders and closed rows stay as they are; deleted rows are
closed too (ADR-293 Undo brings a deleted strategy back, and a finished one must not come back as "Running").

Real PostgreSQL as the owner role, every test rolls back. One row per case; the test asserts the exact ids that change,
and that the SQL rule equals the Python rule on every non-excluded case.
"""
from __future__ import annotations

import datetime
import importlib.util

import pytest
from _migration_replay import VERSIONS, own_step_sql
from ofo.tracking.orderbook import net_positions
from ofo_app import paper_store
from ofo_app import strategy_store as store
from sqlalchemy import text
from test_strategy_store import _saved_in, _user, _with_draft

MIGRATION = "0053_close_finished_strategies.py"
AT = datetime.datetime(2026, 11, 3, 15, 30, tzinfo=datetime.UTC)
_ORDER = text("INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at) "
              "VALUES (:s, :c, :side, :q, 10.00, :k, :t)")
_ROW = text("SELECT status, updated_at FROM public.strategies WHERE id = :s")
_STATUS = text("SELECT id FROM public.strategies WHERE id = ANY(:ids) AND status = 'closed' ORDER BY id")


@pytest.fixture
async def conn(admin_engine):
    async with admin_engine.connect() as c:
        outer = await c.begin()
        try:
            yield c
        finally:
            await outer.rollback()


async def _orders(c, sid: int, rows: list[tuple[int, str, int, str]]) -> None:
    for contract, side, qty, kind in rows:
        await c.execute(_ORDER, {"s": sid, "c": contract, "side": side, "q": qty, "k": kind, "t": AT})


async def _new(c, ids, user: str) -> tuple[int, int, int]:
    stored = await store.save_draft(c, user, await _saved_in(c, user, ids))
    c0, c1 = stored.saved.contract_ids[:2]
    return stored.id, c0, c1


async def _python_rule(c, sid: int) -> bool:
    """The rule of ``paper_store.place`` read back from the stored book: a reducing order and every net quantity 0."""
    book = [o.order.as_paper() for o in await paper_store.load(c, sid)]
    return bool(book) and any(o.kind in paper_store.REDUCING_KINDS for o in book) and not any(
        p.net_quantity for p in net_positions(book, {}).positions)


async def _cases(c) -> dict[str, int]:
    """One strategy per case; every one is 'draft' (what the old code left), except 'closed_before'."""
    ids, first = await _with_draft(c, _user())
    user = _user()
    out: dict[str, int] = {}

    async def make(name: str, orders) -> tuple[int, int, int]:
        sid, c0, c1 = (first.id, *first.saved.contract_ids[:2]) if not out else await _new(c, ids, user)
        await _orders(c, sid, orders(c0, c1))
        out[name] = sid
        return sid, c0, c1

    await make("a_settled", lambda a, b: [(a, "SELL", 65, "open"), (b, "SELL", 65, "open"),
                                          (a, "BUY", 65, "settle"), (b, "BUY", 65, "settle")])
    await make("b_hand_exited", lambda a, b: [(a, "SELL", 65, "open"), (b, "BUY", 65, "open"),
                                              (a, "BUY", 65, "exit"), (b, "SELL", 65, "exit")])
    await make("c_partly_exited", lambda a, b: [(a, "SELL", 130, "open"), (a, "BUY", 65, "exit")])
    await make("d_only_opening", lambda a, b: [(a, "SELL", 65, "open"), (a, "SELL", 65, "add")])
    await make("e_no_orders", lambda a, b: [])
    sid, *_ = await make("f_already_closed", lambda a, b: [(a, "SELL", 65, "open"), (a, "BUY", 65, "exit")])
    await c.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :s"), {"s": sid})
    await make("g_one_leg_still_open", lambda a, b: [(a, "SELL", 65, "open"), (b, "SELL", 65, "open"),
                                                     (a, "BUY", 65, "settle")])
    await make("h_one_leg_never_opened", lambda a, b: [(a, "SELL", 65, "open"), (a, "BUY", 65, "exit")])
    sid, *_ = await make("i_deleted", lambda a, b: [(a, "SELL", 65, "open"), (a, "BUY", 65, "exit")])
    await c.execute(text("UPDATE public.strategies SET deleted_at = clock_timestamp() WHERE id = :s"), {"s": sid})
    await c.execute(text("SELECT set_config('ofo.scenario_id', 'TEST-0053', true)"))
    await make("j_scenario", lambda a, b: [(a, "SELL", 65, "open"), (a, "BUY", 65, "exit")])
    await c.execute(text("SELECT set_config('ofo.scenario_id', '', true)"))
    # (m) open legs that cancel ACROSS contracts (c0 -65, c1 +65) with a reducing order somewhere: still open -> draft
    await make("m_open_legs_cancel_across_contracts", lambda a, b: [(a, "SELL", 130, "open"), (a, "BUY", 65, "exit"),
                                                                    (b, "BUY", 65, "open")])
    await make("n_ends_on_stop", lambda a, b: [(a, "SELL", 65, "open"), (a, "BUY", 65, "stop")])
    sid, *_ = await make("k_real_orders", lambda a, b: [(a, "SELL", 65, "open"), (a, "BUY", 65, "exit")])
    await c.execute(text("INSERT INTO public.execution_plans (strategy_id, plan_number, action) "
                         "VALUES (:s, 1, 'ENTRY')"), {"s": sid})
    sid, *_ = await make("k2_adopted_holding", lambda a, b: [(a, "SELL", 65, "open"), (a, "BUY", 65, "exit")])
    await c.execute(text("INSERT INTO public.adopted_holdings (strategy_id, instrument_id, transaction_type, quantity, "
                         "product, average_price, reference, version_number) "
                         "VALUES (:s, 'NFO:1', 'SELL', 65, 'NRML', 10.5, 'ref-0053', 1)"), {"s": sid})
    return out


async def _closed(c, cases: dict[str, int]) -> set[str]:
    rows = (await c.execute(_STATUS, {"ids": list(cases.values())})).scalars().all()
    return {n for n, sid in cases.items() if sid in rows}


async def test_exactly_the_finished_paper_strategies_become_closed_and_a_second_run_changes_nothing(conn):
    cases = await _cases(conn)
    assert await _closed(conn, cases) == {"f_already_closed"}
    before_closed = (await conn.execute(_ROW, {"s": cases["f_already_closed"]})).one()
    up = own_step_sql(MIGRATION)[1]
    changed = (await conn.execute(text(up[0]))).rowcount
    # (a) settled (b) hand-exited (h) a leg never opened (i) deleted (j) scenario (n) stop; the rest is untouched
    assert await _closed(conn, cases) == {"a_settled", "b_hand_exited", "h_one_leg_never_opened", "i_deleted",
                                          "j_scenario", "n_ends_on_stop", "f_already_closed"}
    assert "m_open_legs_cancel_across_contracts" not in await _closed(conn, cases)
    assert changed == 6  # noqa: PLR2004 - the fresh test database holds only this test's rows
    assert (await conn.execute(_ROW, {"s": cases["f_already_closed"]})).one() == before_closed  # (f) untouched
    again = (await conn.execute(text(up[0]))).rowcount
    assert again == 0  # (l) idempotent


async def test_the_sql_rule_equals_the_python_rule_on_every_case_without_an_exclusion(conn):
    cases = await _cases(conn)
    await conn.execute(text(own_step_sql(MIGRATION)[1][0]))
    closed = await _closed(conn, cases)
    excluded = {"f_already_closed", "k_real_orders", "k2_adopted_holding"}
    for name, sid in cases.items():
        if name not in excluded:
            assert (name in closed) == await _python_rule(conn, sid), name
    assert closed.isdisjoint({"k_real_orders", "k2_adopted_holding"})  # (k) kept as they were


def test_the_migration_names_the_same_reducing_kinds_as_the_store():
    found = importlib.util.spec_from_file_location("m0053", VERSIONS / MIGRATION)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    assert frozenset(module.REDUCING_KINDS) == paper_store.REDUCING_KINDS
