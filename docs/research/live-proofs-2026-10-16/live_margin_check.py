"""W-081 live proof: basket margin for 1 lot far-OTM NIFTY CE, then the margin verdict against live funds. ofo_dev only.
Reads only (POST /margins/basket is a margin calculation, not an order)."""
import asyncio
import os
from decimal import Decimal

from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine
from ofo_app.kite_margin import BasketOrder, KiteMargin, KiteMarginError, margin_verdict

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"
ORDER = BasketOrder(exchange="NFO", tradingsymbol="NIFTY26O1923550CE", transaction_type="BUY", product="NRML",
                    order_type="LIMIT", quantity=65, price=Decimal("5.00"))


async def main():
    cfg = load_broker_config()
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            token = await access_token_for(conn, "owner", TokenCipher(cfg.token_key), engine=engine)
        client = KiteMargin(api_key=cfg.api_key, access_token=token)
        try:
            basket = await asyncio.to_thread(client.fetch_basket_margin, [ORDER])
            print("POST /margins/basket: ok ->", basket)
        except KiteMarginError as exc:
            print("POST /margins/basket: refused, code", exc.code)
        verdict = await asyncio.to_thread(margin_verdict, client, [ORDER])
        print("margin_verdict ->", verdict)
    finally:
        await close_db()


asyncio.run(main())
