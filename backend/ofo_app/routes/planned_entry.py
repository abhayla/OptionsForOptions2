"""POST /api/strategies/planned-entry (W-068 step 3; ADR-068 item 1, ADR-020 Q185/Q186, ADR-008).

Spec basis: ADR-068 (1) "A draft leg's entry price is its planned entry: the leg's LTP captured when the leg is added
(or the mid of bid and ask when no LTP exists)"; ADR-020 Q185 "no fake prices": without a live price the answer is
``planned_entry: null`` with a reason code, NEVER a default, last-known or zero price.

Prices are read only through ``ofo.outcome.read_snapshot`` with the same provider dependency the outcome route uses
(``get_market_context``), so replay mode (APP_ENV=test + OUTCOME_REPLAY=1) works here too. LTP first (a positive value);
the mid of bid and ask only when the quote carries no LTP; only a quote whose health is AVAILABLE counts as live, and
outside market hours (ADR-119 calendar) also the last price the feed holds from the session that closed (ADR-200 (1),
(4): ``ofo.marketdata.quote.planning_price_usable``; the order paths never read this rule).
The browser computes nothing: the price is a string from a Decimal, rounded half-up to the 0.01 the outcome route takes.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.outcome import read_snapshot
from ofo.outcome.planned_entry import planned_entry_of
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ofo_app import live_market
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.errors import ClosedRoute
from ofo_app.live_push import POLL_SECONDS, LiveFeed
from ofo_app.routes.outcome import (
    AnswerClock,
    MarketContext,
    feed_scope,
    get_answer_clock,
    get_market_context,
    market_state,
)
from ofo_app.underlying import Underlying

router = APIRouter(route_class=ClosedRoute)

PLANNED_ENTRY_WAIT_S = 3.0  # gate 4a D-2: the longest the route holds an unheld contract for its first live quote

InstrumentIdIn = Annotated[str, StringConstraints(pattern=r"^[A-Z_]{1,20}:[0-9]{1,12}$")]

Reason = Literal["not_connected", "no_live_price", "unknown_instrument", "wrong_underlying", "expired"]


class PlannedEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Underlying
    instrument_ids: list[InstrumentIdIn] = Field(min_length=1, max_length=20)


class PlannedEntryOut(ApiModel):
    exchange_segment: Identifier
    exchange_token: int
    planned_entry: Money | None
    captured_at: datetime.datetime | None
    source: Literal["ltp", "mid"] | None
    reason_code: Reason | None
    #: ADR-197: set only for an entry captured outside market hours from the last close: the quote's OWN last-price
    #: time (the screen captions it "Close, <time>"); None in market hours
    close_at: datetime.datetime | None = None


class PlannedEntriesOut(ApiModel):
    entries: list[PlannedEntryOut]
    answered_at: datetime.datetime  # ADR-088: when the server produced this answer (the unpriced state's "Checked at")


def _entry(instrument_id: str, **fields: Any) -> dict[str, Any]:
    segment, _, token = instrument_id.partition(":")
    return {"exchange_segment": segment, "exchange_token": int(token), "planned_entry": None, "captured_at": None,
            "source": None, "reason_code": None, **fields}


def get_live_feed() -> LiveFeed | None:
    """The running app's shared fan-out (LIVE_MARKET with a session); None otherwise (not connected, the test replay,
    a test's own context): then nothing is held and the answer is the book as it is. Tests override this dependency."""
    return live_market.current_feed()


def _can_price(ctx: MarketContext | None, at) -> bool:
    """A live context whose provider is connected; or, outside market hours (ADR-200 (4)), one whose socket is down
    but whose session has not ended: the book still holds the last close, which ``planning_price_usable`` judges per
    quote. In market hours a disconnected provider prices nothing, as before. No context: nothing (never a default)."""
    if ctx is None:
        return False
    status = ctx.provider.status()
    if status.connected:
        return True
    return not status.session_ended and market_state(ctx, ctx.clock() if at is None else at).closed


def _no_listener(_quote) -> None:  # the route only waits for the book to fill; it needs no pushed quotes
    return None


