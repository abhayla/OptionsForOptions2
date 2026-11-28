"""Lane TC set-up for I-43: one strategy with a closed ENTRY plan whose fill (BUY 65 of NIFTY 24200 CE at 100.00) is stored
the way the app stores a real fill (execution_plan_store, pattern of tests_app/test_positions_route.py). Throwaway DB only.

    PYTHONPATH=backend:. DATABASE_URL=<owner url of ofo_tc> python tests_browser/r2_1128/seed_real.py
"""
import asyncio
import os
import sys
from decimal import Decimal

import httpx
from ofo.execution.basket import make_tag
from ofo_app import execution_plan_store as plans
from ofo_app.db import close_db, get_engine
from ofo_app.execution_plan_store import PlanFill, PlanOrder
from ofo_app.routes.broker import V1_OWNER_REF
from sqlalchemy import text

TOKEN, SYMBOL, PRICE = 44728, "NIFTY26O1324200CE", Decimal("100.00")


async def main() -> int:
    async with get_engine().connect() as conn:
        cid = (await conn.execute(text("select id from public.catalogue_contracts where exchange_token=:t and exchange_segment='NSE_FO'"), {"t": TOKEN})).scalar_one()
        await conn.rollback()
        r = httpx.post(os.environ["TC_API_BASE"] + "/strategies", json={"underlying": "NIFTY", "name": "TC Real Position",
                       "legs": [{"contract_id": cid, "action": "BUY", "quantity": 65}]}, timeout=30)
        sid = r.json()["id"]
        print("strategy", sid, r.status_code)
        tag = make_tag(sid, 1, 0)
        await plans.record_plan(conn, V1_OWNER_REF, sid, 1, "ENTRY", (PlanOrder(0, tag, f"NSE_FO:{TOKEN}", SYMBOL, "BUY", 65, PRICE),))
        await plans.close_plan(conn, V1_OWNER_REF, sid, 1, reason="filled", filled={tag: 65},
                               fills=(PlanFill(tag, f"ord-{tag}", "1", 65, PRICE),))
        await conn.commit()
        print("plan recorded and closed; tag", tag)
    await close_db()
    return sid


if __name__ == "__main__":
    asyncio.run(main())
