"""GC-TPD R-37: read-only check that no paper exit/settle/stop is dated before the first open/add of its contract.

Usage: python scripts/orchestrator/dev_run.py <repo> python scripts/checks/paper_orders_order_check.py

Class: every (strategy, contract) whose exit/settle/stop row has placed_at strictly earlier than the first open/add
row of that contract (a migrated order book that lost its order). Equal times are not a violation. Writes nothing;
refuses unless DATABASE_URL names ofo_dev. Prints the count, then one line per violation.
"""
from __future__ import annotations

import asyncio
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPENING = frozenset({"open", "add"})
CLOSING = frozenset({"exit", "settle", "stop"})
Row = tuple[int, int, str, datetime.datetime]  # strategy_id, contract_id, kind, placed_at


def violations(rows: list[Row]) -> list[tuple[int, int, str, datetime.datetime, datetime.datetime]]:
    """Pure decision: closing rows strictly earlier than the first opening row of the same (strategy, contract)."""
    first_open: dict[tuple[int, int], datetime.datetime] = {}
    for sid, cid, kind, at in rows:
        if kind in OPENING and ((sid, cid) not in first_open or at < first_open[(sid, cid)]):
            first_open[(sid, cid)] = at
    return [(sid, cid, kind, at, first_open[(sid, cid)]) for sid, cid, kind, at in rows
            if kind in CLOSING and (sid, cid) in first_open and at < first_open[(sid, cid)]]


def report(bad: list) -> list[str]:
    return [f"violations: {len(bad)}", *[
        f"violation strategy {s} contract {c} {k} at {a.isoformat()} before first open at {o.isoformat()}"
        for s, c, k, a, o in bad]]


async def fetch() -> list[Row]:
    from ofo_app.db import get_engine  # noqa: PLC0415 - loads only after the dev-database check
    from sqlalchemy import text  # noqa: PLC0415

    async with get_engine().connect() as conn:
        res = await conn.execute(text("SELECT strategy_id, contract_id, kind, placed_at FROM public.paper_orders "
                                      "ORDER BY strategy_id, id"))
        rows = [(int(r.strategy_id), int(r.contract_id), r.kind, r.placed_at) for r in res]
        await conn.rollback()
    return rows


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url or not url.rstrip("/").endswith("/ofo_dev"):
        sys.exit("REFUSED: DATABASE_URL does not name ofo_dev (run through scripts/orchestrator/dev_run.py)")
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    for line in report(violations(asyncio.run(fetch()))):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
