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
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
from collections.abc import Awaitable, Callable

from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import InvalidStatus

from ofo.marketdata.kite_provider import KiteProvider

log = logging.getLogger("ofo_app.kite_ws")
_silent = logging.getLogger("ofo_app.kite_ws.wire")  # the library logs request lines (with the token) at DEBUG
_silent.propagate = False
_silent.addHandler(logging.NullHandler())
_silent.setLevel(logging.CRITICAL + 1)

KITE_WS_URL = "wss://ws.kite.trade"
MAX_TOKENS_PER_CONNECTION = 3000
BACKOFF_START = 1
BACKOFF_MAX = 30
SESSION_ENDED = "session ended"
STOPPED = "stopped"
_POLL_SECONDS = 0.5  # how often to look for subscription changes while the socket is quiet


class KiteSocket:
    def __init__(self, provider: KiteProvider, *, api_key: str, access_token: str,
                 clock: Callable[[], datetime.datetime], base_url: str = KITE_WS_URL,
                 connect: Callable = ws_connect,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._provider = provider
        self._url = f"{base_url}?api_key={api_key}&access_token={access_token}"  # never logged
        self._clock = clock
        self._connect = connect
        self._sleep = sleep
        self._stop = False
        self.connections = 0
        self.over_limit = 0

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> str:
        """Run until stopped or the session ends. Returns ``STOPPED`` or ``SESSION_ENDED``."""
        backoff = BACKOFF_START
        while not self._stop:
            try:
                async with self._connect(self._url, logger=_silent, open_timeout=10) as ws:
                    self.connections += 1
                    backoff = BACKOFF_START
                    self._provider.on_connected(self._clock())
                    log.info("kite socket connected")
                    await self._subscribe_all(ws)
                    await self._pump(ws)
            except InvalidStatus as exc:
                if exc.response.status_code == 403:
                    self._provider.on_session_ended(self._clock())
                    log.warning("kite socket refused with 403: session ended")
                    return SESSION_ENDED
                self._dropped(type(exc).__name__)
            except Exception as exc:  # network error, close, timeout: all handled the same way
                self._dropped(type(exc).__name__)
            else:
                self._dropped("closed")
            if self._stop:
                break
            await self._sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
        return STOPPED

    def _dropped(self, reason: str) -> None:
        self._provider.on_disconnected(self._clock())
        log.warning("kite socket dropped: %s", reason)

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
            except asyncio.TimeoutError:
                await self._send_changes(ws)
                continue
            if isinstance(message, bytes):
                self._provider.on_frame(message, self._clock())
            else:
                self._provider.on_text(message)
            await self._send_changes(ws)
