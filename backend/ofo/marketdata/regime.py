"""Market regime inputs for T-11c and T-20b (ADR-277, ADR-280 (6) and (12)): pure, exact Decimal, standard library.

- ``vix_percentile``: the share of the last sessions' India VIX closes at or below today's VIX, x 100.
- ``adx``: Wilder's ADX over daily candles (period 14 by default): true range and directional movement smoothed by
  Wilder's running sum, DX from the two directional indices, ADX the Wilder average of DX. 25 or more reads as a
  trending market, 20 or less as range-bound (ADR-277 (3)).
Bad input raises ValueError (the evaluator answers "not checked", never a made-up value).
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, localcontext
from itertools import pairwise
from typing import Final

ADX_PERIOD: Final = 14
PERCENTILE_SESSIONS: Final = 250
_HUNDRED: Final = Decimal(100)
_PRECISION: Final = 40


def _positive(value: object, what: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{what} must be a positive finite Decimal, got {value!r}")
    return value


def vix_percentile(vix: Decimal, closes: Sequence[Decimal], sessions: int = PERCENTILE_SESSIONS) -> Decimal:
    """``vix``'s percentile among the last ``sessions`` closes (at or below it, x 100). Fewer closes than ``sessions``
    raises: a percentile over a shorter window is a different number. Example: VIX 14 among 10, 12, 14, 16, 18 -> 60."""
    _positive(vix, "vix")
    if len(closes) < sessions:
        raise ValueError(f"needs {sessions} closes, got {len(closes)}")
    window = [_positive(c, "close") for c in closes[-sessions:]]
    with localcontext(prec=_PRECISION):
        return Decimal(sum(1 for c in window if c <= vix)) * _HUNDRED / Decimal(sessions)


def adx(bars: Sequence[tuple[Decimal, Decimal, Decimal]], period: int = ADX_PERIOD) -> Decimal:
    """The latest ADX of ``bars`` = (high, low, close) per session, oldest first; needs at least ``2 x period`` bars
    (``period`` changes to seed the smoothing, ``period - 1`` more DX values to seed the average)."""
    if type(period) is not int or period < 1:
        raise ValueError(f"period must be a positive int, got {period!r}")
    if len(bars) < 2 * period:
        raise ValueError(f"needs {2 * period} daily bars, got {len(bars)}")
    rows = [(_positive(h, "high"), _positive(lo, "low"), _positive(c, "close")) for h, lo, c in bars]
    if any(lo > h for h, lo, _ in rows):
        raise ValueError("a bar's low is above its high")
    n = Decimal(period)
    with localcontext(prec=_PRECISION):
        moves = []
        for (ph, pl, pc), (h, lo, _c) in pairwise(rows):
            up, down = h - ph, pl - lo
            tr = max(h - lo, abs(h - pc), abs(lo - pc))
            plus = up if up > down and up > 0 else Decimal(0)
            minus = down if down > up and down > 0 else Decimal(0)
            moves.append((tr, plus, minus))
        tr_s, plus_s, minus_s = (sum((m[i] for m in moves[:period]), Decimal(0)) for i in range(3))
        dxs = [_dx(tr_s, plus_s, minus_s)]
        for tr, plus, minus in moves[period:]:
            tr_s, plus_s, minus_s = tr_s - tr_s / n + tr, plus_s - plus_s / n + plus, minus_s - minus_s / n + minus
            dxs.append(_dx(tr_s, plus_s, minus_s))
        value = sum(dxs[:period], Decimal(0)) / n
        for dx in dxs[period:]:
            value = (value * (n - 1) + dx) / n
        return value


def _dx(tr: Decimal, plus: Decimal, minus: Decimal) -> Decimal:
    if tr <= 0:
        raise ValueError("no true range over the window (every bar flat)")
    total = plus + minus  # the two DIs share the true range, so it cancels out of DX
    return Decimal(0) if total == 0 else _HUNDRED * abs(plus - minus) / total


__all__ = ["ADX_PERIOD", "PERCENTILE_SESSIONS", "adx", "vix_percentile"]
