"""V1 entry and exit condition types, each a Rule of the one model (REQ-041 AC-2, AC-3; ADR-009 Q17, Q18, Q144).

Every threshold is inclusive (``>=`` / ``<=``): a value exactly AT the threshold triggers. Examples: a max loss of
5,000 triggers at live P&L -5,000 and below; a profit target of 3,000 at +3,000 and above; a time window
09:30-11:00 includes both ends.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from enum import Enum

from ofo.rules.conditions import AllOf, Always, Compare, Op
from ofo.rules.inputs import InputName, minutes_of_day, require_finite
from ofo.rules.model import Rule, RuleAction, RuleKind


class Direction(Enum):
    AT_OR_ABOVE = "at_or_above"
    AT_OR_BELOW = "at_or_below"

    @property
    def op(self) -> Op:
        return Op.GTE if self is Direction.AT_OR_ABOVE else Op.LTE


def _positive(value: object, name: str) -> Decimal:
    checked = require_finite(value, name)
    if checked <= 0:
        raise ValueError(f"{name} must be > 0, got {checked}")
    return checked


def _between(name: InputName, low: Decimal, high: Decimal) -> AllOf:
    if low > high:
        raise ValueError(f"range low {low} is above high {high}")
    return AllOf((Compare(name, Op.GTE, low), Compare(name, Op.LTE, high)))


# ---- Entry (AC-2, Q17 = D) ----------------------------------------------------------------------------------


def entry_immediate(rule_id: str, *, action: RuleAction) -> Rule:
    """Enter now (the Q17 default): no condition."""
    return Rule(rule_id, RuleKind.ENTRY, Always(), action, "Enter now")


def entry_level_reached(rule_id: str, level: Decimal, direction: Direction, *, action: RuleAction) -> Rule:
    """Market reaches a level: underlying at or above / at or below ``level``."""
    level = _positive(level, "level")
    return Rule(rule_id, RuleKind.ENTRY, Compare(InputName.UNDERLYING_LEVEL, direction.op, level), action,
                f"Underlying {direction.value.replace('_', ' ')} {level}")


def entry_range(rule_id: str, low: Decimal, high: Decimal, *, action: RuleAction) -> Rule:
    """Market is inside a range, both ends included."""
    low, high = _positive(low, "low"), _positive(high, "high")
    return Rule(rule_id, RuleKind.ENTRY, _between(InputName.UNDERLYING_LEVEL, low, high), action,
                f"Underlying between {low} and {high}")


def entry_premium_target(rule_id: str, target: Decimal, *, receive: bool, action: RuleAction) -> Rule:
    """Wait for better premium: net credit at least ``target`` rupees (``receive``), or net debit at most ``target``.

    NET_PREMIUM is the engine's signed rupee total for the whole strategy, credit positive, so "pay at most 3,750"
    is ``net_premium >= -3750`` (a debit of 3,000 is -3,000, a debit of 4,000 is -4,000).
    """
    target = _positive(target, "target")
    condition = Compare(InputName.NET_PREMIUM, Op.GTE, target if receive else -target)
    label = f"Net credit at least Rs {target}" if receive else f"Net debit at most Rs {target}"
    return Rule(rule_id, RuleKind.ENTRY, condition, action, label)


def entry_volatility(rule_id: str, measure: InputName, low: Decimal | None, high: Decimal | None, *,
                     action: RuleAction) -> Rule:
    """Volatility condition on IV or IV percentile: at or above ``low`` and/or at or below ``high``."""
    if measure not in (InputName.IV, InputName.IV_PERCENTILE):
        raise ValueError(f"a volatility condition reads IV or IV_PERCENTILE, not {measure!r}")
    if low is None and high is None:
        raise ValueError("a volatility condition needs a low and/or a high bound")
    if low is not None and high is not None:
        condition = _between(measure, require_finite(low, "low"), require_finite(high, "high"))
    elif low is not None:
        condition = Compare(measure, Op.GTE, require_finite(low, "low"))
    else:
        condition = Compare(measure, Op.LTE, require_finite(high, "high"))
    return Rule(rule_id, RuleKind.ENTRY, condition, action, f"{measure.value} between {low} and {high}")


def entry_time_window(rule_id: str, start: datetime.time, end: datetime.time, *, action: RuleAction) -> Rule:
    """Enter only between ``start`` and ``end`` IST, both included."""
    return Rule(rule_id, RuleKind.ENTRY, _between(InputName.TIME_OF_DAY, minutes_of_day(start), minutes_of_day(end)),
                action, f"Between {start.isoformat('minutes')} and {end.isoformat('minutes')} IST")


# ---- Exit (AC-3, Q18 = D) -----------------------------------------------------------------------------------


def exit_profit_target(rule_id: str, amount: Decimal, *, action: RuleAction) -> Rule:
    """Live P&L at or above ``amount`` rupees."""
    amount = _positive(amount, "amount")
    return Rule(rule_id, RuleKind.EXIT, Compare(InputName.LIVE_PNL, Op.GTE, amount), action,
                f"Profit target {amount}")


def exit_max_loss(rule_id: str, amount: Decimal, *, action: RuleAction) -> Rule:
    """Live P&L at or below ``-amount`` rupees (``amount`` is the loss as a positive number)."""
    amount = _positive(amount, "amount")
    return Rule(rule_id, RuleKind.EXIT, Compare(InputName.LIVE_PNL, Op.LTE, -amount), action, f"Max loss {amount}")


def exit_time(rule_id: str, *, days_to_expiry: int, at_or_after: datetime.time | None = None,
              action: RuleAction) -> Rule:
    """Time exit: DTE at or below ``days_to_expiry``, optionally also at or after a time of day (IST)."""
    if isinstance(days_to_expiry, bool) or not isinstance(days_to_expiry, int) or days_to_expiry < 0:
        raise ValueError(f"days_to_expiry must be a non-negative integer, got {days_to_expiry!r}")
    dte = Compare(InputName.DTE, Op.LTE, Decimal(days_to_expiry))
    if at_or_after is None:
        return Rule(rule_id, RuleKind.EXIT, dte, action, f"{days_to_expiry} days to expiry or fewer")
    clock = Compare(InputName.TIME_OF_DAY, Op.GTE, minutes_of_day(at_or_after))
    return Rule(rule_id, RuleKind.EXIT, AllOf((dte, clock)), action,
                f"{days_to_expiry} days to expiry or fewer, from {at_or_after.isoformat('minutes')} IST")


def exit_underlying_level(rule_id: str, level: Decimal, direction: Direction, *, action: RuleAction) -> Rule:
    """Underlying at or above / at or below ``level``."""
    level = _positive(level, "level")
    return Rule(rule_id, RuleKind.EXIT, Compare(InputName.UNDERLYING_LEVEL, direction.op, level), action,
                f"Underlying {direction.value.replace('_', ' ')} {level}")
