"""REQ-081 (W-154): the Builder summary's money figures, every one an exact Decimal from the engine (ADR-008).

Net premium (Pay/Get), intrinsic and time value, bounded Reward/Risk and Risk/Reward, and max profit / max loss as a
percentage of the user's Zerodha funds (ADR-164). Pure functions over engine legs: standard library and ``ofo.engine``
only, no float anywhere. Every user-visible sentence is a catalogue template (ADR-003); an absent figure is ``None``
plus a reason text, never ``0.00`` and never an empty string.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, Final

from ofo.engine.legs import Action, Instrument
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.money import PAISE

RATIO_STEP: Final = Decimal("0.01")  # Reward/Risk and Risk/Reward: two decimals, half-even (REQ-081 AC-4)
WHOLE_PERCENT: Final = Decimal(1)
HUNDRED: Final = Decimal(100)
CHECKED: Final = "CHECKED"  # the margin state that carries Zerodha's figures (service.MARGIN_CHECKED)
GET: Final = "get"
PAY: Final = "pay"


def net_premium_amount(legs: Sequence[Any]) -> Decimal:
    """Sells minus buys of entry price x quantity (positive = credit). The ONE rule of the TOTAL Entry Value cell
    (backend/ofo/table/model.py _total_row) and of REQ-081 AC-1; an options-only strategy with every price."""
    return sum(((leg.entry_price if leg.action is Action.SELL else -leg.entry_price) * leg.quantity for leg in legs),
               Decimal(0))


@dataclass(frozen=True)
class NetPremium:
    """``amount`` is the non-negative magnitude, ``side`` get / pay (None for exactly zero), ``per_unit`` the same per
    unit when every leg has the same quantity. When ``amount`` is None the figure is absent and ``reason`` says why."""

    amount: Decimal | None
    side: str | None
    per_unit: Decimal | None
    text: ExplanationText | None
    reason: ExplanationText | None


def _absent_premium(reason_id: str) -> NetPremium:
    return NetPremium(None, None, None, None, render_explanation(reason_id))


def net_premium(legs: Sequence[Any]) -> NetPremium | None:
    """None for no legs (no block). A futures leg, or any leg without a planned entry price, makes the whole figure
    absent with its reason: never a partial sum of the legs that do have prices (REQ-081 AC-1, AC-8)."""
    if not legs:
        return None
    if any(leg.instrument is Instrument.FUT for leg in legs):
        return _absent_premium("money_premium_futures")
    if any(leg.entry_price is None for leg in legs):
        return _absent_premium("money_price_missing")
    net = net_premium_amount(legs)
    if net == 0:
        return NetPremium(Decimal(0).quantize(PAISE), None, Decimal(0).quantize(PAISE) if _same_qty(legs) else None,
                          render_explanation("cell_rupees", amount=Decimal(0).quantize(PAISE)), None)
    side = GET if net > 0 else PAY
    per_unit = abs(sum((leg.entry_price if leg.action is Action.SELL else -leg.entry_price for leg in legs),
                       Decimal(0))) if _same_qty(legs) else None
    template = "money_premium_get" if side == GET else "money_premium_pay"
    return NetPremium(abs(net), side, per_unit, render_explanation(template, amount=abs(net)), None)


def _same_qty(legs: Sequence[Any]) -> bool:
    return len({leg.quantity for leg in legs}) == 1


@dataclass(frozen=True)
class ValueSplit:
    """Intrinsic and time value of the option legs, signed: premium paid is positive, premium received negative."""

    intrinsic: Decimal | None
    time: Decimal | None
    label: ExplanationText | None
    reason: ExplanationText | None


def time_and_intrinsic(legs: Sequence[Any], spot: Decimal | None) -> ValueSplit:
    """Per option leg intrinsic = max(spot - strike, 0) for a call, max(strike - spot, 0) for a put; time = ltp -
    intrinsic; each x quantity, bought +, sold -. A futures leg adds nothing. A leg without an LTP, or no spot, makes
    both figures absent with the reason (REQ-081 AC-3, AC-8)."""
    options = [leg for leg in legs if leg.instrument is not Instrument.FUT]
    if not options:
        return ValueSplit(None, None, None, None)
    if spot is None or any(leg.ltp is None for leg in options):
        return ValueSplit(None, None, None, render_explanation("money_value_price_missing"))
    intrinsic = time = Decimal(0)
    for leg in options:
        gap = spot - leg.strike if leg.instrument is Instrument.CE else leg.strike - spot
        per_unit = max(gap, Decimal(0))
        sign = 1 if leg.action is Action.BUY else -1
        intrinsic += sign * per_unit * leg.quantity
        time += sign * (leg.ltp - per_unit) * leg.quantity
    return ValueSplit(intrinsic.quantize(PAISE, ROUND_HALF_EVEN), time.quantize(PAISE, ROUND_HALF_EVEN),
                      render_explanation("money_value_label"), None)


@dataclass(frozen=True)
class RewardRisk:
    reward_risk: Decimal | None
    risk_reward: Decimal | None
    reason: ExplanationText | None


def _ratio(top: Decimal, bottom: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        return (top / bottom).quantize(RATIO_STEP, ROUND_HALF_EVEN)


def reward_risk(max_profit: Decimal | None, max_loss: Decimal | None, *, single_expiry: bool = True) -> RewardRisk:
    """Reward/Risk = max profit / max loss and its inverse, both from the Summary (already including charges, ADR-082).
    ``None`` = Unlimited. Absent with a reason when either side is Unlimited, the loss is 0, there is no profit, or the
    legs are on different expiries (no worst case, ADR-143)."""
    if not single_expiry:
        return RewardRisk(None, None, render_explanation("money_reward_risk_multi_expiry"))
    if max_profit is None or max_loss is None:
        return RewardRisk(None, None, render_explanation("summary_reward_risk_none"))
    if max_loss <= 0:
        return RewardRisk(None, None, render_explanation("money_reward_risk_zero_loss"))
    if max_profit <= 0:
        return RewardRisk(None, None, render_explanation("summary_make_none"))
    return RewardRisk(_ratio(max_profit, max_loss), _ratio(max_loss, max_profit), None)


@dataclass(frozen=True)
class FundsShare:
    """ADR-164: each maximum as a whole percent of the available funds Zerodha reported, with that figure and the
    read. A side that is Unlimited (or a profit of 0 or less) has no percentage; ``*_text`` is the catalogue wording."""

    funds: Decimal
    read_at: Any
    max_profit_percent: Decimal | None
    max_loss_percent: Decimal | None
    max_profit_text: ExplanationText | None
    max_loss_text: ExplanationText | None


def _share(amount: Decimal | None, funds: Decimal) -> tuple[Decimal | None, ExplanationText | None]:
    if amount is None or amount < 0:
        return None, None
    with localcontext() as ctx:
        ctx.prec = 50
        raw = amount * HUNDRED / funds
    if 0 < raw < 1:  # the whole percent would read 0 or 1 for it: a catalogue sentence says so
        return Decimal(0), render_explanation("money_funds_percent_small")
    whole = raw.quantize(WHOLE_PERCENT, ROUND_HALF_EVEN)
    return whole, render_explanation("money_funds_percent", pct=whole)


def funds_share(max_profit: Decimal | None, max_loss: Decimal | None, margin: Any) -> FundsShare | None:
    """Present ONLY when the margin block is CHECKED with a finite positive Decimal of funds and a read time; every
    state (no session, unreadable, no basket, busy, funds 0 or negative, a reply that is not a Decimal) gives None."""
    available = getattr(margin, "available", None)
    read_at = getattr(margin, "checked_at", None)
    if getattr(margin, "state", None) != CHECKED or read_at is None:
        return None
    if type(available) is not Decimal or not available.is_finite() or available <= 0:
        return None
    profit_pct, profit_text = _share(max_profit, available)
    loss_pct, loss_text = _share(max_loss, available)
    return FundsShare(available, read_at, profit_pct, loss_pct, profit_text, loss_text)


def with_funds(summary: Any, margin: Any) -> Any:
    """The summary with its funds share set (or unchanged when there is none): called after the margin read, with the
    same funds+basket read that answers the margin line (no second Zerodha call, REQ-081 AC-8)."""
    if summary is None:
        return summary
    share = funds_share(summary.max_profit, summary.max_loss, margin)
    return summary if share is None else dataclasses.replace(summary, funds_share=share)
