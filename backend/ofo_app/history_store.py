"""The PostgreSQL implementation of the W-062 ``HistoryStore`` port (W-067, REQ-051 AC-3, ADR-067).

One writer per rule (finding store-rule-enforced-per-call-site): the three rules (no LIVE bar in a feed gap, a source
is never lowered, a FINAL day never changes) live in ``ofo.history.store.InMemoryHistoryStore._write`` and nowhere
else. For each write this store seeds an in-memory working copy with the slice of persisted state the write can touch,
runs the REAL write method on it, and persists the difference in one transaction (serialised by an advisory lock). The
database adds its own last line (migration 0009's guards: no delete, no change to a final day, no lowered source).

The port is synchronous (the recorder is a plain callback), the driver is asyncpg: the store owns a private event loop
on a daemon thread and each call waits for its transaction. Connect and command timeouts are short, and the recorder
catches whatever a call raises, so a slow or dead database costs the recorder a bounded wait and a counted error, never
a fault in the feed (REQ-051 AC-5). Money is NUMERIC(14,2): a price finer than a paisa is refused, never rounded.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import threading
import time
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from ofo.history.bars import IST, BarSource, MinuteBar, session_gaps
from ofo.history.store import DayStatus, FinalizeCounts, Gap, InMemoryHistoryStore

_PAISA = Decimal("0.01")
_LOCK_KEY = 6700067  # pg_advisory_xact_lock key: one history writer at a time (the recorder and the finalize job)
_CONNECT_TIMEOUT_S = 5
_COMMAND_TIMEOUT_S = 15
_UNREACHABLE = (OSError, TimeoutError, InterfaceError, OperationalError)  # the database could not be reached
DOWN_BACKOFF_S = 20.0


class StoreUnavailable(RuntimeError):
    """The database was unreachable a moment ago: the call failed at once instead of waiting for a connect timeout."""

_COLUMNS = "instrument_id, minute, open, high, low, close, volume, oi, source"
_UPSERT = """
    INSERT INTO public.history_minute_bars
        (instrument_id, minute, trade_date, open, high, low, close, volume, oi, source, removed)
    SELECT t.instrument_id, t.minute, t.trade_date, t.open, t.high, t.low, t.close, t.volume, t.oi, t.source, FALSE
    FROM unnest(CAST(:instrument_id AS text[]), CAST(:minute AS timestamptz[]), CAST(:trade_date AS date[]),
                CAST(:open AS numeric[]), CAST(:high AS numeric[]), CAST(:low AS numeric[]), CAST(:close AS numeric[]),
                CAST(:volume AS bigint[]), CAST(:oi AS bigint[]), CAST(:source AS text[]))
        AS t(instrument_id, minute, trade_date, open, high, low, close, volume, oi, source)
    ON CONFLICT (instrument_id, minute) DO UPDATE SET
        open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
        volume = EXCLUDED.volume, oi = EXCLUDED.oi, source = EXCLUDED.source, removed = FALSE
