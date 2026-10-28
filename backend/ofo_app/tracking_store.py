"""PostgreSQL store for paper tracking of a saved strategy (W-122; REQ-109 AC-1, AC-4). Schema: migrations 0021, 0027.

- start: under the strategy's row lock (one writer per strategy), re-checks the revision the user started from, then
  inserts the tracking row and one row per leg. A second start of the same strategy is refused (ALREADY_TRACKED): the
  primary key on strategy_id holds even when two starts race. Insert-only; the caller commits.
- load: the tracking of the user's own strategy, with its paper exits, or None. Another user's strategy answers
  NOT_FOUND like a missing one (strategy_store.load runs first in the route).
- load_all (GC-BP step 4): every tracking of ONE user's visible strategies with legs, exits, name and underlying, in
  three queries whatever the count (finding F-3: a per-strategy loop cost 145 queries x 136 ms = 12 s). The user filter
  is the strategies table's owner column, never a request value.
- exit_legs (GC-BP step 5; REQ-109 AC-4): under the strategy's row lock, one append-only row per exited leg
  (strategy_tracking_exits; the primary key lets a leg exit once). A leg already exited is refused (ALREADY_EXITED),
  also when two exits race. Insert-only; the caller commits.
The prices come only from ofo.tracking.paper (the server's live read); this store takes no price from a request.
REQ-040 timeline: strategy_tracking (the paper entry) and strategy_tracking_exits (the paper exits) ARE the paper
timeline of a tracked strategy; they are paper by where they live and never reach an order table.
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
ALREADY_EXITED = "already_exited"

_INSERT_TRACKING = text(
    "INSERT INTO public.strategy_tracking (strategy_id, strategy_revision, price_health, prices_at) "
    "VALUES (:id, :revision, 'available', :prices_at) ON CONFLICT (strategy_id) DO NOTHING RETURNING started_at")
_INSERT_LEG = text(
    "INSERT INTO public.strategy_tracking_legs (strategy_id, leg_index, contract_id, side, quantity, entry_price, "
    "price_at) VALUES (:id, :leg_index, :contract_id, :side, :quantity, :entry_price, :price_at)")
_INSERT_EXIT = text(
    "INSERT INTO public.strategy_tracking_exits (strategy_id, leg_index, exit_price, price_at) "
    "VALUES (:id, :leg_index, :exit_price, :price_at) ON CONFLICT (strategy_id, leg_index) DO NOTHING "
    "RETURNING leg_index")
_SELECT_TRACKING = text("SELECT started_at, prices_at, strategy_revision FROM public.strategy_tracking "
                        "WHERE strategy_id = :id")
_SELECT_TRACKED = text(
    "SELECT strategy_id FROM public.strategy_tracking WHERE strategy_id = ANY(CAST(:ids AS BIGINT[]))")
_LEG_COLUMNS = "strategy_id, leg_index, contract_id, side, quantity, entry_price, price_at"
_EXIT_COLUMNS = "strategy_id, leg_index, exit_price, price_at, exited_at"
_SELECT_LEGS = text(f"SELECT {_LEG_COLUMNS} FROM public.strategy_tracking_legs "  # noqa: S608 constant columns
                    "WHERE strategy_id = ANY(CAST(:ids AS BIGINT[])) ORDER BY strategy_id, leg_index")
_SELECT_EXITS = text(f"SELECT {_EXIT_COLUMNS} FROM public.strategy_tracking_exits "  # noqa: S608 constant columns
                     "WHERE strategy_id = ANY(CAST(:ids AS BIGINT[])) ORDER BY strategy_id, leg_index")
_SELECT_USER_TRACKINGS = text(
    "SELECT t.strategy_id, t.started_at, t.prices_at, t.strategy_revision, s.name, s.underlying "
    "FROM public.strategy_tracking AS t JOIN public.strategies AS s ON s.id = t.strategy_id "
    "WHERE s.user_ref = :user_ref AND s.deleted_at IS NULL ORDER BY t.strategy_id")


@dataclass(frozen=True)
class StoredLeg:
    leg_index: int
    contract_id: int
    side: str
    quantity: int
    entry_price: Decimal
    price_at: datetime.datetime


@dataclass(frozen=True)
class StoredExit:
    leg_index: int
    exit_price: Decimal
    price_at: datetime.datetime
    exited_at: datetime.datetime


@dataclass(frozen=True)
class Tracking:
    strategy_id: int
    started_at: datetime.datetime
    prices_at: datetime.datetime
    strategy_revision: int
    legs: tuple[StoredLeg, ...]
    exits: tuple[StoredExit, ...] = ()

    @property
    def exit_prices(self) -> dict[int, Decimal]:
        return {e.leg_index: e.exit_price for e in self.exits}


@dataclass(frozen=True)
class UserTracking:
    """One row of the user's tracking list: the tracking plus the strategy's name and underlying."""

    tracking: Tracking
    name: str | None
    underlying: str


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


async def exit_legs(conn: Any, user_ref: str, strategy_id: int,
                    exits: Sequence[tuple[int, Decimal, datetime.datetime]]) -> Tracking:
    """REQ-109 AC-4: stores one paper exit row per (leg_index, exit_price, price_at), under the strategy's row lock.
    Refuses a leg already exited (ALREADY_EXITED, nothing stored), a leg that is not tracked (ValueError) and an
    empty list. The exit prices come only from the server's live read (the route)."""
    if not exits or len({e[0] for e in exits}) != len(exits):
        raise ValueError("a paper exit names each leg once, at least one")
    async with conn.begin_nested():
        await store.lock_strategy(conn, user_ref, strategy_id)  # NOT_FOUND for another user's strategy
        current = await load(conn, strategy_id)
        if current is None:
            raise ValueError(f"strategy {strategy_id} is not tracked")
        tracked = {leg.leg_index for leg in current.legs}
        if any(i not in tracked for i, _, _ in exits):
            raise ValueError(f"strategy {strategy_id}: not a tracked leg")
        done = set(current.exit_prices) & {i for i, _, _ in exits}
        if done:
            raise store.StrategyStoreError(ALREADY_EXITED, f"strategy {strategy_id}: legs {sorted(done)} exited")
        for leg_index, price, at in exits:
            stored = (await conn.execute(_INSERT_EXIT, {"id": strategy_id, "leg_index": leg_index,
                                                        "exit_price": price, "price_at": at})).scalar_one_or_none()
            if stored is None:  # a racing exit stored it first
                raise store.StrategyStoreError(ALREADY_EXITED, f"strategy {strategy_id}: leg {leg_index} exited")
    found = await load(conn, strategy_id)
    if found is None:
        raise RuntimeError(f"strategy {strategy_id}: the tracking just exited cannot be read back")
    return found


