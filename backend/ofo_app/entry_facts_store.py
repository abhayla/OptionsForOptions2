"""Each strategy's entry facts (ADR-243 roll basis "Entry distance from spot"): written ONCE at the strategy's first
fill, never rewritten (migration 0039: insert-only guard, one row per strategy). Migration 0046 adds the entry ATM IV
(ADR-270 (1)); NULL = not known at entry (every row stored before 0046).

- record_first: inside ``paper_store.place`` under the strategy's row lock, only when the book was empty before the
  call (the first fill). ``ON CONFLICT DO NOTHING``: a row already there is kept as it is (never rewritten).
- read: answer states - a row -> its ``EntryFacts`` (``entry_atm_iv`` None when stored NULL); no row (a strategy
  filled before 0039, or no spot at its first fill) -> None; a read that fails or a row that is not exact Decimals
  -> ``EntryFactsUnreadable`` (the caller fails closed with a named reason, never a default).
Known bypass (out of the threat model): live (Zerodha) fills are not written here; the Compare reads paper books only.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from ofo.adjustment.approaches import EntryFacts
from sqlalchemy import text

_INSERT = text(
    "INSERT INTO public.strategy_entry_facts (strategy_id, entry_spot, call_distance, put_distance, entry_atm_iv) "
    "VALUES (:strategy_id, :entry_spot, :call_distance, :put_distance, :entry_atm_iv) "
    "ON CONFLICT (strategy_id) DO NOTHING")
_SELECT = text("SELECT entry_spot, call_distance, put_distance, entry_atm_iv, created_at "
               "FROM public.strategy_entry_facts WHERE strategy_id = :id")


class EntryFactsUnreadable(Exception):
    """The stored entry facts could not be read (fail closed)."""


async def record_first(conn: Any, strategy_id: int, facts: EntryFacts) -> None:
    """Writes ``facts`` for ``strategy_id`` unless a row exists (never rewritten). The caller holds the strategy's row
    lock and commits."""
    await conn.execute(_INSERT, {"strategy_id": strategy_id, "entry_spot": facts.entry_spot,
                                 "call_distance": facts.call_distance, "put_distance": facts.put_distance,
                                 "entry_atm_iv": usable_iv(facts.entry_atm_iv)})


def usable_iv(iv: object) -> Decimal | None:
    """The entry IV to store: a finite Decimal above 0, else None (no IV; the facts are still kept, since they are
    written once). Tier A review: the column's ``> 0`` CHECK lets NaN and Infinity through in PostgreSQL."""
    return iv if isinstance(iv, Decimal) and iv.is_finite() and iv > 0 else None


async def read(conn: Any, strategy_id: int) -> EntryFacts | None:
    """The stored facts, None when none are stored; ``EntryFactsUnreadable`` when they cannot be read."""
    try:
        row = (await conn.execute(_SELECT, {"id": strategy_id})).first()
    except Exception as exc:  # noqa: BLE001 - any read failure is "unreadable", named by the caller
        raise EntryFactsUnreadable(f"strategy {strategy_id}: {type(exc).__name__}") from None
    if row is None:
        return None
    values = (row.entry_spot, row.call_distance, row.put_distance, row.entry_atm_iv)
    exact = all(v is None or (isinstance(v, Decimal) and v.is_finite()) for v in values)
    if not isinstance(row.entry_spot, Decimal) or not exact:
        raise EntryFactsUnreadable(f"strategy {strategy_id}: a stored entry fact is not an exact Decimal")
    return EntryFacts(row.entry_spot, row.call_distance, row.put_distance, row.entry_atm_iv, at=row.created_at)
