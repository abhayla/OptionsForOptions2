"""GC-TP 5b: run the paper expiry settlement once on ofo_dev (the orchestrator's live proof).

Usage (after 15:45 IST on an expiry day):
    python scripts/orchestrator/dev_run.py <repo> python scripts/checks/settle_now.py [--dry-run]

Spec basis: REQ-109 AC-7 ("settles with a "settle" order at its intrinsic value from the official closing value of its
index that day"); F-72. Runs ``ofo_app.paper_settlement.settle_expired`` once with the real close reader (the index's
Kite DAY candle with the owner's cached token: one read-only call per (index, expiry) group). Refuses unless
DATABASE_URL names ofo_dev. ``--dry-run`` reads the closes and prints what would settle, writing nothing.

Prints one line per settled (or would-settle) contract and one per skipped group, never the token:
    settled strategy <id> contract <id> <SIDE> <qty> at <price> (<INDEX> <expiry>)
    skipped <INDEX> <expiry>: <reason>
    failed strategy <id>
"""
from __future__ import annotations

import asyncio
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
USAGE = "usage: settle_now.py [--dry-run]"


def refuse_unless_dev(database_url: str | None) -> None:
    if not database_url or not database_url.rstrip("/").endswith("/ofo_dev"):
        sys.exit("REFUSED: DATABASE_URL does not name ofo_dev (run through scripts/orchestrator/dev_run.py)")


def lines(run) -> list[str]:  # run: a paper_settlement.SettleRun (imported only after the dev check)
    out = [f"settled strategy {s.strategy_id} contract {s.contract_id} {s.side} {s.quantity} at {s.price} "
           f"({s.underlying} {s.expiry.isoformat()})" for s in run.settled]
    out += [f"skipped {k.underlying} {k.expiry.isoformat()}: {k.reason}" for k in run.skipped]
    out += [f"failed strategy {sid}" for sid in run.failed]
    return out or ["nothing to settle"]


async def settle(dry_run: bool) -> list[str]:
    from ofo_app import paper_settlement as ps  # noqa: PLC0415 - loads only after the dev-database check
    from ofo_app.db import get_engine  # noqa: PLC0415

    now = datetime.datetime.now(datetime.UTC)
    async with get_engine().connect() as conn:
        close_of = await ps.owner_close_of(conn)
        if conn.in_transaction():
            await conn.commit()
        if not dry_run:
            return lines(await ps.settle_expired(conn, now, close_of))
        trans = await conn.begin()  # the same code path, rolled back: nothing is written
        try:
            return ["DRY RUN (nothing written)", *lines(await ps.settle_expired(conn, now, close_of))]
        finally:
            await trans.rollback()


def main(argv: list[str]) -> int:
    refuse_unless_dev(os.environ.get("DATABASE_URL"))
    if argv not in ([], ["--dry-run"]):
        sys.exit(USAGE)
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    for line in asyncio.run(settle(argv == ["--dry-run"])):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
