"""The engine's one input model (REQ-032 AC-2).

Per leg: underlying, contract, action, instrument, strike, expiry, quantity (units), premium (entry price), LTP, IV
and Greeks. Per strategy: underlying, the index spot reading (level, time, health - REQ-072 AC-2; there is no bare level),
valuation time, risk-free
rate, day count, and the margin and charges stated by an AC-6 provider. Validation fails closed: every field is
checked on construction and nothing defaults silently; the leg's own checks (paise, positive units, strike rules)
are the :class:`~ofo.engine.legs.Leg` checks, not a copy of them.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.engine.black_scholes import DAYS_IN_YEAR, IV_LOWER, IV_UPPER, Greeks
from ofo.engine.interfaces import ChargesBreakdown, MarginRequirement
from ofo.engine.legs import Action, Instrument, Leg, require_price
from ofo.engine.strategy import Strategy
from ofo.rules.inputs import DataHealth

_IV_MIN: Final = Decimal(repr(IV_LOWER))
_IV_MAX: Final = Decimal(repr(IV_UPPER))


def _name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string, got {value!r}")
    return value


@dataclass(frozen=True)
class LegInput:
    """One leg as the engine receives it. ``iv`` is an annualised fraction (0.142 = 14.2 %)."""

    underlying: str
    contract: str
    action: Action
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    quantity: int
    premium: Decimal
    ltp: Decimal | None = None
    iv: Decimal | None = None
    greeks: Greeks | None = None

    def __post_init__(self) -> None:
        _name(self.underlying, "underlying")
        _name(self.contract, "contract")
        _ = self.leg  # build the Leg once so its checks run at construction
        if self.iv is not None:
            if not isinstance(self.iv, Decimal) or not self.iv.is_finite():
                raise ValueError(f"iv must be a finite decimal.Decimal, got {self.iv!r}")
            if not _IV_MIN <= self.iv <= _IV_MAX:
                raise ValueError(f"iv must be within [{_IV_MIN}, {_IV_MAX}] as a fraction, got {self.iv}")
            if self.instrument is Instrument.FUT:
                raise ValueError("a futures leg has no implied volatility")
        if self.greeks is not None and not isinstance(self.greeks, Greeks):
            raise ValueError(f"greeks must be a Greeks value, got {self.greeks!r}")

    @property
    def leg(self) -> Leg:
        return Leg(self.action, self.instrument, self.strike, self.expiry, self.quantity, self.premium, self.ltp)


@dataclass(frozen=True)
class SpotReading:
    """The index value a calculation is built on, with its time and data health (REQ-072 AC-2/AC-3, W-060)."""

    level: Decimal
    at: datetime.datetime
    health: DataHealth

    def __post_init__(self) -> None:
        require_price(self.level, "spot level", allow_zero=False)
        if not isinstance(self.at, datetime.datetime) or self.at.tzinfo is None:
            raise ValueError(f"a spot reading needs a timezone-aware time, got {self.at!r}")
        if not isinstance(self.health, DataHealth):
            raise ValueError(f"a spot reading needs a DataHealth, got {self.health!r}")


@dataclass(frozen=True)
class StrategyInput:
    """A whole strategy as the engine receives it. ``rate`` is annual, continuously compounded (0.065 = 6.5 %)."""

    underlying: str
    spot: SpotReading  # required: the level, its time and health; gated by ofo.engine.model.model_inputs
    valuation_time: datetime.datetime
    rate: Decimal
    legs: tuple[LegInput, ...]
    days_in_year: int = DAYS_IN_YEAR
    margin: MarginRequirement | None = None
    charges: ChargesBreakdown | None = None

    def __post_init__(self) -> None:
        _name(self.underlying, "underlying")
        if not isinstance(self.spot, SpotReading):
            raise ValueError(f"spot must be a SpotReading (level, time, health), got {self.spot!r}")
        if not isinstance(self.valuation_time, datetime.datetime) or self.valuation_time.tzinfo is None:
            raise ValueError(f"valuation_time must be a timezone-aware datetime, got {self.valuation_time!r}")
        if not isinstance(self.rate, Decimal) or not self.rate.is_finite():
            raise ValueError(f"rate must be a finite decimal.Decimal, got {self.rate!r}")
        if isinstance(self.days_in_year, bool) or not isinstance(self.days_in_year, int) or self.days_in_year <= 0:
            raise ValueError(f"days_in_year must be a positive integer, got {self.days_in_year!r}")
        legs = tuple(self.legs)
        if not legs:
            raise ValueError("a strategy input needs at least one leg")
        for leg in legs:
            if not isinstance(leg, LegInput):
                raise ValueError(f"every leg must be a LegInput, got {leg!r}")
            if leg.underlying != self.underlying:
                raise ValueError(f"leg {leg.contract} is on {leg.underlying}, the strategy is on {self.underlying}")
        object.__setattr__(self, "legs", legs)
        if self.margin is not None and not isinstance(self.margin, MarginRequirement):
            raise ValueError(f"margin must be a MarginRequirement, got {self.margin!r}")
        if self.charges is not None and not isinstance(self.charges, ChargesBreakdown):
            raise ValueError(f"charges must be a ChargesBreakdown, got {self.charges!r}")

    @property
    def strategy(self) -> Strategy:
        """The engine strategy these inputs describe (every P&L number is computed from it)."""
        return Strategy(tuple(leg.leg for leg in self.legs))
