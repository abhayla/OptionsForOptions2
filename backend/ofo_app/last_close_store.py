"""The stored last close: written at the close, read back while the market is closed (Lane N A1 / AF-02).

Spec basis: ADR-330 (36) ("the after-close figure is the last price received up to the calendar close (15:30:00)";
later prices are ignored); ADR-212 (every market-data screen shows the last close until the open; a contract with no
held close stays unpriced with its reason, ADR-200 (4)); ADR-330 (58) (paper and real differ only by tag: this one
module serves both, index and contracts); ADR-008 (money is Decimal, never float); ADR-012 (browsers never reach a
vendor: the table holds what the platform's own feed received).

RCA: the held close lived only in the API process's feed book, so a restart after the close lost every figure (owner PC
27 Nov: every leg "no live quote", Option Chain every LTP "not available"). Migration 0059 adds ``public.last_close``.

Three parts, one module:
- ``PostgresLastCloseStore``: ``write_closes`` (upsert one row per instrument per trade date; Decimal only; a float or a
  sub-paisa price is REFUSED, never rounded) and ``read_latest`` (the newest trade date per instrument). Short
  timeouts; a dead database costs a bounded wait and a logged error, never a fault in the feed (history_store's way).
- ``CloseWriter``: at the close plus a few seconds on a trading day it takes from the feed book every frame made by the
  close (the book's own ``_figure`` rule; this module changes no rule) and writes it. It writes only if this process
  was already running at the close: a process that started later holds no frame it saw at the close, so the table has
  NO row for that day and the screens say prices are not available (never a made-up or older-day figure as today's).
- ``seed_once``: only while the market is closed, hands each stored close to ``QuoteBook.seed_close``, which serves it
  with its OWN date-time (an earlier day's row is labelled with its own date) and never overrides a frame the book
  already holds. While the market is open the table is never read; the first live tick wins.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import threading
import time
from collections.abc import Callable, Iterable
from decimal import Decimal, InvalidOperation

from ofo.instruments.models import INDEX_ROWS
from ofo.market_calendar import is_market_open, last_close
from ofo.marketdata.feed_health import expect_seed as _expect_seed
from ofo.marketdata.quote import Instrument, NormalizedQuote, SourceMetadata
from ofo.money import PAISE
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST, SESSION_CLOSE
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

log = logging.getLogger(__name__)

SOURCE_FEED_BOOK = "feed_book"
#: the live feed's own source stamp (equal to ``kite_provider.SOURCE``; a test pins it): a seeded quote is the feed's
FEED_SOURCE = SourceMetadata(provider="zerodha-kite", feed_id="kite-ws-full")
GRACE = datetime.timedelta(seconds=5)  # write this long after the close (a frame stamped 15:30:00 may arrive late)
WINDOW = datetime.timedelta(minutes=10)  # a failed write is retried until this long after the close, then given up
STEP_SECONDS = 5.0
_CONNECT_TIMEOUT_S = 5
_COMMAND_TIMEOUT_S = 10
DOWN_BACKOFF_S = 20.0
_UNREACHABLE = (OSError, TimeoutError, InterfaceError, OperationalError)
_MAX_PRICE = Decimal("999999999999")

#: (instrument_id, trade_date, price, price_at, source)
CloseRow = tuple[str, datetime.date, Decimal, datetime.datetime, str]
#: instrument_id -> (price, price_at, trade_date)
Latest = dict[str, tuple[Decimal, datetime.datetime, datetime.date]]


class StoreUnavailable(RuntimeError):
    """The database was unreachable a moment ago: the call fails at once instead of waiting for a connect timeout."""


def expect_seed(expected: bool) -> None:
    """The lifespan's switch (M1): a store is configured, so a new book waits for its first seed attempt."""
    _expect_seed(expected)


