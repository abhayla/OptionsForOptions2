"""GC-TPD R-9: read-only report of strategies whose STORED name is wrapped in quote marks.

Usage: python scripts/orchestrator/dev_run.py <repo> python scripts/checks/strategy_name_quotes_report.py

Class: a stored name that starts AND ends with a quote mark (a pair wrapping the whole name). A name that merely
contains a quote (O"Neil) is not reported. Writes nothing; refuses unless DATABASE_URL names ofo_dev.
The quote marks seen in API replies come from the catalogue's UserText slot (strategy_name_shown), not from storage.
"""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QUOTES = "\"'" + "".join(chr(c) for c in (0x201C, 0x201D, 0x2018, 0x2019))


def wrapped(name: str | None) -> bool:
    """True when ``name`` is wrapped by a quote pair (at least two characters, first and last both quote marks)."""
    return isinstance(name, str) and len(name) >= 2 and name[0] in QUOTES and name[-1] in QUOTES  # noqa: PLR2004


def report(rows: list[tuple[int, str | None]]) -> list[str]:
    bad = [(i, n) for i, n in rows if wrapped(n)]
    return [f"quoted names: {len(bad)}", *[f"strategy {i} name {n!r}" for i, n in bad]]


async def fetch() -> list[tuple[int, str | None]]:
    from ofo_app.db import get_engine  # noqa: PLC0415 - loads only after the dev-database check
    from sqlalchemy import text  # noqa: PLC0415

    async with get_engine().connect() as conn:
        res = await conn.execute(text("SELECT id, name FROM public.strategies ORDER BY id"))
        rows = [(int(r.id), r.name) for r in res]
        await conn.rollback()
    return rows


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url or not url.rstrip("/").endswith("/ofo_dev"):
        sys.exit("REFUSED: DATABASE_URL does not name ofo_dev (run through scripts/orchestrator/dev_run.py)")
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    for line in report(asyncio.run(fetch())):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
