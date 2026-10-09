"""Live market data inside the running app (W-065 step 1; REQ-048 AC-1, AC-4; REQ-035 AC-4).

When ``LIVE_MARKET`` is on, the lifespan reads the owner's active Kite session (W-058, ``access_token_for``), builds one
``KiteProvider`` over the stored catalogue, wraps it in one ``FanOut`` (one vendor subscription per instrument, however
many screens watch it) and runs ``KiteSocket`` as a background task. ``get_market_context()`` then answers with it.
No session -> no context ("Draft - Live data not connected", unchanged). A 403 on the socket (session ended) ends the
task; the provider's feed state then reports the session as ended, so every quote shows a not-live health.

The access token lives only in the socket's URL string and in the redaction registry; this module never logs, prints or
stores it. Only generic messages and exception class names are logged.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import os
from decimal import Decimal
from typing import Callable, Optional

from ofo.instruments.models import ZERODHA, ListedContract
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app.live_push import LiveFeed
from ofo_app.routes.outcome import MarketContext

log = logging.getLogger("ofo_app.live_market")

OWNER_REF = "owner"  # ADR-051 V1 single user; the same ref the W-058 login stores the session under
LIVE_RATE = Decimal("0.065")  # the risk-free rate the replay uses too; a rates source is a later item
REAL_KITE_WS = "wss://ws.kite.trade"

NOT_STARTED, NOT_CONNECTED, LIVE, SESSION_ENDED = "off", "not_connected", "live", "session_ended"


class LiveRefused(RuntimeError):
    """LIVE_MARKET was requested under APP_ENV=test with the real Kite address."""


def live_requested() -> bool:
    return os.environ.get("LIVE_MARKET", "").strip().lower() in {"1", "true", "yes", "on"}


def require_safe(app_env: str, ws_url: str) -> None:
    if app_env == "test" and ws_url.startswith(REAL_KITE_WS):
        raise LiveRefused("LIVE_MARKET under APP_ENV=test needs a KITE_WS_URL that is not the real Kite")


def listed_for_kite(entries) -> list[ListedContract]:
    """The listed catalogue entries that have a Zerodha row, as the provider's master."""
    return [ListedContract(contract=e.contract, broker_refs=tuple(e.broker_refs.values()))
            for e in entries if e.currently_listed and e.has_ref(ZERODHA)]


class LiveMarket:
    def __init__(self) -> None:
        self.state = NOT_STARTED
        self.feed: Optional[LiveFeed] = None
        self._socket = None
        self._task: Optional[asyncio.Task] = None

    def context(self) -> Optional[MarketContext]:
        return None if self.feed is None else self.feed.ctx

    def attach(self, provider: KiteProvider, socket, clock: Callable[[], datetime.datetime]) -> None:
        """Wires an already built provider + socket (the real start and the tests share this)."""
        self.feed = LiveFeed(MarketContext(provider, clock, LIVE_RATE), FanOut(provider))
        self._socket = socket
        self.state = LIVE
        self._task = asyncio.get_running_loop().create_task(self._run(), name="kite-socket")

    async def _run(self) -> None:
        try:
            result = await self._socket.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never the message: it could hold the socket URL
            log.error("kite socket task failed: %s", type(exc).__name__)
            self.state = SESSION_ENDED
            return
        if result == "session ended":
            self.state = SESSION_ENDED
            log.warning("live market data stopped: the Kite session has ended")

    async def start(self, broker_config) -> None:
        """Real start: needs the database and the owner's stored session."""
        from ofo_app import catalogue_store
        from ofo_app.broker_crypto import TokenCipher
        from ofo_app.broker_token_store import access_token_for
        from ofo_app.config import get_settings
        from ofo_app.db import get_engine
        from ofo_app.kite_ws import KiteSocket

        engine = get_engine()
        cipher = TokenCipher(broker_config.token_key)
        async with engine.connect() as conn:
            token = await access_token_for(conn, OWNER_REF, cipher, engine=engine)
            if token is None:
                self.state = NOT_CONNECTED
                log.warning("live market data: no active Kite session; connect through the login first")
                return
            catalogue = await catalogue_store.load_catalogue(conn)

        def clock() -> datetime.datetime:
            return datetime.datetime.now(IST)

        provider = KiteProvider(listed_for_kite(catalogue.all_entries()), clock=clock)
        socket = KiteSocket(provider, api_key=broker_config.api_key, access_token=token, clock=clock,
                            base_url=get_settings().KITE_WS_URL)
        del token
        self.attach(provider, socket, clock)
        log.info("live market data started")

    async def stop(self) -> None:
        if self._socket is not None:
            self._socket.stop()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None


_current: Optional[LiveMarket] = None


def set_current(market: Optional[LiveMarket]) -> None:
    global _current
    _current = market


def current_context() -> Optional[MarketContext]:
    return None if _current is None else _current.context()


def current_feed() -> Optional[LiveFeed]:
    return None if _current is None else _current.feed
