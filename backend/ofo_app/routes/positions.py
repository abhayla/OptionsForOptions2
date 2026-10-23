"""W-111 Positions read (REQ-044 AC-3 part 1; ADR-109 (2), (5); ADR-110; REQ-009 AC-3; ADR-027): quantities only.

Basis: ADR-109 (2): a strategy owns the fills of orders this app placed; lots beyond that are OUTSIDE lots, shown
apart and blocking nothing. One GET reads Zerodha's positions through the existing read path, at most once per
45 s per user (REQ-118 AC-7: ``kite_period_reads.screen_positions``, the same answer the connect-time periodic read
stores; ``read_at`` is that read's own time) (``kite_reads`` + ``kite_replies.positions_from_reply``) and Zerodha's order book (``fetch_orders`` +
``kite_replies.orders_from_reply``), and asks W-108's ``attribute_and_compare`` for the split (W-108 loads every stored
plan itself). The route takes NO held units or outside lots from the client (finding
``caller-supplied-verdict-trusted``): it has no body and no query. The answer carries units and the owning strategy's id
only: no price, P&L, margin or Greeks key exists on it (part 2), and no order is ever sent (ADR-002, ADR-027).
No recorded standalone store exists yet (REQ-060 AC-7), so the standalone map passed is empty: a position in no strategy
is shown as outside. Without a Zerodha session, or on a failed or unreadable read of EITHER reply, the answer is a
catalogue refusal (409), never an empty list that would read as "all flat" and never an empty order book (which would
read every open plan as pending for the wrong reason).

ADR-110: a contract an open (or contradicted) plan touches is PENDING: the row carries Zerodha's units as read (the page
marks them "not yet confirmed"), ``pending_plans`` (strategy id, plan number), an empty ``own`` and null
``own_units`` / ``outside_units`` ("makes no own/outside split for it"; 0 would read as a split). Every blocked flag is
W-108's ``blocked`` set: a strategy blocked anywhere (a mismatch or a pending plan) is shown blocked on every row.

ADR-138 (2): "Positions screen: strategy groups, strategy P&L, the mismatch badge and "N outside lots - view on
Kite"; no copy of Kite's full position list." So the answer is grouped by strategy and lists only contracts linked to a
strategy; units no strategy owns are one count (``outside_lots``) the page links to Kite with, never their own rows.
Strategy P&L is W-111 part 2.
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Callable
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from ofo.errors import render
from ofo.instruments.models import is_lot_aligned

from ofo_app import kite_period_reads
from ofo_app import reconcile_attribution as ra
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, Identifier
from ofo_app.catalogue_store import load_catalogue
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.kite_reads import KiteReadError, unconfirmed_template
from ofo_app.kite_replies import ContractIndex, KiteReplyError, log_ignored, orders_from_reply, positions_from_reply
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)


class StrategyContractOut(ApiModel):
    tradingsymbol: Identifier
    zerodha_units: int  # Zerodha's net units on this contract, as read (a pending row marks them "not yet confirmed")
    units: int | None  # this strategy's own units (signed: BUY +, SELL -); null while pending (no own/outside split)
    pending: bool  # an open plan of this strategy is not final at Zerodha yet (ADR-110)
    pending_plans: list[int]  # this strategy's plan numbers that keep the contract pending (empty when not pending)


class StrategyPositionsOut(ApiModel):
    strategy_id: int  # the page links to /strategy/{strategy_id}/execute: every action routes back to the strategy
    blocked: bool  # in W-108's blocked set (a mismatch or a pending plan): the page's mismatch badge
    contracts: list[StrategyContractOut]  # tradingsymbol order; empty for a blocked strategy with no own row


class PositionsOut(ApiModel):
    read_at: datetime.datetime
    strategies: list[StrategyPositionsOut]  # strategy-id order; only contracts linked to a strategy (ADR-138 (2))
    has_outside: bool  # Zerodha holds units on a NIFTY/SENSEX contract that no strategy owns (ADR-109 (2))
    outside_lots: int | None  # those units in lots, summed; null when a lot size cannot be read exactly (never guessed)
    blocked: bool
    blocked_strategy_ids: list[int]  # W-108's blocked set, ascending


def _refuse(template: str) -> StrategyRefused:
    return StrategyRefused(template, Failure.CONFLICT, message=render(template))


@dataclasses.dataclass(frozen=True)
class _Zerodha:
    net: Any
    orders: tuple[Any, ...]
    index: ContractIndex
    read_at: datetime.datetime  # when Zerodha was read (the periodic job's read or this request's), never "now"


def _read(session: KiteSession, catalogue: Any) -> _Zerodha:
    """Both Zerodha reads, or a refusal: a failed or unreadable orders reply is refused exactly like a positions
    reply, never replaced by an empty book. An empty list read successfully is a real answer (no orders today)."""
    index = ContractIndex.from_catalogue(catalogue)
    try:
        answer = kite_period_reads.screen_positions(session.reads)  # REQ-118 AC-7: at most one read per 45 s per user
        positions_reply, orders_reply = answer.value
        read = positions_from_reply(positions_reply, index)
        orders = orders_from_reply(orders_reply)
    except (KiteReadError, KiteReplyError, ValueError) as exc:
        raise _refuse(unconfirmed_template(exc)) from None
    log_ignored(read, "positions read")  # rows never ours, named in one line (as the Execute and return routes do)
    return _Zerodha(read.net, orders, index, answer.read_at)


async def _attribute(db: Any, user_ref: str, zerodha: _Zerodha, sources: ra.Sources,
                     now: datetime.datetime) -> ra.Attribution:
    """The ONE call into W-108: the route hands over only the account (connection + user), Zerodha's net and Zerodha's
    order book; W-108 loads the strategies and plans itself (never held units, plans or outside lots from here or the
    client)."""
    return await ra.attribute_and_compare(ra.Account(db, user_ref), {}, zerodha.net, zerodha.orders, sources, at=now)


def _symbol(key: Any, index: ContractIndex) -> str:
    symbol = index.symbol_of(key)
    if symbol is None:
        raise _refuse("strategy_stored_unreadable")  # a strategy's contract the catalogue cannot name: never guessed
    return symbol


def _outside_lots(result: ra.Attribution, index: ContractIndex) -> int | None:
    """Every outside unit (any sign) in lots, summed: None when a contract's lot size is not exactly one value or its
    units are not a whole number of lots (the page then says "outside positions" without a number)."""
    lots = 0
    for key, units in result.outside.items():
        if not units:
            continue
        lot = index.lot_of(key)
        if lot is None or not is_lot_aligned(units, lot):
            return None
        lots += abs(units) // lot
    return lots


def _groups(result: ra.Attribution, index: ContractIndex) -> list[dict[str, Any]]:
    """ADR-138 (2): one group per strategy, holding only the contracts linked to it: its own units (W-108's ``held``)
    or its plans that keep a contract pending (ADR-110: no own/outside split there). A blocked strategy with no such
    contract still gets its group, so its badge is shown. Outside-only contracts are never a row."""
    rows: dict[str, dict[Any, dict[str, Any]]] = {}
    for sid, units in result.held.items():
        for key, own in units.items():
            rows.setdefault(str(sid), {})[key] = {"units": own, "pending": False, "pending_plans": []}
    for key, entries in result.pending.items():
        for entry in entries:
            row = rows.setdefault(str(entry.strategy_id), {}).setdefault(
                key, {"units": None, "pending": True, "pending_plans": []})
            row.update(units=None, pending=True)
            if entry.plan_number not in row["pending_plans"]:
                row["pending_plans"].append(entry.plan_number)
    for sid in result.blocked:
        rows.setdefault(str(sid), {})
    groups = []
    for sid in sorted(rows, key=int):
        contracts = [{"tradingsymbol": _symbol(key, index), "zerodha_units": result.raw_net.get(key, 0),
                      **row, "pending_plans": sorted(row["pending_plans"])} for key, row in rows[sid].items()]
        groups.append({"strategy_id": int(sid), "blocked": sid in result.blocked,
                       "contracts": sorted(contracts, key=lambda c: c["tradingsymbol"])})
    return groups


def _answer(result: ra.Attribution, index: ContractIndex, read_at: datetime.datetime) -> PositionsOut:
    groups = _groups(result, index)
    blocked_ids = sorted(int(sid) for sid in result.blocked)
    return PositionsOut.model_validate({
        "read_at": read_at, "strategies": groups, "has_outside": any(result.outside.values()),
        "outside_lots": _outside_lots(result, index), "blocked": bool(blocked_ids),
        "blocked_strategy_ids": blocked_ids})


@router.get("/positions", response_model=PositionsOut)
async def read_positions(
    session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045
    clock: Annotated[Callable[[], datetime.datetime], Depends(get_execute_clock)],
    db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
) -> PositionsOut:
    if session is None:
        raise _refuse("gate_broker_not_connected")
    catalogue = await load_catalogue(db)
    zerodha = _read(session, catalogue)
    now = clock()
    try:
        result = await _attribute(db, user_ref, zerodha, ra.Sources(catalogue, clock), now)
    except (ra.AttributionError, store.StrategyStoreError, ValueError):
        raise _refuse("strategy_stored_unreadable") from None
    return _answer(result, zerodha.index, zerodha.read_at)


__all__ = ["PositionsOut", "StrategyContractOut", "StrategyPositionsOut", "read_positions"]
