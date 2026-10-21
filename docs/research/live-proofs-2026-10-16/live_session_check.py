"""Read the stored Kite session from ofo_dev and prove it with GET /user/margins (W-081 live proof). Run via dev_run.py."""
import asyncio
import os

from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine
from ofo_app.kite_margin import KiteMargin, KiteMarginError

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"


async def main():
    cfg = load_broker_config()
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            token = await access_token_for(conn, "owner", TokenCipher(cfg.token_key))
        print("stored session:", "yes" if token else "NO")
        if not token:
            return
        client = KiteMargin(api_key=cfg.api_key, access_token=token)
        try:
            funds = await asyncio.to_thread(client.fetch_available_funds)
            print("GET /user/margins: ok, equity.net type", type(funds).__name__, "value", funds)
        except KiteMarginError as exc:
            print("GET /user/margins: refused, code", exc.code)
    finally:
        await close_db()


asyncio.run(main())
