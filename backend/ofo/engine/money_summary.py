"""REQ-081 (W-154): the money arithmetic of the Builder summary, in the one engine (ADR-008). Exact Decimals, no float.

Net premium (sells minus buys of entry price x quantity: the rule of the table's TOTAL Entry Value), intrinsic and time
value, Reward/Risk and Risk/Reward, and a maximum as a percent of the margin needed (ADR-207 (8)). Pure numbers
only: which sentence or reason
goes with a figure is shaped in ``ofo.outcome.money``.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Final

from ofo.engine.legs import Action, Instrument
from ofo.money import PAISE

ZERO_MONEY: Final = Decimal(0).quantize(PAISE)
_TENTH: Final = Decimal("0.1")
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


def net_price_per_unit(legs: Sequence[Any], prices: Sequence[Decimal]) -> Decimal:
    """Sells plus, buys minus, of one per-unit price per leg (``prices`` parallel to ``legs``): the TOTAL row's net
    per-unit Entry / LTP (GC-UI D-B28). Positive = credit. The caller decides when the figure applies."""
    return sum((_signed(leg, p) for leg, p in zip(legs, prices, strict=True)), Decimal(0))


def combined_price_per_unit(legs: Sequence[Any], closes: Sequence[Decimal | None], *,
                            invert: bool = False) -> Decimal | None:
    """REQ-091 AC-2/AC-3 (ADR-203 consequence 1, F-64): the strategy's combined net price per unit at one minute, from
    one close per leg (``closes`` parallel to ``legs``). Each leg counts at its lots divided by the greatest common
    divisor of all the legs' lots (equal lots -> 1 each; 1 BUY + 2 SELL -> 1 and 2); sells plus, buys minus (a debit
    is negative). Any leg without a close -> None: a gap, never interpolated or carried (AC-4). ``invert`` flips the
    sign of this figure only (AC-3)."""
    if any(c is None for c in closes):
        return None
    lots = [leg.lots for leg in legs]
    if not lots or any(type(n) is not int or n <= 0 for n in lots):
        raise ValueError("every leg needs a whole, positive number of lots")
    unit = math.gcd(*lots)
    value = sum((_signed(leg, close) * (leg.lots // unit) for leg, close in zip(legs, closes, strict=True)),
                Decimal(0))
    return -value if invert else value


def combined_price_series(legs: Sequence[Any], closes_by_leg: Sequence[Mapping[Any, Decimal]], minutes: Sequence[Any],
                          *, invert: bool = False) -> list[Decimal | None]:
    """:func:`combined_price_per_unit` at each of ``minutes`` (the index future's minutes): a minute any leg has no
    close for is a gap (None)."""
    return [combined_price_per_unit(legs, [closes.get(m) for closes in closes_by_leg], invert=invert)
            for m in minutes]


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


def percent_of(amount: Decimal, base: Decimal) -> Decimal:
    """The exact percent ``amount`` is of ``base`` (base positive; the summary's base is the margin needed)."""
    with localcontext(prec=_PRECISION):
        return amount * _HUNDRED / base


def one_decimal_percent(raw: Decimal) -> Decimal:
    """A percent to one decimal, half-up (REQ-081 AC-9: "7.0% of margin needed")."""
    return raw.quantize(_TENTH, ROUND_HALF_UP)
