"""IV, Greeks and Estimated Now on each expiry's parity forward (ADR-061; REQ-072 AC-3).

The engine's Black-Scholes API is unchanged (ADR-061 consequences): for a what-if level S the caller passes
``S e^(-qT)`` (:meth:`ExpiryForward.level_for`), with q the expiry's implied dividend yield. Sensitivities relative to
the index spot are then scaled (Hull, ch. 17, options on an index paying a continuous yield q): delta by e^(-qT),
gamma by e^(-2qT); vega and theta are the engine's at the effective level. The payoff, its CURRENT column and the
default range keep the index spot - they never come through here.

Every result carries ``label``: "estimated from spot" when the expiry's forward fell back to spot (fewer than 3
usable strikes); None otherwise. A leg whose expiry has no forward is refused, never priced silently on spot.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Mapping, Sequence

from ofo.engine.black_scholes import GREEK_STEP, Greeks, bs_greeks_unrounded, implied_volatility
from ofo.engine.estimate import EstimatedNow, estimate_now
from ofo.engine.inputs import StrategyInput
from ofo.engine.legs import Instrument
from ofo.marketdata.forward import FALLBACK_LABEL, ExpiryForward, ForwardUnavailable

Forwards = Mapping[datetime.date, ExpiryForward]


@dataclass(frozen=True)
class ForwardIV:
    iv: Decimal
    level: Decimal  # the effective level the IV was solved at
    label: str | None


@dataclass(frozen=True)
class ForwardGreeks:
    greeks: Greeks  # relative to the index spot, 4 dp
    level: Decimal
    label: str | None


@dataclass(frozen=True)
class ForwardEstimate:
    level: Decimal  # the what-if index level S
    leg_levels: tuple[Decimal, ...]  # S e^(-qT) given to the engine, per leg
    leg_pnls: tuple[Decimal, ...]
    total: Decimal
    label: str | None


def _check(fwd: object) -> ExpiryForward:
    if not isinstance(fwd, ExpiryForward):
        raise ValueError(f"an ExpiryForward is required, got {fwd!r}")
    return fwd


def iv_on_forward(kind: Instrument, price: Decimal, strike: Decimal, fwd: ExpiryForward) -> ForwardIV:
    """Implied volatility of a market price, solved at the expiry's effective spot."""
    f = _check(fwd)
    iv = implied_volatility(kind, price, f.effective_spot, strike, f.years, f.rate)
    return ForwardIV(iv, f.effective_spot, f.label)


def greeks_on_forward(kind: Instrument, strike: Decimal, vol: Decimal, fwd: ExpiryForward,
                      level: Decimal | None = None) -> ForwardGreeks:
    """Per-unit Greeks relative to the index at ``level`` (default: the live spot), rounded once to 4 dp."""
    f = _check(fwd)
    effective = f.level_for(f.spot if level is None else level)
    raw = bs_greeks_unrounded(kind, effective, strike, f.years, f.rate, vol)
    scaled = Greeks(delta=raw.delta * f.delta_scale, gamma=raw.gamma * f.gamma_scale, theta=raw.theta, vega=raw.vega)
    rounded = Greeks(**{n: getattr(scaled, n).quantize(GREEK_STEP, rounding=ROUND_HALF_EVEN)
                        for n in ("delta", "gamma", "theta", "vega")})
    return ForwardGreeks(rounded, effective, f.label)


def combined_label(forwards: Sequence[ExpiryForward]) -> str | None:
    return FALLBACK_LABEL if any(f.label for f in forwards) else None


def estimate_now_on_forward(inputs: StrategyInput, level: Decimal, forwards: Forwards) -> ForwardEstimate:
    """Estimated Now at index level S: each leg is marked by the engine at S e^(-qT) of its own expiry."""
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    used: list[ExpiryForward] = []
    leg_levels: list[Decimal] = []
    leg_pnls: list[Decimal] = []
    for leg in inputs.legs:
        fwd = forwards.get(leg.expiry)
        if fwd is None:
            raise ForwardUnavailable(f"no forward for expiry {leg.expiry} (leg {leg.contract}); estimate refused")
        _check(fwd)
        effective = fwd.level_for(level)
        single: EstimatedNow = estimate_now(dataclasses.replace(inputs, legs=(leg,)), effective)
        used.append(fwd)
        leg_levels.append(effective)
        leg_pnls.append(single.leg_pnls[0])
    return ForwardEstimate(level, tuple(leg_levels), tuple(leg_pnls), sum(leg_pnls, Decimal(0)), combined_label(used))


def estimate_now_grid_on_forward(inputs: StrategyInput, levels: Sequence[Decimal],
                                 forwards: Forwards) -> tuple[ForwardEstimate, ...]:
    if not levels:
        raise ValueError("an estimate grid needs at least one level")
    return tuple(estimate_now_on_forward(inputs, lv, forwards) for lv in levels)
