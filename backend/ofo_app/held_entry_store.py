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


#: ADR-292 (3): the rules of a held entry start from the market at the user's SAVE = the basket-0 fill clock (ADR-283);
#: no facts row -> NULL (never a guess)
_READ = text("SELECT h.strategy_id, h.entry_at, h.broker_text, f.clock AS rules_start_at "
             "FROM public.strategy_held_entries h LEFT JOIN public.strategy_basket_facts f "
             "ON f.strategy_id = h.strategy_id AND f.basket_no = 0 WHERE h.strategy_id = ANY(:ids)")


async def read_many(conn: Any, strategy_ids: list[int]) -> dict[int, Any]:
    """strategy_id -> row (entry_at, broker_text, rules_start_at) of each held strategy among ``strategy_ids``; a
    strategy that is not held is absent. A read failure raises: the reply fails, a held strategy is never hidden."""
    if not strategy_ids:
        return {}
    return {int(r.strategy_id): r for r in await conn.execute(_READ, {"ids": list(strategy_ids)})}
