"""A-37 "alert only, watch a level" as a REQ-041 rule (GC-IC1 step 4a): no new alert path.

Spec basis: brief GC-IC1 4a "this creates a REQ-041 rule with action ``alert_only`` (RuleAction.ALERT_ONLY) on the
underlying level, through the existing rules ... evaluation. No new alert path." Sensibull study catalogue-raw line 222
(conditional exit when the index crosses a level; A-37 only alerts). The rule is the REQ-041 model's own
(``ofo.rules.model.Rule``, ``Compare`` on ``InputName.UNDERLYING_LEVEL``) and is evaluated by
``ofo.rules.model.evaluate`` (three-valued: no healthy underlying level -> CANNOT_EVALUATE, never a guess).

Direction from the level and the spot now: a level above the spot is watched "at or above", below it "at or below".
Answer states of ``watch``: level stated and a spot -> the rule; level not a number (or not finite, or <= 0) ->
``WatchRefused(NOT_A_NUMBER)``; no underlying price now -> ``WatchRefused(NO_SPOT)``; the level equal to the spot ->
``WatchRefused(AT_SPOT)`` (it is already there: there is nothing to watch for).
"""
from __future__ import annotations

import enum
from decimal import Decimal, InvalidOperation

from ofo.errors.explanations import render_explanation
from ofo.rules.conditions import Compare
from ofo.rules.inputs import InputName
from ofo.rules.model import Rule, RuleAction, RuleKind
from ofo.rules.templates import Direction


class Refusal(enum.Enum):
    NOT_A_NUMBER = "not_a_number"
    NO_SPOT = "no_spot"
    AT_SPOT = "at_spot"


class WatchRefused(ValueError):
    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _level(text: object) -> Decimal:
    try:
        level = Decimal(str(text).strip())
    except (InvalidOperation, ValueError):
        raise WatchRefused(Refusal.NOT_A_NUMBER) from None
    if not level.is_finite() or level <= 0:
        raise WatchRefused(Refusal.NOT_A_NUMBER)
    return level


def watch(rule_id: str, level_text: object, spot: Decimal | None) -> Rule:
    """The A-37 rule: alert only when the underlying reaches ``level_text`` (module docstring)."""
    level = _level(level_text)
    if spot is None:
        raise WatchRefused(Refusal.NO_SPOT)
    if level == spot:
        raise WatchRefused(Refusal.AT_SPOT)
    direction = Direction.AT_OR_ABOVE if level > spot else Direction.AT_OR_BELOW
    return Rule(rule_id, RuleKind.ADJUSTMENT, Compare(InputName.UNDERLYING_LEVEL, direction.op, level),
                RuleAction.ALERT_ONLY,
                render_explanation("rule_label_underlying_level", direction=direction, level=level))
