"""The one door the order routes write their audit events through (W-103; REQ-063 AC-5, REQ-073 AC-3).

Spec basis: REQ-063 AC-5 (per-event-type field allowlist; the payloads below are filtered by
``ofo_app.audit_allowlist`` inside ``audit_store.append``); REQ-073 AC-3 (the return reads Zerodha's actual order
states back); W-017 (``broker_response_recorded`` = one Kite ORDER record, ``execution_recorded`` = one Kite TRADE
record).

- ``record_prepared``: one ``order_prepared`` per stored plan, built from the STORED plan only (never a request field).
- ``record_once``: an event is written at most once per correlation id (a replayed return writes nothing new). The
  check and the write run in the caller's transaction, under the strategy row lock the return route holds.
- Every event's time is the database clock (``clock_timestamp()``, ADR-023), never a route's request clock (finding
  request-clock-for-database-stamped-fact): the audit trigger judges the time against its own ``recorded_at``.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from ofo.audit.catalogue import EventType
from sqlalchemy import text

from ofo_app import audit_store
from ofo_app.eligibility_from_zerodha import database_now
from ofo_app.execution_plan_store import StoredPlan

SYSTEM_ACTOR = "system"
TAG_SEPARATOR = ","

_RECORDED = text("SELECT 1 FROM public.audit_events WHERE event_type = :t AND correlation_id = :c")


def prepared_payload(plan: StoredPlan) -> dict[str, object]:
    """The ``order_prepared`` payload of a stored plan: its identity, action and tags (in leg order, one string)."""
    return {"strategy_id": plan.strategy_id, "plan_number": plan.plan_number, "action": plan.action,
            "tags": TAG_SEPARATOR.join(o.tag for o in plan.orders)}


async def record_prepared(conn: Any, plan: StoredPlan, *, actor: str) -> None:
    """Writes ``order_prepared`` for a plan just stored by ``record_plan`` in the same transaction."""
    await audit_store.append(conn, EventType.ORDER_PREPARED, actor=actor, timestamp=await database_now(conn),
                             correlation_id=f"plan:{plan.strategy_id}:{plan.plan_number}",
                             payload=prepared_payload(plan))


async def record_once(conn: Any, kind: EventType, correlation: str, row: Mapping[str, object]) -> bool:
    """Appends ``row`` as ``kind`` unless an event of that kind with that correlation id is stored. True if written."""
    if (await conn.execute(_RECORDED, {"t": kind.value, "c": correlation})).first() is not None:
        return False
    await audit_store.append(conn, kind, actor=SYSTEM_ACTOR, timestamp=await database_now(conn),
                             correlation_id=correlation, payload=dict(row))
    return True


def order_correlation(row: Mapping[str, object]) -> str:
    """One broker response per (order, status, filled): a changed state is a new response, a replay is not."""
    return f"order:{row.get('order_id')}:{row.get('status')}:{row.get('filled_quantity')}"


def trade_correlation(row: Mapping[str, object]) -> str:
    """One execution per (order id, trade id): Kite's trade id is unique per order only (fill-not-exactly-once)."""
    return f"trade:{row.get('order_id')}:{row.get('trade_id')}"


async def record_broker_book(conn: Any, orders: Sequence[Mapping[str, object]],
                             trades: Sequence[Mapping[str, object]], tags: Collection[str]) -> None:
    """Every order row carrying one of ``tags`` -> ``broker_response_recorded``; every trade row of those orders ->
    ``execution_recorded``; each at most once."""
    ours = [row for row in orders if row.get("tag") in tags]
    for row in ours:
        await record_once(conn, EventType.BROKER_RESPONSE_RECORDED, order_correlation(row), row)
    order_ids = {row.get("order_id") for row in ours}
    for row in trades:
        if row.get("order_id") in order_ids:
            await record_once(conn, EventType.EXECUTION_RECORDED, trade_correlation(row), row)


__all__ = ["prepared_payload", "record_broker_book", "record_once", "record_prepared"]
