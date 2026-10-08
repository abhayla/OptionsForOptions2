"""The history store port (W-062, REQ-051 AC-2): it accepts only ``MinuteBar``s, so a quote or a raw tick has no way in.

The PostgreSQL implementation is a later work item (needs the ADR-048 test database); ``InMemoryHistoryStore`` is the
reference and the test double. One bar per instrument and minute; a better source never loses to a worse one
(KITE > BACKFILLED > LIVE). Standard library only.
"""
from __future__ import annotations

import datetime
import enum
from typing import Iterable, Protocol

from ofo.history.bars import BarSource, MinuteBar

_RANK = {BarSource.LIVE: 0, BarSource.BACKFILLED: 1, BarSource.KITE: 2}


class DayStatus(enum.Enum):
    PROVISIONAL = "provisional"
    FINAL = "final"


class HistoryStore(Protocol):
    def put_bars(self, bars: Iterable[MinuteBar]) -> None: ...

    def bars(self, instrument_id: str, day: datetime.date) -> list[MinuteBar]: ...

    def bars_for_day(self, day: datetime.date) -> list[MinuteBar]: ...

    def day_status(self, day: datetime.date) -> DayStatus: ...

    def set_day_status(self, day: datetime.date, status: DayStatus) -> None: ...


class InMemoryHistoryStore:
    def __init__(self) -> None:
        self._bars: dict[tuple[str, datetime.datetime], MinuteBar] = {}
        self._status: dict[datetime.date, DayStatus] = {}

    def put_bars(self, bars: Iterable[MinuteBar]) -> None:
        batch = list(bars)
        for b in batch:  # validate everything first: a bad batch stores nothing
            if not isinstance(b, MinuteBar):
                raise TypeError(f"the history store accepts only MinuteBar, got {type(b).__name__}")
        for b in batch:
            key = (b.instrument_id, b.minute)
            old = self._bars.get(key)
            if old is None or _RANK[b.source] >= _RANK[old.source]:
                self._bars[key] = b

    def bars(self, instrument_id: str, day: datetime.date) -> list[MinuteBar]:
        return sorted((b for (iid, _), b in self._bars.items() if iid == instrument_id and b.minute.date() == day),
                      key=lambda b: b.minute)

    def bars_for_day(self, day: datetime.date) -> list[MinuteBar]:
        return sorted((b for b in self._bars.values() if b.minute.date() == day),
                      key=lambda b: (b.instrument_id, b.minute))

    def day_status(self, day: datetime.date) -> DayStatus:
        return self._status.get(day, DayStatus.PROVISIONAL)

    def set_day_status(self, day: datetime.date, status: DayStatus) -> None:
        self._status[day] = status

    def all_stored(self) -> list[object]:
        return list(self._bars.values())
