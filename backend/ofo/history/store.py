"""The history store port (W-062, REQ-051 AC-2): it accepts only ``MinuteBar``s, so a quote or a raw tick has no way in.

``InMemoryHistoryStore`` is the reference and the test double; the PostgreSQL store (W-067,
``ofo_app.history_store``) runs these same rules through it. Standard library only.
"""
from __future__ import annotations

import datetime
import enum
from collections import Counter
from dataclasses import dataclass, replace
from typing import Iterable, Protocol

from ofo.history.bars import BarSource, MinuteBar, minute_in_gap, session_gaps

_RANK = {BarSource.LIVE: 0, BarSource.BACKFILLED: 1, BarSource.KITE: 2}

Gap = tuple[datetime.datetime, datetime.datetime]


class DayStatus(enum.Enum):
    PROVISIONAL = "provisional"
    FINAL = "final"


@dataclass(frozen=True)
class FinalizeCounts:
    replaced: int  # a live bar replaced by Kite's candle
    kept_live: int  # a live bar Kite has no candle for: stays LIVE
    kite_only: int  # a minute Kite has and the live feed never produced


class HistoryStore(Protocol):
    """Every implementation enforces the same three rules in ONE private writer that EVERY write method passes
    (the contract test ``tests/history/test_store_contract.py`` runs each rule through each write method):

    1. no LIVE bar inside a recorded feed gap: a LIVE bar there is refused, and a LIVE bar already stored when its gap
       is recorded is removed (gaps are clipped to the session 09:15-15:30 IST: a closed market is not a gap);
    2. a source is never lowered: KITE > BACKFILLED > LIVE; a lower bar never replaces a higher one;
    3. a FINAL day never changes: every write to it (bars, gaps, status back to PROVISIONAL) is refused and counted,
       except the finalize transition itself, which is idempotent.

    Only ``MinuteBar`` is accepted (REQ-051 AC-2). A new write method must go through the writer, and the contract test
    must be extended for it."""

    def put_bars(self, bars: Iterable[MinuteBar]) -> None: ...

    def record_gaps(self, gaps: Iterable[Gap]) -> None: ...

    def replace_day_bars(self, day: datetime.date, bars: Iterable[MinuteBar]) -> None: ...

    def apply_candles(self, day: datetime.date, candles: Iterable[MinuteBar]) -> FinalizeCounts: ...

    def set_day_status(self, day: datetime.date, status: DayStatus) -> None: ...

    def bars(self, instrument_id: str, day: datetime.date) -> list[MinuteBar]: ...

    def bars_for_day(self, day: datetime.date) -> list[MinuteBar]: ...

    def gaps(self, day: datetime.date) -> list[Gap]: ...

    def day_status(self, day: datetime.date) -> DayStatus: ...

    def gap_minutes_missing(self, day: datetime.date) -> int: ...

    def last_bar_minutes(self, day: datetime.date) -> dict[str, datetime.datetime]:
        """Per instrument, the minute of its latest stored (not removed) bar of ``day``: what finalize must reach."""
        ...


