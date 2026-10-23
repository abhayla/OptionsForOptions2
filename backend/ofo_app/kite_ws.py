"""The live Kite WebSocket client (W-059, REQ-048). Feeds a ``KiteProvider``; places and sends no order, ever.

Connects to ``wss://ws.kite.trade?api_key=..&access_token=..``, subscribes in ``full`` mode (at most 3,000 tokens per
connection; more is REFUSED and logged, never cut to fit), and reconnects after any drop with backoff 1, 2, 4 ... 30 s,
re-subscribing everything the provider still wants (the numbers live in ``ofo.marketdata.reconnect_policy``, REQ-114).
Every answer state has one behaviour:

- binary data frame / heartbeat  -> ``provider.on_frame`` (which counts them); both are a frame of any kind
- text message (order update, other error) -> ``provider.on_text`` (counted by type, nothing stored)
- text message that is a token error -> the session has ended, no retry (REQ-114 AC-6)
- close, network error, HTTP error other than 403 -> ``provider.on_disconnected`` then back off and reconnect
- HTTP 403 on connect -> the session has ended (token expired or revoked): ``provider.on_session_ended``, no retry
- no frame of any kind for 60 s on an open socket -> closed, ``provider.on_disconnected``, back off, reconnect (AC-2);
  checked at least every 15 s on the CONNECTION, never on one contract's tick age (F-32, AC-1)
- outside market hours (calendar, ADR-119) silence is expected: the same close, but no more than one reconnect per 5 min
- unknown packet length / unsupported segment / cut-short frame -> counted by the provider, never raised

The URL carries the access token, so it is never logged: only generic messages and exception class names are
(the W-058 rule), and the library's own wire logger is replaced by a silent one.

This module is a network door (REQ-073 AC-4, ``NETWORK_DOORS`` in ``ofo.broker.kite_endpoints``): it alone may import
``websockets``, and its connect URL goes through ``ofo.broker.kite_http.check_ws_url`` when the socket is built and
again before EVERY connect (only ``wss://ws.kite.trade`` for a Kite host); a refusal propagates, it is never retried.
Only then, and only around the real ``websockets`` connect, is the runtime egress gate's door context open
(``ofo.broker.egress``); an injected ``connect`` (tests only) never gets it.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import random
import re
import sys
from collections.abc import AsyncIterator as _AsyncIterator
from collections.abc import Awaitable as _Awaitable
from collections.abc import Callable as _Callable

import websockets as _websockets
from ofo.broker import egress as _egress
from ofo.broker.kite_endpoints import KITE_WS_HOST as _KITE_WS_HOST
from ofo.broker.kite_http import check_ws_url as _check_ws_url
from ofo.broker.kite_http import plain_str as _plain_str
from ofo.market_calendar import next_open as _calendar_next_open
from ofo.marketdata.kite_provider import KiteProvider as _KiteProvider
from ofo.marketdata.reconnect_policy import BACKOFF_MAX, BACKOFF_START
from ofo.marketdata.reconnect_policy import CHECK_EVERY as _CHECK_EVERY
from ofo.marketdata.reconnect_policy import SILENT_AFTER as _SILENT_AFTER
from ofo.marketdata.reconnect_policy import Uniform as _Uniform
from ofo.marketdata.reconnect_policy import is_silent as _is_silent
from ofo.marketdata.reconnect_policy import next_backoff as _next_backoff
from ofo.marketdata.reconnect_policy import next_check as _next_check
from ofo.marketdata.reconnect_policy import reconnect_wait as _reconnect_wait
from websockets.asyncio.client import connect as _ws_connect
from websockets.exceptions import InvalidStatus as _InvalidStatus

from ofo_app.redaction import register_secret as _register_secret

_egress._trust_modules(_websockets, __file__)  # W-080 r9: the frames a real connect runs through
_egress.install()  # W-080 integration: importing a Kite door installs the gate (idempotent with create_app's)

_log = logging.getLogger("ofo_app.kite_ws")
_silent = logging.getLogger("ofo_app.kite_ws.wire")  # the library logs request lines (with the token) at DEBUG
_silent.propagate = False
_silent.addHandler(logging.NullHandler())
_silent.setLevel(logging.CRITICAL + 1)

KITE_WS_URL = f"wss://{_KITE_WS_HOST}"
MAX_TOKENS_PER_CONNECTION = 3000
MAX_CONNECTIONS_PER_KEY = 3  # per API key across ALL users of the app (F-59); the source is in order_limits_registry
SESSION_ENDED = "session ended"
STOPPED = "stopped"
_POLL_SECONDS = 0.5  # how often to look for subscription changes while the socket is quiet


class _Silent(Exception):
    pass


class _SessionEnded(Exception):
    pass


_SESSION_TOKEN_ERROR = re.compile(r"\b(?:TokenException|access[ _]token)\b", re.IGNORECASE)


def _is_token_error(message: str) -> bool:
    """A text frame that says the SESSION's token is no good: ``{"type": "error", "data": "TokenException: ..."}`` or
    an error naming the access token. An allow-list of those shapes (REQ-114 AC-6): any other text - an order update,
    another error ("Invalid instrument token 123"), text that is not JSON - is not, and never ends a session; an unknown
    error keeps reconnecting with back-off."""
    try:
        body = json.loads(message)
    except ValueError:
        return False
    return (isinstance(body, dict) and body.get("type") == "error" and isinstance(body.get("data"), str)
            and _SESSION_TOKEN_ERROR.search(body["data"]) is not None)


class KiteSocket:
    def __init__(self, provider: _KiteProvider, *, api_key: str, access_token: str,  # noqa: PLR0913
                 clock: _Callable[[], datetime.datetime], base_url: str = KITE_WS_URL,
                 connect: _Callable | None = None,
                 sleep: _Callable[[float], _Awaitable[None]] = asyncio.sleep,
                 on_reconnect: _Callable[[], _Awaitable[None]] | None = None,
                 user_ref: str = "unknown", rng: _Uniform | None = None,
                 market_open: _Callable[[datetime.datetime], bool] | None = None,
                 next_open: _Callable[[datetime.datetime], datetime.datetime | None] | None = None,
                 on_check: _Callable[[datetime.datetime], None] | None = None) -> None:
        self._provider = provider
        self._user_ref = user_ref  # logged with every disconnect / reconnect / recovery (REQ-114 AC-8); never a secret
        self._rng: _Uniform = rng or random.Random()  # noqa: S311 - jitter (AC-3), not a secret
        # ADR-119 calendar: closed hours expect silence (AC-7). The default is the provider's own feed answer
        # (``FeedState.market_closed``), the one market-state function; ``next_open`` caps the closed wait (REQ-114
        # AC-7). A test that injects ``market_open`` alone gets no next-open cap (its calendar is its own).
        self._market_open = market_open or (lambda now: not provider.feed.market_closed(now))
        self._next_open = next_open or (_calendar_next_open if market_open is None else (lambda _now: None))
        self._connected_at: datetime.datetime | None = None  # when THIS connection opened (back-off reset rule)
        self._on_check = on_check  # observer of each silence check (tests)
        self._stopped = asyncio.Event()
        self._last_frame: datetime.datetime | None = None  # the connection's newest frame of any kind, set at connect
        self._next_check: datetime.datetime | None = None
        self._down_since: datetime.datetime | None = None
        self._on_reconnect = on_reconnect  # REQ-015 AC-5: once per RE-connection, as its own task (see ``run``)
        self._reconnect_tasks: set[asyncio.Task] = set()
        for value in (api_key, access_token, base_url):  # plain data only (W-080 r9): a str subclass is caller code
            _plain_str(value, "the socket address parts")
        self._url = f"{base_url}?api_key={api_key}&access_token={access_token}"  # never logged
        _check_ws_url(self._url)  # refused before anything is held or opened
        _register_secret(api_key)  # W-024 r10: the held values are redacted from every log record
        _register_secret(access_token)
        self._clock = clock
        if connect is not None and not _egress._test_mode():  # the test seam: refused outside the test suites
            raise _egress.EgressRefused("the Kite socket takes an injected connect only inside the test suites")
        self._connect = connect or _ws_connect
        self._real_connect = connect is None  # door context only around the real websockets connect
        self._sleep = sleep
        self._stop = False
        self.connections = 0
        self._backoff: float = BACKOFF_START
        self.over_limit = 0  # instruments wanted beyond the per-connection cap right now (0 = within it)
        self.capped = False
        self._sent: set[int] = set()  # what Kite holds on THIS connection

    def stop(self) -> None:
        self._stop = True
        self._stopped.set()

    async def run(self) -> str:
        """Run until stopped or the session ends. Returns ``STOPPED`` or ``SESSION_ENDED``."""
        try:
            return await self._run()
        finally:
            for task in self._reconnect_tasks:
                task.cancel()

    async def _run(self) -> str:
        self._backoff = BACKOFF_START  # reset only by a data frame on a link up CHECK_EVERY, not by opening one
        while not self._stop:
            _check_ws_url(self._url)  # outside the try: a refusal ends the run, it is never retried
            try:
                async with self._opened() as ws:
                    self.connections += 1
                    await self._subscribe_all(ws)  # REQ-114 AC-4: every subscription is back BEFORE the link counts
                    now = self._clock()
                    self._provider.on_connected(now)
                    self._last_frame, self._next_check = now, _next_check(now, now)
                    self._connected_at = now
                    _log.info("kite socket connected: user=%s connection=%d at=%s", self._user_ref, self.connections,
                              now.isoformat())
                    self._start_reconnect_read()
                    await self._pump(ws)
            except _InvalidStatus as exc:
                if exc.response.status_code == 403:  # noqa: PLR2004
                    self._provider.on_session_ended(self._clock())
                    _log.warning("kite socket refused with 403: session ended: user=%s at=%s", self._user_ref,
                                 self._clock().isoformat())
                    return SESSION_ENDED
                self._dropped(type(exc).__name__)
            except _SessionEnded:
                self._provider.on_session_ended(self._clock())
                _log.warning("kite socket got a token error: session ended, no retry: user=%s at=%s", self._user_ref,
                             self._clock().isoformat())
                return SESSION_ENDED
            except _Silent:
                self._dropped(f"no frame of any kind for {int(_SILENT_AFTER.total_seconds())} s")
            except Exception as exc:  # network error, close, timeout: all handled the same way  # noqa: BLE001
                self._dropped(type(exc).__name__)
            else:
                self._dropped("closed")
            if self._stop:
                break
            now = self._clock()
            wait = _reconnect_wait(self._backoff, self._rng, market_open=self._market_open(now),
                                   until_open=self._seconds_until_open(now))
            _log.warning("kite socket reconnecting: user=%s attempt=%d wait=%.1fs at=%s", self._user_ref,
                         self.connections + 1, wait, now.isoformat())
            await self._sleep_or_stop(wait)
            self._backoff = _next_backoff(self._backoff)
        return STOPPED

    def _seconds_until_open(self, now: datetime.datetime) -> float | None:
        opens = self._next_open(now)
        return None if opens is None else (opens - now).total_seconds()

    async def _sleep_or_stop(self, seconds: float) -> None:
        """Wait ``seconds`` (the injected sleep), but return the moment ``stop`` is called: a 5-minute closed-market
        wait must not hold a stop for 5 minutes."""
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        stopper = asyncio.ensure_future(self._stopped.wait())
        try:
            await asyncio.wait({sleeper, stopper}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (sleeper, stopper):
                if not task.done():
                    task.cancel()
        if sleeper.done() and not sleeper.cancelled():
            sleeper.result()  # a failing sleep still propagates

    def _start_reconnect_read(self) -> None:
        """REQ-015 AC-5: after a RE-connection (not the first connect) run the owner's callback once, as its own task so
        the receive loop never waits on it (ticks keep flowing). One at a time: a read still running is not doubled.
        The callback is a Zerodha read; nothing here can place or submit an order."""
        if self._on_reconnect is None or self.connections < 2:  # noqa: PLR2004
            return
        if any(not t.done() for t in self._reconnect_tasks):
            return
        task = asyncio.get_running_loop().create_task(self._guarded_reconnect_read(), name="kite-reconnect-read")
        self._reconnect_tasks = {task}

    async def _guarded_reconnect_read(self) -> None:
        try:
            await self._on_reconnect()  # type: ignore[misc]
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a failed read never ends the socket; class name only
            _log.warning("kite reconnect read failed: %s", type(exc).__name__)

    @contextlib.asynccontextmanager
    async def _opened(self) -> _AsyncIterator[object]:
        """Open the socket; the egress gate's door context covers ONLY the opening handshake of the real connect,
        after ``check_ws_url`` passed in ``run``. Everything after (subscribe, pump, provider callbacks) runs
        outside."""
        if self._real_connect:  # no environment proxy: a proxy would be a second, unchecked host
            cm = self._connect(self._url, logger=_silent, open_timeout=10, proxy=None)
        else:
            cm = self._connect(self._url, logger=_silent, open_timeout=10)
        if self._real_connect:
            with _egress._door():
                ws = await cm.__aenter__()
        else:
            ws = await cm.__aenter__()
        try:
            yield ws
        except BaseException:
            if not await cm.__aexit__(*sys.exc_info()):
                raise
        else:
            await cm.__aexit__(None, None, None)

    def _dropped(self, reason: str) -> None:
        """AC-2 / AC-8: quotes are stale from this moment; the log line carries the user, the reason and the time."""
        now = self._clock()
        self._provider.on_disconnected(now)
        if self._down_since is None:
            self._down_since = now
        _log.warning("kite socket dropped: %s: user=%s at=%s", reason, self._user_ref, now.isoformat())

    def _recovered(self, now: datetime.datetime) -> None:
        if self._down_since is not None:
            _log.info("kite socket recovered: user=%s down_since=%s first_data_at=%s", self._user_ref,
                      self._down_since.isoformat(), now.isoformat())
            self._down_since = None

    def _health_check(self) -> None:
        """AC-1 / AC-2: the CONNECTION's last frame of any kind, checked at least every 15 s and at the 60 s mark."""
        now = self._clock()
        if self._next_check is None or self._last_frame is None or now < self._next_check:
            return
        if self._on_check is not None:
            self._on_check(now)
        if _is_silent(now, self._last_frame):
            raise _Silent
        self._next_check = _next_check(now, self._last_frame)

    def _refuse(self, wanted: int) -> None:
        """REQ-113 AC-6: more tokens wanted than one connection may carry. REFUSED (nothing sent, nothing cut to fit),
        logged by count only, and visible: ``capped`` / ``over_limit`` (the status the API shows)."""
        self.capped, self.over_limit = True, wanted - MAX_TOKENS_PER_CONNECTION
        _log.warning("kite subscription refused: %d instruments wanted, the cap is %d per connection",
                     wanted, MAX_TOKENS_PER_CONNECTION)

    async def _sync(self, ws) -> None:
        """Make Kite's subscription equal the wanted set, or refuse the whole request when it is over the cap."""
        wanted = set(self._provider.subscribed_tokens())
        if len(wanted) > MAX_TOKENS_PER_CONNECTION:
            self._refuse(len(wanted))
            return
        self.capped, self.over_limit = False, 0
        added, removed = sorted(wanted - self._sent), sorted(self._sent - wanted)
        if added:
            await ws.send(json.dumps({"a": "subscribe", "v": added}))
            await ws.send(json.dumps({"a": "mode", "v": ["full", added]}))
        if removed:
            await ws.send(json.dumps({"a": "unsubscribe", "v": removed}))
        self._sent = wanted

    async def _subscribe_all(self, ws) -> None:
        self._sent = set()  # a new connection holds nothing
        self._provider.drain_subscription_changes()  # everything wanted is synced below
        await self._sync(ws)

    async def _send_changes(self, ws) -> None:
        added, removed = self._provider.drain_subscription_changes()
        if added or removed:
            await self._sync(ws)

    async def _pump(self, ws) -> None:
        while not self._stop:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=_POLL_SECONDS)
            except TimeoutError:  # asyncio.TimeoutError is this builtin on Python 3.11+
                self._health_check()
                await self._send_changes(ws)
                continue
            if isinstance(message, bytes):
                now = self._clock()
                self._last_frame = now  # a tick or the 1-byte heartbeat: either proves the connection is alive
                if len(message) > 1:  # a data frame (not a heartbeat) proves the connection is useful
                    # ... but only a link that has STAYED up ``CHECK_EVERY`` resets the back-off: one frame then a
                    # drop, repeated, must not reconnect every 0.5-1 s forever (chunk 1 review F1 MINOR 2)
                    if self._connected_at is not None and now - self._connected_at >= _CHECK_EVERY:
                        self._backoff = BACKOFF_START
                    self._recovered(now)
                self._provider.on_frame(message, now)
            else:
                self._provider.on_text(message)
                if _is_token_error(message):
                    raise _SessionEnded
            self._health_check()
            await self._send_changes(ws)


__all__ = ["BACKOFF_MAX", "BACKOFF_START", "KITE_WS_URL", "MAX_CONNECTIONS_PER_KEY", "MAX_TOKENS_PER_CONNECTION",
           "SESSION_ENDED", "STOPPED", "KiteSocket"]
