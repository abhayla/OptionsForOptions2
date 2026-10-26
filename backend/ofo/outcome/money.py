"""REQ-081 (W-154): the Builder summary's money figures, shaped for the answer.

Every number comes from ``ofo.engine.money_summary`` (ADR-008: the one engine owns the arithmetic); this module only
decides which figure is present, which catalogue sentence or reason goes with it (ADR-003), and the funds-share block
(ADR-164). An absent figure is ``None`` plus a reason text, never ``0.00`` and never an empty string.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo.engine import money_summary as engine
from ofo.engine.legs import Instrument
from ofo.errors.explanations import ExplanationText, render_explanation

CHECKED: Final = "CHECKED"  # the margin state that carries Zerodha's figures (service.MARGIN_CHECKED)
GET: Final = "get"
PAY: Final = "pay"


@dataclass(frozen=True)
class NetPremium:
    """``amount`` is the non-negative magnitude, ``side`` get / pay (None for exactly zero), ``per_unit`` the same per
    unit when every leg has the same quantity. When ``amount`` is None the figure is absent and ``reason`` says why."""

    amount: Any
    side: str | None
    per_unit: Any
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
    net = engine.net_premium_amount(legs)
    per_unit = engine.net_premium_per_unit(legs)
    if net == 0:
        return NetPremium(engine.ZERO_MONEY, None, None if per_unit is None else engine.ZERO_MONEY,
                          render_explanation("cell_rupees", amount=engine.ZERO_MONEY), None)
    side = GET if net > 0 else PAY
    template = "money_premium_get" if side == GET else "money_premium_pay"
    return NetPremium(abs(net), side, per_unit, render_explanation(template, amount=abs(net)), None)


@dataclass(frozen=True)
class ValueSplit:
    """Intrinsic and time value of the option legs, signed: premium paid is positive, premium received negative."""

    intrinsic: Any
    time: Any
    label: ExplanationText | None
    reason: ExplanationText | None


def time_and_intrinsic(legs: Sequence[Any], spot: Any) -> ValueSplit:
    """A leg without an LTP, or no spot, makes both figures absent with the reason (REQ-081 AC-3, AC-8)."""
    options = [leg for leg in legs if leg.instrument is not Instrument.FUT]
    if not options:
        return ValueSplit(None, None, None, None)
    if spot is None or any(leg.ltp is None for leg in options):
        return ValueSplit(None, None, None, render_explanation("money_value_price_missing"))
    intrinsic, time = engine.intrinsic_and_time(options, spot)
    return ValueSplit(intrinsic, time, render_explanation("money_value_label"), None)


@dataclass(frozen=True)
class RewardRisk:
    reward_risk: Any
    risk_reward: Any
    reason: ExplanationText | None


def reward_risk(max_profit: Any, max_loss: Any, *, single_expiry: bool = True) -> RewardRisk:
    """Both maximums come from the Summary (already including charges, ADR-082); ``None`` = Unlimited. Absent with a
    reason when either side is Unlimited, the loss is 0, there is no profit, or the legs are on different expiries."""
    if not single_expiry:
        return RewardRisk(None, None, render_explanation("money_reward_risk_multi_expiry"))
    if max_profit is None or max_loss is None:
        return RewardRisk(None, None, render_explanation("summary_reward_risk_none"))
    if max_loss <= 0:
        return RewardRisk(None, None, render_explanation("money_reward_risk_zero_loss"))
    if max_profit <= 0:
        return RewardRisk(None, None, render_explanation("summary_make_none"))
    ratio, inverse = engine.reward_risk_ratios(max_profit, max_loss)
    return RewardRisk(ratio, inverse, None)


@dataclass(frozen=True)
class FundsShare:
    """ADR-164: each maximum as a whole percent of the available funds Zerodha reported, with that figure and when it
    was read. A side that is Unlimited (or a profit below 0) has no percentage; ``*_text`` is the catalogue wording."""

    funds: Any
    read_at: Any
    max_profit_percent: Any
    max_loss_percent: Any
    max_profit_text: ExplanationText | None
    max_loss_text: ExplanationText | None


def _share(amount: Any, funds: Any) -> tuple[Any, ExplanationText | None]:
    if amount is None or amount < 0:
        return None, None
    raw = engine.percent_of_funds(amount, funds)
    if 0 < raw < 1:  # the whole percent would read 0 or 1 for it: a catalogue sentence says so
        return engine.whole_percent(engine.ZERO_MONEY), render_explanation("money_funds_percent_small")
    whole = engine.whole_percent(raw)
    return whole, render_explanation("money_funds_percent", pct=whole)


def funds_share(max_profit: Any, max_loss: Any, margin: Any) -> FundsShare | None:
    """Present ONLY when the margin block is CHECKED with a finite positive Decimal of funds and a read time; every
    other state (no session, unreadable, no basket, busy, funds 0 or negative, not a Decimal) gives None."""
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

