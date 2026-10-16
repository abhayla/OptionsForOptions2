"""The live Kite WebSocket client (W-059, REQ-048). Feeds a ``KiteProvider``; places and sends no order, ever.

Connects to ``wss://ws.kite.trade?api_key=..&access_token=..``, subscribes in ``full`` mode (at most 3,000 tokens per
connection), and reconnects after any drop with backoff 1, 2, 4 ... 30 s, re-subscribing everything the provider
still wants. Every answer state has one behaviour:

- binary data frame / heartbeat  -> ``provider.on_frame`` (which counts them)
- text message (order update, error) -> ``provider.on_text`` (counted by type, nothing stored)
- close, network error, HTTP error other than 403 -> ``provider.on_disconnected`` then back off and reconnect
- HTTP 403 on connect -> the session has ended (token expired or revoked): ``provider.on_session_ended``, no retry
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
import sys
from collections.abc import AsyncIterator as _AsyncIterator
from collections.abc import Awaitable as _Awaitable
from collections.abc import Callable as _Callable

from ofo.broker import egress as _egress
from ofo.broker.kite_endpoints import KITE_WS_HOST as _KITE_WS_HOST
from ofo.broker.kite_http import check_ws_url as _check_ws_url
from ofo.marketdata.kite_provider import KiteProvider as _KiteProvider
from websockets.asyncio.client import connect as _ws_connect
from websockets.exceptions import InvalidStatus as _InvalidStatus

from ofo_app.redaction import register_secret as _register_secret

_log = logging.getLogger("ofo_app.kite_ws")
_silent = logging.getLogger("ofo_app.kite_ws.wire")  # the library logs request lines (with the token) at DEBUG
_silent.propagate = False
_silent.addHandler(logging.NullHandler())
_silent.setLevel(logging.CRITICAL + 1)

KITE_WS_URL = f"wss://{_KITE_WS_HOST}"
MAX_TOKENS_PER_CONNECTION = 3000
BACKOFF_START = 1
BACKOFF_MAX = 30
SESSION_ENDED = "session ended"
STOPPED = "stopped"
_POLL_SECONDS = 0.5  # how often to look for subscription changes while the socket is quiet


class KiteSocket:
    def __init__(self, provider: _KiteProvider, *, api_key: str, access_token: str,  # noqa: PLR0913
                 clock: _Callable[[], datetime.datetime], base_url: str = KITE_WS_URL,
                 connect: _Callable | None = None,
                 sleep: _Callable[[float], _Awaitable[None]] = asyncio.sleep) -> None:
        self._provider = provider
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
        self._backoff = BACKOFF_START
        self.over_limit = 0

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> str:
        """Run until stopped or the session ends. Returns ``STOPPED`` or ``SESSION_ENDED``."""
        self._backoff = BACKOFF_START  # reset only by the first data frame of a connection, not by opening one
        while not self._stop:
            _check_ws_url(self._url)  # outside the try: a refusal ends the run, it is never retried
            try:
                async with self._opened() as ws:
                    self.connections += 1
                    self._provider.on_connected(self._clock())
                    _log.info("kite socket connected")
                    await self._subscribe_all(ws)
                    await self._pump(ws)
            except _InvalidStatus as exc:
                if exc.response.status_code == 403:  # noqa: PLR2004
                    self._provider.on_session_ended(self._clock())
                    _log.warning("kite socket refused with 403: session ended")
                    return SESSION_ENDED
                self._dropped(type(exc).__name__)
            except Exception as exc:  # network error, close, timeout: all handled the same way  # noqa: BLE001
                self._dropped(type(exc).__name__)
            else:
                self._dropped("closed")
            if self._stop:
                break
            await self._sleep(self._backoff)
            self._backoff = min(self._backoff * 2, BACKOFF_MAX)
        return STOPPED

    @contextlib.asynccontextmanager
    async def _opened(self) -> _AsyncIterator[object]:
        """Open the socket; the egress gate's door context covers ONLY the opening handshake of the real connect,
        after ``check_ws_url`` passed in ``run``. Everything after (subscribe, pump, provider callbacks) runs
        outside."""
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
        self._provider.on_disconnected(self._clock())
        _log.warning("kite socket dropped: %s", reason)

    async def _subscribe_all(self, ws) -> None:
        tokens = self._provider.subscribed_tokens()
        if len(tokens) > MAX_TOKENS_PER_CONNECTION:
            self.over_limit += len(tokens) - MAX_TOKENS_PER_CONNECTION
            tokens = tokens[:MAX_TOKENS_PER_CONNECTION]
        self._provider.drain_subscription_changes()  # everything wanted is sent below
        if tokens:
            await ws.send(json.dumps({"a": "subscribe", "v": tokens}))
            await ws.send(json.dumps({"a": "mode", "v": ["full", tokens]}))

    async def _send_changes(self, ws) -> None:
        added, removed = self._provider.drain_subscription_changes()
        if added:
            await ws.send(json.dumps({"a": "subscribe", "v": added}))
            await ws.send(json.dumps({"a": "mode", "v": ["full", added]}))
        if removed:
            await ws.send(json.dumps({"a": "unsubscribe", "v": removed}))

    async def _pump(self, ws) -> None:
        while not self._stop:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=_POLL_SECONDS)
            except TimeoutError:  # asyncio.TimeoutError is this builtin on Python 3.11+
                await self._send_changes(ws)
                continue
            if isinstance(message, bytes):
                if len(message) > 1:  # a data frame (not a heartbeat) proves the connection is useful
                    self._backoff = BACKOFF_START
                self._provider.on_frame(message, self._clock())
            else:
                self._provider.on_text(message)
            await self._send_changes(ws)


__all__ = ["BACKOFF_MAX", "BACKOFF_START", "KITE_WS_URL", "MAX_TOKENS_PER_CONNECTION", "SESSION_ENDED", "STOPPED",
           "KiteSocket"]
