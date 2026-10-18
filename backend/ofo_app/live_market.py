"""Live market data inside the running app (W-065 step 1; REQ-048 AC-1, AC-4; REQ-035 AC-4).

When ``LIVE_MARKET`` is on, the lifespan reads the owner's active Kite session (W-058, ``access_token_for``), builds one
``KiteProvider`` over the stored catalogue, wraps it in one ``FanOut`` (one vendor subscription per instrument, however
many screens watch it) and runs ``KiteSocket`` as a background task. ``get_market_context()`` then answers with it.
No session -> no context ("Draft — Live data not connected", unchanged). A 403 on the socket (session ended) ends the
task; the provider's feed state then reports the session as ended, so every quote shows a not-live health.
#296: a Kite login stored by the callback while the app runs calls ``pick_up_login``; a market that is not running
(not_connected, session_ended) stops its old socket and starts again from the new session, under one lock, so two
logins never make two sockets and a login while live leaves the running socket alone.

The access token lives only in the socket's URL string and in the redaction registry; this module never logs, prints or
stores it. Only generic messages and exception class names are logged.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import functools
import hashlib
import logging
import os
from decimal import Decimal
from typing import Callable, Optional  # noqa: UP035

from ofo.broker.kite_endpoints import KITE_WS_HOST
from ofo.engine.executable_price import Depth
from ofo.instruments.models import ZERODHA, ListedContract
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.kite_provider import IST, KiteProvider

from ofo_app.config import app_env, get_settings
from ofo_app.kite_margin import KiteMargin, urllib_transport
from ofo_app.kite_reads import KiteReads
from ofo_app.live_push import LiveFeed
from ofo_app.outcome_margin import CALL_TIMEOUT_SECONDS, OutcomeMargin
from ofo_app.routes.outcome import MarketContext, server_now

log = logging.getLogger("ofo_app.live_market")

OWNER_REF = "owner"  # ADR-051 V1 single user; the same ref the W-058 login stores the session under
LIVE_RATE = Decimal("0.065")  # the risk-free rate the replay uses too; a rates source is a later item
REAL_KITE_WS = f"wss://{KITE_WS_HOST}"

NOT_STARTED, NOT_CONNECTED, LIVE, SESSION_ENDED = "off", "not_connected", "live", "session_ended"


def token_fingerprint(token: str) -> bytes:
    """A non-reversible stand-in for a token (#296): tells two sessions apart without keeping the token.
    Memory only; never logged, printed or stored."""
    return hashlib.sha256(token.encode("utf-8")).digest()


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
        self.feed: Optional[LiveFeed] = None  # noqa: UP045
        self._socket = None
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()  # one start/stop at a time: never two sockets (#296)
        self._closed = False  # set by the app shutdown; a login after it starts nothing
        self._fingerprint: bytes | None = None  # token_fingerprint of the running socket's token; never logged
        self._config = None  # the broker config of the last start, for the one re-read after a session ends
        self._recheck: asyncio.Task | None = None

    def context(self) -> Optional[MarketContext]:  # noqa: UP045
        return None if self.feed is None else self.feed.ctx

    def attach(self, provider: KiteProvider, socket, clock: Callable[[], datetime.datetime],
               fingerprint: bytes | None = None) -> None:
        """Wires an already built provider + socket (the real start and the tests share this). ``fingerprint`` is
        ``token_fingerprint`` of the token the socket was built with (#296), None when unknown."""
        self.feed = LiveFeed(MarketContext(provider, clock, LIVE_RATE), FanOut(provider))
        self._socket = socket
        self._fingerprint = fingerprint
        self.state = LIVE
        self._task = asyncio.get_running_loop().create_task(self._run(), name="kite-socket")

    async def _run(self) -> None:
        try:
            result = await self._socket.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never the message: it could hold the socket URL  # noqa: BLE001
            log.error("kite socket task failed: %s", type(exc).__name__)
            self._session_ended()
            return
        if result == "session ended":
            log.warning("live market data stopped: the Kite session has ended")
            self._session_ended()

    def _session_ended(self) -> None:
        """#296 (b): the socket ended; a login may have stored a fresh session meanwhile (in the reconnect backoff,
        or while the dead socket still looked live). Re-read the stored session ONCE for this ended socket."""
        self.state = SESSION_ENDED
        if self._config is None or self._closed:
            return
        self._recheck = asyncio.get_running_loop().create_task(self._recheck_after_end(self._fingerprint),
                                                               name="kite-session-recheck")

    async def _recheck_after_end(self, dead: bytes | None) -> None:
        async with self._lock:
            if self._closed or self.state != SESSION_ENDED or self._fingerprint != dead:
                return  # closed, or another login already restarted the market
            await self._restart_if_new(self._config, skip_if=dead, after="the Kite session ended")

    async def start(self, broker_config) -> None:
        """Real start: needs the database and the owner's stored session."""
        self._config = broker_config
        token = await self._stored_token(broker_config)
        if token is None:
            self.state = NOT_CONNECTED
            log.warning("live market data: no active Kite session; connect through the login first")
            return
        await self._launch(broker_config, token)
        del token
        log.info("live market data started")

    async def _stored_token(self, broker_config) -> str | None:
        from ofo_app.broker_crypto import TokenCipher
        from ofo_app.broker_token_store import access_token_for
        from ofo_app.db import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            return await access_token_for(conn, OWNER_REF, TokenCipher(broker_config.token_key), engine=engine)

    async def _launch(self, broker_config, token: str) -> None:
        from ofo_app import catalogue_store
        from ofo_app.db import get_engine
        from ofo_app.kite_ws import KiteSocket

        async with get_engine().connect() as conn:
            catalogue = await catalogue_store.load_catalogue(conn)

        def clock() -> datetime.datetime:
            return datetime.datetime.now(IST)

        provider = KiteProvider(listed_for_kite(catalogue.all_entries()), clock=clock)
        socket = KiteSocket(provider, api_key=broker_config.api_key, access_token=token, clock=clock,
                            base_url=get_settings().KITE_WS_URL)
        self.attach(provider, socket, clock, token_fingerprint(token))

    def running(self) -> bool:
        return self.state == LIVE and self._task is not None and not self._task.done()

    async def pick_up_login(self, broker_config) -> None:
        """#296: called after a login stored a session. Restarts from the stored session unless the socket is
        running on that same session. Never raises: a failure is logged by class name only."""
        async with self._lock:
            if self._closed:
                return
            self._config = broker_config
            await self._restart_if_new(broker_config, skip_if=self._fingerprint if self.running() else None,
                                       after="the new Kite login")

    async def _restart_if_new(self, broker_config, *, skip_if: bytes | None, after: str) -> None:
        """Under the lock. Reads the stored session; when its fingerprint is ``skip_if`` (or there is none) nothing
        changes. Otherwise the old socket is stopped and awaited, then one new socket starts on the stored session.
        A failure before the halt leaves the running socket alone; after it, the state is ``not_connected``."""
        halted = False
        try:
            require_safe(app_env() or "", get_settings().KITE_WS_URL)
            token = await self._stored_token(broker_config)
            if token is None or (skip_if is not None and token_fingerprint(token) == skip_if):
                if token is None and not self.running():
                    self.state = NOT_CONNECTED
                return
            await self._halt()
            halted = True
            self.feed, self._socket, self._fingerprint = None, None, None
            await self._launch(broker_config, token)
            del token
        except Exception as exc:  # noqa: BLE001 - the login stands; never the message (token, socket URL)
            if halted or not self.running():
                self.state = NOT_CONNECTED
            log.error("live market data did not start after %s: %s", after, type(exc).__name__)
            return
        log.info("live market data restarted after %s", after)

    async def stop(self) -> None:
        async with self._lock:
            await self._halt()

    async def close(self) -> None:
        """App shutdown: stop the socket and any pending re-read, and refuse any later pick-up."""
        self._closed = True
        recheck, self._recheck = self._recheck, None
        if recheck is not None and recheck is not asyncio.current_task():
            recheck.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await recheck
        await self.stop()

    async def _halt(self) -> None:
        if self._socket is not None:
            self._socket.stop()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None


_current: Optional[LiveMarket] = None  # noqa: UP045


def set_current(market: Optional[LiveMarket]) -> None:  # noqa: UP045
    global _current  # noqa: PLW0603
    _current = market


def current_context() -> Optional[MarketContext]:  # noqa: UP045
    return None if _current is None else _current.context()


def latest_depth(instrument_id: str) -> Depth | None:
    """ADR-080 (3): the live 5-level depth of one instrument for the Execute price, or None when there is no live
    market, no full frame, or the feed is not healthy. The live socket subscribes in ``full`` mode (kite_ws.py)."""
    ctx = current_context()
    if ctx is None:
        return None
    reader = getattr(ctx.provider, "latest_depth", None)  # a provider without depth (the test replay) has none
    return None if reader is None else reader(instrument_id, ctx.clock())


def current_state() -> str:
    """W-089: the live market's state word for the Settings page (``off`` when LIVE_MARKET is not on)."""
    return NOT_STARTED if _current is None else _current.state


async def stop_current() -> None:
    """W-089 Disconnect (ADR-020 Q94): stop the running socket and mark the market not connected. Nothing when no
    market was registered (LIVE_MARKET off). A later login restarts it through ``pick_up_login``."""
    market = _current
    if market is None:
        return
    await market.stop()
    market.feed, market._socket, market._fingerprint = None, None, None
    market.state = NOT_CONNECTED


def current_feed() -> Optional[LiveFeed]:  # noqa: UP045
    return None if _current is None else _current.feed


def current_session() -> tuple[str, bytes | None] | None:
    """ADR-099: the live Kite session as (user, the running socket's token fingerprint - never the token), or None
    when none is live (not started, not connected, ended, or the test replay). The outcome margin reads Zerodha only
    with one, and keys its cache by it, so a new login never shows the old session's figures. An unknown fingerprint
    is None: the margin is then read but never cached (two unknown sessions never share figures)."""
    if _current is None or not _current.running():
        return None
    fingerprint = _current._fingerprint  # the module's own market object
    return OWNER_REF, fingerprint


async def owner_margin_client() -> KiteMargin | None:
    """ADR-099: the owner's margin client from the stored session (the same read the socket start uses), or None."""
    market = _current
    if market is None or market._config is None:
        return None
    token = await market._stored_token(market._config)
    if token is None:
        return None
    # each call bounded so the worker thread never outlives the outcome read timeout
    transport = functools.partial(urllib_transport, timeout=CALL_TIMEOUT_SECONDS)
    return KiteMargin(api_key=market._config.api_key, access_token=token, transport=transport)


async def owner_kite_reads() -> tuple[str, KiteReads] | None:
    """W-095: (api key, the owner's Zerodha read client) from the stored session - the same read as
    ``owner_margin_client`` - or None when not connected. The token never leaves this module."""
    market = _current
    if market is None or market._config is None:
        return None
    token = await market._stored_token(market._config)
    if token is None:
        return None
    transport = functools.partial(urllib_transport, timeout=CALL_TIMEOUT_SECONDS)
    api_key = market._config.api_key
    return api_key, KiteReads(api_key=api_key, access_token=token, transport=transport)


@functools.cache
def margin_source() -> OutcomeMargin:
    """The running app's one margin reader: one plan-keyed cache for the REST route and every live push."""
    return OutcomeMargin(current_session, owner_margin_client, clock=server_now)


async def pick_up_login(broker_config) -> None:
    """#296: the login callback's hook. Nothing unless LIVE_MARKET is on and the lifespan registered a market."""
    market = _current
    if market is None or not live_requested():
        return
    await market.pick_up_login(broker_config)
