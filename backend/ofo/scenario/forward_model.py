"""IV, Greeks and Estimated Now with each expiry's implied dividend yield (ADR-061, ADR-063; REQ-072 AC-3).

ADR-063: the engine owns the yield. Every call here passes the index level S (the live spot, or a what-if level) and
q = ``ExpiryForward.implied_yield`` to the engine, which returns price, IV and every Greek (theta included) already
relative to spot. Nothing in this module multiplies or rescales an engine output. The payoff, its CURRENT column and
the default range keep the index spot and never come through here.

Every result carries ``label``: "estimated from spot" when the expiry's forward fell back to spot (q = 0, fewer than 3
usable strikes); None otherwise. A leg whose expiry has no forward, or whose forward was read for another valuation
time, rate or day count, is refused - never priced silently.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from ofo.engine.black_scholes import Greeks, bs_greeks, implied_volatility
from ofo.engine.estimate import estimate_now
from ofo.engine.inputs import StrategyInput
from ofo.engine.legs import Instrument
from ofo.marketdata.forward import FALLBACK_LABEL, ExpiryForward, ForwardUnavailable

Forwards = Mapping[datetime.date, ExpiryForward]


@dataclass(frozen=True)
class ForwardIV:
    iv: Decimal
    dividend_yield: Decimal
    label: str | None


@dataclass(frozen=True)
class ForwardGreeks:
    greeks: Greeks  # from the engine, relative to the index level, 4 dp
    level: Decimal
    dividend_yield: Decimal
    label: str | None


@dataclass(frozen=True)
class ForwardEstimate:
    level: Decimal  # the what-if index level S, as given to the engine
    dividend_yields: tuple[Decimal, ...]  # q per leg
    leg_pnls: tuple[Decimal, ...]
    total: Decimal
    label: str | None


def _check(fwd: object) -> ExpiryForward:
    if not isinstance(fwd, ExpiryForward):
        raise ValueError(f"an ExpiryForward is required, got {fwd!r}")
    return fwd


def iv_on_forward(kind: Instrument, price: Decimal, strike: Decimal, fwd: ExpiryForward) -> ForwardIV:
    """Implied volatility of a market price at the live spot with the expiry's yield q."""
    f = _check(fwd)
    iv = implied_volatility(kind, price, f.spot, strike, f.years, f.rate, dividend_yield=f.implied_yield)
    return ForwardIV(iv, f.implied_yield, f.label)


def greeks_on_forward(kind: Instrument, strike: Decimal, vol: Decimal, fwd: ExpiryForward,
                      level: Decimal | None = None) -> ForwardGreeks:
    """Per-unit engine Greeks at ``level`` (default: the live spot) with the expiry's yield q, 4 dp."""
    f = _check(fwd)
    s = f.spot if level is None else level
    greeks = bs_greeks(kind, s, strike, f.years, f.rate, vol, days_in_year=f.days_in_year,
                       dividend_yield=f.implied_yield)
    return ForwardGreeks(greeks, s, f.implied_yield, f.label)


def combined_label(forwards: Sequence[ExpiryForward]) -> str | None:
    return FALLBACK_LABEL if any(f.label for f in forwards) else None


def _matching(fwd: ExpiryForward, inputs: StrategyInput) -> ExpiryForward:
    mismatched = [name for name, mine, theirs in (
        ("valuation time", fwd.valuation_time, inputs.valuation_time), ("rate", fwd.rate, inputs.rate),
        ("days in year", fwd.days_in_year, inputs.days_in_year)) if mine != theirs]
    if mismatched:
        raise ForwardUnavailable(f"the {fwd.expiry} forward was read with a different {', '.join(mismatched)} than the "
                                 f"strategy input; estimate refused")
    return fwd


def estimate_now_on_forward(inputs: StrategyInput, level: Decimal, forwards: Forwards) -> ForwardEstimate:
    """Estimated Now at index level S: each leg is marked by the engine at S with its own expiry's yield q."""
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    used: list[ExpiryForward] = []
    leg_pnls: list[Decimal] = []
    for leg in inputs.legs:
        fwd = forwards.get(leg.expiry)
        if fwd is None:
            raise ForwardUnavailable(f"no forward for expiry {leg.expiry} (leg {leg.contract}); estimate refused")
        fwd = _matching(_check(fwd), inputs)
        single = estimate_now(dataclasses.replace(inputs, legs=(leg,)), level, dividend_yield=fwd.implied_yield)
        used.append(fwd)
        leg_pnls.append(single.leg_pnls[0])
    return ForwardEstimate(level, tuple(f.implied_yield for f in used), tuple(leg_pnls), sum(leg_pnls, Decimal(0)),
                           combined_label(used))


def estimate_now_grid_on_forward(inputs: StrategyInput, levels: Sequence[Decimal],
                                 forwards: Forwards) -> tuple[ForwardEstimate, ...]:
    if not levels:
        raise ValueError("an estimate grid needs at least one level")
    return tuple(estimate_now_on_forward(inputs, lv, forwards) for lv in levels)
