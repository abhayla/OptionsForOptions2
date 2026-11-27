# scratch: load the scenario's instrument rows into ofo_dev's catalogue (as_of the scenario clock) so seed_scenario can link contracts
import asyncio, csv, datetime, io, sys
from sqlalchemy.ext.asyncio import create_async_engine
from ofo_app import scenario_mode as sm
from ofo_app.catalogue_load import run
sid = sys.argv[1]
scn = sm.read(sid)
rows, _, _ = sm._instrument_rows(scn, None)
buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
as_of = datetime.datetime.fromisoformat(scn["clock"]["ist"]).replace(hour=9, minute=0)
async def main():
    eng = create_async_engine("postgresql+asyncpg://postgres:postgres_ci_dummy_pw@localhost:5432/ofo_dev")
    async with eng.connect() as conn:
        rc = await run(conn, buf.getvalue(), as_of=as_of)
        await conn.commit()
    print("rc", rc, "rows", len(rows))
asyncio.run(main())
