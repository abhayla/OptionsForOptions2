"""Append to the ledger. The caller supplies the event's own date; the database stamps recorded_at.

Spec basis: ADR-023 Q225 clarification ("recorded at" is stamped by the ledger from its own clock; a caller can never
supply it) and Q256 (an event dated outside the stamp +/- 60 s is refused by the database, SQLSTATE OF001).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app.models import LedgerEntry


async def append(session: AsyncSession, kind: str, event_at: datetime, payload: dict[str, Any]) -> tuple[int, datetime]:
    """Insert one ledger row and return (id, recorded_at) as stamped by the database.

    recorded_at is never sent. Transaction control stays with the caller.
    """
    if event_at.tzinfo is None or event_at.utcoffset() is None:
        raise ValueError("event_at must be timezone-aware")
    stmt = (
        insert(LedgerEntry)
        .values(kind=kind, event_at=event_at, payload=payload)
        .returning(LedgerEntry.id, LedgerEntry.recorded_at)
    )
    row = (await session.execute(stmt)).one()
    return int(row.id), row.recorded_at
