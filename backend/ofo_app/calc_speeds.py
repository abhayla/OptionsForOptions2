"""REQ-166 AC-1, AC-3 (ADR-220 (3)): the four calculation speeds and the safety valve.

Speeds (``read_speeds``, called on EVERY cycle so a changed setting takes effect with no restart):
(a) per-option figures at most once per ``speeds.per_option_seconds`` per option (default 1 s);
(b) a strategy open on a screen at most once per ``speeds.open_strategy_seconds`` (GC-SET's key, only read here);
(c) background checks of a strategy with no screen open at most once per ``speeds.background_check_seconds`` (1 s);
(d) a saved draft no screen has open: only when opened (a behaviour, not a key: ``draft_on_open`` is always True).

Safety valve (``Valve``): when the maths step's backlog or reply time crosses its limit, the open-screen and
background speeds step to the next of ``speeds.valve_step_seconds.1`` / ``.2`` / ``.3`` (1 / 2 / 5 s); once the maths
step has stayed under both limits for ``VALVE_CALM_SECONDS`` the speed returns to the first step (1 s). Every step is
logged with its reason. Seconds are exact ``Decimal`` (no float anywhere in a speed).

Answer states of the reader: a key the store holds -> its value; a key missing or not a positive whole/decimal number
-> ``SpeedSettingRefused`` (fail closed: the worker does not guess a speed).
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

log = logging.getLogger("ofo_app.calc_speeds")

KEY_PER_OPTION: Final = "speeds.per_option_seconds"
KEY_OPEN_SCREEN: Final = "speeds.open_strategy_seconds"  # GC-SET's key; read only, never redefined here
KEY_BACKGROUND: Final = "speeds.background_check_seconds"
VALVE_STEP_KEYS: Final = ("speeds.valve_step_seconds.1", "speeds.valve_step_seconds.2", "speeds.valve_step_seconds.3")

# MERGE-SWAP(GC-SET): read from the settings store (Speeds group, keys sent by GC-SET)
_STAND_IN: dict[str, Decimal] = {KEY_PER_OPTION: Decimal(1), KEY_OPEN_SCREEN: Decimal(1), KEY_BACKGROUND: Decimal(1),
                                 VALVE_STEP_KEYS[0]: Decimal(1), VALVE_STEP_KEYS[1]: Decimal(2),
                                 VALVE_STEP_KEYS[2]: Decimal(5)}

# MERGE-SWAP(GC-SET): read from the settings store (Speeds group, keys sent by GC-SET)
VALVE_REPLY_LIMIT_SECONDS: Final = Decimal("0.5")  # one maths step slower than this = maths is behind
VALVE_BACKLOG_LIMIT: Final = 50  # strategies due but rolled to the next cycle
VALVE_CALM_SECONDS: Final = 30  # under both limits this long -> back to the first step


class SpeedSettingRefused(ValueError):
    """A speed setting is missing or not a positive number (fail closed)."""


def setting_seconds(key: str) -> Decimal:
    """One speed setting in seconds, read now."""
    # MERGE-SWAP(GC-SET): read from the settings store (Speeds group, keys sent by GC-SET)
    raw = _STAND_IN.get(key)
    try:
        value = Decimal(raw) if isinstance(raw, (Decimal, int, str)) and not isinstance(raw, bool) else None
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite() or value <= 0:
        raise SpeedSettingRefused(f"speed setting {key} is missing or not a positive number: {raw!r}")
    return value


@dataclass(frozen=True)
class Speeds:
    per_option: Decimal
    open_screen: Decimal
    background: Decimal
    draft_on_open: bool = True  # (d): a saved draft is computed only when opened, never in the background


def read_speeds() -> Speeds:
    """THE one reader of the four speeds; called on every cycle (REQ-166 AC-1: no restart for a change)."""
    return Speeds(setting_seconds(KEY_PER_OPTION), setting_seconds(KEY_OPEN_SCREEN), setting_seconds(KEY_BACKGROUND))


def valve_steps() -> tuple[Decimal, ...]:
    return tuple(setting_seconds(k) for k in VALVE_STEP_KEYS)


class Valve:
    """The safety valve's state: the current step (0 = the first) and since when maths has been under the limits."""

    def __init__(self) -> None:
        self.step = 0
        self._calm_since: datetime.datetime | None = None
        self.log: list[tuple[datetime.datetime, int, str]] = []  # (when, new step, reason): every step, for tests

    def _move(self, now: datetime.datetime, step: int, reason: str) -> None:
        self.step = step
        self.log.append((now, step, reason))
        log.warning("speed valve: step %s (%s s): %s", step + 1, valve_steps()[step], reason)

    def observe(self, now: datetime.datetime, reply_seconds: Decimal, backlog: int) -> None:
        """One cycle's maths load: the slowest reply time and the backlog left for the next cycle."""
        over = []
        if reply_seconds > VALVE_REPLY_LIMIT_SECONDS:
            over.append(f"maths reply {reply_seconds} s over the {VALVE_REPLY_LIMIT_SECONDS} s limit")
        if backlog > VALVE_BACKLOG_LIMIT:
            over.append(f"maths backlog {backlog} over the {VALVE_BACKLOG_LIMIT} limit")
        if over:
            self._calm_since = None
            if self.step < len(VALVE_STEP_KEYS) - 1:
                self._move(now, self.step + 1, "; ".join(over))
            return
        if self._calm_since is None:
            self._calm_since = now
        elif self.step > 0 and now - self._calm_since >= datetime.timedelta(seconds=VALVE_CALM_SECONDS):
            self._move(now, 0, f"maths under its limits for {VALVE_CALM_SECONDS} s")
            self._calm_since = now

    def slowed(self, seconds: Decimal) -> Decimal:
        """A screen or background speed with the valve applied: never faster than the current step."""
        return max(seconds, valve_steps()[self.step])