def check_row(row: CloseRow) -> None:
    """ADR-008: refuse a float, a non-finite, a negative, a too large or a sub-paisa price (the database does too)."""
    instrument_id, trade_date, price, price_at, source = row
    if not isinstance(instrument_id, str) or not instrument_id or not source:
        raise ValueError("a stored close needs an instrument id and a source")
    if isinstance(trade_date, datetime.datetime) or not isinstance(trade_date, datetime.date):
        raise ValueError(f"trade_date must be a date, got {trade_date!r}")
    if not isinstance(price_at, datetime.datetime) or price_at.tzinfo is None:
        raise ValueError(f"price_at must be a timezone-aware datetime, got {price_at!r}")
    local = price_at.astimezone(IST)
    if local.date() != trade_date or local.time() > SESSION_CLOSE:
        raise ValueError(f"price_at {price_at} is not on the trade date {trade_date} at or before the close")
    if isinstance(price, bool) or not isinstance(price, Decimal):
        raise ValueError(f"price must be a Decimal, got {type(price).__name__}: money is never a float (ADR-008)")
    try:
        exact = price.is_finite() and price == price.quantize(PAISE) and 0 <= price <= _MAX_PRICE
    except InvalidOperation:
        exact = False
    if not exact:
        raise ValueError(f"price {price} is not a whole number of paise in range: the store never rounds a price")


_UPSERT = text("""
    INSERT INTO public.last_close (instrument_id, trade_date, price, price_at, source)
    SELECT t.instrument_id, t.trade_date, t.price, t.price_at, t.source
    FROM unnest(CAST(:instrument_id AS text[]), CAST(:trade_date AS date[]), CAST(:price AS numeric[]),
                CAST(:price_at AS timestamptz[]), CAST(:source AS text[]))
        AS t(instrument_id, trade_date, price, price_at, source)
    ON CONFLICT (instrument_id, trade_date) DO UPDATE SET
        price = EXCLUDED.price, price_at = EXCLUDED.price_at, source = EXCLUDED.source
""")
_LATEST = """
    SELECT DISTINCT ON (instrument_id) instrument_id, price, price_at, trade_date
    FROM public.last_close {where} ORDER BY instrument_id, trade_date DESC
"""


class PostgresLastCloseStore:
    """Synchronous port over a private event loop on a daemon thread (as ``PostgresHistoryStore``): callers in the
    API's loop use ``asyncio.to_thread``. A dead database: one bounded wait, then calls fail at once for a while."""

    def __init__(self, url: str, *, down_backoff_s: float = DOWN_BACKOFF_S) -> None:
        self._url = url
        self._down_backoff_s = down_backoff_s
        self._down_until = 0.0
        self._engine: AsyncEngine | None = None
        self._call = threading.Lock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="ofo-last-close-pg", daemon=True)
        self._thread.start()

    def _engine_(self) -> AsyncEngine:
        if self._engine is None:  # created on the store's own loop, the one every connection runs on
            self._engine = create_async_engine(
                self._url, pool_size=1, max_overflow=1, pool_pre_ping=True,
                connect_args={"timeout": _CONNECT_TIMEOUT_S, "command_timeout": _COMMAND_TIMEOUT_S,
                              "server_settings": {"jit": "off"}})
        return self._engine

    def _run(self, coro):
        if self._loop.is_closed() or not self._thread.is_alive():
            coro.close()
            raise RuntimeError("the last-close store is closed")
        with self._call:
            if time.monotonic() < self._down_until:
                coro.close()
                raise StoreUnavailable("the database was unreachable; retrying shortly")
            try:
                return asyncio.run_coroutine_threadsafe(coro, self._loop).result()
            except _UNREACHABLE:
                self._down_until = time.monotonic() + self._down_backoff_s
                raise

    def write_closes(self, rows: Iterable[CloseRow]) -> int:
        """Upsert one row per (instrument, trade date). Every row is checked first: one bad row writes nothing."""
        rows = list(rows)
        for row in rows:
            check_row(row)
        if not rows:
            return 0
        columns = {"instrument_id": [r[0] for r in rows], "trade_date": [r[1] for r in rows],
                   "price": [r[2] for r in rows], "price_at": [r[3] for r in rows], "source": [r[4] for r in rows]}

        async def write() -> None:
            async with self._engine_().begin() as conn:
                await conn.execute(_UPSERT, columns)

        self._run(write())
        return len(rows)

    def read_latest(self, instrument_ids: Iterable[str] | None = None) -> Latest:
        """The newest trade date's close per instrument; ``None`` = every instrument held."""
        ids = None if instrument_ids is None else list(instrument_ids)
        if ids is not None and not ids:
            return {}

        async def read() -> Latest:
            sql = _LATEST.format(where="" if ids is None else "WHERE instrument_id = ANY(CAST(:ids AS text[]))")
            async with self._engine_().connect() as conn:
                result = await conn.execute(text(sql), {} if ids is None else {"ids": ids})
                return {r[0]: (r[1], r[2].astimezone(IST), r[3]) for r in result.all()}

        return self._run(read())

    def close(self) -> None:
        if self._loop.is_closed():
            return

        async def shut() -> None:
            if self._engine is not None:
                await self._engine.dispose()
                self._engine = None

        try:
            with self._call:
                asyncio.run_coroutine_threadsafe(shut(), self._loop).result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)
            if not self._thread.is_alive():
                self._loop.close()


