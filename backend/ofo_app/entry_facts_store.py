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

import datetime
import json
import logging
from dataclasses import dataclass
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


log = logging.getLogger(__name__)

#: ADR-283 (1), migration 0050: the market state at every basket's fill (basket_no 0 = the entry)
_INSERT_BASKET = text(
    "INSERT INTO public.strategy_basket_facts (strategy_id, basket_no, clock, spot, atm_iv, legs) "
    "VALUES (:strategy_id, :basket_no, :clock, :spot, :atm_iv, CAST(:legs AS JSONB)) "
    "ON CONFLICT (strategy_id, basket_no) DO NOTHING")
_SELECT_BASKETS = text("SELECT basket_no, clock, spot, atm_iv, legs FROM public.strategy_basket_facts "
                       "WHERE strategy_id = :id")

LegKey = tuple[str, Decimal, datetime.date, str]  # (type, strike, expiry, side)


@dataclass(frozen=True)
class BasketFacts:
    """A strategy's market state at a basket's fill (ADR-283 (1)): the order clock (the scenario clock in test-data
    mode), the spot, the ATM IV (None = not read) and every open leg's price then, keyed (type, strike, expiry,
    side); a price None = not read at the fill (the rules on that leg are not held)."""

    clock: datetime.datetime
    spot: Decimal
    atm_iv: Decimal | None
    prices: dict[LegKey, Decimal | None]


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


async def record_basket(conn: Any, strategy_id: int, basket_no: int, facts: BasketFacts) -> None:
    """Writes the basket's facts in the caller's transaction (a savepoint: a failed write, e.g. before migration 0050,
    is logged and never fails the fill); a row already stored for this basket number is kept (never rewritten)."""
    legs = [{"type": t, "strike": str(k), "expiry": e.isoformat(), "side": sd, "price": None if p is None else str(p)}
            for (t, k, e, sd), p in facts.prices.items()]
    try:
        async with conn.begin_nested():
            await conn.execute(_INSERT_BASKET, {"strategy_id": strategy_id, "basket_no": basket_no,
                                                "clock": facts.clock, "spot": facts.spot,
                                                "atm_iv": usable_iv(facts.atm_iv), "legs": json.dumps(legs)})
    except Exception as exc:  # noqa: BLE001 - no stored facts = nothing held (warns), never a refused fill
        log.warning("basket facts not stored (strategy %s, basket %s): %s", strategy_id, basket_no,
                    type(exc).__name__)


def _basket(row: Any) -> BasketFacts:
    legs = row.legs if isinstance(row.legs, list) else json.loads(row.legs)
    prices = {(x["type"], Decimal(x["strike"]), datetime.date.fromisoformat(x["expiry"]), x["side"]):
              None if x["price"] is None else Decimal(x["price"]) for x in legs}
    if not isinstance(row.spot, Decimal) or not isinstance(row.clock, datetime.datetime):
        raise TypeError("spot or clock")
    return BasketFacts(row.clock, row.spot, row.atm_iv if isinstance(row.atm_iv, Decimal) else None, prices)


async def read_baskets(conn: Any, strategy_id: int) -> dict[int, BasketFacts]:
    """Basket number -> its stored facts ({} = none stored); ``EntryFactsUnreadable`` when they cannot be read."""
    try:
        rows = (await conn.execute(_SELECT_BASKETS, {"id": strategy_id})).all()
        return {int(r.basket_no): _basket(r) for r in rows}
    except Exception as exc:  # noqa: BLE001 - a failed read or a malformed row is "unreadable", named
        raise EntryFactsUnreadable(f"strategy {strategy_id} basket facts: {type(exc).__name__}") from None


async def read_basket(conn: Any, strategy_id: int, marker: int) -> BasketFacts | None:
    """The stored facts of basket ``marker`` (the rule starting point, ADR-283); None when none are stored or they
    cannot be read (logged: read as absent, so no rule is held)."""
    try:
        return (await read_baskets(conn, strategy_id)).get(marker)
    except EntryFactsUnreadable as exc:
        log.warning("%s: no rule held", exc)
        return None
