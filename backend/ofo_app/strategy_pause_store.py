"""A-38: a user's pause of adjustment monitoring per strategy, until a chosen time (GC-IC1 step 4a). Table: 0037.

Spec basis: REQ-170 AC-5 (a pause covers adjustment suggestions only; the paper exit path never imports this module,
``tests_app/test_risk_exit_not_gated.py``); REQ-168 AC-3 "every read and write is keyed by the user".
Copy from: ``strategy_alert_style_store`` (same key, same append-only rows, same ownership check).

Answer states of ``pause_of``: the newest row holds an end -> that end (whether it is still in force is the caller's
compare with ITS check time, ``monitor_pause.in_force``); the newest row is a clear, or no row -> None; a strategy
that is not this user's, deleted or missing -> PauseNotFound (never another user's pause). Writes take effect at the
database clock now; a clear is a new row with paused_until NULL, never a delete. Transaction control stays with the
caller.
"""
from __future__ import annotations

import datetime

from ofo.adjustment import monitor_pause
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ofo_app import settings_store

Session = AsyncSession | AsyncConnection

_OWNED = text("SELECT 1 FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL")
_LATEST = text(
    "SELECT paused_until FROM public.strategy_monitor_pause WHERE user_ref = :u AND strategy_id = :s "
    "ORDER BY effective_from DESC LIMIT 1"
)
_INSERT = text(
    "INSERT INTO public.strategy_monitor_pause (user_ref, strategy_id, paused_until, effective_from) "
    "VALUES (:u, :s, :until, :at)"
)


class PauseError(Exception):
    """The pause cannot be read or written (fail closed)."""


class PauseNotFound(PauseError):
    """Not this user's strategy (or deleted, or missing)."""


class PauseSameTime(PauseError):
    """Another change of this pause took effect at the same instant."""


def _user(user_ref: object) -> str:
    if not isinstance(user_ref, str) or not user_ref.strip():
        raise PauseError("a monitoring pause read or write needs the user it belongs to")
    return user_ref


async def _owned(session: Session, user: str, strategy_id: int) -> None:
    if (await session.execute(_OWNED, {"s": strategy_id, "u": user})).first() is None:
        raise PauseNotFound(f"strategy {strategy_id} is not this user's")


async def pause_of(session: Session, user_ref: str, strategy_id: int) -> datetime.datetime | None:
    """The end of the newest pause of ``user_ref`` on ``strategy_id`` (None: never paused, or cleared)."""
    user = _user(user_ref)
    await _owned(session, user, strategy_id)
    row = (await session.execute(_LATEST, {"u": user, "s": strategy_id})).first()
    return None if row is None else row.paused_until


async def _write(session: Session, user: str, strategy_id: int, until: datetime.datetime | None,
                 now: datetime.datetime) -> None:
    async with session.begin_nested():
        try:
            await session.execute(_INSERT, {"u": user, "s": strategy_id, "until": until, "at": now})
        except IntegrityError:
            raise PauseSameTime("another change of this pause took effect at the same instant") from None


async def set_pause(session: Session, user_ref: str, strategy_id: int, until: datetime.datetime,
                    now: datetime.datetime | None = None) -> datetime.datetime:
    """Pause until ``until`` (today, after now, by the close: ``monitor_pause.check_until``, PauseRefused otherwise).
    ``now`` defaults to the database clock; the row takes effect at the database clock."""
    user = _user(user_ref)
    await _owned(session, user, strategy_id)
    db_now = await settings_store.database_now(session)
    end = monitor_pause.check_until(until, db_now if now is None else now)
    await _write(session, user, strategy_id, end, db_now)
    return end


async def clear_pause(session: Session, user_ref: str, strategy_id: int) -> None:
    """End the pause now (a new row with no end)."""
    user = _user(user_ref)
    await _owned(session, user, strategy_id)
    await _write(session, user, strategy_id, None, await settings_store.database_now(session))
