"""W-111 Positions read (REQ-044 AC-3 part 1; ADR-109 (2), (5); REQ-009 AC-3; ADR-027): quantities only, no money.

Basis: ADR-109 (2): a strategy owns the fills of orders this app placed; lots beyond that are OUTSIDE lots, shown
apart and blocking nothing. One GET reads Zerodha's positions through the existing read path (``kite_reads`` +
``kite_replies.positions_from_reply``), loads every stored plan of the user's strategies, and asks W-108's
``attribute_and_compare`` for the split. The route takes NO held units or outside lots from the client (finding
``caller-supplied-verdict-trusted``): it has no body and no query. The answer carries units and the owning strategy's id
only: no price, P&L, margin or Greeks key exists on it (part 2), and no order is ever sent (ADR-002, ADR-027).
No recorded standalone store exists yet (REQ-060 AC-7), so the standalone map passed is empty: a position in no strategy
is shown as outside. Without a Zerodha session, or on a failed or unreadable read, the answer is a catalogue refusal
(409), never an empty list that would read as "all flat".
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
from ofo_app.kite_replies import ContractIndex, KiteReplyError, positions_from_reply
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)


class OwnLotsOut(ApiModel):
    strategy_id: int  # the page links to /strategy/{strategy_id}/execute: every action routes back to the strategy
    units: int  # this strategy's own units (signed: BUY +, SELL -)
    blocked: bool  # this strategy is blocked by a mismatch on this contract (REQ-060 AC-7)


class PositionContractOut(ApiModel):
    tradingsymbol: Identifier
    zerodha_units: int  # Zerodha's net units, as read
    own: list[OwnLotsOut]  # each strategy's own units, in strategy-id order
    own_units: int  # the sum of ``own`` (summed here: the browser does no arithmetic)
    outside_units: int  # signed units in no strategy: shown apart, blocking nothing (ADR-109 (2))
    blocked: bool


class PositionsOut(ApiModel):
    read_at: datetime.datetime
    contracts: list[PositionContractOut]
    blocked: bool


def _refuse(template: str) -> StrategyRefused:
    return StrategyRefused(template, Failure.CONFLICT, message=render(template))


@dataclasses.dataclass(frozen=True)
class _Zerodha:
    net: Any
    index: ContractIndex


def _read(session: KiteSession, catalogue: Any) -> _Zerodha:
    index = ContractIndex.from_catalogue(catalogue)
    try:
        return _Zerodha(positions_from_reply(session.reads.fetch_positions(), index).net, index)
    except (KiteReadError, KiteReplyError, ValueError):
        raise _refuse("gate_broker_unconfirmed") from None


async def _attribute(db: Any, user_ref: str, net: Any, sources: ra.Sources, now: datetime.datetime) -> ra.Attribution:
    """The ONE call into W-108: the route hands over only the account (connection + user) and Zerodha's net; W-108
    loads the strategies and plans itself (never held units, plans or outside lots from here or the client)."""
    return await ra.attribute_and_compare(ra.Account(db, user_ref), {}, net, sources, at=now)


def _answer(result: ra.Attribution, index: ContractIndex, now: datetime.datetime) -> PositionsOut:
    blocked_ids = {sid for m in result.report.mismatches for sid in m.strategy_ids}
    keys = set(result.raw_net) | set(result.outside) | {k for units in result.held.values() for k in units}
    rows = []
    for key in sorted(keys, key=repr):
        symbol = index.symbol_of(key)
        if symbol is None:
            raise _refuse("strategy_stored_unreadable")  # a held contract the catalogue cannot name: never guessed
        own = [{"strategy_id": int(sid), "units": units[key], "blocked": sid in blocked_ids}
               for sid, units in sorted(result.held.items(), key=lambda item: int(item[0])) if key in units]
        rows.append({"tradingsymbol": symbol, "zerodha_units": result.raw_net.get(key, 0), "own": own,
                     "own_units": sum(o["units"] for o in own), "outside_units": result.outside.get(key, 0),
                     "blocked": any(o["blocked"] for o in own)})
    return PositionsOut.model_validate({"read_at": now, "contracts": rows, "blocked": any(r["blocked"] for r in rows)})


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
        result = await _attribute(db, user_ref, zerodha.net, ra.Sources(catalogue, clock), now)
    except (ra.AttributionError, store.StrategyStoreError, ValueError):
        raise _refuse("strategy_stored_unreadable") from None
    return _answer(result, zerodha.index, now)


__all__ = ["PositionsOut", "read_positions"]
