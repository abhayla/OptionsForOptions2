"""Leg value type and the locked per-leg P&L formulas.

Spec: spec/business-rules/scenario-calculations.md §1 (expiry P&L, entry price only; ADR-035),
§2 (live P&L from LTP), ADR-041 (futures legs). Money is exact ``Decimal``; quantity is integer units
(lots x lot size), never lots. Invalid input raises ``ValueError``; nothing defaults silently.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Final

PRICE_STEP: Final = Decimal("0.01")


class Action(Enum):
    BUY = "BUY"
    SELL = "SELL"


class Instrument(Enum):
    CE = "CE"
    PE = "PE"
    FUT = "FUT"


def require_decimal(value: object, name: str, *, allow_zero: bool = True) -> Decimal:
    """Return ``value`` if it is a finite, non-negative Decimal; raise ``ValueError`` otherwise."""
    if not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a decimal.Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite, got {value}")
    if value < 0 or (not allow_zero and value == 0):
        bound = "> 0" if not allow_zero else ">= 0"
        raise ValueError(f"{name} must be {bound}, got {value}")
    return value


def require_price(value: object, name: str, *, allow_zero: bool = True) -> Decimal:
    """Like :func:`require_decimal`, and the value must be a whole number of paise (at most 2 decimal places).

    This is the AC-4 guard against binary floats: ``Decimal(0.1)`` is
    0.1000000000000000055511151231257827..., which is not a multiple of 0.01 and is refused here, so a price,
    strike or LTP built from a float cannot enter the engine. ``Decimal("1.50")`` and ``Decimal("1.500")`` pass.
    """
    checked = require_decimal(value, name, allow_zero=allow_zero)
    try:
        exact = checked.quantize(PRICE_STEP) == checked
    except InvalidOperation:
        exact = False
    if not exact:
        raise ValueError(
            f"{name} must have at most 2 decimal places (a Decimal built from a float is refused), got {checked}"
        )
    return checked


@dataclass(frozen=True)
class Leg:
    """One leg of a strategy. A leg carries no breakeven (strategy-level only, §3)."""

    action: Action
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    quantity: int
    entry_price: Decimal
    ltp: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, Action):
            raise ValueError(f"action must be an Action, got {self.action!r}")
        if not isinstance(self.instrument, Instrument):
            raise ValueError(f"instrument must be an Instrument, got {self.instrument!r}")
        if self.instrument is Instrument.FUT:
            if self.strike is not None:
                raise ValueError("a futures leg has no strike")
        else:
            require_price(self.strike, "strike", allow_zero=False)
        if not isinstance(self.expiry, datetime.date) or isinstance(self.expiry, datetime.datetime):
            raise ValueError(f"expiry must be a datetime.date, got {self.expiry!r}")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity <= 0:
            raise ValueError(f"quantity must be a positive integer number of units, got {self.quantity!r}")
        require_price(self.entry_price, "entry_price")
        if self.ltp is not None:
            require_price(self.ltp, "ltp")

    @property
    def is_option(self) -> bool:
        return self.instrument is not Instrument.FUT


def _long_value_at(leg: Leg, market: Decimal) -> Decimal:
    """Value per unit of the long side at ``market``: option intrinsic value, or the level for futures."""
    if leg.instrument is Instrument.CE:
        return max(market - leg.strike, Decimal(0))
    if leg.instrument is Instrument.PE:
        return max(leg.strike - market, Decimal(0))
    return market


def position_pnl(leg: Leg, value: Decimal) -> Decimal:
    """The one P&L sign convention: BUY (Value - Entry) x Qty, SELL (Entry - Value) x Qty.

    ``value`` is the per-unit value the leg is marked at: its expiry value (§1), its LTP (§2) or a model estimate
    (Estimated Now). Every P&L number in the engine goes through this function.
    """
    per_unit = value - leg.entry_price if leg.action is Action.BUY else leg.entry_price - value
    return per_unit * leg.quantity


def expiry_pnl(leg: Leg, market: Decimal) -> Decimal:
    """Expiry scenario P&L of one leg at underlying level ``market`` (§1). Uses entry price, never LTP."""
    require_decimal(market, "market")
    return position_pnl(leg, _long_value_at(leg, market))


def live_pnl(leg: Leg) -> Decimal:
    """Live (current) P&L of one leg (§2): BUY (LTP - Entry) x Qty, SELL (Entry - LTP) x Qty."""
    if leg.ltp is None:
        raise ValueError("live P&L needs an LTP; this leg has none")
    return position_pnl(leg, leg.ltp)
