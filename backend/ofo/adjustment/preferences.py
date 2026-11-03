"""A user's adjustment preferences as the pure adjustment functions take them (REQ-168 AC-1, AC-4; ADR-222 (6), (9)).

Spec basis: REQ-168 AC-1 lists the preferences (approach short-strike delta, roll distances, iron fly days, reduce
divisor, the alert distance with no playbook, the gap-at-open window, the Compare range, steps and move columns);
AC-4 "A change applies at the next check ... every alert line names the value it used"; ADR-222 (1) no number typed in
code: every value here comes from a values mapping the app layer built for ONE user (``user_preferences_store``).

``from_values`` is the one conversion; a missing key is a KeyError (``ofo.settings.value_of``), never a default. The
pure functions take the resulting values as REQUIRED parameters. Standard library and Decimal only.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.adjustment.approaches import Config
from ofo.settings import hhmm_text, value_of

PREFIX: Final = "adjustments."
SHORT_DELTA_WEEKLY: Final = "adjustments.short_delta_weekly"
SHORT_DELTA_MONTHLY: Final = "adjustments.short_delta_monthly"
ROLL_POINTS_NIFTY: Final = "adjustments.roll_points_nifty"
ROLL_POINTS_SENSEX: Final = "adjustments.roll_points_sensex"
IRON_FLY_MIN_DAYS: Final = "adjustments.iron_fly_min_days"
REDUCE_DIVISOR: Final = "adjustments.reduce_divisor"
PARTIAL_CLOSE_PERCENT: Final = "adjustments.partial_close_percent"  # ADR-238 (2)
UNTESTED_DECAY_PERCENT: Final = "adjustments.untested_decay_percent"  # ADR-238 (3)
NEAR_LEVEL_PERCENT: Final = "adjustments.near_level_percent"
GAP_AT_OPEN_UNTIL: Final = "adjustments.gap_at_open_until"
COMPARE_RANGE_PERCENT: Final = "adjustments.compare_range_percent"
COMPARE_STEPS: Final = "adjustments.compare_steps"
COMPARE_MOVE_SMALL: Final = "adjustments.compare_move_small"
COMPARE_MOVE_LARGE: Final = "adjustments.compare_move_large"
KEYS: Final = (SHORT_DELTA_WEEKLY, SHORT_DELTA_MONTHLY, ROLL_POINTS_NIFTY, ROLL_POINTS_SENSEX, IRON_FLY_MIN_DAYS,
               REDUCE_DIVISOR, NEAR_LEVEL_PERCENT, GAP_AT_OPEN_UNTIL, COMPARE_RANGE_PERCENT, COMPARE_STEPS,
               COMPARE_MOVE_SMALL, COMPARE_MOVE_LARGE, PARTIAL_CLOSE_PERCENT, UNTESTED_DECAY_PERCENT)


@dataclass(frozen=True)
class CompareView:
    """The Compare chart's span (percent either side of spot), its equal steps and the four move columns' percents."""

    range_percent: Decimal
    steps: int
    move_small: Decimal
    move_large: Decimal

    def moves(self) -> dict[str, Decimal]:
        """Row id -> the signed index move in percent (the row ids are the catalogue's criterion rows)."""
        return {"move_m2": -self.move_large, "move_m1": -self.move_small, "move_p1": self.move_small,
                "move_p2": self.move_large}


@dataclass(frozen=True)
class Preferences:
    approach: Config
    near_level_percent: Decimal
    gap_until: str  # "HH:MM"
    compare: CompareView


def from_values(values: Mapping[str, Decimal]) -> Preferences:
    """One user's values (every key in ``KEYS``) as the typed preferences; a missing key raises KeyError."""
    def v(key: str) -> Decimal:
        return value_of(values, key)

    approach = Config({"weekly": v(SHORT_DELTA_WEEKLY), "monthly": v(SHORT_DELTA_MONTHLY)},
                      {"NIFTY": v(ROLL_POINTS_NIFTY), "SENSEX": v(ROLL_POINTS_SENSEX)},
                      int(v(IRON_FLY_MIN_DAYS)), int(v(REDUCE_DIVISOR)), int(v(PARTIAL_CLOSE_PERCENT)),
                      int(v(UNTESTED_DECAY_PERCENT)))
    compare = CompareView(v(COMPARE_RANGE_PERCENT), int(v(COMPARE_STEPS)), v(COMPARE_MOVE_SMALL),
                          v(COMPARE_MOVE_LARGE))
    return Preferences(approach, v(NEAR_LEVEL_PERCENT), hhmm_text(v(GAP_AT_OPEN_UNTIL)), compare)
