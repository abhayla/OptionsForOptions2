"""PostgreSQL store for paper tracking of a saved strategy (W-122; REQ-109 AC-1). Schema: migration 0021.

- start: under the strategy's row lock (one writer per strategy), re-checks the revision the user started from, then
  inserts the tracking row and one row per leg. A second start of the same strategy is refused (ALREADY_TRACKED): the
  primary key on strategy_id holds even when two starts race. Insert-only; the caller commits.
- load: the tracking of the user's own strategy, or None. Another user's strategy answers NOT_FOUND like a missing one
  (strategy_store.load runs first in the route).
The prices come only from ofo.tracking.paper.capture_entry (the server's live read); this store takes no price from a
request.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.tracking.paper import TrackedLeg
from sqlalchemy import text

from ofo_app import strategy_store as store

ALREADY_TRACKED = "already_tracked"

_INSERT_TRACKING = text(
    "INSERT INTO public.strategy_tracking (strategy_id, strategy_revision, price_health, prices_at) "
    "VALUES (:id, :revision, 'available', :prices_at) ON CONFLICT (strategy_id) DO NOTHING RETURNING started_at")
_INSERT_LEG = text(
    "INSERT INTO public.strategy_tracking_legs (strategy_id, leg_index, contract_id, side, quantity, entry_price, "
    "price_at) VALUES (:id, :leg_index, :contract_id, :side, :quantity, :entry_price, :price_at)")
_SELECT_TRACKING = text("SELECT started_at, prices_at, strategy_revision FROM public.strategy_tracking "
                        "WHERE strategy_id = :id")
_SELECT_TRACKED = text(
    "SELECT strategy_id FROM public.strategy_tracking WHERE strategy_id = ANY(CAST(:ids AS BIGINT[]))")
_SELECT_LEGS = text("SELECT leg_index, contract_id, side, quantity, entry_price, price_at "
                    "FROM public.strategy_tracking_legs WHERE strategy_id = :id ORDER BY leg_index")


@dataclass(frozen=True)
class StoredLeg:
    leg_index: int
    contract_id: int
    side: str
    quantity: int
    entry_price: Decimal
    price_at: datetime.datetime


@dataclass(frozen=True)
class Tracking:
    strategy_id: int
    started_at: datetime.datetime
    prices_at: datetime.datetime
    strategy_revision: int
    legs: tuple[StoredLeg, ...]


async def start(conn: Any, user_ref: str, strategy_id: int, revision: int,  # noqa: PLR0913 - one stored entry
                contract_ids: Sequence[int],
                entry: Sequence[TrackedLeg]) -> Tracking:
    """Stores the paper entry (one row per leg, in the saved leg order). Refuses a changed revision
    (REVISION_CONFLICT), an already tracked strategy (ALREADY_TRACKED) and a leg count that does not match."""
    if not entry or len(contract_ids) != len(entry):
        raise ValueError("one paper entry leg per saved leg")
    prices_at = min(leg.price_at for leg in entry)
    async with conn.begin_nested():
        stored = await store.load(conn, user_ref, strategy_id)  # NOT_FOUND for a missing or another user's strategy
        await store.lock_strategy(conn, user_ref, strategy_id)
        if stored.revision != revision:
            raise store.StrategyStoreError(store.REVISION_CONFLICT, f"strategy {strategy_id} is at revision "
                                                                    f"{stored.revision}, tracking asked for {revision}")
        started = (await conn.execute(_INSERT_TRACKING, {"id": strategy_id, "revision": revision,
                                                         "prices_at": prices_at})).scalar_one_or_none()
        if started is None:
            raise store.StrategyStoreError(ALREADY_TRACKED, f"strategy {strategy_id} is already tracked")
        for i, (contract_id, leg) in enumerate(zip(contract_ids, entry, strict=True)):
            await conn.execute(_INSERT_LEG, {"id": strategy_id, "leg_index": i, "contract_id": contract_id,
                                             "side": leg.action.value, "quantity": leg.quantity,
                                             "entry_price": leg.entry_price, "price_at": leg.price_at})
    found = await load(conn, strategy_id)
    if found is None:
        raise RuntimeError(f"strategy {strategy_id}: the tracking just written cannot be read back")
    return found


async def tracked_ids(conn: Any, strategy_ids: Sequence[int]) -> set[int]:
    """REQ-134 AC-4: which of the given strategies (already filtered to the signed-in user's own) have a tracking row.
    A read failure raises: the caller decides what 'unknown' shows."""
    if not strategy_ids:
        return set()
    rows = await conn.execute(_SELECT_TRACKED, {"ids": list(strategy_ids)})
    return {int(r.strategy_id) for r in rows}


async def load(conn: Any, strategy_id: int) -> Tracking | None:
    """The tracking of a strategy the caller already loaded for its user (ownership is checked there)."""
    row = (await conn.execute(_SELECT_TRACKING, {"id": strategy_id})).one_or_none()
    if row is None:
        return None
    legs = tuple(StoredLeg(int(r.leg_index), int(r.contract_id), r.side, int(r.quantity), r.entry_price, r.price_at)
                 for r in (await conn.execute(_SELECT_LEGS, {"id": strategy_id})).all())
    return Tracking(strategy_id, row.started_at, row.prices_at, int(row.strategy_revision), legs)