"""
_COLUMN_NAMES = ("instrument_id", "minute", "trade_date", "open", "high", "low", "close", "volume", "oi", "source")


def _columns(rows: list[dict]) -> dict[str, list]:
    """Row dicts -> one list per column: a whole batch is ONE statement (arrays unnested server-side), not a round
    trip per row."""
    return {name: [r[name] for r in rows] for name in _COLUMN_NAMES}


def _row(b: MinuteBar) -> dict:
    return {"instrument_id": b.instrument_id, "minute": b.minute, "trade_date": b.minute.astimezone(IST).date(),
            "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume, "oi": b.oi,
            "source": b.source.value}


def _bar(r) -> MinuteBar:
    return MinuteBar(r[0], r[1].astimezone(IST), r[2], r[3], r[4], r[5], r[6], r[7], BarSource(r[8]))


def _check_paisa(bars: Iterable[MinuteBar]) -> None:
    for b in bars:
        for name in ("open", "high", "low", "close"):
            value = getattr(b, name)
            try:
                exact = value == value.quantize(_PAISA)
            except InvalidOperation:
                exact = False
            if not exact:
                raise ValueError(f"{name} {value} is not a whole number of paise: the history keeps NUMERIC(14,2) "
                                 "and never rounds a price (ADR-008)")


class PostgresHistoryStore:
    def __init__(self, url: str, *, down_backoff_s: float = DOWN_BACKOFF_S) -> None:
        self._url = url
        self._down_backoff_s = down_backoff_s
        self._down_until = 0.0  # monotonic time before which calls fail at once (REQ-051 AC-5: never stall the feed)
        self.counters: Counter = Counter()
        self._engine: AsyncEngine | None = None
        self._iso: AsyncConnection | None = None
        self._call = threading.Lock()  # one call at a time from this process
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="ofo-history-pg", daemon=True)
        self._thread.start()

    # ---- plumbing ---------------------------------------------------------------------------------------------------
    def _run(self, coro):
        if self._loop.is_closed() or not self._thread.is_alive():
            coro.close()
            raise RuntimeError("the history store is closed")
        with self._call:
            if time.monotonic() < self._down_until:
                coro.close()
                self.counters["skipped_unreachable"] += 1
                raise StoreUnavailable("the history database was unreachable; retrying shortly")
            try:
                return asyncio.run_coroutine_threadsafe(coro, self._loop).result()
            except _UNREACHABLE:
                self._down_until = time.monotonic() + self._down_backoff_s
                self.counters["unreachable"] += 1
                raise

    def _engine_(self) -> AsyncEngine:
        if self._engine is None:  # created on the store's own loop, the one every connection runs on
            self._engine = create_async_engine(
                self._url, pool_size=2, max_overflow=2, pool_pre_ping=True,
                connect_args={"timeout": _CONNECT_TIMEOUT_S, "command_timeout": _COMMAND_TIMEOUT_S,
                              "server_settings": {"jit": "off"}})
        return self._engine

    @contextlib.asynccontextmanager
    async def _tx(self):
        if self._iso is not None:  # test isolation: everything inside one outer transaction that is rolled back
            async with self._iso.begin_nested():
                yield self._iso
        else:
            async with self._engine_().begin() as conn:
                yield conn

    def close(self) -> None:
        """Dispose the engine (every connection) and stop the private loop. The store is unusable afterwards."""
        if self._loop.is_closed():
            return

        async def shut():
            if self._iso is not None:
                await self._iso.close()
                self._iso = None
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

    def begin_isolated(self) -> None:
        """Tests: run every following call inside one transaction on one connection; ``rollback_isolated`` undoes it."""
        async def start():
            conn = await self._engine_().connect()
            await conn.begin()
            self._iso = conn

        self._run(start())

    def rollback_isolated(self) -> None:
        async def stop():
            if self._iso is not None:
                await self._iso.rollback()
                await self._iso.close()
                self._iso = None

        self._run(stop())

    # ---- the public write methods: thin, each one only calls the one writer -----------------------------------------
    def put_bars(self, bars: Iterable[MinuteBar]) -> None:
        self._write(bars=list(bars))

    def record_gaps(self, gaps: Iterable[Gap]) -> None:
        self._write(gaps=list(gaps))

    def replace_day_bars(self, day: datetime.date, bars: Iterable[MinuteBar]) -> None:
        self._write(bars=list(bars), replace_day=day)

    def apply_candles(self, day: datetime.date, candles: Iterable[MinuteBar]) -> FinalizeCounts:
        return self._write(candles=list(candles), candle_day=day)

    def set_day_status(self, day: datetime.date, status: DayStatus) -> None:
        self._write(status=(day, status))

    def _write(self, *, bars: list[MinuteBar] = (), gaps: list[Gap] = (), replace_day: datetime.date | None = None,
               candles: list[MinuteBar] = (), candle_day: datetime.date | None = None,
               status: tuple[datetime.date, DayStatus] | None = None) -> FinalizeCounts | None:
        for b in (*bars, *candles):  # a bad batch changes nothing: refuse before any connection is opened
            if not isinstance(b, MinuteBar):
                raise TypeError(f"the history store accepts only MinuteBar, got {type(b).__name__}")
        _check_paisa((*bars, *candles))
        kw = dict(bars=list(bars), gaps=list(gaps), replace_day=replace_day, candles=list(candles),
                  candle_day=candle_day, status=status)
        return self._run(self._write_async(kw))

    async def _write_async(self, kw: dict) -> FinalizeCounts | None:
        pieces = [p for start, end in kw["gaps"] for p in session_gaps(start, end)]
        days = {b.minute.date() for b in (*kw["bars"], *kw["candles"])} | {p[0].date() for p in pieces}
        days |= {d for d in (kw["replace_day"], kw["candle_day"]) if d is not None}
        if kw["status"] is not None:
            days.add(kw["status"][0])
        async with self._tx() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
            work = InMemoryHistoryStore()
            work.seed(statuses=await self._statuses(conn, days), gaps=await self._gaps(conn, days),
                      bars=await self._slice(conn, kw, pieces))
            before_bars, before_gaps, before_status, before_dropped = work.state()
            counts = work._write(**kw)  # THE writer: rules 1-3, validation, counters
            bars, gaps, statuses, dropped = work.state()
            self.counters.update(work.counters)

            changed = [_row(b) for k, b in bars.items() if before_bars.get(k) != b]
            if changed:
                await conn.execute(text(_UPSERT), _columns(changed))
            removed = [k for k in before_bars if k not in bars]
            if removed:  # the application role cannot DELETE: a removed LIVE bar is flagged, and reads honour it
                await conn.execute(text(
                    "UPDATE public.history_minute_bars AS b SET removed = TRUE FROM unnest(CAST(:i AS text[]), "
                    "CAST(:m AS timestamptz[])) AS k(i, m) WHERE b.instrument_id = k.i AND b.minute = k.m"),
                    {"i": [k[0] for k in removed], "m": [k[1] for k in removed]})
            new_gaps = sorted(gaps - before_gaps)
            if new_gaps:
                await conn.execute(text(
                    "INSERT INTO public.history_feed_gaps (gap_start, gap_end, trade_date) SELECT s, e, d FROM "
                    "unnest(CAST(:s AS timestamptz[]), CAST(:e AS timestamptz[]), CAST(:d AS date[])) AS k(s, e, d) "
                    "ON CONFLICT DO NOTHING"),
                    {"s": [g[0] for g in new_gaps], "e": [g[1] for g in new_gaps],
                     "d": [g[0].astimezone(IST).date() for g in new_gaps]})
            new_dropped = sorted(dropped - before_dropped)
            if new_dropped:
                await conn.execute(text(
                    "INSERT INTO public.history_gap_dropped (instrument_id, minute, trade_date) SELECT i, m, d FROM "
                    "unnest(CAST(:i AS text[]), CAST(:m AS timestamptz[]), CAST(:d AS date[])) AS k(i, m, d) "
                    "ON CONFLICT DO NOTHING"),
                    {"i": [k[0] for k in new_dropped], "m": [k[1] for k in new_dropped],
                     "d": [k[1].astimezone(IST).date() for k in new_dropped]})
            for day, new in statuses.items():
                if before_status.get(day) is not new:
                    await conn.execute(text(
                        "INSERT INTO public.history_day_status (trade_date, status) VALUES (:d, :s) "
                        "ON CONFLICT (trade_date) DO UPDATE SET status = EXCLUDED.status"),
                        {"d": day, "s": new.value})
            if counts is not None and before_status.get(kw["candle_day"]) is not DayStatus.FINAL:
                # the LIVE bars left on the day, all of them (a refused final day reports zeros, as in memory)
                kept = await conn.scalar(text(
                    "SELECT count(*) FROM public.history_minute_bars "
                    "WHERE trade_date = :d AND source = 'live' AND NOT removed"), {"d": kw["candle_day"]})
                counts = FinalizeCounts(counts.replaced, int(kept), counts.kite_only)
            return counts

    # ---- what a write can touch -------------------------------------------------------------------------------------
    @staticmethod
    async def _statuses(conn, days):
        rows = await conn.execute(text("SELECT trade_date, status FROM public.history_day_status "
                                       "WHERE trade_date = ANY(:d)"), {"d": sorted(days)})
        return [(r[0], DayStatus(r[1])) for r in rows]

    @staticmethod
    async def _gaps(conn, days):
        rows = await conn.execute(text("SELECT gap_start, gap_end FROM public.history_feed_gaps "
                                       "WHERE trade_date = ANY(:d)"), {"d": sorted(days)})
        return [(r[0].astimezone(IST), r[1].astimezone(IST)) for r in rows]

    @staticmethod
    async def _slice(conn, kw: dict, pieces) -> list[MinuteBar]:
        """The stored bars the write can look at: the keys it names, the LIVE bars inside a NEW gap, the LIVE bars of
        a day being replaced. (A LIVE bar elsewhere is untouchable by this write, so it need not be loaded.)"""
        found: dict[tuple[str, datetime.datetime], MinuteBar] = {}
        named = [(b.instrument_id, b.minute) for b in (*kw["bars"], *kw["candles"])]
        if named:
            # a JOIN on the primary key: one index probe per named key (the round-1 IN (SELECT ...) planned as a full
            # scan with a nested loop: 6.8 s for 240 keys, no completion at 240 instruments x 375 minutes)
            rows = await conn.execute(text(
                "SELECT b.instrument_id, b.minute, b.open, b.high, b.low, b.close, b.volume, b.oi, b.source "
                "FROM unnest(CAST(:i AS text[]), CAST(:m AS timestamptz[])) AS k(i, m) "
                "JOIN public.history_minute_bars AS b ON b.instrument_id = k.i AND b.minute = k.m WHERE NOT b.removed"),
                {"i": [n[0] for n in named], "m": [n[1] for n in named]})
            found.update({(b.instrument_id, b.minute): b for b in map(_bar, rows)})
        for start, end in pieces:  # a minute [m, m+60s) overlaps the gap [s, e)
            rows = await conn.execute(text(
                f"SELECT {_COLUMNS} FROM public.history_minute_bars WHERE trade_date = :d AND NOT removed "
                "AND source = 'live' AND minute < :e AND minute + interval '1 minute' > :s"),
                {"s": start, "e": end, "d": start.astimezone(IST).date()})
            found.update({(b.instrument_id, b.minute): b for b in map(_bar, rows)})
        if kw["replace_day"] is not None:
            rows = await conn.execute(text(
                f"SELECT {_COLUMNS} FROM public.history_minute_bars WHERE NOT removed AND source = 'live' "
                "AND trade_date = :d"), {"d": kw["replace_day"]})
            found.update({(b.instrument_id, b.minute): b for b in map(_bar, rows)})
        return list(found.values())

    # ---- reads ------------------------------------------------------------------------------------------------------
    def bars(self, instrument_id: str, day: datetime.date) -> list[MinuteBar]:
        async def read():
            async with self._tx() as conn:
                rows = await conn.execute(text(
                    f"SELECT {_COLUMNS} FROM public.history_minute_bars "
                    "WHERE instrument_id = :i AND trade_date = :d AND NOT removed"), {"i": instrument_id, "d": day})
                return sorted(map(_bar, rows), key=lambda b: b.minute)

        return self._run(read())

    def bars_for_day(self, day: datetime.date) -> list[MinuteBar]:
        async def read():
            async with self._tx() as conn:
                rows = await conn.execute(text(
                    f"SELECT {_COLUMNS} FROM public.history_minute_bars WHERE trade_date = :d AND NOT removed"),
                    {"d": day})
                return sorted(map(_bar, rows), key=lambda b: (b.instrument_id, b.minute))  # Python order, as in memory

        return self._run(read())

    def gaps(self, day: datetime.date) -> list[Gap]:
        async def read():
            async with self._tx() as conn:
                return sorted(await self._gaps(conn, {day}))

        return self._run(read())

    def day_status(self, day: datetime.date) -> DayStatus:
        async def read():
            async with self._tx() as conn:
                return dict(await self._statuses(conn, {day})).get(day, DayStatus.PROVISIONAL)

        return self._run(read())

    def last_bar_minutes(self, day: datetime.date) -> dict[str, datetime.datetime]:
        async def read():
            async with self._tx() as conn:
                rows = await conn.execute(text(
                    "SELECT instrument_id, max(minute) FROM public.history_minute_bars "
                    "WHERE trade_date = :d AND NOT removed GROUP BY instrument_id"), {"d": day})
                return {r[0]: r[1].astimezone(IST) for r in rows}

        return self._run(read())

    def gap_minutes_missing(self, day: datetime.date) -> int:
        async def read():
            async with self._tx() as conn:
                return int(await conn.scalar(text(
                    "SELECT count(*) FROM public.history_gap_dropped AS d WHERE d.trade_date = :d AND NOT EXISTS "
                    "(SELECT 1 FROM public.history_minute_bars AS b WHERE b.instrument_id = d.instrument_id "
                    "AND b.minute = d.minute AND NOT b.removed)"), {"d": day}))

        return self._run(read())
