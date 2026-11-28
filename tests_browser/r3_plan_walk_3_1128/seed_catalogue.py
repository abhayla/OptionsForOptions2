"""Lane TC set-up: load the recorded instrument list into the THROWAWAY test database with every expiry moved forward
56 days (8 weeks keeps the weekday), so the contracts are live on 28 Nov 2026. Test database only; guarded loader.

    PYTHONPATH=backend APP_ENV=test DATABASE_URL=<owner url> python tests_browser/r2_1128/seed_catalogue.py
"""
import asyncio
import csv
import datetime
import io
import pathlib
import sys

from sqlalchemy import text

from ofo.timeutil import IST_UNNAMED as IST
from ofo_app.catalogue_load import run
from ofo_app.db import close_db, get_engine

SRC = pathlib.Path("tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv")


def shifted() -> str:
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    for r in rows:
        if r["expiry"]:
            r["expiry"] = (datetime.date.fromisoformat(r["expiry"]) + datetime.timedelta(days=56)).isoformat()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


async def main() -> int:
    async with get_engine().connect() as conn:
        held = (await conn.execute(text("SELECT count(*) FROM public.catalogue_contracts"))).scalar_one()
        if held:
            print(f"catalogue already holds {held} rows; nothing done")
            return 0
        code = await run(conn, shifted(), as_of=datetime.datetime(2026, 11, 27, 10, 0, tzinfo=IST))
        await (conn.commit() if code == 0 else conn.rollback())
        return code


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    finally:
        pass
