"""Making a day final from Kite's candles, filling feed gaps, and deriving 5-minute and daily bars (W-062, ADR-067).

Per ADR-067: after the close every minute Kite has replaces the live bar (source KITE); a minute only the live feed has
stays LIVE (provisional); a minute inside a recorded feed gap is filled from Kite's candles and marked BACKFILLED,
never LIVE; 5-minute and daily bars are derived on demand from one-minute bars and are never stored here. A day that
could not be fully fetched stays PROVISIONAL and says so. Standard library only; no float.
"""
from __future__ import annotations

import datetime
import logging
from collections import Counter
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Iterable, Sequence

from ofo.history.bars import ONE_MINUTE, BarSource, MinuteBar, minute_of
from ofo.history.candles import CandleError, MinuteCandleSource
from ofo.history.store import DayStatus, HistoryStore

log = logging.getLogger("ofo.history")

Gap = tuple[datetime.datetime, datetime.datetime]


@dataclass(frozen=True)
class FinalizeCounts:
    replaced: int  # a live bar replaced by Kite's candle
    kept_live: int  # a live bar Kite has no candle for: stays LIVE
    kite_only: int  # a minute Kite has and the live feed never produced


def _key(bar: MinuteBar) -> tuple[str, datetime.datetime]:
    return (bar.instrument_id, bar.minute)


def finalize_day(live: Iterable[MinuteBar], kite: Iterable[MinuteBar]) -> tuple[list[MinuteBar], FinalizeCounts]:
    kite_by = {_key(b): b for b in kite}
    live_by = {_key(b): b for b in live}
    out: dict[tuple[str, datetime.datetime], MinuteBar] = dict(live_by)
    replaced = kite_only = 0
    for key, candle in kite_by.items():
        if key in live_by:
            replaced += 1
        else:
            kite_only += 1
        out[key] = replace(candle, source=BarSource.KITE)
    kept = sum(1 for key in live_by if key not in kite_by)
    return sorted(out.values(), key=_key), FinalizeCounts(replaced, kept, kite_only)


def in_gap(minute: datetime.datetime, gaps: Sequence[Gap]) -> bool:
    """A minute is touched by a gap when the gap overlaps any part of it."""
    return any(minute_of(start) <= minute <= minute_of(end) for start, end in gaps)


def fill_gaps(live: Iterable[MinuteBar], kite: Iterable[MinuteBar], gaps: Sequence[Gap]) -> list[MinuteBar]:
    """Every minute touched by a gap and present in Kite's candles becomes a BACKFILLED bar (a live bar there, whose
    close may be stale, is replaced); a gap minute Kite lacks is dropped from the live bars (it is not trustworthy)."""
    kite_by = {_key(b): b for b in kite}
    out: dict[tuple[str, datetime.datetime], MinuteBar] = {}
    for bar in live:
        if in_gap(bar.minute, gaps):
            continue
        out[_key(bar)] = bar
    for key, candle in kite_by.items():
        if in_gap(candle.minute, gaps):
            out[key] = replace(candle, source=BarSource.BACKFILLED)
    return sorted(out.values(), key=_key)


@dataclass(frozen=True)
class DayResult:
    status: DayStatus
    counts: FinalizeCounts | None
    errors: dict[str, int]


def finalize_into(store: HistoryStore, day: datetime.date, instrument_ids: Sequence[str], source: MinuteCandleSource,
                  *, start: datetime.datetime, end: datetime.datetime) -> DayResult:
    """Fetch Kite's candles for each instrument and make the day final only if EVERY fetch gave a usable answer.

    Answer states: candles returned (replace); empty list (no trades - keep live); error or timeout (counted, day stays
    PROVISIONAL); malformed body (refused, stays PROVISIONAL); a candle outside the requested range (ignored, counted).
    Nothing is raised to the caller."""
    errors: Counter = Counter()
    kite: list[MinuteBar] = []
    for iid in instrument_ids:
        try:
            candles = source.minute_candles(iid, start, end)
        except CandleError:
            errors["malformed"] += 1
            continue
        except Exception as exc:  # HTTP error, timeout, anything: the day stays provisional
            errors["fetch_failed"] += 1
            log.warning("history fetch failed: %s", type(exc).__name__)  # never the token, never the values
            continue
        for candle in candles:
            if not (start <= candle.minute <= end) or candle.instrument_id != iid:
                errors["out_of_range"] += 1
                continue
            kite.append(candle)
    live = store.bars_for_day(day)
    final, counts = finalize_day(live, kite)
    store.put_bars(final)
    fetched_all = not (errors["malformed"] or errors["fetch_failed"])
    status = DayStatus.FINAL if fetched_all else DayStatus.PROVISIONAL
    store.set_day_status(day, status)
    return DayResult(status, counts, dict(errors))


# ---- derived bars, on demand ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PeriodBar:
    instrument_id: str
    start: datetime.datetime
    minutes: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    oi: int | None
    source: BarSource


def _combine(bars: list[MinuteBar], start: datetime.datetime) -> PeriodBar:
    bars = sorted(bars, key=lambda b: b.minute)
    volumes = [b.volume for b in bars if b.volume is not None]
    sources = {b.source for b in bars}
    if sources == {BarSource.KITE}:
        source = BarSource.KITE
    elif BarSource.LIVE in sources:
        source = BarSource.LIVE
    else:
        source = BarSource.BACKFILLED
    return PeriodBar(bars[0].instrument_id, start, len(bars), bars[0].open, max(b.high for b in bars),
                     min(b.low for b in bars), bars[-1].close, sum(volumes) if volumes else None, bars[-1].oi, source)


def five_minute(bars: Iterable[MinuteBar]) -> list[PeriodBar]:
    groups: dict[tuple[str, datetime.datetime], list[MinuteBar]] = {}
    for b in bars:
        start = b.minute.replace(minute=b.minute.minute - b.minute.minute % 5)
        groups.setdefault((b.instrument_id, start), []).append(b)
    return [_combine(v, k[1]) for k, v in sorted(groups.items())]


def daily_bar(bars: Iterable[MinuteBar]) -> PeriodBar:
    bars = list(bars)
    if not bars:
        raise ValueError("a daily bar needs at least one minute bar")
    if len({b.instrument_id for b in bars}) != 1 or len({b.minute.date() for b in bars}) != 1:
        raise ValueError("a daily bar is for one instrument and one day")
    first = min(b.minute for b in bars)
    return _combine(bars, first.replace(hour=0, minute=0))
