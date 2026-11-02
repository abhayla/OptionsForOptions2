"""A user's alert-style pin per strategy: read the pin in force, pin a style, return to automatic (REQ-170 Q-AD-2).
Table: migration 0035.

Spec basis: REQ-170 Q-AD-2 "the style is taken from the strategy and changes by itself as expiry nears ... the user
may pin a style per strategy"; REQ-168 AC-3 "every read and write is keyed by the user".

Answer states of ``pin_of`` (each has a test in tests_app/test_strategy_alert_style.py):
- the newest row holds a style: that style ("pinned");
- the newest row is NULL, or there is no row: None (automatic: ``alert_presets.style_for`` decides from the expiry);
- a strategy that is not this user's, deleted, or missing: StyleNotFound (never another user's pin, never a default);
- a stored style that is not one of the styles (a retired style): AlertStyleError, fail closed.

Every query is keyed by ``user_ref``; writes take effect at the database clock now; a return to automatic is a new
row with style NULL, never a delete. Transaction control stays with the caller.

Known bypasses (out of the threat model): a database superuser or the table owner can disable or drop the guard.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from ofo.adjustment import alert_presets
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ofo_app import settings_store

Session = AsyncSession | AsyncConnection

_OWNED = text("SELECT 1 FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL")
_LATEST = text(
    "SELECT style, effective_from FROM public.strategy_alert_style WHERE user_ref = :u AND strategy_id = :s "
    "AND effective_from <= :at ORDER BY effective_from DESC LIMIT 1"
)
_INSERT = text(
    "INSERT INTO public.strategy_alert_style (user_ref, strategy_id, style, effective_from) "
    "VALUES (:u, :s, :style, :at)"
)


class AlertStyleError(Exception):
    """The stored pin cannot answer (fail closed)."""


class StyleNotFound(AlertStyleError):
    """Not this user's strategy (or deleted, or missing)."""


class StyleSameTime(AlertStyleError):
    """Another change of this pin took effect at the same instant."""


@dataclass(frozen=True)
class StoredPin:
    style: alert_presets.Style | None  # None = automatic
    effective_from: datetime.datetime | None  # None: never pinned


def _user(user_ref: object) -> str:
    if not isinstance(user_ref, str) or not user_ref.strip():
        raise AlertStyleError("an alert-style read or write needs the user it belongs to")
    return user_ref


def _checked(style: object) -> alert_presets.Style | None:
    if style is None:
        return None
    try:
        return alert_presets.style_for(None, None, style)  # the pin branch: the one style check
    except alert_presets.StyleRefused:
        raise AlertStyleError(f"not a trading style: {style!r}") from None


async def _owned(session: Session, user: str, strategy_id: int) -> None:
    if (await session.execute(_OWNED, {"s": strategy_id, "u": user})).first() is None:
        raise StyleNotFound(f"strategy {strategy_id} is not this user's")


async def require_owned(session: Session, user_ref: str, strategy_id: int) -> None:
    """StyleNotFound unless the strategy is this user's: the check a caller makes BEFORE it writes."""
    await _owned(session, _user(user_ref), strategy_id)


def require_style(style: object) -> None:
    """AlertStyleError unless ``style`` is None or one of the styles: the check a caller makes BEFORE it writes."""
    _checked(style)


async def pin_of(session: Session, user_ref: str, strategy_id: int, at: datetime.datetime | None = None) -> StoredPin:
    """The pin of ``user_ref`` on ``strategy_id`` in force at ``at`` (default: the database clock)."""
    user = _user(user_ref)
    await _owned(session, user, strategy_id)
    if at is None:
        at = await settings_store.database_now(session)
    row = (await session.execute(_LATEST, {"u": user, "s": strategy_id, "at": at})).first()
    if row is None:
        return StoredPin(None, None)
    return StoredPin(_checked(row.style), row.effective_from)


async def set_pin(session: Session, user_ref: str, strategy_id: int, style: object) -> StoredPin:
    """From now: ``style`` pinned (one of the styles) or automatic (None). A bad style is AlertStyleError."""
    user = _user(user_ref)
    checked = _checked(style)
    await _owned(session, user, strategy_id)
    now = await settings_store.database_now(session)
    async with session.begin_nested():
        try:
            await session.execute(_INSERT, {"u": user, "s": strategy_id, "style": checked, "at": now})
        except IntegrityError:
            raise StyleSameTime("another change of this pin took effect at the same instant") from None
    return StoredPin(checked, now)
