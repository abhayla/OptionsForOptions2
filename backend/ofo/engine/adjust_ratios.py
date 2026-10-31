"""The money ratios the adjustment triggers compare (GC-ADJ2 step 1B; ADR-008: money arithmetic lives in the engine).

Each function returns the ratio as an exact ``(numerator, denominator)`` pair of Decimals with a positive denominator,
so the caller compares ``numerator <= limit x denominator`` exactly and divides only for display. No rounding here.
A missing (``None``) or non-positive denominator, or a missing amount, is refused with ValueError: the evaluator turns
that into NotChecked, never a pass.

- T-06 loss as a % of max loss: ``max(-pnl, 0) x 100 / max_loss``
- T-07 profit as a % of max profit: ``max(pnl, 0) x 100 / max_profit``
- T-16 loss as a % of the margin blocked: ``max(-pnl, 0) x 100 / margin``
- T-19 premium still left / the adjustment's cost: ``premium_left / adjustment_cost``
"""
from __future__ import annotations

from decimal import Decimal
from typing import Final

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
