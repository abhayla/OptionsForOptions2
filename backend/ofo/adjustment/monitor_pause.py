"""A-38: the user pauses ADJUSTMENT monitoring of one strategy until a chosen time today (GC-IC1 step 4a).

Spec basis: REQ-170 AC-5 "Risk exits are not delayed: a stop-loss or conditional exit (REQ-041 / paper triggers) acts
on the live price at once; this requirement applies only to adjustment suggestions" -> a pause skips the strategy's
adjustment checks only; nothing on the paper exit path reads it (``tests_app/test_risk_exit_not_gated.py`` walks it).
Technical calls (orchestrator, brief GC-IC1 4a): the pause always carries an end time; it ends by itself at that time
(the caller compares with ITS OWN check time, never the wall clock); the end is today, after now, at or before the
session close (``ofo.timeutil.SESSION_CLOSE``).

Pure; the caller passes ``now``. Answer states of ``in_force``: no pause / cleared (None) -> False; a pause whose end
is after ``now`` -> True; a pause whose end is at or before ``now`` (expired) -> False.
Answer states of ``check_until``: accepted; a naive time -> ``NO_ZONE``; at or before now -> ``IN_PAST``; another day
-> ``NOT_TODAY``; after the session close -> ``AFTER_CLOSE``.
"""
from __future__ import annotations

import datetime
import enum

from ofo.timeutil import IST, SESSION_CLOSE


class Refusal(enum.Enum):
    NO_ZONE = "no_zone"
    IN_PAST = "in_past"
    NOT_TODAY = "not_today"
    AFTER_CLOSE = "after_close"


class PauseRefused(ValueError):
    """The chosen end time cannot be a pause end; ``reason`` says why."""

    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


def check_until(until: datetime.datetime, now: datetime.datetime) -> datetime.datetime:
    """The accepted end (IST), or PauseRefused naming the reason."""
    if until.tzinfo is None or now.tzinfo is None:
        raise PauseRefused(Refusal.NO_ZONE)
    end, at = until.astimezone(IST), now.astimezone(IST)
    if end <= at:
        raise PauseRefused(Refusal.IN_PAST)
    if end.date() != at.date():
        raise PauseRefused(Refusal.NOT_TODAY)
    if end.timetz().replace(tzinfo=None) > SESSION_CLOSE:
        raise PauseRefused(Refusal.AFTER_CLOSE)
    return end


def in_force(until: datetime.datetime | None, now: datetime.datetime) -> bool:
    """True while a pause ending at ``until`` holds at ``now`` (the check's own time)."""
    return until is not None and now < until
