# Lane TD set-up: load the instrument rows of one or more scenarios into ofo_dev's catalogue through the guarded loader
# (catalogue_load.run), as of the earliest scenario day, so seed_scenario can link contracts. Several ids in one call because the
# loader refuses a list that drops more than 10 percent of the live contracts (ADR-058). Usage: python load_cat.py ADJ-02 ADJ-13 ADJ-08
import asyncio, csv, datetime, io, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from ofo_app import scenario_mode as sm
from ofo_app.catalogue_load import run
rows, seen, days = [], set(), []
for sid in sys.argv[1:]:
    scn = sm.read(sid); days.append(datetime.datetime.fromisoformat(scn["clock"]["ist"]))
    for r in sm._instrument_rows(scn, None)[0]:
        if r["tradingsymbol"] not in seen: seen.add(r["tradingsymbol"]); rows.append(r)
buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
as_of = min(days).replace(hour=9, minute=0)
async def main():
    eng = create_async_engine(os.environ["TD_ADMIN_DB_URL"])  # owner-role URL of the local ofo_dev, from the environment
    async with eng.connect() as conn:
        rc = await run(conn, buf.getvalue(), as_of=as_of); await conn.commit()
    print("rc", rc, "rows", len(rows), "as_of", as_of)
asyncio.run(main())
