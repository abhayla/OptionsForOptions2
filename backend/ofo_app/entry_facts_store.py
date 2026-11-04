"""Each strategy's entry facts (ADR-243 roll basis "Entry distance from spot"): written ONCE at the strategy's first
fill, never rewritten (migration 0039: insert-only guard, one row per strategy).

- record_first: inside ``paper_store.place`` under the strategy's row lock, only when the book was empty before the
  call (the first fill). ``ON CONFLICT DO NOTHING``: a row already there is kept as it is (never rewritten).
- read: answer states - a row -> its ``EntryFacts``; no row (a strategy filled before 0039, or no spot at its first
  fill) -> None; a read that fails or a row that is not exact Decimals -> ``EntryFactsUnreadable`` (the caller fails
  closed with a named reason, never a default).
Known bypass (out of the threat model): live (Zerodha) fills are not written here; the Compare reads paper books only.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from ofo.adjustment.approaches import EntryFacts
from sqlalchemy import text

_INSERT = text(
    "INSERT INTO public.strategy_entry_facts (strategy_id, entry_spot, call_distance, put_distance) "
    "VALUES (:strategy_id, :entry_spot, :call_distance, :put_distance) ON CONFLICT (strategy_id) DO NOTHING")
_SELECT = text("SELECT entry_spot, call_distance, put_distance FROM public.strategy_entry_facts "
               "WHERE strategy_id = :id")


class EntryFactsUnreadable(Exception):
    """The stored entry facts could not be read (fail closed)."""


async def record_first(conn: Any, strategy_id: int, facts: EntryFacts) -> None:
    """Writes ``facts`` for ``strategy_id`` unless a row exists (never rewritten). The caller holds the strategy's row
    lock and commits."""
    await conn.execute(_INSERT, {"strategy_id": strategy_id, "entry_spot": facts.entry_spot,
                                 "call_distance": facts.call_distance, "put_distance": facts.put_distance})


async def read(conn: Any, strategy_id: int) -> EntryFacts | None:
    """The stored facts, None when none are stored; ``EntryFactsUnreadable`` when they cannot be read."""
    try:
        row = (await conn.execute(_SELECT, {"id": strategy_id})).first()
    except Exception as exc:  # noqa: BLE001 - any read failure is "unreadable", named by the caller
        raise EntryFactsUnreadable(f"strategy {strategy_id}: {type(exc).__name__}") from None
    if row is None:
        return None
    values = (row.entry_spot, row.call_distance, row.put_distance)
    if not isinstance(row.entry_spot, Decimal) or any(v is not None and not isinstance(v, Decimal) for v in values):
        raise EntryFactsUnreadable(f"strategy {strategy_id}: a stored entry fact is not an exact Decimal")
    return EntryFacts(row.entry_spot, row.call_distance, row.put_distance)
