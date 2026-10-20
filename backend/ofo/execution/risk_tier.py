"""The Execute review's risk tier: the ONE rule that turns the engine's worst-case loss and Zerodha's available funds
into NORMAL / ELEVATED / EXCEPTIONAL (owner decision 2026-10-20, ADR-140; REQ-056 AC-6; ADR-008).

Spec basis: ADR-140 (tiers), REQ-056 AC-6. Every input is a server figure (the engine's ``strategy_metrics`` worst case,
Zerodha's ``equity.net``, the user's own max-loss limit when the app stores one - it stores none yet, so the
route passes ``None``). The page only renders the result; the browser computes no tier and no percentage.

Rule (``loss`` = the worst-case loss, ``funds`` = available funds, ``limit`` = the user's limit):
- EXCEPTIONAL: the loss is unlimited, or ``loss > funds`` when funds are known.
- else ELEVATED: ``loss > limit`` when a limit is set; or ``loss > 25%`` of funds; or (no limit) ``loss > 10%``.
- else NORMAL.
- Funds unknown (absent / failed read): decided by the limit alone; no limit -> ELEVATED; no percentage is given.
- Funds stated as 0 or below: any loss above 0 is EXCEPTIONAL; a loss of 0 is NORMAL with no percentage (no division).
- Loss unknown (a multi-expiry entry: the engine returns no worst case) - ADR-143 (owner 2026-10-20): never a silent
  pass. At least ELEVATED with reason LOSS_UNKNOWN (the screen's line is exactly "Worst case: the loss for this strategy
  can't be estimated."); EXCEPTIONAL (reason UNCOVERED_SHORT) when any short leg has no protective buy of the same
  option type in the strategy. An exit (``unknown_loss`` None) is the one case with no tier (``None``): its closing
  orders say nothing about the risk left.
Boundaries are inclusive on the NORMAL side: exactly 10% is NORMAL, exactly 25% with a limit set is NORMAL, exactly the
funds is not EXCEPTIONAL.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from ofo.engine.legs import Action, Leg

NORMAL_SHARE = Decimal("0.10")
ELEVATED_SHARE = Decimal("0.25")
_HUNDRED = Decimal(100)
_ONE_DP = Decimal("0.1")


class Tier(StrEnum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    EXCEPTIONAL = "EXCEPTIONAL"


class Reason(StrEnum):
    UNLIMITED = "UNLIMITED"
    ABOVE_FUNDS = "ABOVE_FUNDS"
    LOSS_UNKNOWN = "LOSS_UNKNOWN"  # ADR-143: the engine returned no worst-case loss (tier ELEVATED at least)
    UNCOVERED_SHORT = "UNCOVERED_SHORT"  # ADR-143: loss unknown AND a short leg has no protective buy (EXCEPTIONAL)


@dataclass(frozen=True)
class RiskTier:
    tier: Tier
    percent_of_funds: Decimal | None  # one decimal place; None when funds are unknown/zero or the loss is unlimited
    reason: Reason | None  # set for EXCEPTIONAL, and for the unknown-loss ELEVATED (ADR-143)


def has_uncovered_short(legs: Iterable[Leg]) -> bool:
    """ADR-143: True when any SELL leg has no BUY leg of the same instrument type (CE / PE / FUT) in ``legs``."""
    legs = tuple(legs)
    bought = {leg.instrument for leg in legs if leg.action is Action.BUY}
    return any(leg.action is Action.SELL and leg.instrument not in bought for leg in legs)


def unknown_loss_reason(legs: Iterable[Leg], *, is_exit: bool) -> Reason | None:
    """What to report when the engine states no worst case (ADR-143): None for an exit (no tier), UNCOVERED_SHORT when
    any short leg has no protective buy, else LOSS_UNKNOWN."""
    if is_exit:
        return None
    return Reason.UNCOVERED_SHORT if has_uncovered_short(legs) else Reason.LOSS_UNKNOWN


def _unknown(reason: Reason | None) -> RiskTier | None:
    if reason is None:
        return None
    return RiskTier(Tier.EXCEPTIONAL if reason is Reason.UNCOVERED_SHORT else Tier.ELEVATED, None, reason)


def risk_tier(max_loss: Decimal | None, *, unlimited: bool, funds: Decimal | None, limit: Decimal | None,
              unknown_loss: Reason | None = Reason.LOSS_UNKNOWN) -> RiskTier | None:
    """The tier for one plan. ``unknown_loss`` is what a plan with no stated worst case is reported as
    (``unknown_loss_reason``): None (an exit) gives no tier, LOSS_UNKNOWN is ELEVATED, UNCOVERED_SHORT is EXCEPTIONAL."""
    if unlimited:
        return RiskTier(Tier.EXCEPTIONAL, None, Reason.UNLIMITED)
    if max_loss is None:
        return _unknown(unknown_loss)
    if funds is None:
        over = limit is None or max_loss > limit
        return RiskTier(Tier.ELEVATED if over else Tier.NORMAL, None, None)
    if max_loss > funds:
        return RiskTier(Tier.EXCEPTIONAL, None if funds <= 0 else _percent(max_loss, funds), Reason.ABOVE_FUNDS)
    if funds <= 0:  # the loss is 0 here (it is not above the funds)
        return RiskTier(Tier.NORMAL, None, None)
    over = (limit is not None and max_loss > limit) or max_loss > funds * ELEVATED_SHARE or (
        limit is None and max_loss > funds * NORMAL_SHARE)
    return RiskTier(Tier.ELEVATED if over else Tier.NORMAL, _percent(max_loss, funds), None)


def _percent(loss: Decimal, funds: Decimal) -> Decimal:
    return (loss * _HUNDRED / funds).quantize(_ONE_DP, rounding=ROUND_HALF_UP)
