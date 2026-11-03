"""A-37: a user's watched index level per strategy and direction (GC-IC1 step 4c, ADR-242). Table: 0038.

Spec basis: ADR-242 (one active watch per strategy per direction, set / cleared by its owner, evaluated as a yes/no
rule through the alert gate); REQ-170 AC-5 (the paper exit path never imports this module); REQ-168 AC-3 "every
read and write is keyed by the user". Copy from: ``strategy_pause_store`` (same key, same append-only rows, same
ownership check).

Answer states of ``watches_of``: the newest row of each direction holds a level -> that watch; the newest row is a
clear, or no row -> no watch of that direction; a strategy that is not this user's, deleted or missing ->
WatchNotFound (never another user's watch). Writes take effect at the database clock now; a clear is a new row with
level NULL, never a delete. Transaction control stays with the caller.
"""
from __future__ import annotations

from decimal import Decimal

from ofo.adjustment import level_watch
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ofo_app import settings_store

Session = AsyncSession | AsyncConnection

_OWNED = text("SELECT 1 FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL")
_LATEST = text(
    "SELECT DISTINCT ON (direction) direction, level FROM public.strategy_level_watch "
    "WHERE user_ref = :u AND strategy_id = :s ORDER BY direction, effective_from DESC"
)
_INSERT = text(
    "INSERT INTO public.strategy_level_watch (user_ref, strategy_id, direction, level, effective_from) "
    "VALUES (:u, :s, :d, :level, :at)"
)


class WatchError(Exception):
    """The watch cannot be read or written (fail closed)."""


class WatchNotFound(WatchError):
    """Not this user's strategy (or deleted, or missing)."""


class WatchSameTime(WatchError):
    """Another change of this watch took effect at the same instant."""


def _user(user_ref: object) -> str:
    if not isinstance(user_ref, str) or not user_ref.strip():
        raise WatchError("a level watch read or write needs the user it belongs to")
    return user_ref


async def _owned(session: Session, user: str, strategy_id: int) -> None:
    if (await session.execute(_OWNED, {"s": strategy_id, "u": user})).first() is None:
        raise WatchNotFound(f"strategy {strategy_id} is not this user's")


async def watches_of(session: Session, user_ref: str, strategy_id: int) -> tuple[level_watch.LevelWatch, ...]:
    """The active watches of ``user_ref`` on ``strategy_id``, "above" first; () when none."""
    user = _user(user_ref)
    await _owned(session, user, strategy_id)
    rows = (await session.execute(_LATEST, {"u": user, "s": strategy_id})).all()
    found = {r.direction: r.level for r in rows if r.level is not None}
    return tuple(level_watch.LevelWatch(d, Decimal(found[d])) for d in level_watch.DIRECTIONS if d in found)


async def _write(session: Session, user: str, strategy_id: int, direction: str, level: Decimal | None) -> None:
    now = await settings_store.database_now(session)
    async with session.begin_nested():
        try:
            await session.execute(_INSERT, {"u": user, "s": strategy_id, "d": direction, "level": level, "at": now})
        except IntegrityError:
            raise WatchSameTime("another change of this watch took effect at the same instant") from None


async def set_watch(session: Session, user_ref: str, strategy_id: int, direction: object,
                    level: object) -> level_watch.LevelWatch:
    """Watch ``direction`` at ``level`` (``level_watch.parse_*``: WatchRefused when not a direction / a number)."""
    user = _user(user_ref)
    await _owned(session, user, strategy_id)
    watch = level_watch.LevelWatch(level_watch.parse_direction(direction), level_watch.parse_level(level))
    await _write(session, user, strategy_id, watch.direction, watch.level)
    return watch


async def clear_watch(session: Session, user_ref: str, strategy_id: int, direction: object) -> None:
    """End the watch of ``direction`` now (a new row with no level)."""
    user = _user(user_ref)
    await _owned(session, user, strategy_id)
    await _write(session, user, strategy_id, level_watch.parse_direction(direction), None)
