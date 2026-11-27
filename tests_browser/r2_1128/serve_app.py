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
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(create_app(), host="127.0.0.1", port=port, loop="ofo_app.event_loop:selector_loop")