# ---- the writer ---------------------------------------------------------------------------------------------------
def closes_of(book, close: datetime.datetime, now: datetime.datetime) -> tuple[list[CloseRow], int]:
    """(rows, skipped): every quote the book serves at ``now`` that was made by this ``close`` on this day (inside the
    session or exactly at the close; a later frame, an earlier day's seeded figure or a quote with no price is not).
    The book's own ``_figure`` picks the frame (this reads, never re-decides); skipped counts unwritable prices."""
    day = close.astimezone(IST).date()
    rows: list[CloseRow] = []
    skipped = 0
    for q in book.quotes(now):
        if q.timestamp > close or q.timestamp.astimezone(IST).date() != day:
            continue
        row = (q.instrument_id, day, q.ltp, q.timestamp, SOURCE_FEED_BOOK)
        try:
            check_row(row)
        except ValueError:
            skipped += 1
            continue
        rows.append(row)
    return rows, skipped


class CloseWriter:
    """One write per trading day at the close plus ``GRACE``. ``book_of()`` returns the CURRENT feed book or None.
    Book work (reading the book) runs on the event loop; only the database call goes to a worker thread (m7).
    The book must have been attached before the close (m8): a book first seen after it, as after a re-login, holds
    no frame this process saw at the close, so nothing is written for that day."""

    def __init__(self, store, book_of: Callable[[], object | None]) -> None:
        self._store = store
        self._book_of = book_of
        self._book: object | None = None
        self._seen_at: datetime.datetime | None = None  # when the CURRENT book was first seen by this writer
        self._done: datetime.date | None = None
        self.counters = {"written": 0, "skipped_rows": 0, "errors": 0}

    def _observe(self, now: datetime.datetime) -> object | None:
        book = self._book_of()
        if book is not self._book:
            self._book, self._seen_at = book, (None if book is None else now)
        return book

    async def step(self, now: datetime.datetime) -> int | None:
        """One check. Rows written (>= 0) or None when nothing was due. Called every few seconds, so the book is seen
        within one step of its attach (a book attached in the 5 s before the close may be seen just after it: no row,
        the safe side)."""
        book = self._observe(now)
        close = last_close(now)
        if close is None or now < close + GRACE or now > close + WINDOW or is_market_open(now):
            return None
        day = close.astimezone(IST).date()
        if self._done == day or book is None:
            return None
        if self._seen_at is None or self._seen_at > close:  # no book here saw the close: no row, nothing made up
            self._done = day
            log.info("last close %s: the current book was attached after the close, nothing written", day)
            return None
        rows, skipped = closes_of(book, close, now)  # on the event loop
        self.counters["skipped_rows"] += skipped
        try:
            n = await asyncio.to_thread(self._store.write_closes, rows)  # the only part off the loop
        except Exception as exc:  # noqa: BLE001 - a dead database is a logged error and a retry, never a feed fault
            self.counters["errors"] += 1
            log.error("last close write for %s failed: %s", day, type(exc).__name__)
            return None
        self._done = day
        self.counters["written"] += n
        log.info("last close %s: %d written, %d skipped", day, n, skipped)
        return n


