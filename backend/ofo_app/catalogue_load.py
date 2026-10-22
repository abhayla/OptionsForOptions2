"""One-shot command: load Zerodha's public instrument list into the catalogue (W-068 step 4).

    python -m ofo_app.catalogue_load

Spec basis: REQ-053 AC-2 and ADR-058/059 (the guarded update): the command only DOWNLOADS, PARSES and calls the existing
``apply_update`` unchanged, so every guard (truncated-list refusal per index and per expiry, retirement, identity
rules) applies exactly as for any other caller. The ADR-058 admin setting ``CATALOGUE_MAX_DELIST_PERCENT`` is read from
``ofo_app.config.Settings`` and passed explicitly. This command covers only "read the setting" of issue #126; the
Notifier alert and audit record for a refusal are not built here.

``as_of`` is the DATABASE clock (``clock_timestamp()``), never the application's. On success it commits and prints the
StoreUpdateResult counts; on a guard refusal it prints the refusal, writes nothing and exits non-zero. The scheduler
(``ofo_app.catalogue_refresh``, W-133) calls ``load_once`` and so applies every guard unchanged.
"""

from __future__ import annotations

import asyncio
import io
import sys
from datetime import datetime
from typing import Any, TextIO

from sqlalchemy import text

from ofo_app.catalogue_store import StoreUpdateResult, apply_update, parse_rows_naming_the_row

_NOW = text("SELECT clock_timestamp()")


def format_counts(result: StoreUpdateResult) -> str:
    return (f"catalogue updated: added={result.added} seen={result.seen} revised={result.revised} "
            f"newly_unlisted={result.newly_unlisted} retired={result.retired} delisted={result.delisted} "
            f"reinstated={result.reinstated}")


async def run(conn: Any, csv_text: str, settings: Any, out: TextIO | None = None, *,
              as_of: datetime | None = None) -> int:
    """Apply one downloaded list on ``conn``; returns the exit code. Never commits. A refusal (a guard, an unparseable
    row, a value the store cannot hold) is printed and returns 1 with nothing written (the work runs in a savepoint).
    ``as_of`` defaults to the database clock; only tests pass one."""
    out = out if out is not None else sys.stdout
    try:
        rows = parse_rows_naming_the_row(io.StringIO(csv_text))
        if as_of is None:
            as_of = (await conn.execute(_NOW)).scalar_one()
        async with conn.begin_nested():
            result = await apply_update(conn, rows, as_of=as_of,
                                        max_delist_percent=settings.CATALOGUE_MAX_DELIST_PERCENT)
    except ValueError as exc:  # CatalogueStoreError is a ValueError; so are the domain's truncation guards
        print(f"catalogue update REFUSED, nothing written: {exc}", file=out)
        return 1
    print(format_counts(result), file=out)
    return 0


async def load_once(settings: Any, out: TextIO | None = None) -> int:
    """Download today's list and apply it through ``run`` in one transaction (commit on 0, roll back otherwise). The
    shared body of the command and the scheduler (``ofo_app.catalogue_refresh``); the download goes through the Kite
    door (``ofo.broker.kite_http.open_url``, checked against ALLOWED_CALLS and the egress gate). A download failure
    raises (the caller logs its type only); a guard refusal returns 1."""
    from ofo.instruments.downloader import download_instruments_csv  # noqa: PLC0415 - kept off the import path
    from ofo_app.db import get_engine  # noqa: PLC0415

    csv_text = await asyncio.to_thread(download_instruments_csv)
    async with get_engine().connect() as conn:
        trans = await conn.begin()
        code = await run(conn, csv_text, settings, out)
        if code == 0:
            await trans.commit()
        else:
            await trans.rollback()
        return code


async def main() -> int:
    from ofo_app.config import get_settings  # noqa: PLC0415 - kept off the import path
    from ofo_app.db import close_db  # noqa: PLC0415

    settings = get_settings()
    try:
        return await load_once(settings)
    finally:
        await close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
