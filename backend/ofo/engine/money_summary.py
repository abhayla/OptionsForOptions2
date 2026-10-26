"""REQ-081 (W-154): the money arithmetic of the Builder summary, in the one engine (ADR-008). Exact Decimals, no float.

Net premium (sells minus buys of entry price x quantity: the rule of the table's TOTAL Entry Value), intrinsic and time
value, Reward/Risk and Risk/Reward, and a maximum as a percent of funds. Pure numbers only: which sentence or reason
goes with a figure is shaped in ``ofo.outcome.money``.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Final

from ofo.engine.legs import Action, Instrument
from ofo.money import PAISE

ZERO_MONEY: Final = Decimal(0).quantize(PAISE)
_WHOLE: Final = Decimal(1)
_HUNDRED: Final = Decimal(100)
_PRECISION: Final = 50


def _signed(leg: Any, value: Decimal) -> Decimal:
    """A sold leg's premium is received (positive), a bought leg's is paid (negative)."""
    return value if leg.action is Action.SELL else -value


def net_premium_amount(legs: Sequence[Any]) -> Decimal:
    """Sells minus buys of entry price x quantity (positive = credit); options with every price assumed."""
    return sum((_signed(leg, leg.entry_price) * leg.quantity for leg in legs), Decimal(0))


def net_premium_per_unit(legs: Sequence[Any]) -> Decimal | None:
    """The magnitude per unit, only when every leg has the same quantity (else None)."""
    if len({leg.quantity for leg in legs}) != 1:
        return None
    return abs(sum((_signed(leg, leg.entry_price) for leg in legs), Decimal(0)))


def intrinsic_and_time(legs: Sequence[Any], spot: Decimal) -> tuple[Decimal, Decimal]:
    """Over the option legs (all with an LTP): intrinsic = max(spot - strike, 0) for a call, max(strike - spot, 0) for a
    put; time = ltp - intrinsic; each x quantity; bought +, sold -. A futures leg adds nothing."""
    intrinsic = time = Decimal(0)
    for leg in legs:
        if leg.instrument is Instrument.FUT:
            continue
        gap = spot - leg.strike if leg.instrument is Instrument.CE else leg.strike - spot
        per_unit = max(gap, Decimal(0))
        sign = 1 if leg.action is Action.BUY else -1
        intrinsic += sign * per_unit * leg.quantity
        time += sign * (leg.ltp - per_unit) * leg.quantity
    return intrinsic.quantize(PAISE, ROUND_HALF_EVEN), time.quantize(PAISE, ROUND_HALF_EVEN)


def _ratio(top: Decimal, bottom: Decimal) -> Decimal:
    with localcontext(prec=_PRECISION):
        return (top / bottom).quantize(PAISE, ROUND_HALF_EVEN)


def reward_risk_ratios(max_profit: Decimal, max_loss: Decimal) -> tuple[Decimal, Decimal]:
    """(Reward/Risk, Risk/Reward) to two decimals, half-even; both maximums positive."""
    return _ratio(max_profit, max_loss), _ratio(max_loss, max_profit)


def percent_of_funds(amount: Decimal, funds: Decimal) -> Decimal:
    """The exact percent ``amount`` is of ``funds`` (funds positive)."""
    with localcontext(prec=_PRECISION):
        return amount * _HUNDRED / funds


def whole_percent(raw: Decimal) -> Decimal:
    return raw.quantize(_WHOLE, ROUND_HALF_UP)
