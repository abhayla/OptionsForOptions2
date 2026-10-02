"""Append to the ledger. The caller supplies the event's own date; the database stamps recorded_at.

Spec basis: ADR-023 Q225 clarification ("recorded at" is stamped by the ledger from its own clock; a caller can never
supply it) and Q256 (an event dated outside the stamp +/- 60 s is refused by the database, SQLSTATE OF001).
Money is never float (ADR-008): a payload carrying a float anywhere is refused; pass Decimal amounts as strings
(e.g. "12.50") or the audit log's {"$decimal": "..."} tagged form.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app.models import LedgerEntry


def _reject_floats(value: Any, path: str = "payload") -> None:
    if isinstance(value, float):
        raise TypeError(f"{path} is a float; money is never float (ADR-008) - pass a string or {{'$decimal': ...}}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}[{key!r}]")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


async def append(session: AsyncSession, kind: str, event_at: datetime, payload: dict[str, Any]) -> tuple[int, datetime]:
    """Insert one ledger row and return (id, recorded_at) as stamped by the database.

    recorded_at and id are never sent. Transaction control stays with the caller.
    """
    if event_at.tzinfo is None or event_at.utcoffset() is None:
        raise ValueError("event_at must be timezone-aware")
    _reject_floats(payload)
    stmt = (
        insert(LedgerEntry)
        .values(kind=kind, event_at=event_at, payload=payload)
        .returning(LedgerEntry.id, LedgerEntry.recorded_at)
    )
    row = (await session.execute(stmt)).one()
    return int(row.id), row.recorded_at
