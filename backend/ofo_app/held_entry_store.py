"""A strategy entered "held at my broker" (ADR-292 (1)(2), migration 0052): the user's stated entry time and the
broker's name (optional free text, shown and never used), one insert-only row per strategy.

- record: written in the SAME transaction as the strategy's first paper basket; the caller commits or rolls back. A
  second row for the same strategy raises (primary key): the held block is accepted on the first basket only.
"""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import text

_INSERT = text("INSERT INTO public.strategy_held_entries (strategy_id, entry_at, broker_text) "
               "VALUES (:strategy_id, :entry_at, :broker_text)")


async def record(conn: Any, strategy_id: int, entry_at: datetime.datetime, broker_text: str | None) -> None:
    await conn.execute(_INSERT, {"strategy_id": strategy_id, "entry_at": entry_at, "broker_text": broker_text})
