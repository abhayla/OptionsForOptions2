"""GC-UI step 5 (D-B40 / D-B41; REQ-091 AC-2..AC-5, ADR-203, F-64): the Strategy Chart's points from minute bars.

Pure: the caller fetched each leg's and the index future's Kite minute bars (``ofo_app.kite_history``). One point per
minute the FUTURE has, inside the window: the strategy's combined net price per unit from the one engine
(:func:`ofo.engine.money_summary.combined_price_series`; a minute any leg lacks is a gap, never interpolated) beside
the future's close. Window: the last ``days`` trading days the future has bars for, starting no earlier than the
latest leg's first bar (AC-5, a ``leg_listed_from`` note) and ending no later than the earliest leg's last bar when a
leg's bars stop before the future's (an expired leg, a ``leg_ended_on`` note). States: available; a leg with no bars
(not listed in the window); the future with no bars; every minute a gap.
"""
from __future__ import annotations

import datetime
import enum
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.engine.money_summary import combined_price_series
from ofo.errors.explanations import render_explanation
from ofo.history.bars import MinuteBar
from ofo.money import PAISE


class State(enum.Enum):
    AVAILABLE = "available"
    LEG_NOT_LISTED = "leg_not_listed"
    NO_FUTURE_CANDLES = "no_future_candles"
    ALL_GAPS = "all_gaps"


@dataclass(frozen=True)
class Point:
    t: datetime.datetime
    strategy: Decimal | None  # None = a gap (a leg without a candle that minute)
    future: Decimal


@dataclass(frozen=True)
class Chart:
    state: State
    points: tuple[Point, ...] = ()
    as_of: datetime.datetime | None = None
    #: ("leg_listed_from", label, date, days shown) / ("leg_ended_on", label, date)
    notes: tuple[tuple[Any, ...], ...] = ()
    missing_leg: str | None = None


def strategy_display(value: Decimal) -> str:
    """Two decimals (REQ-091 AC-2: a per-unit price)."""
    return render_explanation("cell_number", value=value.quantize(PAISE))


def future_display(value: Decimal) -> str:
    return render_explanation("cell_points", value=value)


def build_chart(legs: Sequence[Any], leg_bars: Sequence[Sequence[MinuteBar]], future_bars: Sequence[MinuteBar], *,
                leg_labels: Sequence[str], days: int, invert: bool = False) -> Chart:
    """``legs`` carry ``action`` and ``lots``; ``leg_bars`` and ``leg_labels`` are parallel to them."""
    for label, bars in zip(leg_labels, leg_bars, strict=True):
        if not bars:
            return Chart(State.LEG_NOT_LISTED, missing_leg=label)
    if not future_bars:
        return Chart(State.NO_FUTURE_CANDLES)
    fut = sorted(future_bars, key=lambda b: b.minute)
    dates = sorted({b.minute.date() for b in fut})[-days:]
    start = next(b.minute for b in fut if b.minute.date() == dates[0])
    notes: list[tuple[Any, ...]] = []
    firsts = [min(b.minute for b in bars) for bars in leg_bars]
    lasts = [max(b.minute for b in bars) for bars in leg_bars]
    latest_first = max(firsts)
    if latest_first > start:
        start = latest_first
        i = firsts.index(latest_first)
        shown = len([d for d in dates if d >= latest_first.date()])
        notes.append(("leg_listed_from", leg_labels[i], latest_first.date(), shown))
    end = fut[-1].minute
    earliest_last = min(lasts)
    if earliest_last < end:
        end = earliest_last
        notes.append(("leg_ended_on", leg_labels[lasts.index(earliest_last)], earliest_last.date()))
    window = [b for b in fut if start <= b.minute <= end]
    closes = [{b.minute: b.close for b in bars} for bars in leg_bars]
    values = combined_price_series(legs, closes, [b.minute for b in window], invert=invert)
    points = tuple(Point(b.minute, v, b.close) for b, v in zip(window, values, strict=True))
    if not points or all(p.strategy is None for p in points):
        return Chart(State.ALL_GAPS, points, points[-1].t if points else None, tuple(notes))
    return Chart(State.AVAILABLE, points, points[-1].t, tuple(notes))
