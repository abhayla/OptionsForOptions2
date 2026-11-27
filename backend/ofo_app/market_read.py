"""The ONE price door for a decision that needs a live price now (ADR-327; D-01, S-20 of 25 Nov 2026).

Spec basis: ADR-327 (a paper trigger is judged on a live price it ASKED the feed for, waiting up to 3 s); ADR-015 (a
stale price is never live); ADR-119 (the market calendar); ``read_door.read_quotes`` is "THE one read door of a
request read" and this door is built on it, not beside it.

Why: in bus mode the API process's provider books a tick only for a token something in THIS process holds
(``kite_provider.on_frame``). A reader that did not hold what it read saw "no price" whenever no other consumer happened
to hold it, and the save guard treated "no price" as "saved". ``read_market`` is the only way a trigger decision reads a
price: it asks the fan-out to hold the legs (and the index when asked), polls while held, releases in a ``finally``.

Answer states, one per price: ``live``, ``stale`` (a quote whose health is not available), ``missing`` (no quote) and
``market_closed`` (the ADR-119 calendar through the feed's own state; nothing is held, read or waited for). A paper
decision uses only a ``live`` price (``paper.is_live``); the caller judges the other three.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import chain
from typing import Final, Literal

from ofo.outcome import read_snapshot
from ofo.tracking import paper

from ofo_app import may_act
from ofo_app.live_push import POLL_SECONDS, LiveFeed
from ofo_app.read_door import NO_TOKEN, read_quotes
from ofo_app.routes.outcome import MarketContext, feed_scope

log = logging.getLogger(__name__)

READ_WAIT_S: Final = 3.0  # ADR-327 (1): the longest a read waits for a price it asked the feed for
MARKET_CLOSED: Final = "market_closed"
# named so a log line says what a wait was for; the basis is always ``leg_price``
Purpose = Literal["trigger_check", "stop_fire"]


@dataclass(frozen=True)
class Wait:
    """How long a read waits and the seams it waits with (tests inject ``sleep`` and ``now``: no test sleeps)."""

    seconds: float = READ_WAIT_S
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    now: Callable[[], float] | None = None  # None: the running loop's own clock


DEFAULT_WAIT: Final = Wait()


@dataclass(frozen=True)
class MarketPrice:
    instrument_id: str
    state: str  # live | stale | missing | market_closed
    price: Decimal | None  # set only when live
    at: datetime.datetime | None = None  # the quote time when known


@dataclass(frozen=True)
class MarketRead:
    market_closed: bool
    index: MarketPrice | None  # None when the index was not asked for
    legs: Mapping[str, MarketPrice] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return all(p.state == paper.LIVE for p in chain([self.index] if self.index else [], self.legs.values()))


def _from(p: paper.Price) -> MarketPrice:
    return MarketPrice(p.instrument_id, p.state, p.price, p.at)


def live_price(answer: MarketPrice) -> paper.Price:
    """The ``paper.Price`` of a LIVE answer (what ``stops.crossed`` takes); never built for any other state."""
    if answer.state != paper.LIVE:
        raise ValueError(f"{answer.instrument_id}: {answer.state} is not a live price")
    return paper.Price(answer.instrument_id, paper.LIVE, answer.price, answer.at)  # type: ignore[arg-type]


def _read(ctx: MarketContext, underlying: str, keys: Sequence[str], need_index: bool) -> MarketRead:
    snap = read_snapshot(ctx.provider, underlying, list(keys), ctx.clock(), ctx.rate, feed_scope(ctx),
                         quality=ctx.forward_quality)
    return MarketRead(False, _from(paper.price_of(snap.spot, underlying)) if need_index else None,
                      {k: _from(paper.leg_price(snap, k)) for k in keys})


async def read_market(ctx: MarketContext, feed: LiveFeed | None, underlying: str, leg_keys: Sequence[str],  # noqa: PLR0913
                      need_index: bool, purpose: Purpose, *, wait: Wait = DEFAULT_WAIT) -> MarketRead:
    """Each of ``leg_keys`` (feed keys) and, with ``need_index``, the index of ``underlying``: one answer each.

    Market closed (ADR-119): every answer is ``market_closed`` and nothing is read. Otherwise one read; when a price is
    not live yet and there is a fan-out, ONE hold of the legs and the index until every price is live, the provider
    disconnects or ``wait.seconds`` pass (``read_door.read_quotes``). No fan-out (no feed): the read as it is, nothing
    held. A read that raises raises: the caller refuses by name (ADR-327), never reads "no price" as "fine"."""
    keys = list(dict.fromkeys(leg_keys))
    provider = ctx.provider
    if not may_act.market_open(ctx, ctx.clock()):
        return MarketRead(True, MarketPrice(underlying, MARKET_CLOSED, None) if need_index else None,
                          {k: MarketPrice(k, MARKET_CLOSED, None) for k in keys})

    def read() -> MarketRead:
        return _read(ctx, underlying, keys, need_index)

    answer = read()
    if feed is None:
        return answer
    index_id = getattr(provider, "index_id", lambda _u: None)(underlying) if need_index else None
    held = await read_quotes(feed, [*keys, *([index_id] if index_id else [])], read,
                               lambda a: a.ready, lambda: provider.status().connected, wait.seconds, POLL_SECONDS,
                               sleep=wait.sleep, now=wait.now)
    if held is NO_TOKEN:  # the fan-out has no token for any id: nothing was held, the read stands
        log.info("market read (%s): nothing to hold for %s", purpose, underlying)
        return answer
    if not held.ready:
        log.info("market read (%s): not live after the wait for %s", purpose, underlying)
    return held
