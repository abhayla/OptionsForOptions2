"""ADR-330 (7): the plan's time exit, any trading day. Pure: today and the IST clock are passed in, never read."""
from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Final

ON_EXPIRY: Final = "expiry"  # the stored `on` for "blank date = expiry day" (Q9)


def is_hhmm(text: str) -> bool:
    return len(text) == 5 and text[2] == ":" and text[:2].isdigit() and text[3:].isdigit()  # noqa: PLR2004


def day_of(text: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def time_exit_parts(raw: object) -> tuple[str, str] | None:
    """(at "HH:MM", on "expiry" | "YYYY-MM-DD") of a stored guard; a plain "HH:MM" reads as on expiry (no data
    migration). Anything else (absent, empty, unreadable) -> None: no time exit, never a guess."""
    if isinstance(raw, str):
        return (raw, ON_EXPIRY) if is_hhmm(raw) else None
    if isinstance(raw, Mapping):
        at, on = raw.get("at"), raw.get("on") or ON_EXPIRY
        if isinstance(at, str) and is_hhmm(at) and isinstance(on, str) and (on == ON_EXPIRY or day_of(on) is not None):
            return at, on
    return None


def time_exit_due(today: datetime.date | None, now_hhmm: str | None, on: datetime.date | None, at: str) -> bool:
    """Met on the chosen day at or after ``at``, and for the rest of that day; before it, or on any other day (the
    day passed), not met. ``on`` is the resolved day (the legs' expiry for "expiry"); an unknown day or clock is
    never met."""
    return today is not None and now_hhmm is not None and on is not None and today == on and now_hhmm >= at


def resolve_on(on: str, expiry: datetime.date | None) -> datetime.date | None:
    """The day a stored ``on`` means: "expiry" -> the legs' nearest expiry (None when not known)."""
    return expiry if on == ON_EXPIRY else day_of(on)