class InMemoryHistoryStore:
    def __init__(self) -> None:
        self._bars: dict[tuple[str, datetime.datetime], MinuteBar] = {}
        self._status: dict[datetime.date, DayStatus] = {}
        self._gaps: set[Gap] = set()
        self._gap_dropped: set[tuple[str, datetime.datetime]] = set()  # LIVE bars the gap rule kept out
        self.counters: Counter = Counter()

    @property
    def dropped_in_gap(self) -> int:
        return self.counters["dropped_in_gap"]

    # ---- the public write methods: thin, each one only calls the writer --------------------------------------------
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

    # ---- the ONE writer ---------------------------------------------------------------------------------------------
    def _write(self, *, bars: list[MinuteBar] = (), gaps: list[Gap] = (), replace_day: datetime.date | None = None,
               candles: list[MinuteBar] = (), candle_day: datetime.date | None = None,
               status: tuple[datetime.date, DayStatus] | None = None) -> FinalizeCounts | None:
        for b in (*bars, *candles):  # validate everything first: a bad batch changes nothing
            if not isinstance(b, MinuteBar):
                raise TypeError(f"the history store accepts only MinuteBar, got {type(b).__name__}")
        if replace_day is not None and any(b.minute.date() != replace_day for b in bars):
            raise TypeError("replace_day_bars takes only MinuteBars of that day")
        if candle_day is not None and any(c.minute.date() != candle_day for c in candles):
            raise TypeError("apply_candles takes only candles of that day")

        # gaps: clipped to the session; none on a FINAL day; a LIVE bar already stored inside one is removed
        for start, end in gaps:
            for piece in session_gaps(start, end):
                if self._final(piece[0].date()):
                    self.counters["refused_final"] += 1
                else:
                    self._gaps.add(piece)
        for key in [k for k, b in self._bars.items() if b.source is BarSource.LIVE and self._in_gap(b.minute)]:
            del self._bars[key]
            self._gap_dropped.add(key)
            self.counters["dropped_in_gap"] += 1

        # replacing a day's bars removes only LIVE bars the new batch does not carry (a higher source is never removed)
        if replace_day is not None:
            if self._final(replace_day):
                self.counters["refused_final"] += len(bars) or 1
                bars = []
            else:
                keep = {(b.instrument_id, b.minute) for b in bars}
                for key in [k for k, b in self._bars.items() if k[1].date() == replace_day and k not in keep
                            and b.source is BarSource.LIVE]:
                    del self._bars[key]

        for b in bars:
            self._admit(b)

        counts = None
        if candle_day is not None:
            counts = self._apply_candles(candle_day, candles)

        if status is not None:
            day, new = status
            if self._final(day) and new is not DayStatus.FINAL:
                self.counters["refused_final"] += 1  # a FINAL day never goes back
            else:
                self._status[day] = new
        return counts

    def _admit(self, b: MinuteBar) -> None:
        """Rules 1-3 for one bar; the only place a bar enters ``_bars``."""
        key = (b.instrument_id, b.minute)
        if self._final(b.minute.date()):
            self.counters["refused_final"] += 1
        elif b.source is BarSource.LIVE and self._in_gap(b.minute):
            self._gap_dropped.add(key)
            self.counters["dropped_in_gap"] += 1
        elif key in self._bars and _RANK[b.source] < _RANK[self._bars[key].source]:
            self.counters["refused_lower"] += 1
        else:
            self._bars[key] = b

    def _apply_candles(self, day: datetime.date, candles: list[MinuteBar]) -> FinalizeCounts:
        """Kite's candles for a day: in a gap -> BACKFILLED, elsewhere -> KITE; the store decides the source."""
        if self._final(day):
            self.counters["refused_final"] += len(candles) or 1
            return FinalizeCounts(0, 0, 0)
        replaced = kite_only = 0
        for c in candles:
            key = (c.instrument_id, c.minute)
            source = BarSource.BACKFILLED if self._in_gap(c.minute) else BarSource.KITE
            if key in self._bars and self._bars[key].source is BarSource.LIVE:
                replaced += 1
            elif key not in self._bars:
                kite_only += 1
            self._admit(replace(c, source=source))
        kept = sum(1 for b in self._bars.values() if b.minute.date() == day and b.source is BarSource.LIVE)
        return FinalizeCounts(replaced, kept, kite_only)

    # ---- a persistent store's working set ---------------------------------------------------------------------------
    def seed(self, *, bars: Iterable[MinuteBar] = (), gaps: Iterable[Gap] = (),
             statuses: Iterable[tuple[datetime.date, DayStatus]] = ()) -> None:
        """Load state that was ALREADY accepted by the rules (rows a database holds) without applying any rule. A
        database-backed store seeds the slice a write can touch, runs the real write method, and persists the
        difference (``state()`` before and after): the three rules stay in ``_write``, never re-implemented."""
        for b in bars:
            self._bars[(b.instrument_id, b.minute)] = b
        self._gaps.update(gaps)
        for day, status in statuses:
            self._status[day] = status

    def state(self) -> tuple[dict[tuple[str, datetime.datetime], MinuteBar], set[Gap], dict[datetime.date, DayStatus],
                             set[tuple[str, datetime.datetime]]]:
        """Copies of (bars, gaps, day statuses, LIVE bars the gap rule kept out) for diffing."""
        return dict(self._bars), set(self._gaps), dict(self._status), set(self._gap_dropped)

    # ---- reads ------------------------------------------------------------------------------------------------------
    def _final(self, day: datetime.date) -> bool:
        return self._status.get(day) is DayStatus.FINAL

    def _in_gap(self, minute: datetime.datetime) -> bool:
        return any(minute_in_gap(minute, g) for g in self._gaps)

    def gaps(self, day: datetime.date) -> list[Gap]:
        return sorted(g for g in self._gaps if g[0].date() == day)

    def gap_minutes_missing(self, day: datetime.date) -> int:
        """LIVE bars the gap rule kept out for which no Kite candle exists (a gap minute with nothing to fill it)."""
        return sum(1 for key in self._gap_dropped if key[1].date() == day and key not in self._bars)

    def last_bar_minutes(self, day: datetime.date) -> dict[str, datetime.datetime]:
        out: dict[str, datetime.datetime] = {}
        for iid, minute in self._bars:
            if minute.date() == day and (iid not in out or minute > out[iid]):
                out[iid] = minute
        return out

    def bars(self, instrument_id: str, day: datetime.date) -> list[MinuteBar]:
        return sorted((b for (iid, _), b in self._bars.items() if iid == instrument_id and b.minute.date() == day),
                      key=lambda b: b.minute)

    def bars_for_day(self, day: datetime.date) -> list[MinuteBar]:
        return sorted((b for b in self._bars.values() if b.minute.date() == day),
                      key=lambda b: (b.instrument_id, b.minute))

    def day_status(self, day: datetime.date) -> DayStatus:
        return self._status.get(day, DayStatus.PROVISIONAL)

    def all_stored(self) -> list[object]:
        return list(self._bars.values())
