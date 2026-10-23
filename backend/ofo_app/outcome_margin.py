"""ADR-099: Zerodha's margin for a strategy's planned orders, on the outcome answer (REST and the live push).

With a live Kite session the margin block carries the amount needed (the W-081 client's ``required_total``: Zerodha's
basket figure plus the ADR-094 top-up, a closing basket counting as 0) and Zerodha's available funds, with the time
they were read (ADR-088, "Checked at"). The read happens once per change of the PLAN - the legs' instruments, sides,
quantities and planned prices - never per price tick: the cache key is the planned basket itself, per user and per
session, and the cache is bounded. The figure is information on the planning screen; the hard gate stays the check
before the basket (REQ-055, ``ofo_app.kite_margin.margin_verdict``), untouched here.

States (run-discipline B4 (d)):

- no live session (no market context, or the socket not running on a session): the existing login text
  (``outcome_margin_pending``); no Kite call, nothing cached.
- a leg that is not a listed Zerodha contract: ``NO_BASKET``; no Kite call.
- both figures read: ``CHECKED`` with the figures; cached until the plan changes.
- Kite says the token is no longer valid: the login text; cached for ``RETRY_SECONDS``.
- Kite busy / refused / down / junk / no figure / a timeout / the token store unreadable: ``UNREADABLE``
  ("could not be read", never a made-up figure); cached for ``RETRY_SECONDS`` so a Kite outage costs one read per
  ``RETRY_SECONDS`` per plan, not one per push.

Concurrency: the cache is read without any lock (one event loop thread). Only a miss reads Zerodha, through ONE
in-flight task per key (single flight): concurrent requests for the same uncached plan share one read, and a cached plan
or another plan never waits on that network read. A session whose id is None (unknown) is read every time and never
stored, so two unknown sessions can never share figures.

A margin failure never changes the rest of the outcome: the P&L answer is computed as before. The Kite read runs in a
worker thread (``asyncio.to_thread``, like every other Kite read) under ``READ_TIMEOUT_SECONDS``; the event loop never
waits on the network. The access token is never logged, cached or put in an answer: only exception class names are
logged.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.engine.product import Product
from ofo.instruments.models import ZERODHA
from ofo.instruments.parser import ZERODHA_EXCHANGE_TO_SEGMENT
from ofo.execution.margin_gate import MARGIN_BUSY_CODE
from ofo.marketdata.provider import MarketDataProvider
from ofo.outcome.service import MARGIN, Margin, margin_busy, margin_checked, margin_no_basket, margin_unreadable
from ofo.outcome.snapshot import contract_id

from ofo_app.kite_margin import BasketOrder, KiteMargin, KiteMarginError

log = logging.getLogger("ofo_app.outcome_margin")

READ_TIMEOUT_SECONDS: Final = 8.0  # one funds read + one basket read, together
#: Each of the two HTTP calls gets half the read timeout, so a worker thread never outlives READ_TIMEOUT_SECONDS.
CALL_TIMEOUT_SECONDS: Final = READ_TIMEOUT_SECONDS / 2
RETRY_SECONDS: Final = 30.0  # a failed read is not retried sooner (Kite rate limits; a push asks every second)
CACHE_SIZE: Final = 256  # plans kept per process (all users together); the oldest is dropped first
#: The platform's exchange segment -> Zerodha's exchange code, the reverse of the parser's one map (never retyped).
EXCHANGE_OF_SEGMENT: Final = {segment: exchange for exchange, segment in ZERODHA_EXCHANGE_TO_SEGMENT.items()}
_ORDER_TYPE: Final = "LIMIT"  # a planned price is a limit price (ADR-094: the user may pay up to it)

OpenClient = Callable[[], Awaitable[KiteMargin | None]]
Clock = Callable[[], datetime.datetime]


@dataclass(frozen=True)
class PlannedOrderIn:
    """One planned leg as the margin needs it (taken from the validated outcome request)."""

    instrument_id: str
    action: str  # "BUY" / "SELL"
    lots: int
    planned_entry: Decimal


def basket_orders(provider: MarketDataProvider, legs: Sequence[PlannedOrderIn]) -> tuple[BasketOrder, ...] | None:
    """The planned orders as Zerodha's basket call takes them, or None when a leg is not a listed Zerodha contract
    (unknown instrument, no Zerodha row, an exchange outside V1, a shape BasketOrder refuses). Product NRML (ADR-080),
    a LIMIT at the planned entry, quantity = lots x the contract's lot size."""
    master = {contract_id(lc): lc for lc in provider.instrument_master()}
    orders = []
    for leg in legs:
        listed = master.get(leg.instrument_id)
        if listed is None or not any(r.broker == ZERODHA for r in listed.broker_refs):
            return None
        exchange = EXCHANGE_OF_SEGMENT.get(listed.contract.exchange_segment)
        if exchange is None:
            return None
        try:
            orders.append(BasketOrder(exchange, listed.ref(ZERODHA).broker_symbol, leg.action, Product.NRML.value,
                                      _ORDER_TYPE, leg.lots * listed.contract.lot_size, leg.planned_entry))
        except (ValueError, TypeError):
            return None
    return tuple(orders)


