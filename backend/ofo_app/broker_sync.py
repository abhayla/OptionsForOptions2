"""The moment of the last successful read from Zerodha, kept in this process (W-089, REQ-015 AC-4).

``KiteReads`` calls ``note_read`` after a reply that parsed as a success. Memory only, one worker (ADR-051): a restart
forgets it, and the Settings page then says no read is recorded yet rather than inventing a time. It holds a time and
nothing else: no token, no reply, no account figure.
"""
from __future__ import annotations

import datetime

_last: datetime.datetime | None = None


def note_read(now: datetime.datetime | None = None) -> None:
    global _last  # noqa: PLW0603
    _last = now if now is not None else datetime.datetime.now(datetime.UTC)


def last_read() -> datetime.datetime | None:
    return _last


def forget() -> None:
    """A disconnect forgets the last read: the next session starts with no sync recorded."""
    global _last  # noqa: PLW0603
    _last = None
