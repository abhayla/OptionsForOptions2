"""The money ratios the adjustment triggers compare (GC-ADJ2 step 1B; ADR-008: money arithmetic lives in the engine).

Each function returns the ratio as an exact ``(numerator, denominator)`` pair of Decimals with a positive denominator,
so the caller compares ``numerator <= limit x denominator`` exactly and divides only for display. No rounding here.
A missing (``None``) or non-positive denominator, or a missing amount, is refused with ValueError: the evaluator turns
that into NotChecked, never a pass.

- T-06 loss as a % of max loss: ``max(-pnl, 0) x 100 / max_loss``
- T-07 profit as a % of max profit: ``max(pnl, 0) x 100 / max_profit``
- T-16 loss as a % of the margin blocked: ``max(-pnl, 0) x 100 / margin``
- T-19 premium still left / the adjustment's cost: ``premium_left / adjustment_cost``
- S-02 net delta per lot (ADR-240 (3)): ``|sum of per-unit delta x lots x sign| / lots of the largest leg``
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from ofo.engine.black_scholes import Greeks
from ofo.engine.legs import Action
from ofo.engine.target import greeks_total
from ofo.table.model import position_greeks

Ratio = tuple[Decimal, Decimal]
_HUNDRED: Final = Decimal(100)
_ZERO: Final = Decimal(0)


def _amount(value: Decimal | None, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal, got {value!r}")
    return value


def _denominator(value: Decimal | None, name: str) -> Decimal:
    value = _amount(value, name)
    if value <= _ZERO:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def loss_pct_of_max_loss(pnl: Decimal | None, max_loss: Decimal | None) -> Ratio:
    return max(-_amount(pnl, "pnl"), _ZERO) * _HUNDRED, _denominator(max_loss, "max_loss")


def profit_pct_of_max_profit(pnl: Decimal | None, max_profit: Decimal | None) -> Ratio:
    return max(_amount(pnl, "pnl"), _ZERO) * _HUNDRED, _denominator(max_profit, "max_profit")


def loss_pct_of_margin(pnl: Decimal | None, margin: Decimal | None) -> Ratio:
    return max(-_amount(pnl, "pnl"), _ZERO) * _HUNDRED, _denominator(margin, "margin")


def premium_left_per_cost(premium_left: Decimal | None, adjustment_cost: Decimal | None) -> Ratio:
    left = _amount(premium_left, "premium_left")
    if left < _ZERO:
        raise ValueError(f"premium_left must be >= 0 (net long premium has nothing to earn), got {left}")
    return left, _denominator(adjustment_cost, "adjustment_cost")


def net_delta_per_lot(legs: Sequence[tuple[Greeks, Action, int]]) -> Ratio:
    """S-02 (ADR-240 (3)): the position's net delta per lot as ``(|net delta|, lots of the largest leg)``.

    Each leg is ``(per-unit engine Greeks, BUY / SELL, lots)``; it is signed and scaled by the table's own
    ``position_greeks`` (per-unit x lots x sign) and summed by ``greeks_total`` (one engine sum, ADR-008), so the
    numerator is the net delta in lots and the ratio is per lot. Example: SELL 2 lots of a 0.35 call, BUY 2 lots of a
    0.20 call, SELL 2 lots of a -0.10 put, BUY 2 lots of a -0.05 put: net (-0.70 + 0.40 + 0.20 - 0.10) = -0.20 lots
    of delta, per lot 0.20 / 2 = 0.10. No leg, a lot count that is not a positive int, or a non-finite delta is
    refused with ValueError (never a zero)."""
    if not legs:
        raise ValueError("no leg to sum")
    rows = []
    for greeks, action, lots in legs:
        if type(lots) is not int or lots <= 0:
            raise ValueError(f"lots must be a positive int, got {lots!r}")
        _amount(greeks.delta, "delta")
        rows.append(position_greeks(greeks, action, lots))
    return abs(greeks_total(rows).delta), Decimal(max(lots for _, _, lots in legs))
