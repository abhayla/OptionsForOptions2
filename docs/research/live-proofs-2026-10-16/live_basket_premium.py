"""F-39 follow-up: 2-leg BUY basket (CE + PE) with limits above live; read Kite's per-leg option_premium. Read-only.
POST /margins/basket is a margin calculation, not an order. ofo_dev only."""
import asyncio
import json
import os
import urllib.request
from decimal import Decimal

from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"
LEGS = [("NIFTY26O1923550CE", "CE"), ("NIFTY26O1922750PE", "PE")]


def call(api_key, token, method, path, body=None):
    req = urllib.request.Request("https://api.kite.trade" + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Kite-Version": "3", "Authorization": f"token {api_key}:{token}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed Kite read-only URL
        return json.loads(r.read(), parse_float=Decimal)


async def main():
    cfg = load_broker_config()
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            token = await access_token_for(conn, "owner", TokenCipher(cfg.token_key))
        q = "&".join(f"i=NFO:{s}" for s, _ in LEGS)
        ltp = await asyncio.to_thread(call, cfg.api_key, token, "GET", "/quote/ltp?" + q)
        lt = {s: Decimal(str(ltp["data"][f"NFO:{s}"]["last_price"])) for s, _ in LEGS}
        orders = [{"exchange": "NFO", "tradingsymbol": s, "transaction_type": "BUY", "variety": "regular",
                   "product": "NRML", "order_type": "LIMIT", "quantity": 65, "price": float(lt[s] + Decimal("5"))}
                  for s, _ in LEGS]
        rep = await asyncio.to_thread(call, cfg.api_key, token, "POST", "/margins/basket?consider_positions=true", orders)
        after = await asyncio.to_thread(call, cfg.api_key, token, "GET", "/quote/ltp?" + q)
        d = rep["data"]
        print("final.total", d["final"]["total"], "initial.total", d["initial"]["total"])
        for o, (s, _) in zip(d["orders"], LEGS):
            lim = lt[s] + Decimal("5")
            print(s, "ltp", lt[s], "->", after["data"][f"NFO:{s}"]["last_price"], "limit", lim,
                  "option_premium", o.get("option_premium"), "total", o.get("total"),
                  "| 65xltp", 65 * lt[s], "65xlimit", 65 * lim)
    finally:
        await close_db()


asyncio.run(main())
