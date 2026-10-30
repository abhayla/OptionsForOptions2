"""The live strategy push (W-065 step 2; ADR-068, REQ-035 AC-4, REQ-048 AC-4). Framework-free.

One :class:`StrategyPush` serves one browser connection. The client sends an ``OutcomeRequest`` (the REST route's model);
the push subscribes the legs' instruments and the underlying index on the shared fan-out, then at most once every
``MIN_PUSH_INTERVAL`` seconds, and only if a quote of an input instrument changed since the last push, it sends the
outcome from :func:`ofo_app.routes.outcome.outcome_response` (the same function the REST route returns). A new client
message with a CHANGED strategy replaces it (still at most one push a second);
an identical one changes nothing. When the connection ends, everything it subscribed is released.

The channel is a two-method adapter (``receive`` / ``send``) so this logic is tested without a socket; in the app it is
the door's ``ClosedSocket`` (ofo_app.errors), which mints every message from the model with ``emit``. Bad input is
answered with one catalogue message (``user_input_request_invalid``), never free text. The access token is never here.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from ofo.errors import UserFacingError, render
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import is_live_price
from ofo.outcome.snapshot import forward_strike_ids
from pydantic import ValidationError

from ofo_app.errors import SocketClosed
from ofo_app.outcome_margin import OutcomeMargin
from ofo_app.outcome_oi import hold_ids as oi_hold_ids
from ofo_app.routes.outcome import (
    BookedReader,
    ContractLookup,
    MarketContext,
    OutcomeRequest,
    get_booked,
    get_booked_reader,
    get_contract_lookup,
    get_margin_source,
    load_charge_rates,
    margin_for_request,
    outcome_response,
    stored_legs_for,
)
from ofo_app.underlying import refusal_of

MIN_PUSH_INTERVAL = 1.0  # ADR-068: at most once a second per strategy
POLL_SECONDS = 0.05


ChannelClosed = SocketClosed  # the browser connection ended (the door socket raises it)


class Channel(Protocol):
    async def receive(self) -> Any: ...  # one client message; ChannelClosed when the connection ends

    async def send(self, source: Any) -> None: ...  # an OutcomeResponse or a catalogue message; the door mints it


@dataclass(frozen=True)
class LiveFeed:
    ctx: MarketContext
    fanout: FanOut


def _input_state(quote) -> tuple:
    return (quote.ltp, quote.bid, quote.ask, quote.health)


def no_listener(_quote: Any) -> None:
    """The forward strikes' holder: reads take the provider's current quotes; a forward tick alone pushes nothing."""


class StrategyPush:
    def __init__(self, channel: Channel, feed: Optional[LiveFeed], *,  # noqa: PLR0913 - one seam per collaborator
                 monotonic: Callable[[], float],
                 poll: float = POLL_SECONDS, lookup: Optional[ContractLookup] = None,
                 margin_source: Optional[OutcomeMargin] = None,
                 booked_reader: BookedReader | None = None) -> None:
        self._channel = channel
        # GC-LIVE R-26 (ADR-209): the follow message may carry a what-if target and a paper strategy; each push then
        # reads that strategy's booked P&L with the REST route's own reader, so its target block equals the REST answer
        self._booked_reader = booked_reader if booked_reader is not None else get_booked_reader()
        # ADR-099: the app's one plan-keyed margin cache, shared with the REST route: a tick re-push reads no margin
        self._margin_source = margin_source if margin_source is not None else get_margin_source()
        self._feed = feed
        self._monotonic = monotonic
        self._poll = poll
        self._lookup = lookup or get_contract_lookup()  # the stored catalogue, for the no-provider answer (#259)
        self._req: Optional[OutcomeRequest] = None
        self._handle: Optional[int] = None
        self._forward_handle: Optional[int] = None  # D-C33: the strikes nearest the money of each leg expiry
        self._oi_handle: Optional[int] = None  # REQ-083 AC-5: the OI bars' strikes over the reply's range
        self._oi_ids: tuple[str, ...] = ()
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

    def _release_forward(self, handle: Optional[int]) -> None:
        if handle is not None and self._feed is not None:
            self._feed.fanout.unsubscribe(handle)

    def _hold_forward(self, req: OutcomeRequest) -> Optional[int]:
        """D-C33: hold the strikes nearest the money of every leg expiry (``forward_strike_ids``) so the chain the
        outcome hands ``parity_forward`` has ADR-061's 3+ two-sided strikes; with only the legs held the live chain
        snapshot (the book of subscribed contracts) fell back to spot while the chain was live. A separate handle with
        no listener (a forward tick alone does not drive a push; the legs and the index do), max_queue 1 like the
        picker's leases. A contract the provider does not know holds nothing (the legs' own answer is unchanged)."""
        provider = self._feed.ctx.provider
        spot = provider.underlying_quote(req.underlying)
        live_spot = spot.ltp if spot is not None and is_live_price(spot.ltp) else None
        ids = forward_strike_ids(provider.instrument_master(), req.underlying,
                                 [leg.instrument_id for leg in req.legs], live_spot)
        if not ids:
            return None
        try:
            return self._feed.fanout.subscribe(no_listener, ids, max_queue=1)
        except KeyError:
            return None

    def _hold_oi(self, req: OutcomeRequest, body: Any) -> None:
        """REQ-083 AC-5: hold the contracts of the OI bars of the reply just sent (its scenario range, the strategy's
        expiry), so the next push carries their OI. Swapped new-first (a shared contract is never dropped and re-added),
        released when the follow message stops asking for OI and when the socket ends (``run``'s finally). A changed
        set marks the strategy dirty: the next push (the 1 s gate still holds) reads the newly held contracts."""
        if self._feed is None:
            return
        ids: tuple[str, ...] = ()
        if req.open_interest:
            ids = tuple(oi_hold_ids(self._feed.ctx.provider, req.underlying, [leg.instrument_id for leg in req.legs],
                                    body.model_dump(mode="json")))
        if ids == self._oi_ids:
            return
        new_handle = None
        if ids:
            try:
                new_handle = self._feed.fanout.subscribe(no_listener, list(ids), max_queue=1)
            except KeyError:  # a contract the provider does not know: hold nothing (the reply says not streaming)
                new_handle = None
        self._release_forward(self._oi_handle)
        self._oi_handle, self._oi_ids = new_handle, ids if new_handle is not None else ()
        if new_handle is not None:
            self._dirty = True

    def _input_ids(self, req: OutcomeRequest) -> list[str]:
        ids = [leg.instrument_id for leg in req.legs]
        index_id = getattr(self._feed.ctx.provider, "index_id", lambda _u: None)(req.underlying)
        return ids + ([index_id] if index_id else [])

    async def _error(self, message: UserFacingError | None = None) -> None:
        await self._channel.send(message or render("user_input_request_invalid"))

    async def _replace(self, raw: Any) -> None:
        if isinstance(raw, dict) and "fallback" in raw:  # the REST refresh's flag; it means nothing on the socket (#234)
            await self._error()
            return
        try:
            req = OutcomeRequest.model_validate(raw)
        except ValidationError as exc:
            await self._error(refusal_of(exc.errors()))
            return
        if req == self._req:  # an identical strategy changes nothing: no reset, no re-subscribe, no push (ADR-068 (2))
            return
        new_handle = None
        if self._feed is not None:
            try:
                new_handle = self._feed.fanout.subscribe(self._on_quote, self._input_ids(req))
            except KeyError:  # an instrument the catalogue does not know: nothing was subscribed
                await self._error()
                return
        old_forward = self._forward_handle
        self._forward_handle = None if self._feed is None else self._hold_forward(req)
        self._release()  # after the new subscription, so a shared instrument is never dropped and re-added
        self._release_forward(old_forward)
        self._handle, self._req, self._seen = new_handle, req, {}
        # A changed strategy is an input change: it recomputes, but the 1 s gate since the LAST push still holds (only the
        # first push after the socket opens goes at once), so client messages cannot drive pushes or engine work faster.
        self._dirty = True

    async def _push(self) -> None:
        self._dirty = False
        req = self._req  # the one follow message this push is computed for, read once
        try:
            rates = await load_charge_rates()
            ctx = None if self._feed is None else self._feed.ctx
            stored = await stored_legs_for(req, ctx, self._lookup)  # same helper as the REST route
            margin = await margin_for_request(req, ctx, self._margin_source)  # same step as the REST route
            booked = await get_booked(req, self._booked_reader)  # same step as the REST route (nothing for a plan)
            # REQ-133 AC-2: the push echoes the version (seq) of the follow message it was computed for (echo_seq)
            body = outcome_response(req, ctx, stored=stored, rates=rates, margin=margin, seq=req.seq, booked=booked)
        except Exception:  # a path we did not expect: one fixed message, the exception is not shown
            await self._error()
            return
        await self._channel.send(body)
        self.pushes += 1
        self._last_push = self._monotonic()
        self._hold_oi(req, body)

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
            self._release_forward(self._forward_handle)
            self._forward_handle = None
            self._release_forward(self._oi_handle)  # REQ-083 AC-5: the OI bars' lease ends with the socket
            self._oi_handle, self._oi_ids = None, ()