def _read(ctx: MarketContext, underlying: str, ids: list[str]):
    valuation = ctx.clock()
    snapshot = read_snapshot(ctx.provider, underlying, ids, valuation, ctx.rate, feed_scope(ctx))
    closed = market_state(ctx, valuation).closed  # the ONE market-state answer (ADR-119), at the read's instant
    priced = {i: planned_entry_of(snapshot.legs[i].quote, market_closed=closed)
              for i in ids if snapshot.legs[i].problem is None}
    return valuation, snapshot, priced


async def hold_until_priced(feed: LiveFeed, ctx: MarketContext, underlying: str, ids: list[str],
                             unpriced: list[str]):
    """Gate 4a D-2 (ADR-075, ADR-020): hold the contracts that have no live price on the shared fan-out until each has
    its first AVAILABLE quote or PLANNED_ENTRY_WAIT_S passes, and ALWAYS release exactly that hold (timeout, error,
    client disconnect). Subscribe and release run on the event loop, like the live push's. A contract that already has
    a live price is never acquired, so another holder's hold is never touched by this one."""
    try:
        handle = feed.fanout.subscribe(_no_listener, unpriced, max_queue=1)
    except KeyError:  # a contract the provider has no token for: nothing was subscribed, the unpriced answer stands
        return _read(ctx, underlying, ids)
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + PLANNED_ENTRY_WAIT_S
        while True:
            await asyncio.sleep(POLL_SECONDS)
            result = _read(ctx, underlying, ids)
            if all(result[2].get(i) is not None for i in unpriced):
                return result
            if not ctx.provider.status().connected or loop.time() >= deadline:
                return result
    finally:
        with contextlib.suppress(Exception):
            feed.fanout.unsubscribe(handle)


@router.post("/api/strategies/planned-entry", response_model=PlannedEntriesOut)
async def planned_entry(body: PlannedEntryIn,
                        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                        now: Annotated[AnswerClock, Depends(get_answer_clock)],
                        feed: Annotated[LiveFeed | None, Depends(get_live_feed)]) -> PlannedEntriesOut:
    answered_at = now()
    ids = list(dict.fromkeys(body.instrument_ids))
    if not _can_price(ctx, answered_at):
        return PlannedEntriesOut.model_validate({"entries": [_entry(i, reason_code="not_connected") for i in ids],
                                               "answered_at": answered_at})
    valuation, snapshot, priced_by_id = _read(ctx, body.underlying, ids)
    unpriced = [i for i, p in priced_by_id.items() if p is None]
    if unpriced and feed is not None:
        valuation, snapshot, priced_by_id = await hold_until_priced(feed, ctx, body.underlying, ids, unpriced)
    closed = market_state(ctx, valuation).closed  # the same one market-state answer the capture read used
    entries = []
    for iid in ids:
        leg = snapshot.legs[iid]
        if leg.problem is not None:
            reason = ("unknown_instrument" if leg.problem == "unknown instrument"
                      else "expired" if leg.problem == "expired" else "wrong_underlying")
            entries.append(_entry(iid, reason_code=reason))
            continue
        priced = priced_by_id[iid]  # the domain rule (ofo.outcome.planned_entry); the route only calls it
        if priced is None:
            entries.append(_entry(iid, reason_code="no_live_price"))
        else:
            close_at = leg.quote.timestamp if closed and leg.quote is not None else None  # ADR-197: the close's time
            entries.append(_entry(iid, planned_entry=priced.price, captured_at=valuation, source=priced.source,
                                  close_at=close_at))
    return PlannedEntriesOut.model_validate({"entries": entries, "answered_at": answered_at})


async def capture_entries(ctx: MarketContext | None, feed: LiveFeed | None, underlying: str, ids: list[str]):
    """W-148: the same capture the route above does (one read, then the bounded hold for contracts nobody streams), for
    a caller that already holds the answer clock: ``(valuation, {instrument id: PlannedEntry or None})``. No live
    context, or a provider that is not connected, prices nothing (ADR-020 Q185: never a default)."""
    if not _can_price(ctx, None):
        return None, dict.fromkeys(ids)
    valuation, _, priced = _read(ctx, underlying, ids)
    unpriced = [i for i in ids if priced.get(i) is None]
    if unpriced and feed is not None:
        valuation, _, priced = await hold_until_priced(feed, ctx, underlying, ids, unpriced)
    return valuation, {i: priced.get(i) for i in ids}
