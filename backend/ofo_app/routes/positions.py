"""W-111 Positions read (REQ-044 AC-3 part 1; ADR-109 (2), (5); ADR-110; REQ-009 AC-3; ADR-027): quantities only.

Basis: ADR-109 (2): a strategy owns the fills of orders this app placed; lots beyond that are OUTSIDE lots, shown
apart and blocking nothing. One GET reads Zerodha's positions through the existing read path (``kite_reads`` +
``kite_replies.positions_from_reply``) and Zerodha's order book (``fetch_orders`` +
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
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Callable
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from ofo.errors import render

from ofo_app import reconcile_attribution as ra
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, Identifier
from ofo_app.catalogue_store import load_catalogue
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.kite_reads import KiteReadError
from ofo_app.kite_replies import ContractIndex, KiteReplyError, orders_from_reply, positions_from_reply
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)


class OwnLotsOut(ApiModel):
    strategy_id: int  # the page links to /strategy/{strategy_id}/execute: every action routes back to the strategy
    units: int  # this strategy's own units (signed: BUY +, SELL -)
    blocked: bool  # this strategy is in W-108's blocked set (a mismatch or a pending plan; REQ-060 AC-7, ADR-110)


class PendingPlanOut(ApiModel):
    strategy_id: int  # the page links to /strategy/{strategy_id}/execute, where Check with Zerodha is (ADR-110)
    plan_number: int


class PositionContractOut(ApiModel):
    tradingsymbol: Identifier
    zerodha_units: int  # Zerodha's net units, as read
    own: list[OwnLotsOut]  # each strategy's own units, in strategy-id order (empty while pending)
    own_units: int | None  # the sum of ``own`` (summed here: the browser does no arithmetic); null while pending
    outside_units: int | None  # signed units in no strategy, shown apart (ADR-109 (2)); null while pending
    pending: bool  # an open plan's orders are not final at Zerodha yet (ADR-110): no own/outside split
    pending_plans: list[PendingPlanOut]  # the plans that keep this contract pending (empty when not pending)
    blocked: bool


class PositionsOut(ApiModel):
    read_at: datetime.datetime
    contracts: list[PositionContractOut]
    blocked: bool
    blocked_strategy_ids: list[int]  # W-108's blocked set, ascending (a pending row has no own lots to carry the flag)


def _refuse(template: str) -> StrategyRefused:
    return StrategyRefused(template, Failure.CONFLICT, message=render(template))


@dataclasses.dataclass(frozen=True)
class _Zerodha:
    net: Any
    orders: tuple[Any, ...]
    index: ContractIndex


def _read(session: KiteSession, catalogue: Any) -> _Zerodha:
    """Both Zerodha reads, or a refusal: a failed or unreadable orders reply is refused exactly like a positions
    reply, never replaced by an empty book. An empty list read successfully is a real answer (no orders today)."""
    index = ContractIndex.from_catalogue(catalogue)
    try:
        net = positions_from_reply(session.reads.fetch_positions(), index).net
        orders = orders_from_reply(session.reads.fetch_orders())
    except (KiteReadError, KiteReplyError, ValueError):
        raise _refuse("gate_broker_unconfirmed") from None
    return _Zerodha(net, orders, index)


async def _attribute(db: Any, user_ref: str, zerodha: _Zerodha, sources: ra.Sources,
                     now: datetime.datetime) -> ra.Attribution:
    """The ONE call into W-108: the route hands over only the account (connection + user), Zerodha's net and Zerodha's
    order book; W-108 loads the strategies and plans itself (never held units, plans or outside lots from here or the
    client)."""
    return await ra.attribute_and_compare(ra.Account(db, user_ref), {}, zerodha.net, zerodha.orders, sources, at=now)


def _row(key: Any, symbol: str, result: ra.Attribution) -> dict[str, Any]:
    zerodha_units = result.raw_net.get(key, 0)
    entries = result.pending.get(key, ())
    if entries:  # ADR-110: "makes no own/outside split for it"
        plans = sorted({(int(e.strategy_id), e.plan_number) for e in entries})
        return {"tradingsymbol": symbol, "zerodha_units": zerodha_units, "own": [], "own_units": None,
                "outside_units": None, "pending": True,
                "pending_plans": [{"strategy_id": sid, "plan_number": n} for sid, n in plans], "blocked": True}
    own = [{"strategy_id": int(sid), "units": units[key], "blocked": sid in result.blocked}
           for sid, units in sorted(result.held.items(), key=lambda item: int(item[0])) if key in units]
    return {"tradingsymbol": symbol, "zerodha_units": zerodha_units, "own": own,
            "own_units": sum(o["units"] for o in own), "outside_units": result.outside.get(key, 0),
            "pending": False, "pending_plans": [], "blocked": any(o["blocked"] for o in own)}


def _answer(result: ra.Attribution, index: ContractIndex, now: datetime.datetime) -> PositionsOut:
    keys = (set(result.raw_net) | set(result.outside) | set(result.pending)
            | {k for units in result.held.values() for k in units})
    rows = []
    for key in sorted(keys, key=repr):
        symbol = index.symbol_of(key)
        if symbol is None:
            raise _refuse("strategy_stored_unreadable")  # a held contract the catalogue cannot name: never guessed
        rows.append(_row(key, symbol, result))
    blocked = bool(result.blocked) or any(r["blocked"] for r in rows)
    return PositionsOut.model_validate({"read_at": now, "contracts": rows, "blocked": blocked,
                                        "blocked_strategy_ids": sorted(int(sid) for sid in result.blocked)})


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
    return _answer(result, zerodha.index, now)


__all__ = ["OwnLotsOut", "PendingPlanOut", "PositionContractOut", "PositionsOut", "read_positions"]
