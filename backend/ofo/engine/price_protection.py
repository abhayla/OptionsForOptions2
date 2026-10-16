"""Price protection (ADR-095, ADR-080 (3), REQ-056 AC-7): split one strategy-level rupee tolerance into per-leg limits.

Standard library only, exact ``Decimal``, no float. Domain only: no UI, no route, and NOT wired into the basket yet
(that is a later work item).

- Each leg's planned value is ``planned price x quantity`` (always positive: prices and quantities are refused
  unless positive, so the value is never signed by BUY/SELL).
- Pro rata: a leg's rupee share = tolerance x its planned value / the sum of all legs' planned values (ADR-095).
  The share is ROUNDED DOWN to the paisa, so the shares add up to at most the tolerance; the leftover is never handed to
  another leg.
- The share becomes a per-unit allowance (share / quantity, also rounded down). The leg's LIMIT is planned + allowance
  for a BUY and planned - allowance for a SELL, then rounded to the tick toward the user with ``round_to_tick`` (BUY
  floors, SELL ceils), so a leg never gets more room than its share.
- A SELL limit that would be 0 or below is clamped to one tick (never 0 or negative).
- ``fills_within``: today's depth fills the quantity (``executable_limit``) AND that executable limit is not worse
  than the protected limit (BUY: <=, SELL: >=).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext

from ofo.engine.executable_price import (
    Depth,
    _action,
    _positive_int,
    executable_limit,
    round_to_tick,
)
from ofo.engine.legs import Action
from ofo.money import PAISE

# Working precision for the share maths: far above any rupee amount we carry, so the only rounding is the deliberate
# rounding toward the user.
_PRECISION = 60
# The candidate limit is cut (toward the user) to this many decimal places finer than the tick before
# ``round_to_tick``, so its own division by the tick stays exact in the default 28-digit context.
_SUB_TICK_PLACES = 6


@dataclass(frozen=True)
class PlannedLeg:
    side: Action
    quantity: int
    planned_price: Decimal  # the price the user planned at (LTP or the user's own price)
    depth: Depth  # the leg's market depth (``depth_from_quote``), used only for ``fills_within``


@dataclass(frozen=True)
class ProtectedLeg:
    side: Action
    quantity: int
    planned_price: Decimal
    share: Decimal  # rupees of the tolerance this leg may use (rounded down to the paisa)
    limit: Decimal  # the protected LIMIT price, on the tick, rounded toward the user
    adverse: Decimal  # rupees the limit actually allows against the user: (limit - planned) x qty, sign per side
    fills_within: bool  # today's depth fills the quantity at a price not worse than ``limit``
    executable_limit: Decimal | None  # the depth-walk limit (None when the depth cannot fill)


@dataclass(frozen=True)
class ProtectedLimits:
    tolerance: Decimal
    legs: tuple[ProtectedLeg, ...]
    # Sum of the legs' ``adverse`` rupees; never above ``tolerance``. It can be below 0 when rounding tightens a leg
    # past its planned price, so it is NOT "remaining room" and must not be used as such.
    total_adverse: Decimal


def _strict_decimal(value: object, name: str) -> Decimal:
    # Stricter than executable_price._decimal: an int (or bool) is refused too, so every caller converts on purpose.
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal (int, bool and float are refused), got {value!r}")
    return value


def _tolerance(value: object) -> Decimal:
    value = _strict_decimal(value, "tolerance")
    if value < 0:
        raise ValueError(f"tolerance must be >= 0, got {value}")
    return value


def _leg_inputs(leg: object) -> tuple[Action, int, Decimal, Depth]:
    if not isinstance(leg, PlannedLeg):
        raise ValueError(f"each leg must be a PlannedLeg, got {leg!r}")
    side, quantity = _action(leg.side), _positive_int(leg.quantity, "quantity")
    price = _strict_decimal(leg.planned_price, "planned_price")
    if price <= 0:
        raise ValueError(f"planned_price must be positive, got {price}")
    if not isinstance(leg.depth, Depth):
        raise ValueError("depth must come from depth_from_quote")
    return side, quantity, price, leg.depth


def _protected_price(planned: Decimal, allowance: Decimal, tick: Decimal, side: Action) -> Decimal:
    toward_user = ROUND_FLOOR if side is Action.BUY else ROUND_CEILING
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = _PRECISION, toward_user
        candidate = planned + allowance if side is Action.BUY else planned - allowance
        # quantize keeps only the argument's exponent: the tick's exponent minus _SUB_TICK_PLACES
        candidate = candidate.quantize(tick.scaleb(-_SUB_TICK_PLACES), rounding=toward_user)
    if side is Action.SELL and candidate <= 0:
        return tick  # clamp: a SELL limit never goes to 0 or below
    limit = round_to_tick(candidate, tick, side)
    if side is Action.SELL:
        return max(limit, tick)  # a higher SELL limit is only tighter
    if limit < tick:  # a BUY at 0 is not an order, and raising it to one tick would exceed the share
        raise ValueError(f"no BUY limit of at least one tick fits planned price {planned}")
    return limit


def protected_limits(legs: Sequence[PlannedLeg], tolerance: Decimal, tick: Decimal) -> ProtectedLimits:
    """Split ``tolerance`` (rupees, whole strategy) across ``legs`` pro rata to planned value (ADR-095)."""
    tolerance = _tolerance(tolerance)
    tick = _strict_decimal(tick, "tick")
    if tick <= 0:
        raise ValueError(f"tick must be positive, got {tick}")
    if isinstance(legs, (str, bytes)) or not isinstance(legs, Sequence) or not legs:
        raise ValueError("legs must be a non-empty sequence of PlannedLeg")
    inputs = [_leg_inputs(leg) for leg in legs]
    total_value = sum((price * quantity for _, quantity, price, _ in inputs), Decimal(0))
    if total_value <= 0:
        raise ValueError("total planned value must be positive")
    out: list[ProtectedLeg] = []
    for side, quantity, price, depth in inputs:
        with localcontext() as ctx:
            ctx.prec, ctx.rounding = _PRECISION, ROUND_FLOOR
            share = (tolerance * (price * quantity) / total_value).quantize(PAISE, rounding=ROUND_FLOOR)
            allowance = share / quantity
        limit = _protected_price(price, allowance, tick, side)
        adverse = (limit - price) * quantity if side is Action.BUY else (price - limit) * quantity
        walk = executable_limit(depth, side, quantity, tick, price)
        fills = walk.fillable and walk.limit is not None and (
            walk.limit <= limit if side is Action.BUY else walk.limit >= limit
        )
        out.append(ProtectedLeg(side, quantity, price, share, limit, adverse, fills, walk.limit))
    total_adverse = sum((leg.adverse for leg in out), Decimal(0))
    if total_adverse > tolerance:  # cannot happen by construction; fail closed if it ever does
        raise ValueError(f"protected limits allow {total_adverse} against a tolerance of {tolerance}")
    return ProtectedLimits(tolerance, tuple(out), total_adverse)
