"""GC-6 ORDERS-SCREEN: one strategy order -> exactly one of the four owner-approved states (ADR-135), never a guess.

Spec basis: ADR-135 (the four states: Not sent to Zerodha / Order placed / Executed <filled> of <ordered> /
Not executed - see Kite); ADR-138 (1) (one line per strategy order); ADR-079 (an open plan is decided by a fresh
Zerodha orders read on page load); finding trust-broker-status-word (Zerodha's status word is only asked "terminal?"
or "COMPLETE?" against an allow-list; any other word is a working order); finding caller-supplied-verdict-trusted
(the state is derived here from stored data and Zerodha's rows, never from a request field).

Pure functions, no I/O. Every answer state of where a line's facts come from (B4 (d)):

Source of the line -> answer:
- fresh read ok, one row for the tag: COMPLETE -> ``executed`` (the row's filled of the plan's ordered);
  REJECTED / CANCELLED -> ``not_executed``; any other status word -> ``placed``.
- fresh read ok, no row, plan from today's session -> ``not_sent`` (Zerodha never received the tag).
- fresh read ok, no row, plan from an earlier session -> Kite's book holds only today: the audit row, else unknown.
- fresh read ok, several rows for one tag -> unknown (a basket posted twice: never picked between).
- read failed / no session / unreadable row -> the tag's latest audit row, else unknown.
- audit row COMPLETE without a whole filled count inside the ordered quantity -> unknown.
- no audit row, plan closed: filled > 0 -> ``executed`` from the stored count; 0 filled -> ``not_sent`` (a Check ran at
  the close and no row for the tag existed); ``unresolved_from_positions`` -> reconciliation (ADR-137), no order state.
- no audit row, plan open, nothing readable -> unknown: "could not confirm" + Check with Zerodha, never a guessed state.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Final, Literal, Optional

from ofo_app import execution_return as er
from ofo_app.execution_plan_store import UNRESOLVED, PlanOrder, StoredPlan

State = Literal["not_sent", "placed", "executed", "not_executed"]
NOT_SENT: Final = "not_sent"
PLACED: Final = "placed"
EXECUTED: Final = "executed"
NOT_EXECUTED: Final = "not_executed"
COMPLETE = "COMPLETE"
#: Zerodha's words after which an order ended without a fill we can rely on (allow-list; the rest are working).
ENDED_UNFILLED = frozenset({"REJECTED", "CANCELLED"})


@dataclasses.dataclass(frozen=True)
class Seen:
    """What Zerodha said about one tag: its status word and filled quantity (from the fresh read or the audit row)."""

    status: str
    filled: int


@dataclasses.dataclass(frozen=True)
class Resolved:
    state: Optional[State]  # noqa: UP045 - None = no order state (unknown or reconciliation)
    filled: Optional[int]  # noqa: UP045 - set for ``executed``
    unknown: bool = False  # could not confirm: the screen shows the catalogue message and "Check with Zerodha"
    reconciliation: bool = False  # ADR-137 block instead of an order state


UNKNOWN = Resolved(None, None, unknown=True)


def from_seen(order: PlanOrder, seen: Seen) -> Resolved:
    if seen.status == COMPLETE:
        if not 0 <= seen.filled <= order.quantity:
            return UNKNOWN
        return Resolved(EXECUTED, seen.filled)
    if seen.status in ENDED_UNFILLED:
        return Resolved(NOT_EXECUTED, None)
    return Resolved(PLACED, None)


def _from_stored(order: PlanOrder, plan: StoredPlan) -> Resolved:
    if plan.status == "open":
        return UNKNOWN
    if plan.close_reason == UNRESOLVED:
        return Resolved(None, None, reconciliation=True)
    if order.filled_quantity:
        return Resolved(EXECUTED, order.filled_quantity)
    return Resolved(NOT_SENT, None)


def resolve(plan: StoredPlan, order: PlanOrder, *, fresh: Optional[Mapping[str, tuple[Seen, ...]]],  # noqa: UP045
            audit: Mapping[str, Seen], earlier_session: bool) -> Resolved:
    """``fresh``: tag -> Zerodha's rows from this request's read (None = no read happened or it failed)."""
    if fresh is not None and plan.status == "open":
        rows = fresh.get(order.tag, ())
        if len(rows) > 1:
            return UNKNOWN
        if len(rows) == 1:
            return from_seen(order, rows[0])
        if not earlier_session:
            return Resolved(NOT_SENT, None)
    seen = audit.get(order.tag)
    if seen is not None:
        return from_seen(order, seen)
    return _from_stored(order, plan)


def earlier_session(plan: StoredPlan, today) -> bool:
    return er.from_earlier_session(plan, today)


__all__ = ["COMPLETE", "ENDED_UNFILLED", "EXECUTED", "NOT_EXECUTED", "NOT_SENT", "PLACED", "UNKNOWN", "Resolved",
           "Seen", "State", "earlier_session", "from_seen", "resolve"]
