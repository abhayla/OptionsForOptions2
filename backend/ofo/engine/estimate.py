"""Estimated Now: model-based strategy P&L at a hypothetical level before expiry (ADR-008 Q33A = C; §4).

This is an ESTIMATE, not the at-expiry number: each option leg is marked at its Black-Scholes price at ``level``
with the leg's own IV and the time left from the input's valuation time to its expiry close; a futures leg at its
cost-of-carry fair value. The mark goes through the engine's one P&L sign convention
(:func:`ofo.engine.legs.position_pnl`), so the estimate cannot disagree with the expiry grid or live P&L on sign or
quantity. The result carries its assumptions so a display can label it (REQ-032 AC-5).
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal, Sequence

from ofo.engine import legs as _legs
from ofo.engine.black_scholes import bs_price, forward_price, year_fraction
from ofo.engine.inputs import StrategyInput
from ofo.engine.legs import Instrument, require_price

MODEL: Final = render_explanation("estimate_model_name")  # ADR-061, ADR-063


@dataclass(frozen=True)
class EstimateAssumptions:
    model: str
    valuation_time: datetime.datetime
    rate: Decimal
    days_in_year: int
    ivs: tuple[Decimal | None, ...]
    years_to_expiry: tuple[Decimal, ...]
    # ADR-063: the dividend yield q each leg was valued with, and where it came from ("parity", "spot fallback",
    # or "none" when no yield was given, q = 0)
    dividend_yields: tuple[Decimal, ...] = ()
    yield_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class EstimatedNow:
    """Estimated strategy P&L at one level. ``kind`` is always "estimate"; it is never the exact expiry P&L."""

    level: Decimal
    marks: tuple[Decimal, ...]
    leg_pnls: tuple[Decimal, ...]
    total: Decimal
    assumptions: EstimateAssumptions
    kind: Literal["estimate"] = "estimate"


def estimate_now(inputs: StrategyInput, level: Decimal, *, dividend_yield: Decimal = Decimal("0"),
                 yield_source: str = "none") -> EstimatedNow:
    """Estimated Now P&L of the whole strategy if the underlying were at ``level`` at the valuation time.

    ``level`` is index points, not money, but it must be finite, > 0 and have at most 2 decimal places (the
    exchange quotes index levels to 0.01), so a float-built level cannot enter. An exact breakeven with more
    decimals (see metrics) is rounded to 0.01 by the caller before it is estimated. ``dividend_yield`` is the
    implied yield q of the legs' expiry (ADR-063), applied to every leg; default 0 (q = 0, the spot fallback of ADR-061).
    """
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    require_price(level, "level", allow_zero=False)
    marks: list[Decimal] = []
    years_list: list[Decimal] = []
    for leg_input in inputs.legs:
        years = year_fraction(inputs.valuation_time, leg_input.expiry, days_in_year=inputs.days_in_year)
        if leg_input.instrument is Instrument.FUT:
            mark = forward_price(level, years, inputs.rate, dividend_yield=dividend_yield)
        else:
            if leg_input.iv is None:
                raise ValueError(f"leg {leg_input.contract} has no IV; an estimate needs one for every option leg")
            mark = bs_price(leg_input.instrument, level, leg_input.strike, years, inputs.rate, leg_input.iv,
                            dividend_yield=dividend_yield)
        marks.append(mark)
        years_list.append(years)
    leg_pnls = tuple(_legs.position_pnl(li.leg, mark) for li, mark in zip(inputs.legs, marks))
    return EstimatedNow(
        level=level,
        marks=tuple(marks),
        leg_pnls=leg_pnls,
        total=sum(leg_pnls, Decimal(0)),
        assumptions=EstimateAssumptions(
            model=MODEL,
            valuation_time=inputs.valuation_time,
            rate=inputs.rate,
            days_in_year=inputs.days_in_year,
            ivs=tuple(li.iv for li in inputs.legs),
            years_to_expiry=tuple(years_list),
            dividend_yields=tuple(dividend_yield for _ in inputs.legs),
            yield_sources=tuple(yield_source for _ in inputs.legs),
        ),
    )


def estimate_now_grid(inputs: StrategyInput, levels: Sequence[Decimal]) -> tuple[EstimatedNow, ...]:
    """The Estimated Now view of the scenario columns: one estimate per level."""
    if not levels:
        raise ValueError("an estimate grid needs at least one level")
    return tuple(estimate_now(inputs, level) for level in levels)