def _read(client: KiteMargin, orders: tuple[BasketOrder, ...]) -> tuple[Decimal, Decimal]:
    """In a worker thread: Zerodha's available funds, then the basket's required total."""
    available = client.fetch_available_funds()
    return available, client.fetch_basket_margin(orders).required_total


@dataclass(frozen=True)
class _Entry:
    margin: Margin
    until: float | None  # None = kept until the plan changes (a success); else the monotonic retry time


@dataclass(frozen=True)
class MarginLimits:
    """The read's bounds: its timeout, the wait before a failed read is tried again, and the cache size."""

    timeout: float = READ_TIMEOUT_SECONDS
    retry: float = RETRY_SECONDS
    size: int = CACHE_SIZE


class OutcomeMargin:
    """The margin reader with its plan-keyed cache. ``session`` gives the live Kite session as ``(user, session id)``,
    or None when there is none; ``open_client`` builds that user's margin client (reads the stored token) and is
    called only on a cache miss."""

    def __init__(self, session: Callable[[], Hashable | None], open_client: OpenClient, *, clock: Clock,
                 monotonic: Callable[[], float] = time.monotonic, limits: MarginLimits | None = None) -> None:
        self._session = session
        self._open = open_client
        self._clock = clock
        self._monotonic = monotonic
        self._limits = limits or MarginLimits()
        self._cache: OrderedDict[Hashable, _Entry] = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Future] = {}
        self.reads = 0  # Kite reads started (a test counter; one read = funds + basket)

    def __repr__(self) -> str:
        return "OutcomeMargin()"

    def session(self) -> Hashable | None:
        return self._session()

    def _cached(self, key: Hashable) -> Margin | None:
        entry = self._cache.get(key)
        if entry is None or (entry.until is not None and self._monotonic() >= entry.until):
            return None
        self._cache.move_to_end(key)
        return entry.margin

    async def margin_for(self, session: Hashable, orders: tuple[BasketOrder, ...]) -> Margin:
        """The cached margin of ``orders`` for ``session`` (its user and session id), read from Zerodha on a miss.
        No lock is held across the network read: a hit answers at once whatever another key is waiting for."""
        key = (session, orders)
        hit = self._cached(key)
        if hit is not None:
            return hit
        flight = self._inflight.get(key)
        if flight is None:
            flight = asyncio.ensure_future(self._read_and_store(key, orders, store=_known(session)))
            self._inflight[key] = flight
        return await asyncio.shield(flight)  # a waiter that goes away never cancels the shared read

    async def _read_and_store(self, key: Hashable, orders: tuple[BasketOrder, ...], *, store: bool) -> Margin:
        try:
            margin, kept = await self._fetch(orders)
            if store:
                self._cache[key] = _Entry(margin, None if kept else self._monotonic() + self._limits.retry)
                self._cache.move_to_end(key)
                while len(self._cache) > self._limits.size:
                    self._cache.popitem(last=False)
            return margin
        finally:
            self._inflight.pop(key, None)

    async def _fetch(self, orders: tuple[BasketOrder, ...]) -> tuple[Margin, bool]:
        """(the margin, whether it is kept until the plan changes)."""
        self.reads += 1
        timeout = self._limits.timeout
        try:
            client = await asyncio.wait_for(self._open(), timeout)
            if client is None:  # no stored session after all
                return MARGIN, False
            available, needed = await asyncio.wait_for(asyncio.to_thread(_read, client, orders), timeout)
        except KiteMarginError as exc:
            log.warning("outcome margin: Zerodha could not be read: %s", exc.code)
            if exc.code == MARGIN_BUSY_CODE:
                return margin_busy(), False
            return (MARGIN if exc.code == "kite_margin_token" else margin_unreadable()), False
        except Exception as exc:  # noqa: BLE001 - a timeout, the token store, anything: "could not be read"
            log.warning("outcome margin: Zerodha could not be read: %s", type(exc).__name__)
            return margin_unreadable(), False
        try:
            return margin_checked(needed, available, self._clock()), True
        except ValueError:
            return margin_unreadable(), False


def _known(session: Hashable) -> bool:
    """A session ``(user, id)`` with id None is unknown: its figures are never stored."""
    return not (isinstance(session, tuple) and session and session[-1] is None)


async def margin_answer(source: OutcomeMargin | None, ctx, legs: Sequence[PlannedOrderIn]) -> Margin:
    """The margin block for one outcome answer. ``ctx`` is the market context (None = not connected)."""
    if source is None or ctx is None:
        return MARGIN
    session = source.session()
    if session is None:
        return MARGIN
    orders = basket_orders(ctx.provider, legs)
    if orders is None:
        return margin_no_basket()
    return await source.margin_for(session, orders)