async def tracked_ids(conn: Any, strategy_ids: Sequence[int]) -> set[int]:
    """REQ-134 AC-4: which of the given strategies (already filtered to the signed-in user's own) have a tracking row.
    A read failure raises: the caller decides what 'unknown' shows."""
    if not strategy_ids:
        return set()
    rows = await conn.execute(_SELECT_TRACKED, {"ids": list(strategy_ids)})
    return {int(r.strategy_id) for r in rows}


async def _legs_and_exits(conn: Any, ids: list[int]) -> tuple[dict[int, list[StoredLeg]], dict[int, list[StoredExit]]]:
    legs: dict[int, list[StoredLeg]] = {i: [] for i in ids}
    exits: dict[int, list[StoredExit]] = {i: [] for i in ids}
    if not ids:
        return legs, exits
    for r in (await conn.execute(_SELECT_LEGS, {"ids": ids})).all():
        legs[int(r.strategy_id)].append(StoredLeg(int(r.leg_index), int(r.contract_id), r.side, int(r.quantity),
                                                  r.entry_price, r.price_at))
    for r in (await conn.execute(_SELECT_EXITS, {"ids": ids})).all():
        exits[int(r.strategy_id)].append(StoredExit(int(r.leg_index), r.exit_price, r.price_at, r.exited_at))
    return legs, exits


async def load(conn: Any, strategy_id: int) -> Tracking | None:
    """The tracking of a strategy the caller already loaded for its user (ownership is checked there)."""
    row = (await conn.execute(_SELECT_TRACKING, {"id": strategy_id})).one_or_none()
    if row is None:
        return None
    legs, exits = await _legs_and_exits(conn, [strategy_id])
    return Tracking(strategy_id, row.started_at, row.prices_at, int(row.strategy_revision), tuple(legs[strategy_id]),
                    tuple(exits[strategy_id]))


async def load_all(conn: Any, user_ref: str) -> list[UserTracking]:
    """Every tracking of ``user_ref``'s visible strategies, oldest strategy first, in three queries (module docstring).
    A read failure raises: the caller refuses the whole list, never a partial one."""
    heads = (await conn.execute(_SELECT_USER_TRACKINGS, {"user_ref": user_ref})).all()
    ids = [int(h.strategy_id) for h in heads]
    legs, exits = await _legs_and_exits(conn, ids)
    return [UserTracking(Tracking(int(h.strategy_id), h.started_at, h.prices_at, int(h.strategy_revision),
                                  tuple(legs[int(h.strategy_id)]), tuple(exits[int(h.strategy_id)])),
                         h.name, h.underlying) for h in heads]
