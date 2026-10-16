"""Measure: does Kite's basket margin for an option BUY use the LIMIT price or the live price? Read-only. ofo_dev only."""
import asyncio
import json
import os
import urllib.request
from decimal import Decimal

from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine
from ofo_app.kite_margin import BasketOrder, KiteMargin

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"
SYM = "NIFTY26O1923550CE"


def ltp(api_key, token):
    req = urllib.request.Request(f"https://api.kite.trade/quote/ltp?i=NFO:{SYM}",
                                 headers={"X-Kite-Version": "3", "Authorization": f"token {api_key}:{token}"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed Kite read-only quote URL
        return Decimal(str(json.loads(r.read(), parse_float=Decimal)["data"][f"NFO:{SYM}"]["last_price"]))


async def main():
    cfg = load_broker_config()
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            token = await access_token_for(conn, "owner", TokenCipher(cfg.token_key), engine=engine)
        client = KiteMargin(api_key=cfg.api_key, access_token=token)
        for price in (Decimal("5.00"), Decimal("10.00"), Decimal("0.50")):
            before = await asyncio.to_thread(ltp, cfg.api_key, token)
            m = await asyncio.to_thread(client.fetch_basket_margin, [BasketOrder(
                exchange="NFO", tradingsymbol=SYM, transaction_type="BUY", product="NRML", order_type="LIMIT",
                quantity=65, price=price)])
            after = await asyncio.to_thread(ltp, cfg.api_key, token)
            print(f"limit {price}: margin {m.final_total} = 65 x {m.final_total / 65}; ltp before {before} after {after}")
    finally:
        await close_db()


asyncio.run(main())
