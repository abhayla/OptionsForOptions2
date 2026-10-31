"""Each expiry's put-call-parity forward and implied dividend yield (ADR-061, REQ-072 AC-3, F-32).

Method (ADR-061): take the strikes nearest spot (21 by default: the at-the-money strike and 10 either side, over
the strikes the
chain lists); keep a strike only when its call AND its put both have a bid and an ask; per kept strike
``K + e^(rT)(C_mid - P_mid)``; the forward F is the MEDIAN of those values; the implied continuous dividend yield is
``q = r - ln(F/S)/T``. The engine is given spot S and q (ADR-063) and owns every Greek; ``effective_spot``
(``F e^(-rT)`` = ``S e^(-qT)``) is stored as a figure only and never fed to the engine.

Answer states (run-discipline B4 (d)), each a distinct outcome:

- the minimum number of usable strikes (3 by default) or more: ``source == "parity"``.
- fewer than that: ``source == "spot fallback"``, q = 0, the effective spot is spot itself, and ``label`` is
  "estimated from spot" so every IV and Greek built on it carries that label - never silent.
- spot missing, UNHEALTHY or UNAVAILABLE: :class:`ForwardUnavailable` (refused).
- spot STALE or DELAYED: computed from the option quotes of the same snapshot (each quote must itself be AVAILABLE,
  so a stale snapshot falls back to spot) and ``spot_health`` records it; :func:`ofo.engine.model.model_inputs`
  labels every output "stale since HH:MM IST" - the one stale policy, never used silently (REQ-072 AC-2).
- T at or below zero (the valuation is at or after the expiry close): :class:`ForwardUnavailable` (expired).
- a median forward at or below zero (absurd quotes): :class:`ForwardUnavailable`, never a raw math error.
- a strike with ask below bid on either leg: skipped and counted in ``crossed_skipped``.

``quality_spread`` (W-060 "Measured robustness") is max - min of the per-strike forwards over the strikes whose two
quotes are each no wider than the width setting (5% by default) of their own mid; it is stored only as a quality
figure and never changes F.

Standard library only; Decimal at every boundary, floats only inside the formulas.
"""
from __future__ import annotations

import datetime
import math
import statistics
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final, Iterable, Literal

from ofo.engine.black_scholes import DAYS_IN_YEAR, year_fraction
from ofo.errors.explanations import render_explanation
from ofo.engine.legs import Instrument
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.rules.inputs import DataHealth
from ofo.money import HUNDREDTH as _POINT

PARITY: Final = "parity"
SPOT_FALLBACK: Final = "spot fallback"
FALLBACK_LABEL: Final = render_explanation("label_estimated_from_spot")
_YIELD_STEP: Final = Decimal("0.0000000001")


