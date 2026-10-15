"""Executable order price (W-078, ADR-080): tick rounding toward the user and the depth-based executable limit.

Standard library only, exact ``Decimal``, no float anywhere (a float price or tick raises ``ValueError``).

- ``round_to_tick``: a BUY limit rounds DOWN to the tick, a SELL limit rounds UP, so the price sent is never worse
  than the price the user accepted (3.975 BUY -> 3.95, SELL -> 4.00 on tick 0.05).
- ``executable_limit``: walk the depth side the order trades against (a BUY lifts the ASK side, key ``sell`` in
  Zerodha's reply; a SELL hits the BID side, key ``buy``) until the whole quantity is covered. The limit is the WORST
  level price needed, rounded per ``round_to_tick``.
- Slippage base: the WALKED cost (each level's own price x the quantity taken from it), not the limit x quantity.
  ADR-080's case: 130 units = 65 @ 4.00 + 65 @ 4.05 = 523.25 vs 130 @ LTP 3.95 = 513.50, slippage 9.75.
  Slippage is signed so a worse price is positive for BUY (walked - planned) and for SELL (planned - walked).
- When the 5 levels cannot cover the quantity the result is ``fillable=False`` with no limit, no cost, no slippage:
  nothing is invented beyond level 5.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from ofo.engine.legs import Action


def _decimal(value: object, name: str) -> Decimal:
    # Zerodha prints a whole-number price as a JSON integer ("price": 4 in the real CE reply), so an int is exact
    # and accepted; a float is not.
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal (floats are refused), got {value!r}")
    return value


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive int, got {value!r}")
    return value


def _action(side: object) -> Action:
    if not isinstance(side, Action):
        raise ValueError(f"side must be an Action, got {side!r}")
    return side


def round_to_tick(price: Decimal, tick: Decimal, side: Action) -> Decimal:
    """BUY floors to a multiple of ``tick``, SELL ceils; a price already on the tick is unchanged."""
    price, tick, side = _decimal(price, "price"), _decimal(tick, "tick"), _action(side)
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    if tick <= 0:
        raise ValueError(f"tick must be positive, got {tick}")
    steps = (price / tick).to_integral_value(rounding=ROUND_FLOOR if side is Action.BUY else ROUND_CEILING)
    return steps * tick


@dataclass(frozen=True)
class DepthLevel:
    price: Decimal
    quantity: int


@dataclass(frozen=True)
class Depth:
    """Both sides of a quote's market depth, best level first. ``bids`` = Zerodha ``buy``, ``asks`` = ``sell``."""

    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]


def _levels(rows: object, name: str) -> tuple[DepthLevel, ...]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError(f"depth {name} must be a list of levels, got {rows!r}")
    out: list[DepthLevel] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"depth {name} level must be a mapping, got {row!r}")
        price = _decimal(row.get("price"), "depth_price")
        quantity = row.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError(f"depth {name} quantity must be a whole number >= 0, got {quantity!r}")
        if price > 0 and quantity > 0:  # an empty level (price 0 / quantity 0) is padding, not liquidity
            out.append(DepthLevel(price, quantity))
    return tuple(out)


def depth_from_quote(quote: Mapping[str, object]) -> Depth:
    """Read ``depth`` of one instrument's quote reply (parsed with ``parse_float=Decimal``)."""
    depth = quote.get("depth") if isinstance(quote, Mapping) else None
    if not isinstance(depth, Mapping):
        raise ValueError("quote has no depth mapping")
    return Depth(bids=_levels(depth.get("buy", []), "buy"), asks=_levels(depth.get("sell", []), "sell"))


@dataclass(frozen=True)
class ExecutablePrice:
    side: Action
    quantity: int
    fillable: bool
    limit: Decimal | None  # worst level needed, rounded toward the user; None when not fillable
    walked_cost: Decimal | None  # each level at its own price: the slippage base
    planned_cost: Decimal  # quantity x the planned price (LTP or the user's price)
    slippage: Decimal | None  # rupees, worse = positive; None when not fillable


def executable_limit(
    depth: Depth, side: Action, quantity: int, tick: Decimal, planned_price: Decimal,
) -> ExecutablePrice:
    side, quantity = _action(side), _positive_int(quantity, "quantity")
    tick, planned_price = _decimal(tick, "tick"), _decimal(planned_price, "planned_price")
    if planned_price <= 0:
        raise ValueError(f"planned_price must be positive, got {planned_price}")
    if not isinstance(depth, Depth):
        raise ValueError("depth must come from depth_from_quote")
    planned_cost = planned_price * quantity
    levels = depth.asks if side is Action.BUY else depth.bids
    remaining, walked, worst = quantity, Decimal(0), None
    for level in levels:
        take = min(remaining, level.quantity)
        walked += level.price * take
        worst = level.price
        remaining -= take
        if remaining == 0:
            break
    if remaining > 0 or worst is None:
        return ExecutablePrice(side, quantity, False, None, None, planned_cost, None)
    slippage = walked - planned_cost if side is Action.BUY else planned_cost - walked
    return ExecutablePrice(side, quantity, True, round_to_tick(worst, tick, side), walked, planned_cost, slippage)


def leg_slippage(result: ExecutablePrice) -> Decimal | None:
    return result.slippage


def total_slippage(results: Iterable[ExecutablePrice]) -> Decimal | None:
    """Sum of leg slippage; None when any leg is not fillable (a partial total would understate the cost)."""
    total = Decimal(0)
    for result in results:
        if result.slippage is None:
            return None
        total += result.slippage
    return total
