"""The live strategy push (W-065 step 2; ADR-068, REQ-035 AC-4, REQ-048 AC-4). Framework-free.

One :class:`StrategyPush` serves one browser connection. The client sends an ``OutcomeRequest`` (the REST route's model);
the push subscribes the legs' instruments and the underlying index on the shared fan-out, then at most once every
``MIN_PUSH_INTERVAL`` seconds, and only if a quote of an input instrument changed since the last push, it sends the
outcome from :func:`ofo_app.routes.outcome.outcome_response` (the same function the REST route returns). A new client
message replaces the strategy. When the connection ends, everything it subscribed is released.

The channel is a two-method adapter (``receive`` / ``send``) so this logic is tested without a socket. Bad input is
answered with one catalogue message (``user_input_request_invalid``), never free text. The access token is never here.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from pydantic import ValidationError

from ofo.errors import render
from ofo.marketdata.fanout import FanOut
from ofo_app.routes.outcome import MarketContext, OutcomeRequest, outcome_response

MIN_PUSH_INTERVAL = 1.0  # ADR-068: at most once a second per strategy
POLL_SECONDS = 0.05


class ChannelClosed(Exception):
    """The browser connection ended."""


class Channel(Protocol):
    async def receive(self) -> Any: ...  # one client message; ChannelClosed when the connection ends

    async def send(self, body: dict) -> None: ...


@dataclass(frozen=True)
class LiveFeed:
    ctx: MarketContext
    fanout: FanOut


def _input_state(quote) -> tuple:
    return (quote.ltp, quote.bid, quote.ask, quote.health)


class StrategyPush:
    def __init__(self, channel: Channel, feed: Optional[LiveFeed], *, monotonic: Callable[[], float],
                 poll: float = POLL_SECONDS) -> None:
        self._channel = channel
        self._feed = feed
        self._monotonic = monotonic
        self._poll = poll
        self._req: Optional[OutcomeRequest] = None
        self._handle: Optional[int] = None
        self._seen: dict[str, tuple] = {}
        self._dirty = False
        self._last_push: Optional[float] = None
        self.pushes = 0

    # ---- the input listener (called by the fan-out pump) --------------------------------------------------
    def _on_quote(self, quote) -> None:
        state = _input_state(quote)
        if self._seen.get(quote.instrument_id) != state:
            self._seen[quote.instrument_id] = state
            self._dirty = True

    def _release(self) -> None:
        if self._handle is not None and self._feed is not None:
            self._feed.fanout.unsubscribe(self._handle)
        self._handle = None

    def _input_ids(self, req: OutcomeRequest) -> list[str]:
        ids = [leg.instrument_id for leg in req.legs]
        index_id = getattr(self._feed.ctx.provider, "index_id", lambda _u: None)(req.underlying)
        return ids + ([index_id] if index_id else [])

    async def _error(self) -> None:
        await self._channel.send(render("user_input_request_invalid").as_dict())

    async def _replace(self, raw: Any) -> None:
        try:
            req = OutcomeRequest.model_validate(raw)
        except ValidationError:
            await self._error()
            return
        new_handle = None
        if self._feed is not None:
            try:
                new_handle = self._feed.fanout.subscribe(self._on_quote, self._input_ids(req))
            except KeyError:  # an instrument the catalogue does not know: nothing was subscribed
                await self._error()
                return
        self._release()  # after the new subscription, so a shared instrument is never dropped and re-added
        self._handle, self._req, self._seen = new_handle, req, {}
        self._dirty, self._last_push = True, None  # the first answer is sent at once: it is the baseline

    async def _push(self) -> None:
        self._dirty = False
        try:
            body = outcome_response(self._req, None if self._feed is None else self._feed.ctx).model_dump(
                mode="json", exclude_unset=True)
        except Exception:  # a path we did not expect: one fixed message, the exception is not shown
            await self._error()
            return
        await self._channel.send(body)
        self.pushes += 1
        self._last_push = self._monotonic()

    async def run(self) -> None:
        recv: Optional[asyncio.Future] = None
        try:
            while True:
                if recv is None:
                    recv = asyncio.ensure_future(self._channel.receive())
                done, _ = await asyncio.wait({recv}, timeout=self._poll)
                if done:
                    task, recv = recv, None
                    try:
                        raw = task.result()
                    except ChannelClosed:
                        return
                    await self._replace(raw)
                if self._handle is not None:
                    self._feed.fanout.pump_one(self._handle)
                if self._req is not None and self._dirty and (
                        self._last_push is None or self._monotonic() - self._last_push >= MIN_PUSH_INTERVAL):
                    await self._push()
        finally:
            if recv is not None:
                recv.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await recv
            self._release()