@dataclass(frozen=True)
class ForwardQuality:
    """The three forward settings (REQ-167 AC-5 Pricing group), one required parameter object of
    :func:`parity_forward`: ``width`` (a strike's quotes count toward ``quality_spread`` when each is no wider than this
    fraction of its own mid), ``strikes_near`` (the strikes nearest spot read, the at-the-money one and half the rest
    either side) and ``min_strikes`` (fewest usable strikes for ``source == "parity"``). Frozen and hashable, so it is
    part of the shared compute-cache key: a changed setting can never be served from an entry computed with the old
    one. There is no default here: the number is written only in ``ofo/settings/registry.json``."""

    width: Decimal
    strikes_near: int
    min_strikes: int

    def __post_init__(self) -> None:
        if not isinstance(self.width, Decimal) or not self.width.is_finite() or self.width <= 0:
            raise ValueError(f"width must be a positive finite decimal.Decimal, got {self.width!r}")
        for name in ("strikes_near", "min_strikes"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(f"{name} must be a whole number of at least 1, got {v!r}")


class ForwardUnavailable(ValueError):
    """The forward cannot be computed at all (spot missing or stale, expiry passed); the calculation must refuse."""


def _q2(value: float) -> Decimal:
    if not math.isfinite(value):
        raise ValueError(f"non-finite value {value}")
    return Decimal(repr(value)).quantize(_POINT, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class ExpiryForward:
    """One expiry's forward, stored with its chain snapshot (ADR-061 consequences)."""

    expiry: datetime.date
    forward: Decimal
    implied_yield: Decimal
    effective_spot: Decimal
    strikes_used: int
    quality_spread: Decimal | None
    source: Literal["parity", "spot fallback"]
    spot: Decimal
    spot_timestamp: datetime.datetime
    years: Decimal
    rate: Decimal
    valuation_time: datetime.datetime
    days_in_year: int = DAYS_IN_YEAR
    strikes_considered: int = 0
    crossed_skipped: int = 0
    spot_health: DataHealth = DataHealth.AVAILABLE

    @property
    def label(self) -> str | None:
        """"estimated from spot" on the fallback, else None (ADR-061: the switch is never silent)."""
        return FALLBACK_LABEL if self.source == SPOT_FALLBACK else None


def _mid(q: NormalizedQuote | None) -> tuple[Decimal | None, bool]:
    """(mid, crossed). mid is None when the quote lacks a bid or an ask, or is crossed, or is not AVAILABLE."""
    if q is None or q.health is not DataHealth.AVAILABLE or q.bid is None or q.ask is None:
        return None, False
    if q.bid <= 0 or q.ask <= 0:
        return None, False
    if q.ask < q.bid:
        return None, True
    return mid_price(q.bid, q.ask), False


def mid_price(bid: Decimal, ask: Decimal) -> Decimal:
    """The bid-ask mid to 0.01 rupee, half-even: the one mid used by the forward AND by IV (the engine's price
    boundary accepts at most 2 decimals, so a half-paisa mid could not be solved for IV otherwise)."""
    return ((bid + ask) / 2).quantize(_POINT, rounding=ROUND_HALF_EVEN)


def _narrow(q: NormalizedQuote, mid: Decimal, width: Decimal) -> bool:
    return (q.ask - q.bid) <= width * mid  # type: ignore[operator]


def parity_forward(  # noqa: PLR0913
        chain: Iterable[NormalizedQuote], spot: NormalizedQuote | None, expiry: datetime.date,
        valuation: datetime.datetime, rate: Decimal, quality: ForwardQuality) -> ExpiryForward:
    """The ADR-061 forward of one expiry from its chain snapshot, the index spot quote and the valuation time;
    ``quality`` (required, no fallback) carries the three settings in force."""
    if not isinstance(quality, ForwardQuality):
        raise ValueError(f"quality must be a ForwardQuality, got {quality!r}")
    if not isinstance(rate, Decimal) or not rate.is_finite():
        raise ValueError(f"rate must be a finite decimal.Decimal, got {rate!r}")
    if spot is None or not is_live_price(spot.ltp):
        raise ForwardUnavailable("index spot is missing; the forward (and every IV/Greek on it) is refused")
    if spot.health in (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE):
        raise ForwardUnavailable(f"index spot is {spot.health.value}; never used in a calculation")
    try:
        years = year_fraction(valuation, expiry)
    except ValueError as exc:
        raise ForwardUnavailable(f"expired: {exc}") from exc
    s, t, r = float(spot.ltp), float(years), float(rate)
    by: dict[tuple[Decimal, Instrument], NormalizedQuote] = {}
    for q in chain:
        if q.expiry == expiry and q.instrument_type in (Instrument.CE, Instrument.PE) and q.strike is not None:
            by[(q.strike, q.instrument_type)] = q
    strikes = sorted({k for k, _ in by})
    near: list[Decimal] = []
    if strikes:
        atm = min(strikes, key=lambda k: abs(k - spot.ltp))
        i = strikes.index(atm)
        half = quality.strikes_near // 2
        near = strikes[max(0, i - half): i + half + 1]
    growth = math.exp(r * t)
    values: list[float] = []
    narrow: list[float] = []
    crossed = 0
    for k in near:
        cq, pq = by.get((k, Instrument.CE)), by.get((k, Instrument.PE))
        c_mid, c_x = _mid(cq)
        p_mid, p_x = _mid(pq)
        if c_x or p_x:
            crossed += 1
            continue
        if c_mid is None or p_mid is None:
            continue
        value = float(k) + growth * (float(c_mid) - float(p_mid))
        values.append(value)
        if _narrow(cq, c_mid, quality.width) and _narrow(pq, p_mid, quality.width):  # type: ignore[arg-type]
            narrow.append(value)
    spread = _q2(max(narrow) - min(narrow)) if narrow else None
    if len(values) < quality.min_strikes:
        return ExpiryForward(expiry=expiry, forward=_q2(s * growth), implied_yield=Decimal(0),
                             effective_spot=spot.ltp, strikes_used=len(values), quality_spread=spread,
                             source=SPOT_FALLBACK, spot=spot.ltp, spot_timestamp=spot.timestamp, years=years,
                             rate=rate, valuation_time=valuation, strikes_considered=len(near),
                             crossed_skipped=crossed, spot_health=spot.health)
    f = statistics.median(values)
    if not math.isfinite(f) or f <= 0:
        raise ForwardUnavailable(f"the median parity forward is {f}, not a positive level; the chain is unusable")
    q = r - math.log(f / s) / t
    return ExpiryForward(expiry=expiry, forward=_q2(f),
                         implied_yield=Decimal(repr(q)).quantize(_YIELD_STEP, rounding=ROUND_HALF_EVEN),
                         effective_spot=_q2(f * math.exp(-r * t)), strikes_used=len(values), quality_spread=spread,
                         source=PARITY, spot=spot.ltp, spot_timestamp=spot.timestamp, years=years, rate=rate,
                         valuation_time=valuation, strikes_considered=len(near), crossed_skipped=crossed,
                         spot_health=spot.health)


def spot_fallback_forward(expiry: datetime.date, spot: Decimal, spot_at: datetime.datetime,
                          valuation: datetime.datetime, rate: Decimal, *, days_in_year: int = DAYS_IN_YEAR,
                          spot_health: DataHealth = DataHealth.AVAILABLE) -> ExpiryForward:
    """The ADR-061 fallback when no chain snapshot is at hand: q = 0, labelled "estimated from spot", never silent."""
    if not isinstance(rate, Decimal) or not rate.is_finite():
        raise ValueError(f"rate must be a finite decimal.Decimal, got {rate!r}")
    try:
        years = year_fraction(valuation, expiry, days_in_year=days_in_year)
    except ValueError as exc:
        raise ForwardUnavailable(f"expired: {exc}") from exc
    return ExpiryForward(expiry=expiry, forward=_q2(float(spot) * math.exp(float(rate) * float(years))),
                         implied_yield=Decimal(0), effective_spot=spot, strikes_used=0, quality_spread=None,
                         source=SPOT_FALLBACK, spot=spot, spot_timestamp=spot_at, years=years, rate=rate,
                         valuation_time=valuation, days_in_year=days_in_year, spot_health=spot_health)
