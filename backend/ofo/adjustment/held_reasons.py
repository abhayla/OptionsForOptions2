"""The held reasons of an alert crossing and the catalogue ids that show them (REQ-170 AC-4).

A neutral leaf module (stdlib only, imports nothing from the gate): the gate stores these reasons, and the Adjustment
opportunities route shows them. The route lives in the app's route tree that the paper order routes also reach, and
no paper-exit module may reach the alert gate (REQ-170 AC-5), so the shared words live here, not in the gate.
"""
from __future__ import annotations

from collections.abc import Mapping

HELD_DAILY_LIMIT = "daily_limit"
HELD_QUIET_TIME = "quiet_time"
#: The held reasons (stored values) -> the catalogue ids that render them.
HELD_TEXT_IDS: Mapping[str, str] = {
    HELD_DAILY_LIMIT: "alert_held_daily_limit",
    HELD_QUIET_TIME: "alert_held_quiet_time",
}
