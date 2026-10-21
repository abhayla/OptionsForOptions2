"""Platform detection, condition 1 of owner decision Q253 (W-122; REQ-045 AC-1, AC-2; REQ-046 AC-1).

Spec basis: REQ-045 Q253 - "the index is within **0.5%** of a short strike or of a breakeven" and "every threshold is an
admin setting with these defaults"; "Each detection names the condition that fired and its exact numbers (REQ-046
AC-1)". REQ-045 AC-1: platform-detected risk areas are labelled 'Adjustment opportunity detected'. Conditions 2 and 3
(loss share of max loss, days to expiry) are a later step.

Distance (the spec defines no basis; this module states it):

    distance points  = |index - level|
    distance percent = |index - level| / index x 100, shown rounded half-up to 2 decimals

"Within" is inclusive: a distance EXACTLY equal to the threshold fires. The comparison is exact
(|index - level| x 100 <= threshold x index), never on the rounded percentage, so 0.504% does not fire at 0.5 even though
it shows as 0.50.

Detection runs with or without a user rule (REQ-045 AC-2): its inputs are the legs, the index level, the breakevens and
the threshold only. It names the condition and its numbers, never a candidate setup (REQ-045 AC-5). Standard library
and Decimal only; no clock is read here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Iterable, Literal

from ofo.engine.legs import Action, Instrument
from ofo.money import HUNDREDTH

#: Q253 condition 1's default, the one home of the number (an admin setting overrides it; the admin screen is Step 6).
NEAR_LEVEL_THRESHOLD_PERCENT: Final = Decimal("0.5")
#: REQ-045 AC-1's label for every platform detection.
PLATFORM_DETECTION_LABEL: Final = "Adjustment opportunity detected"
NEAR_SHORT_STRIKE: Final = "near_short_strike"
NEAR_BREAKEVEN: Final = "near_breakeven"
Condition = Literal["near_short_strike", "near_breakeven"]
_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Detection:
    """One fired condition with the exact numbers it fired on (REQ-046 AC-1 Layer 1)."""

    condition: Condition
    level: Decimal
    index_level: Decimal
    distance_points: Decimal
    distance_percent: Decimal  # rounded half-up to 0.01
    threshold_percent: Decimal


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal, got {value!r}")
    return value


def short_strikes(legs: Iterable[object]) -> tuple[Decimal, ...]:
    """The strikes of the SELL option legs (a leg is anything with ``action``, ``instrument`` and ``strike``), ascending,
    each once. A sold future has no strike and is not a short strike."""
    out = set()
    for leg in legs:
        if leg.action is Action.SELL and leg.instrument is not Instrument.FUT:
            out.add(_decimal(leg.strike, "strike"))
    return tuple(sorted(out))


def check_threshold(threshold_percent: object) -> Decimal:
    """A threshold is a Decimal percent in (0, 100]; anything else is refused, never defaulted."""
    value = _decimal(threshold_percent, "threshold_percent")
    if not Decimal(0) < value <= _HUNDRED:
        raise ValueError(f"threshold_percent must be above 0 and at most 100, got {value}")
    return value


def _near(condition: Condition, level: Decimal, index_level: Decimal, threshold: Decimal) -> Detection | None:
    distance = abs(index_level - level)
    if distance * _HUNDRED > threshold * index_level:  # exact: the rounded percent never decides
        return None
    percent = (distance * _HUNDRED / index_level).quantize(HUNDREDTH, rounding=ROUND_HALF_UP)
    return Detection(condition, level, index_level, distance, percent, threshold)


def detect_near_levels(*, short_strike_levels: Iterable[Decimal], breakevens: Iterable[Decimal],
                       index_level: Decimal, threshold_percent: Decimal) -> tuple[Detection, ...]:
    """Q253 condition 1: one Detection per short strike and per breakeven the index is within ``threshold_percent`` of.
    Short strikes first, then breakevens, each ascending. No breakevens (none exist, or a multi-expiry strategy has no
    exact ones) means no breakeven condition; it never makes one up."""
    index = _decimal(index_level, "index_level")
    if index <= 0:
        raise ValueError(f"index_level must be above 0, got {index}")
    threshold = check_threshold(threshold_percent)
    found: list[Detection] = []
    for condition, levels in ((NEAR_SHORT_STRIKE, short_strike_levels), (NEAR_BREAKEVEN, breakevens)):
        for level in sorted({_decimal(v, "level") for v in levels}):
            hit = _near(condition, level, index, threshold)
            if hit is not None:
                found.append(hit)
    return tuple(found)
