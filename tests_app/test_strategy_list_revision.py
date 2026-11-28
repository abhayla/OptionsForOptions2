"""N-30: the list reply carries each row's saved revision, so Delete sends it with no per-row GET.

Spec basis: REQ-070 (single and bulk delete); ADR-330 (8). The stale-revision refusal stays with the server.
"""

from __future__ import annotations

from test_execution_plan_store import _new_strategy, _Tx
from test_strategy_delete_app import _revision
from test_strategy_followups import _ConnMaker
from test_strategy_store import _app, _client


async def test_list_rows_carry_the_saved_revision(app_engine):
    async with _Tx(app_engine) as tx:
        ids = [tx.strategy_id] + [await _new_strategy(tx.conn, tx.user, catalogue=False) for _ in range(2)]
        async with _client(_app(_ConnMaker(tx.conn), tx.user)) as ac:
            rows = (await ac.get("/strategies")).json()["strategies"]
            assert sorted(r["id"] for r in rows) == sorted(ids)
            for r in rows:
                assert r["revision"] == await _revision(tx.conn, r["id"])
                assert r["revision"] == (await ac.get(f"/strategies/{r['id']}")).json()["revision"]
