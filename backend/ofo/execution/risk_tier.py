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
- Loss unknown (an exit, a multi-expiry plan): no tier (``None``); the screen shows no risk line.
Boundaries are inclusive on the NORMAL side: exactly 10% is NORMAL, exactly 25% with a limit set is NORMAL, exactly the
funds is not EXCEPTIONAL.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

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


@dataclass(frozen=True)
class RiskTier:
    tier: Tier
    percent_of_funds: Decimal | None  # one decimal place; None when funds are unknown/zero or the loss is unlimited
    reason: Reason | None  # set only for EXCEPTIONAL


def risk_tier(max_loss: Decimal | None, *, unlimited: bool, funds: Decimal | None,
              limit: Decimal | None) -> RiskTier | None:
    """The tier for one plan, or None when the loss is neither unlimited nor known."""
    if unlimited:
        return RiskTier(Tier.EXCEPTIONAL, None, Reason.UNLIMITED)
    if max_loss is None:
        return None
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
