"""GC-UI step 5 (D-B40 / D-B41; REQ-091 AC-1..AC-5, ADR-203, F-64): the Strategy Chart's data for one saved strategy.

Reads each leg's and the index future's minute candles ONLY through the reader the caller opened (the adapter's
opener, wired by ``ofo_app.price_history_source``; this module never imports the vendor, B1), one call per contract
per window, cached in process for
5 minutes per (contract, window) so an Invert toggle does not refetch. Combines through the one engine
(``ofo.outcome.price_history`` -> ``ofo.engine.money_summary``). Credentials come from the encrypted session store,
never the environment; the token never reaches a log, a reason or a reply (only exception class names are logged).
Kite refusing (non-200, 429 busy, transport, malformed body) is one state, never retried here (no auto retry).
Answer states: available / leg_not_listed / no_future_candles / all_gaps / no_session / broker_refused /
future_not_in_catalogue.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ofo.errors.explanations import render_explanation
from ofo.history.bars import MinuteBar
from ofo.history.candles import CandleError
from ofo.instruments.models import ZERODHA, ListedContract
from ofo.outcome import price_history as ph
from ofo.timeutil import IST

log = logging.getLogger("ofo_app.strategy_price_history")
CACHE_SECONDS = 300.0
MAX_DAYS = 15
#: calendar days fetched for N trading days: weekends plus room for exchange holidays (one call: Kite's minute limit is
#: 60 days per call, F-64)
_CALENDAR_SPAN = {n: n * 7 // 5 + 7 for n in range(1, MAX_DAYS + 1)}

Fetcher = Callable[[str, datetime.datetime, datetime.datetime], list[MinuteBar]]
#: (listed contracts) -> the minute-candle fetch for exactly those contracts
ReaderFactory = Callable[[list[ListedContract]], Fetcher]
#: (db) -> the reader factory on the owner's stored session, or None (no usable session). Called FIRST on the request
#: connection (the token read may commit and refuses a connection in a transaction, S5-1); wired by
#: ``ofo_app.price_history_source`` (the adapter boundary, B1).
HistoryOpener = Callable[[Any], Awaitable[ReaderFactory | None]]
#: (db, underlying) -> the nearest not-yet-expired monthly future of the stored catalogue, or None
FutureFinder = Callable[[Any, str], Awaitable[ListedContract | None]]
Clock = Callable[[], float]

_cache: dict[tuple[str, datetime.date, datetime.date], tuple[float, list[MinuteBar]]] = {}


@dataclass(frozen=True)
class ChartLeg:
    """A saved leg as the engine's combine reads it: its side and its lots."""

    action: Any
    lots: int


@dataclass(frozen=True)
class Answer:
    state: str
    reason: Any = None
    future_label: Any = None
    chart: ph.Chart | None = None
    notes: tuple[Any, ...] = ()


def instrument_id(lc: ListedContract) -> str:
    return f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"


def label(lc: ListedContract) -> str:
    return str(lc.ref(ZERODHA).broker_symbol)


async def nearest_future(db: Any, underlying: str) -> ListedContract | None:
    """Production finder: the stored catalogue's nearest listed FUT of ``underlying`` (NIFTY -> NFO, SENSEX -> BFO)."""
    from ofo_app import catalogue_picker as picker  # noqa: PLC0415
    from ofo_app import catalogue_store  # noqa: PLC0415

    today = await picker.database_today(db)
    futures = [r for r in await picker.pickable_contracts(db, underlying, today) if r.instrument_type == "FUT"]
    if not futures:
        return None
    nearest = min(futures, key=lambda r: r.expiry)
    return (await catalogue_store.load_contract(db, nearest.contract_id)).listed


async def _bars(fetch: Fetcher, iid: str, start: datetime.datetime, end: datetime.datetime,
                clock: Clock) -> list[MinuteBar]:
    key = (iid, start.date(), end.date())
    hit = _cache.get(key)
    if hit is not None and clock() - hit[0] < CACHE_SECONDS:
        return hit[1]
    bars = await asyncio.to_thread(fetch, iid, start, end)
    _cache[key] = (clock(), bars)
    return bars


async def answer(db: Any, legs: Sequence[Any], listed: Sequence[ListedContract], underlying: str, *,  # noqa: PLR0913 - one seam each
                 days: int, invert: bool, now: datetime.datetime, reader: ReaderFactory | None,
                 finder: FutureFinder, clock: Clock = time.monotonic) -> Answer:
    """``reader`` was opened by the caller BEFORE anything touched ``db`` (``HistoryOpener``); None = no session."""
    future = await finder(db, underlying)
    if future is None:
        return Answer("future_not_in_catalogue", render_explanation("price_history_future_not_in_catalogue"))
    future_label = render_explanation("price_history_future_label", underlying=underlying,
                                      expiry=future.contract.expiry)
    if reader is None:
        return Answer("no_session", render_explanation("price_history_no_session"), future_label)
    fetch = reader([*listed, future])
    end = now.astimezone(IST)
    start = datetime.datetime.combine(end.date() - datetime.timedelta(days=_CALENDAR_SPAN[days]), datetime.time(9),
                                      tzinfo=IST)
    try:
        leg_bars = [await _bars(fetch, instrument_id(lc), start, end, clock) for lc in listed]
        future_bars = await _bars(fetch, instrument_id(future), start, end, clock)
    except (CandleError, RuntimeError) as exc:  # CandleFetchError is a RuntimeError; the message carries no token
        log.warning("strategy price history: kite refused: %s", type(exc).__name__)
        return Answer("broker_refused", render_explanation("price_history_kite_refused"), future_label)
    chart = ph.build_chart(legs, leg_bars, future_bars, leg_labels=[label(lc) for lc in listed], days=days,
                           invert=invert)
    notes = tuple(_note(n) for n in chart.notes)
    if chart.state is ph.State.LEG_NOT_LISTED:
        reason = render_explanation("price_history_leg_not_listed", leg=chart.missing_leg)
    elif chart.state is ph.State.NO_FUTURE_CANDLES:
        reason = render_explanation("price_history_no_future_candles")
    elif chart.state is ph.State.ALL_GAPS:
        reason = render_explanation("price_history_all_gaps")
    else:
        reason = None
    return Answer(chart.state.value, reason, future_label, chart, notes)


def _note(note: tuple[Any, ...]) -> Any:
    if note[0] == "leg_listed_from":
        return render_explanation("price_history_leg_listed_from", leg=note[1], date=note[2], days=note[3])
    return render_explanation("price_history_leg_ended_on", leg=note[1], date=note[2])
