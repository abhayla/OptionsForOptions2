"""The alert gate's preset for a trading style, resolved from settings at run time (REQ-170 AC-6, AC-7; Q-AD-2).

Spec basis: REQ-170 AC-6 "the check speed is an admin setting only, per style; the re-arm margin and the daily cap
are admin settings (the user may lower the cap, never raise it); confirmation candle, cool-down and quiet time have
admin defaults the user may change on the Preferences tab"; AC-7 every value read at run time; Q-AD-2 "0-1 day to
expiry = intraday rules, a weekly expiry = weekly, a monthly expiry = monthly ... the user may pin a style per
strategy"; ADR-235 (1) the check speed per style.

``preset_for`` is THE one builder of an ``alert_gate.Preset`` (finding engine-input-chosen-per-caller: no caller
rebuilds one). It takes two mappings the app layer resolved once at the caller's ``now`` (finding
check-clock-read-once-per-batch): ``values`` = the user's values in force (their own, else the admin default), and
``admin`` = the admin settings in force. The re-arm margin is read from ``admin`` only; the daily cap is
min(user value, admin ceiling), a second fence behind the write-time refusal (an admin may lower the ceiling after a
user saved a higher one). A missing key is a KeyError (``ofo.settings.value_of``), never a default.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Final, Literal

from ofo.adjustment.gate_rows import Preset
from ofo.settings import time_of, value_of

Style = Literal["intraday", "weekly", "monthly"]
STYLES: Final[tuple[Style, ...]] = ("intraday", "weekly", "monthly")
EXPIRY_KINDS: Final = ("weekly", "monthly")  # the kinds ofo_app.adjustment_readers.expiry_kind_of answers
INTRADAY_LAST_DAY: Final = 1  # REQ-170 table: "Intraday (0-1 day)"; days from ofo.timeutil.days_to_expiry

CANDLE: Final = "confirm_candle_minutes"
COOLDOWN: Final = "cooldown_minutes"
QUIET: Final = "quiet_until"
REARM: Final = "rearm_percent"
CAP: Final = "daily_cap"
USER_FIELDS: Final = (CANDLE, COOLDOWN, QUIET, CAP)  # AC-6: changeable on the Preferences tab (the cap only lower)
SPEED: Final = "check_seconds"


class StyleRefused(ValueError):
    """The style cannot be told (unknown style, pin, expiry kind or days): the caller holds, never guesses."""


# Every registry key by its exact text (the settings guard finds each key's reader by its quoted string).
KEYS: Final[dict[str, dict[str, str]]] = {
    "intraday": {CANDLE: "alerts.intraday.confirm_candle_minutes", COOLDOWN: "alerts.intraday.cooldown_minutes",
                 QUIET: "alerts.intraday.quiet_until", REARM: "alerts.intraday.rearm_percent",
                 CAP: "alerts.intraday.daily_cap", SPEED: "speeds.background_check_seconds.intraday"},
    "weekly": {CANDLE: "alerts.weekly.confirm_candle_minutes", COOLDOWN: "alerts.weekly.cooldown_minutes",
               QUIET: "alerts.weekly.quiet_until", REARM: "alerts.weekly.rearm_percent",
               CAP: "alerts.weekly.daily_cap", SPEED: "speeds.background_check_seconds.weekly"},
    "monthly": {CANDLE: "alerts.monthly.confirm_candle_minutes", COOLDOWN: "alerts.monthly.cooldown_minutes",
                QUIET: "alerts.monthly.quiet_until", REARM: "alerts.monthly.rearm_percent",
                CAP: "alerts.monthly.daily_cap", SPEED: "speeds.background_check_seconds.monthly"},
}


def key(style: str, field: str) -> str:
    return KEYS[_style(style)][field]


def style_keys(style: str) -> tuple[str, ...]:
    return tuple(key(style, f) for f in (CANDLE, COOLDOWN, QUIET, REARM, CAP))


def speed_key(style: str) -> str:
    """The admin-only background check interval of the style (ADR-235 (1))."""
    return key(style, SPEED)


USER_KEYS: Final = tuple(KEYS[s][f] for s in STYLES for f in USER_FIELDS)
CAP_KEYS: Final = frozenset(KEYS[s][CAP] for s in STYLES)


def _style(style: object) -> Style:
    for s in STYLES:
        if style == s:
            return s
    raise StyleRefused(f"not a trading style: {style!r}")


def _whole(value: Decimal, setting: str) -> int:
    if value != value.to_integral_value():
        raise ValueError(f"setting {setting} must be whole, got {value}")
    return int(value)


def preset_for(style: str, values: Mapping[str, Decimal], admin: Mapping[str, Decimal]) -> Preset:
    """The gate preset of ``style`` from the user's values in force and the admin settings in force."""
    s = _style(style)
    user_cap = _whole(value_of(values, key(s, CAP)), key(s, CAP))
    admin_cap = _whole(value_of(admin, key(s, CAP)), key(s, CAP))
    return Preset(
        candle=timedelta(minutes=_whole(value_of(values, key(s, CANDLE)), key(s, CANDLE))),
        cooldown=timedelta(minutes=_whole(value_of(values, key(s, COOLDOWN)), key(s, COOLDOWN))),
        rearm_fraction=value_of(admin, key(s, REARM)).scaleb(-2),  # exact percent -> fraction
        daily_cap=min(user_cap, admin_cap),
        quiet_until=time_of(value_of(values, key(s, QUIET))),
    )


def style_for(expiry_kind: str | None, days_to_expiry: int | None, pin: str | None) -> Style:
    """The strategy's trading style: the user's pin wins (None = automatic); else 0-1 day to expiry is intraday; else
    the expiry kind (``expiry_kind_of``). An unknown kind, or days absent or past, is a StyleRefused."""
    if pin is not None:
        return _style(pin)
    if not isinstance(days_to_expiry, int) or isinstance(days_to_expiry, bool) or days_to_expiry < 0:
        raise StyleRefused(f"days to expiry unknown: {days_to_expiry!r}")
    if expiry_kind not in EXPIRY_KINDS:
        raise StyleRefused(f"expiry kind unknown: {expiry_kind!r}")
    if days_to_expiry <= INTRADAY_LAST_DAY:
        return "intraday"
    return _style(expiry_kind)
