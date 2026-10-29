"""PostgreSQL store of the paper stop triggers and their alerts (GC-TP step 7a; ADR-207 (5); REQ-109 AC-8). Schema:
migration 0029.

- add / cancel / list_for: one strategy's triggers; the route checks the strategy's owner first (strategy_store.load).
- armed: every armed trigger of every user (fired_at and cancelled_at NULL) with its strategy's user, name and
  underlying, in ONE query whatever the count (finding F-3); and orders_of: the paper orders of those strategies, in
  ONE query.
- claim_fire: ``UPDATE ... SET fired_at = clock_timestamp() WHERE id = :id AND fired_at IS NULL AND cancelled_at IS
  NULL RETURNING id``; True only for the one caller that fires (two ticks, two monitors, a restart: one winner). The
  database guard (0029) also refuses any later change of fired_at.
- add_alert / alerts / mark_all_read: the alert rows. One alert per trigger (a unique index).
Insert and update only; nothing is deleted. The caller commits.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.tracking.stops import Trigger
from sqlalchemy import text

from ofo_app import paper_store

_TRIGGER_COLUMNS = "t.id, t.strategy_id, t.kind, t.direction, t.level, t.contract_id, t.underlying"
_ADD = text("INSERT INTO public.paper_triggers (strategy_id, kind, contract_id, underlying, direction, level) "
            "VALUES (:strategy_id, :kind, :contract_id, :underlying, :direction, :level) RETURNING id")
_FOR = text(f"SELECT {_TRIGGER_COLUMNS}, t.created_at, t.fired_at, t.cancelled_at "  # noqa: S608 constant columns
            "FROM public.paper_triggers AS t WHERE t.strategy_id = :sid ORDER BY t.id")
_ARMED = text(f"SELECT {_TRIGGER_COLUMNS}, s.user_ref, s.name, s.underlying AS strategy_underlying "  # noqa: S608
              "FROM public.paper_triggers AS t JOIN public.strategies AS s ON s.id = t.strategy_id "
              "WHERE t.fired_at IS NULL AND t.cancelled_at IS NULL AND s.deleted_at IS NULL ORDER BY t.id")
_ORDERS_OF = text("SELECT id, strategy_id, contract_id, side, quantity, price, kind, placed_at, created_at, reason, "
                  "trigger_id FROM public.paper_orders WHERE strategy_id = ANY(:ids) ORDER BY strategy_id, id")
_CLAIM = text("UPDATE public.paper_triggers SET fired_at = clock_timestamp() "
              "WHERE id = :id AND fired_at IS NULL AND cancelled_at IS NULL RETURNING id")
_CANCEL = text("UPDATE public.paper_triggers SET cancelled_at = clock_timestamp() "
               "WHERE strategy_id = :sid AND (CAST(:id AS BIGINT) IS NULL OR id = :id) "
               "AND fired_at IS NULL AND cancelled_at IS NULL RETURNING id")
_ALERT = text("INSERT INTO public.paper_alerts (strategy_id, trigger_id, title, body) "
              "VALUES (:sid, :tid, :title, :body) RETURNING id")
_ALERTS = text("SELECT a.id, a.strategy_id, a.trigger_id, a.created_at, a.title, a.body, a.read_at "
               "FROM public.paper_alerts AS a JOIN public.strategies AS s ON s.id = a.strategy_id "
               "WHERE s.user_ref = :user_ref ORDER BY a.id DESC LIMIT :limit")
_UNREAD = text("SELECT count(*) FROM public.paper_alerts AS a JOIN public.strategies AS s ON s.id = a.strategy_id "
               "WHERE s.user_ref = :user_ref AND a.read_at IS NULL")
_READ_ALL = text("UPDATE public.paper_alerts AS a SET read_at = clock_timestamp() FROM public.strategies AS s "
                 "WHERE s.id = a.strategy_id AND s.user_ref = :user_ref AND a.read_at IS NULL")


@dataclass(frozen=True)
class ArmedTrigger:
    trigger: Trigger
    user_ref: str
    name: str | None
    underlying: str  # the strategy's


@dataclass(frozen=True)
class TriggerRow:
    trigger: Trigger
    created_at: datetime.datetime
    fired_at: datetime.datetime | None
    cancelled_at: datetime.datetime | None


@dataclass(frozen=True)
class AlertRow:
    id: int
    strategy_id: int
    trigger_id: int
    created_at: datetime.datetime
    title: str
    body: str
    read_at: datetime.datetime | None


def _trigger(r: Any) -> Trigger:
    return Trigger(int(r.id), int(r.strategy_id), r.kind, r.direction, Decimal(r.level),
                   None if r.contract_id is None else int(r.contract_id), r.underlying)


@dataclass(frozen=True)
class NewTrigger:
    kind: str
    direction: str
    level: Decimal
    contract_id: int | None = None  # leg_stop
    underlying: str | None = None  # conditional_exit


async def add(conn: Any, strategy_id: int, new: NewTrigger) -> int:
    row = (await conn.execute(_ADD, {"strategy_id": strategy_id, "kind": new.kind, "contract_id": new.contract_id,
                                     "underlying": new.underlying, "direction": new.direction,
                                     "level": new.level})).one()
    return int(row.id)


async def cancel(conn: Any, strategy_id: int, trigger_id: int | None = None) -> list[int]:
    """Cancels one armed trigger of the strategy (or every armed one when ``trigger_id`` is None); the ids cancelled."""
    return [int(r.id) for r in (await conn.execute(_CANCEL, {"sid": strategy_id, "id": trigger_id})).all()]


async def list_for(conn: Any, strategy_id: int) -> list[TriggerRow]:
    return [TriggerRow(_trigger(r), r.created_at, r.fired_at, r.cancelled_at)
            for r in (await conn.execute(_FOR, {"sid": strategy_id})).all()]


async def armed(conn: Any) -> list[ArmedTrigger]:
    return [ArmedTrigger(_trigger(r), r.user_ref, r.name, r.strategy_underlying)
            for r in (await conn.execute(_ARMED)).all()]


async def orders_of(conn: Any, strategy_ids: Sequence[int]) -> dict[int, list[paper_store.StoredOrder]]:
    out: dict[int, list[paper_store.StoredOrder]] = {sid: [] for sid in strategy_ids}
    if not strategy_ids:
        return out
    for r in (await conn.execute(_ORDERS_OF, {"ids": list(strategy_ids)})).all():
        order = paper_store.NewOrder(int(r.contract_id), r.side, int(r.quantity), r.price, r.kind, r.placed_at,
                                     r.reason, None if r.trigger_id is None else int(r.trigger_id))
        out[int(r.strategy_id)].append(paper_store.StoredOrder(int(r.id), int(r.strategy_id), order, r.created_at))
    return out


async def claim_fire(conn: Any, trigger_id: int) -> bool:
    return (await conn.execute(_CLAIM, {"id": trigger_id})).first() is not None


async def add_alert(conn: Any, strategy_id: int, trigger_id: int, title: str, body: str) -> int:
    row = (await conn.execute(_ALERT, {"sid": strategy_id, "tid": trigger_id, "title": title, "body": body})).one()
    return int(row.id)


async def alerts(conn: Any, user_ref: str, limit: int = 100) -> tuple[list[AlertRow], int]:
    """The user's newest alerts first (at most ``limit``) and the user's unread count."""
    rows = [AlertRow(int(r.id), int(r.strategy_id), int(r.trigger_id), r.created_at, r.title, r.body, r.read_at)
            for r in (await conn.execute(_ALERTS, {"user_ref": user_ref, "limit": limit})).all()]
    unread = int((await conn.execute(_UNREAD, {"user_ref": user_ref})).scalar_one())
    return rows, unread


async def mark_all_read(conn: Any, user_ref: str) -> int:
    return (await conn.execute(_READ_ALL, {"user_ref": user_ref})).rowcount