# ---- the reader ---------------------------------------------------------------------------------------------------
def quote_of(lc, price: Decimal, price_at: datetime.datetime) -> NormalizedQuote | None:
    """The catalogue contract's quote carrying only the stored close (no bid/ask/day values: none were stored)."""
    c = lc.contract
    common = {"instrument_id": f"{c.exchange_segment}:{c.exchange_token}",
              "exchange": c.exchange_segment.split("_")[0], "segment": c.exchange_segment, "ltp": price,
              "bid": None, "ask": None, "volume": None, "oi": None, "oi_change": None, "iv": None, "delta": None,
              "gamma": None, "theta": None, "vega": None, "timestamp": price_at, "source": FEED_SOURCE,
              "health": DataHealth.STALE}
    index = INDEX_ROWS.get((c.exchange_segment, c.exchange_token))
    if index is not None:
        return NormalizedQuote(underlying=index[1], instrument_type=None, expiry=None, strike=None, **common)
    if c.is_index():
        return None
    return NormalizedQuote(underlying=c.name, instrument_type=Instrument(c.instrument_type), expiry=c.expiry,
                           strike=None if c.instrument_type == "FUT" else c.strike, **common)


def seed_wanted(provider, now: datetime.datetime) -> bool:
    """Only a book that exists and a market that is closed (nothing is read while it is open)."""
    book = getattr(provider, "book", None)
    return book is not None and not is_market_open(now) and book.feed.market_closed(now) is True


def apply_latest(provider, latest: Latest, now: datetime.datetime) -> int:
    """Hand the stored closes to the provider's book (on the event loop). Returns how many entries the book took."""
    by_id = {f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}": lc for lc in provider.instrument_master()}
    taken = 0
    for iid, (price, price_at, _day) in latest.items():
        lc = by_id.get(iid)
        if lc is None:
            continue
        try:
            quote = quote_of(lc, price, price_at)
        except ValueError:
            continue
        if quote is not None and provider.book.seed_close(quote, now):
            taken += 1
    return taken


async def seed_once(provider, store, now: datetime.datetime) -> int | None:
    """One seed attempt for THIS book (m7: only ``read_latest`` runs in a worker thread). None = not asked (market open
    or no book): nothing is read. Otherwise the attempt always ENDS the book's wait (``seed_attempted``), whether the
    database answered, had nothing, or failed: a screen is never held back by a dead database (M1)."""
    if not seed_wanted(provider, now):
        return None
    book = provider.book
    taken = 0
    try:
        latest = await asyncio.to_thread(store.read_latest, None)
        taken = apply_latest(provider, latest, now)
    except Exception as exc:  # noqa: BLE001 - a dead database or a bad row: logged, the A2 rule then serves
        log.error("last close seed failed: %s", type(exc).__name__)
    finally:
        book.seed_attempted()
    return taken


# ---- the one background task --------------------------------------------------------------------------------------
async def run_forever(market, store, *, sleep=asyncio.sleep) -> None:
    """The lifespan's one task: every ``STEP_SECONDS`` seed each book once per closed spell (M2: keyed on the book
    instance AND the spell, so a re-login in the same spell seeds the new book) and write the close once per trading
    day. Every failure is logged and the loop goes on; it never touches the feed."""
    def current_book():
        return None if market.feed is None else getattr(market.feed.ctx.provider, "book", None)

    writer = CloseWriter(store, current_book)
    seeded: tuple[object, datetime.datetime] | None = None  # (book, spell) last seeded

    while True:
        try:
            if market.feed is not None:
                now = market.feed.ctx.clock()
                provider = market.feed.ctx.provider
                spell = last_close(now)
                book = getattr(provider, "book", None)
                if spell is not None and book is not None and (seeded is None or seeded[0] is not book
                                                               or seeded[1] != spell):
                    taken = await seed_once(provider, store, now)
                    if taken is not None:
                        seeded = (book, spell)
                        log.info("last close: %d stored closes seeded into the book", taken)
                await writer.step(now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the loop outlives a dead database or a bad row
            log.error("last close task: %s", type(exc).__name__)
        await sleep(STEP_SECONDS)


def start(market) -> asyncio.Task[None] | None:
    """The lifespan's entry (live market only). None when there is no market."""
    if market is None:
        return None
    from ofo_app.config import get_settings  # noqa: PLC0415

    store = PostgresLastCloseStore(get_settings().DATABASE_URL)
    task = asyncio.get_running_loop().create_task(run_forever(market, store), name="last-close")
    task._ofo_store = store  # type: ignore[attr-defined]  # closed by ``stop``
    return task


async def stop(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    store = getattr(task, "_ofo_store", None)
    if store is not None:
        await asyncio.to_thread(store.close)
