"""A-37 "alert only, watch a level": a user's watched index level per strategy, answered as a yes/no rule that goes
through the alert gate (GC-IC1 step 4c; ADR-242). Pure: no clock, no I/O.

Spec basis: ADR-242 (A-37 is an adjustment alert: stored per strategy, one active watch per direction, set / cleared
by its owner, evaluated as a yes/no rule through ``gate_readings`` into the alert gate, ADR-237 (6) one writer);
REQ-170 AC-5 (risk exits never pass through the gate or read a watch). Sensibull study catalogue-raw line 222
(conditional exit when the index crosses a level; A-37 only alerts). Replaces step 4a's REQ-041 rule object (one path).

Rule id ``watch.level.above`` / ``watch.level.below`` (Identifier-safe: no colon). A watch is reached when the spot is
at or above (``ge``) / at or below (``le``) its level, exact and inclusive. The gate opens one record per episode
(edge, not level) and re-arms at a false close (ADR-237 (1)).

Answer states of ``answer``: a spot -> True / False; no spot -> None (no reading: neither opens nor clears, never
False). Answer states of ``parse_level``: a finite number above zero -> its Decimal; anything else (a word, empty,
NaN, zero, negative, a float) -> ``WatchRefused(NOT_A_NUMBER)``. ``parse_direction``: "above" / "below" only, else
``WatchRefused(NOT_A_DIRECTION)``.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

RULE_PREFIX: Final = "watch.level."
ABOVE: Final = "above"
BELOW: Final = "below"
DIRECTIONS: Final = (ABOVE, BELOW)
CMP: Final = {ABOVE: "ge", BELOW: "le"}


class Refusal(enum.Enum):
    NOT_A_NUMBER = "not_a_number"
    NOT_A_DIRECTION = "not_a_direction"


class WatchRefused(ValueError):
    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class LevelWatch:
    """One active watch: its direction ("above" / "below") and its level (a positive Decimal)."""

    direction: str
    level: Decimal


def parse_level(text: object) -> Decimal:
    """A level as entered (a string; an int is accepted) -> a positive finite Decimal; WatchRefused otherwise."""
    if isinstance(text, bool) or not isinstance(text, (str, int, Decimal)):
        raise WatchRefused(Refusal.NOT_A_NUMBER)
    try:
        level = Decimal(str(text).strip())
    except (InvalidOperation, ValueError):
        raise WatchRefused(Refusal.NOT_A_NUMBER) from None
    if not level.is_finite() or level <= 0:
        raise WatchRefused(Refusal.NOT_A_NUMBER)
    return level


def parse_direction(text: object) -> str:
    if text not in DIRECTIONS:
        raise WatchRefused(Refusal.NOT_A_DIRECTION)
    return str(text)


def rule_id(direction: str) -> str:
    """``watch.level.above`` / ``watch.level.below``."""
    return f"{RULE_PREFIX}{parse_direction(direction)}"


def is_rule_id(value: object) -> bool:
    return isinstance(value, str) and value in (RULE_PREFIX + ABOVE, RULE_PREFIX + BELOW)


def direction_of(value: object) -> str | None:
    return value[len(RULE_PREFIX):] if is_rule_id(value) else None  # type: ignore[index]


def answer(watch: LevelWatch, spot: Decimal | None) -> bool | None:
    """True when ``spot`` has reached the level (inclusive); None when there is no spot (no reading, never False)."""
    if spot is None:
        return None
    return spot >= watch.level if watch.direction == ABOVE else spot <= watch.level
