"""GC-6 ORDERS-SCREEN: ``GET /orders`` - one line per strategy order of the caller, in the four approved states.

Spec basis: ADR-135 (four states), ADR-138 (1) (one line per strategy order, a link to Kite's order book for the rest),
ADR-079 ("every page load of that strategy" re-reads Zerodha: ONE read-only orders read decides the open plans),
REQ-073 AC-3 (the read-back by tag), REQ-063 AC-5 (the audit allowlist keeps ``status``, drops the status message).

One request = one transaction:
1. the caller's strategies and their stored plans (owner-checked by ``user_ref`` in every store call; another user's
   orders can never appear);
2. when a plan is open and a Zerodha session exists: ONE ``GET /orders`` (the same ``KiteReads.fetch_orders`` the
   return route uses; no new Kite call type), the rows of the open plans' tags read as strictly as the return route
   reads them, then recorded once per (order, status, filled) by ``order_audit.record_broker_book`` under the
   strategy row lock (trades are not read: orders only);
3. each order resolved by ``orders_view.resolve`` (a pure function; see its table of answer states).
Nothing is ever sent to Zerodha. A failed read (no session, token expired, Kite down, an unreadable row) never rolls
a line into a guessed state: it falls back to the latest audit row of the tag, else the line is "could not confirm".
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.errors import render
from sqlalchemy import text

from ofo_app import eligibility_from_zerodha as elig
from ofo_app import execution_plan_store as plans
from ofo_app import order_audit, orders_view
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute
from ofo_app.kite_reads import KiteReadError
from ofo_app.kite_replies import KiteReplyError, order_from_row
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session

router = APIRouter(route_class=ClosedRoute)

#: The latest ``broker_response_recorded`` row per tag (the audit log is append-only; highest seq = latest).
_AUDIT_ROWS = text(
    "SELECT payload->>'tag' AS tag, payload->>'status' AS status, payload->>'filled_quantity' AS filled "
    "FROM public.audit_events WHERE event_type = 'broker_response_recorded' AND payload->>'tag' = ANY(:tags) "
    "ORDER BY seq DESC")

KiteRead = Literal["not_needed", "read", "failed"]  # no open plan / the one read worked / no session or read error


class OrderLineOut(ApiModel):
    strategy_id: int
    plan_number: int
    action: Literal["ENTRY", "EXIT"]
    tradingsymbol: Identifier
    transaction_type: Literal["BUY", "SELL"]
    ordered_quantity: int
    filled_quantity: Optional[int]  # noqa: UP045 - set exactly when state is ``executed``
    state: Optional[Literal["not_sent", "placed", "executed", "not_executed"]]  # noqa: UP045 - None: see the flags
    could_not_confirm: bool  # no state: the message below and "Check with Zerodha" are shown instead
    needs_reconciliation: bool  # no state: the strategy's reconciliation block (ADR-137) is shown instead
    message: Optional[CatalogueText]  # noqa: UP045 - the catalogue's "could not confirm", set with could_not_confirm
    updated_at: datetime.datetime  # the plan's close time, else its creation time (database clock)


class OrdersOut(ApiModel):
    read_at: datetime.datetime
    kite_read: KiteRead
    orders: list[OrderLineOut]


def _audit_seen(rows: Sequence[Any]) -> dict[str, orders_view.Seen]:
    out: dict[str, orders_view.Seen] = {}
    for r in rows:  # newest first: the first row of a tag is its latest
        if r.tag in out or r.status is None or r.filled is None or not r.filled.isdigit():
            continue
        out[r.tag] = orders_view.Seen(r.status, int(r.filled))
    return out


def _fresh(rows: Sequence[object], tags: frozenset[str]) -> dict[str, tuple[orders_view.Seen, ...]]:
    """Zerodha's rows of the open plans' tags, read as strictly as the return route (ValueError / KiteReplyError: the
    whole read counts as failed)."""
    out: dict[str, tuple[orders_view.Seen, ...]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("an order row must be a mapping")
        if row.get("tag") in tags:
            parsed = order_from_row(row)
            out[row["tag"]] = (*out.get(row["tag"], ()), orders_view.Seen(parsed.status, parsed.filled_quantity))
    return out


@router.get("/orders", response_model=OrdersOut)
async def list_orders(
    session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045
    clock: Annotated[Any, Depends(get_execute_clock)],
    today_of: Annotated[elig.TodayReader, Depends(elig.get_eligibility_today)],
    db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
) -> OrdersOut:
    try:
        out = await _orders(db, user_ref, session, clock(), await today_of(db))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return out


async def _orders(db: Any, user_ref: str, session: Optional[KiteSession],  # noqa: UP045
                  now: datetime.datetime, today: datetime.date) -> OrdersOut:
    history = {s.id: await plans.plans_for(db, user_ref, s.id) for s in await store.list_strategies(db, user_ref)}
    open_tags = {sid: frozenset(o.tag for p in ps if p.status == "open" for o in p.orders)
                 for sid, ps in history.items() if any(p.status == "open" for p in ps)}
    kite_read, fresh = await _read_open_orders(db, user_ref, session, open_tags)
    all_tags = [o.tag for ps in history.values() for p in ps for o in p.orders]
    audit = _audit_seen((await db.execute(_AUDIT_ROWS, {"tags": all_tags})).all()) if all_tags else {}
    lines = []
    for sid, ps in history.items():
        for p in ps:
            for o in p.orders:
                got = orders_view.resolve(p, o, fresh=fresh, audit=audit,
                                          earlier_session=orders_view.earlier_session(p, today))
                lines.append((p.created_at, sid, p.plan_number, o.leg_index, _line(sid, p, o, got)))
    lines.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
    return OrdersOut.model_validate({"read_at": now, "kite_read": kite_read, "orders": [t[4] for t in lines]})


async def _read_open_orders(db: Any, user_ref: str, session: Optional[KiteSession],  # noqa: UP045
                            open_tags: dict[int, frozenset[str]]
                            ) -> tuple[KiteRead, Optional[dict[str, tuple[orders_view.Seen, ...]]]]:  # noqa: UP045
    if not open_tags:
        return "not_needed", None
    if session is None:
        return "failed", None
    try:
        rows = session.reads.fetch_orders()
        fresh = _fresh(rows, frozenset().union(*open_tags.values()))
    except (KiteReadError, KiteReplyError, ValueError):
        return "failed", None
    for sid in sorted(open_tags):  # the strategy row lock: two page loads never record a row twice
        await store.lock_strategy(db, user_ref, sid)
        await order_audit.record_broker_book(db, rows, [], open_tags[sid])  # orders only; no trades read here
    return "read", fresh


def _line(sid: int, plan: plans.StoredPlan, order: plans.PlanOrder, got: orders_view.Resolved) -> dict[str, object]:
    return {"strategy_id": sid, "plan_number": plan.plan_number, "action": plan.action,
            "tradingsymbol": order.tradingsymbol, "transaction_type": order.transaction_type,
            "ordered_quantity": order.quantity, "filled_quantity": got.filled, "state": got.state,
            "could_not_confirm": got.unknown, "needs_reconciliation": got.reconciliation,
            "message": render("gate_broker_unconfirmed") if got.unknown else None,
            "updated_at": plan.closed_at or plan.created_at}


__all__ = ["OrdersOut", "list_orders"]
