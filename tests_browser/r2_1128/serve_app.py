"""Lane TC harness: the real app (create_app, real routes, real last-close seed task) with a market that has a book but
whose socket never delivers a tick, i.e. "the owner's session existed, the feed is stopped". No Kite call is made: the
socket is idle, no token is read, no periodic position read starts. Test database only.

    PYTHONPATH=backend:. LIVE_MARKET=1 APP_ENV=development python tests_browser/r2_1128/serve_app.py
"""
import asyncio
import sys

import uvicorn

from ofo_app import live_market
from ofo_app.main import create_app


class IdleSocket:
    """A socket that connected (as Kite's does on a weekend) and then receives no frame at all."""

    def __init__(self, provider, clock) -> None:
        self._provider, self._clock = provider, clock

    def stop(self) -> None:
        pass

    async def run(self) -> str:
        self._provider.on_connected(self._clock())
        await asyncio.sleep(10**6)
        return "stopped"


class IdleMarket(live_market.LiveMarket):
    async def start(self, broker_config) -> None:
        import datetime

        from ofo.marketdata.kite_provider import IST, KiteProvider
        from ofo_app import catalogue_store
        from ofo_app.db import get_engine

        self._config = broker_config
        async with get_engine().connect() as conn:
            catalogue = await catalogue_store.load_catalogue(conn)
        clock = lambda: datetime.datetime.now(IST)  # noqa: E731
        provider = KiteProvider(live_market.listed_for_kite(catalogue.all_entries()), clock=clock)
        self.attach(provider, IdleSocket(provider, clock), clock, None)


import os
if not os.environ.get("TC_PLAIN"):  # TC_PLAIN=1: the real LiveMarket, which finds no stored Zerodha session
    live_market.LiveMarket = IdleMarket
def _fake_zerodha(app) -> None:
    """TC_REAL=1 (item I-43): the Positions route's Zerodha reads are answered by a local fake: one net row, BUY 65 of
    NIFTY 24200 CE, avg 100.00, last 110.00, and the order row of the stored plan. No network, no order endpoint."""
    import json

    from ofo.execution.basket import make_tag
    from ofo_app.kite_reads import KiteReads
    from ofo_app.routes import execute as route

    sid = int(os.environ.get("TC_REAL_SID", "6"))
    row = {"tradingsymbol": "NIFTY26O1324200CE", "exchange": "NFO", "instrument_token": 11450370, "product": "NRML",
           "segment": "FO", "quantity": 65, "overnight_quantity": 0, "overnight_value": 0, "multiplier": 1,
           "average_price": "100.00", "close_price": 105, "last_price": "110.00", "value": "-6500", "pnl": "650",
           "m2m": "650", "unrealised": "650", "realised": 0, "buy_quantity": 65, "buy_price": "100.00",
           "buy_value": "6500", "buy_m2m": "6500", "sell_quantity": 0, "sell_price": 0, "sell_value": 0, "sell_m2m": 0,
           "day_buy_quantity": 65, "day_buy_price": "100.00", "day_buy_value": "6500", "day_sell_quantity": 0,
           "day_sell_price": 0, "day_sell_value": 0}
    order = {"placed_by": "XX0000", "account_id": "XX0000", "order_timestamp": "2026-11-27 10:15:00",
             "order_id": "261127000001", "exchange_order_id": "1400000000001", "parent_order_id": None,
             "status": "COMPLETE", "status_message": None, "status_message_raw": None,
             "exchange_update_timestamp": "2026-11-27 10:15:00", "exchange_timestamp": "2026-11-27 10:15:00",
             "variety": "regular", "modified": False, "auction_number": "", "exchange": "NFO",
             "tradingsymbol": "NIFTY26O1324200CE", "instrument_token": 11450370, "order_type": "LIMIT",
             "transaction_type": "BUY", "validity": "DAY", "validity_ttl": 0, "product": "NRML", "quantity": 65,
             "disclosed_quantity": 0, "price": "100.00", "trigger_price": 0, "average_price": "100.00",
             "filled_quantity": 65, "pending_quantity": 0, "cancelled_quantity": 0, "market_protection": 0,
             "meta_raw": None, "meta": {}, "tag": make_tag(sid, 1, 0), "tags": [make_tag(sid, 1, 0)], "guid": "tc"}

    def transport(method, url, headers, body):
        assert method == "GET" and body is None, (method, url)
        data = {"day": [row], "net": [row]} if url.endswith("/portfolio/positions") else [order]
        return 200, json.dumps({"status": "success", "data": data})

    reads = KiteReads(api_key="local-fake", access_token="local-fake", transport=transport)  # noqa: S106

    class _Session:
        api_key = "local-fake"
        margin = None  # nothing here can place an order

    _Session.reads = reads
    app.dependency_overrides[route.get_kite_session] = lambda: _Session()


if __name__ == "__main__":
    port = int(sys.argv[1])  # the port is an argument: nothing is written down here
    application = create_app()
    if os.environ.get("TC_REAL"):
        _fake_zerodha(application)
    uvicorn.run(application, host="127.0.0.1", port=port, loop="ofo_app.event_loop:selector_loop")
