"""The issue-65 repair tool (``scripts/repair_rule_entry_baseline.py``) on a throwaway DB: dry run counts the class and
writes nothing; ``--apply`` turns seen_clear on for exactly the rows NOT true at the real entry; held_at_entry and the
row count never change; a second run finds the class empty for those rows (re-runnable).

Setup: scenario ADJ-02 (iron condor, 23500 CE short), entry facts stored with a spot far from both shorts (T-01 false
at entry), and two stored rows held at entry, not seen clear: T-01 (false at entry -> repaired) and a rule the entry
cannot compute (T-03, short delta: no Greeks at entry -> left, counted).
"""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import test_background_worker as bw
from ofo.adjustment.approaches import EntryFacts
from ofo_app import entry_facts_store, playbook_store
from ofo_app.adjustment_readers import read_tracked
from sqlalchemy import text
from test_background_worker import app_db_url  # noqa: F401 - the fixture

TOOL = Path(__file__).resolve().parents[1] / "scripts" / "repair_rule_entry_baseline.py"
FAR_SPOT = Decimal("23000")  # 500 points under the 23500 CE: T-01 (within 0.5 %) is false at this entry


def _tool():
    found = importlib.util.spec_from_file_location("ofo_repair_rule_entry_baseline", TOOL)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def _rows(conn, sid: int) -> dict:
    rows = (await conn.execute(text("SELECT rule_id, held_at_entry, seen_clear FROM public.adjustment_rule_state "
                                    "WHERE strategy_id = :s AND adjustment_no = 0"), {"s": sid})).all()
    return {r[0]: (r[1], r[2]) for r in rows}


async def test_dry_run_counts_and_apply_repairs_only_rows_false_at_the_real_entry(app_db_url, monkeypatch):  # noqa: F811
    tool = _tool()
    sid, _scn = await bw._seeded(app_db_url, monkeypatch)

    async def position_of(strategy_id: int):
        tracked = await read_tracked(strategy_id, None)
        return None if tracked is None else tracked.position

    async with app_db_url.begin() as conn:
        await entry_facts_store.record_first(conn, sid, EntryFacts(FAR_SPOT, None, None))
        for rule in ("T-01", "T-03"):
            await playbook_store.put_rule_state(conn, "owner", sid, rule, held_at_entry=True, seen_clear=False)
    async with app_db_url.begin() as conn:
        dry = await tool.repair(conn, position_of, apply=False)
        assert await _rows(conn, sid) == {"T-01": (True, False), "T-03": (True, False)}  # dry run: nothing written
    print(f"REPAIR-DRY {dry}")
    assert {k: v for k, v in dry.items() if v} == {tool.HELD: 2, tool.FALSE_AT_ENTRY: 1, tool.NOT_COMPUTABLE: 1}
    async with app_db_url.begin() as conn:
        applied = await tool.repair(conn, position_of, apply=True)
    assert applied == dry
    async with app_db_url.begin() as conn:
        assert await _rows(conn, sid) == {"T-01": (True, True), "T-03": (True, False)}
        again = await tool.repair(conn, position_of, apply=False)
    print(f"REPAIR-AFTER {again}")
    assert {k: v for k, v in again.items() if v} == {tool.HELD: 1, tool.NOT_COMPUTABLE: 1}  # class 2 -> 1
