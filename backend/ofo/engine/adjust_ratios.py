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
- T-05 one side's value / the other's (ADR-280 (2)): ``larger side value / smaller side value``
- T-06b loss / credit received (ADR-280 (3)): ``max(-pnl, 0) / credit``
- T-15 margin used (ADR-280 (10)): ``margin x 100 / (margin + available margin)``
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


def position_total(legs: Sequence[tuple[Greeks, Action, int]]) -> Greeks:
    """The position's Greeks in lots: per-unit x lots x sign (``position_greeks``) summed by ``greeks_total`` (one
    engine sum, ADR-008); x lot size gives rupees. No leg or a lot count that is not a positive int -> ValueError."""
    if not legs:
        raise ValueError("no leg to sum")
    rows = []
    for greeks, action, lots in legs:
        rows.append(position_greeks(greeks, action, _units(lots, "lots")))
    return greeks_total(rows)


def side_value_ratio(legs: Sequence[tuple[str, Action, int, Decimal | None]], lot_size: int) -> Ratio:
    """T-05 (ADR-280 (2)): each side's value = (its SELL legs' LTP minus its BUY legs' LTP) x lots x lot size, for
    the CE side and the PE side; ``(larger, smaller)``. Example: CE SELL 120 / BUY 40 and PE SELL 30 / BUY 10, 1 lot
    of 75: CE 6000, PE 1500 -> 6000 / 1500 = 4. A leg unpriced, a side worth 0 or less -> ValueError."""
    units = _units(lot_size)
    side = {"CE": _ZERO, "PE": _ZERO}
    for kind, action, lots, ltp in legs:
        if kind not in side:
            raise ValueError(f"kind must be CE or PE, got {kind!r}")
        price = _amount(ltp, "ltp")
        side[kind] += price * _units(lots, "lots") * units * (1 if action is Action.SELL else -1)
    small, large = sorted(side.values())
    return large, _denominator(small, "side_value")


def credit_received(legs: Sequence[tuple[Action, int, Decimal | None]], lot_size: int) -> Decimal:
    """T-06b (ADR-280 (3)): the open legs' net entry premium, (SELL entry - BUY entry) x lots x lot size (a debit is
    negative). A leg without an entry price -> ValueError."""
    units = _units(lot_size)
    return sum((_amount(entry, "entry") * _units(lots, "lots") * units * (1 if action is Action.SELL else -1)
                for action, lots, entry in legs), _ZERO)


def loss_per_credit(pnl: Decimal | None, credit: Decimal | None) -> Ratio:
    return max(-_amount(pnl, "pnl"), _ZERO), _denominator(credit, "credit")


def margin_used_pct(margin: Decimal | None, available: Decimal | None) -> Ratio:
    used = _denominator(margin, "margin")
    return used * _HUNDRED, _denominator(used + _amount(available, "available"), "margin_room")


def _units(count: object, name: str = "lot_size") -> int:
    if type(count) is not int or count <= 0:
        raise ValueError(f"{name} must be a positive int, got {count!r}")
    return count


def net_delta_per_lot(legs: Sequence[tuple[Greeks, Action, int]]) -> Ratio:
    """S-02 (ADR-240 (3)): the position's net delta per lot as ``(|net delta|, lots of the largest leg)``.

    Each leg is ``(per-unit engine Greeks, BUY / SELL, lots)``; it is signed and scaled by the table's own
    ``position_greeks`` (per-unit x lots x sign) and summed by ``greeks_total`` (one engine sum, ADR-008), so the
    numerator is the net delta in lots and the ratio is per lot. Example: SELL 2 lots of a 0.35 call, BUY 2 lots of a
    0.20 call, SELL 2 lots of a -0.10 put, BUY 2 lots of a -0.05 put: net (-0.70 + 0.40 + 0.20 - 0.10) = -0.20 lots
    of delta, per lot 0.20 / 2 = 0.10. No leg, a lot count that is not a positive int, or a non-finite delta is
    refused with ValueError (never a zero)."""
    total = position_total(legs)
    return abs(total.delta), Decimal(max(lots for _, _, lots in legs))
