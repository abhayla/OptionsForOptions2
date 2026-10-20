"""#380-3: ``POST /strategies/{id}/recovery`` - the recovery actions of a partly executed or blocked strategy.

Spec basis: ADR-136 (1) "Place missing legs" / "Close filled legs"; ADR-137 (3) "Close via a basket" while blocked;
ADR-142 (1) (the refusal lines); ADR-119 (market hours for every action that builds a basket, ADR-141 (3)); REQ-058
Q238 / ADR-117 (shorts first, two baskets); ADR-100 / ADR-079 (never a second order for a leg still open).

Every basket goes through the ONE Execute pipeline (``routes/execute.run_pipeline``): the per-user lock first, Zerodha's
order book (an open order of this strategy refuses with the ADR-142 line), the drift check, pricing from depth, the
``ExecutionContext`` from real sources, ``check_pre_execution`` (market hours, kill switch, data health, margin, the
reconciliation block and its one narrow blocked-exit rule), the freeze limits, ``checked_basket`` and the stored plan.
This module only DECIDES the legs, from ``ofo.execution.recovery`` on Zerodha's reads taken inside the request: the
order book the pipeline just read and the positions the ONE reconciler (``route_reconciliation.reconcile_account``)
parses.
The body carries the action name only: no verdict, no quantity, no side (finding caller-supplied-verdict-trusted).

Answer states of Zerodha's reads (standing item (d)) and what each does here:
- stated: decided by the recovery domain (its own allow-lists).
- failed (positions or orders unreadable, a reconciler error): refused ``read_failed``, nothing stored.
- empty (no position lines / empty book): the domain reads it as flat (``not_partial`` / ``nothing_to_close``).
- absent (a plan contract with no row): flat for that contract (ADR-135 "Not sent to Zerodha").
- not found (no stored ENTRY plan to recover, a contract the catalogue cannot resolve): refused, nothing stored.
- ambiguous (a tag twice, our tag on the other side of the base plan): refused ``ambiguous``.

"Use Zerodha's numbers for this contract" (ADR-137 (2), ADR-141) is NOT offered here yet: it changes each holder's
units through an audited resolution the stores do not have (reported as not done, GC-6 #380-3); the body refuses it.
"""
from __future__ import annotations

import asyncio
import datetime
from collections.abc import Callable
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.charges.rates import ChargeRates
from ofo.engine import Action, Instrument, Leg
from ofo.execution import recovery as rc
from ofo.execution.context import VersionState, ZerodhaNow, product_key
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from pydantic import BaseModel, ConfigDict

from ofo_app import execute_plan as ep
from ofo_app import route_reconciliation as rr
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.kite_reads import KiteReadError
from ofo_app.kite_replies import KiteReplyError
from ofo_app.recovery_reads import zerodha_read
from ofo_app.routes import execute as ex
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import load_charge_rates
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)

PLACE, CLOSE_FILLED, CLOSE_VIA_BASKET = "place_missing_legs", "close_filled_legs", "close_via_basket"
RecoveryName = Literal["place_missing_legs", "close_filled_legs", "close_via_basket"]


class RecoveryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: RecoveryName


class RecoveryOut(ApiModel):
    """Either the basket (the Execute reply, the plan stored) or the refusal and its ADR-142 line (nothing stored)."""

    action: RecoveryName
    refusal: Optional[Identifier]  # noqa: UP045 - None when a basket was built
    line: Optional[CatalogueText]  # noqa: UP045 - the ADR-142 line; None when ADR-142 gives the refusal no line
    execute: Optional[ex.ExecuteOut]  # noqa: UP045 - None when refused


def _base_plan(history: tuple[Any, ...]) -> Any:
    """The strategy's latest ENTRY plan: the plan a recovery completes or closes (not found -> refused)."""
    entries = [p for p in history if p.action == ex.ENTRY]
    if not entries:
        raise ex.Declined(rc.Refusal.NOT_PARTIAL.value)
    return max(entries, key=lambda p: p.plan_number)


def _domain_plan(req: Any, base: Any, catalogue: Any) -> tuple[ExecutionPlan, dict[str, int], dict[str, Any]]:
    """The base plan as the domain's ``ExecutionPlan`` keyed by Zerodha's tradingsymbol, the lot size per contract and
    each contract's catalogue id (read from the catalogue, never from the request)."""
    legs, lots, ids = [], {}, {}
    for order in sorted(base.orders, key=lambda o: o.leg_index):
        entry = catalogue.get(ex.instrument_of(order.instrument_id))
        c = entry.contract
        leg = Leg(Action(order.transaction_type), Instrument(c.instrument_type), c.strike, c.expiry, order.quantity,
                  order.price)
        legs.append(PlannedLeg(f"L{order.leg_index}", order.tradingsymbol, leg))
        lots[order.tradingsymbol], ids[order.tradingsymbol] = c.lot_size, entry
    return ExecutionPlan(str(req.strategy_id), tuple(legs)), lots, ids


def _zerodha_now(plan: ExecutionPlan, read: rc.ZerodhaRead) -> ZerodhaNow | None:
    """Zerodha's position at the click on every contract of the plan, for the gate's narrow blocked-exit rule; an
    unread book or positions -> None (the block stands)."""
    if read.net is None or read.orders is None:
        return None
    open_symbols = {o.contract for o in read.orders if o.is_open}
    net = {product_key(p.leg): read.net.get(p.contract, 0) for p in plan.legs}
    opened = frozenset(product_key(p.leg) for p in plan.legs if p.contract in open_symbols)
    return ZerodhaNow(net, opened, read.read_at)


def _decide(name: str) -> Callable[..., Any]:
    async def decide(req: Any, history: tuple[Any, ...], order_rows: list[object], catalogue: Any) -> ex.Recovery:
        try:
            reply = await asyncio.to_thread(req.session.reads.fetch_positions)
            verdict = await rr.reconcile_account(req.db, req.user_ref, catalogue, reply, order_rows, at=req.now,
                                                 clock=req.clock, source=None)
        except (KiteReadError, KiteReplyError, ValueError):  # AttributionError / ReconciliationError included
            raise ex.Declined(rc.Refusal.READ_FAILED.value) from None
        read = zerodha_read(order_rows, verdict.positions, req.clock())  # stamped after both replies
        base = _base_plan(history)
        plan, lots, entries = _domain_plan(req, base, catalogue)
        blocked = verdict.blocks(req.strategy_id)
        now = req.clock()
        if name == PLACE:
            out = rc.missing_legs(plan, read, rc.Scope(req.strategy_id, base.plan_number, lots, now, blocked))
        elif name == CLOSE_FILLED:
            out = rc.close_filled_legs(plan, read, rc.Scope(req.strategy_id, base.plan_number, lots, now, blocked))
        else:
            out = rc.close_via_basket(plan, read, now=now, blocked=blocked)
        if not out.builds:
            refusal = out.refusal or rc.Refusal.NOTHING_TO_PLACE
            raise ex.Declined(refusal.value, rc.refusal_line(out) if refusal is not rc.Refusal.MARGIN_SHORT else None)
        legs = [ep.LegToPrice(entries[leg.contract].id, leg.side, leg.units, None) for leg in out.legs]
        return ex.Recovery(VersionState.ACTIVE, legs, verdict.positions, frozenset(verdict.attribution.blocked),
                           _zerodha_now(plan, read) if name == CLOSE_VIA_BASKET else None)

    return decide


@router.post("/strategies/{strategy_id}/recovery", response_model=RecoveryOut)
async def recover(  # noqa: PLR0913 - FastAPI dependencies
    strategy_id: int, body: RecoveryIn,
    session: Annotated[Optional[ex.KiteSession], Depends(ex.get_kite_session)],  # noqa: UP045
    quotes: Annotated[ex.QuoteReader, Depends(ex.get_quote_reader)],
    clock: Annotated[Callable[[], datetime.datetime], Depends(ex.get_execute_clock)],
    db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
    rates: Annotated[Optional[ChargeRates], Depends(load_charge_rates)],  # noqa: UP045
) -> RecoveryOut:
    """Place missing legs builds an ENTRY basket of the missing legs only; both closes build an EXIT basket (shorts
    first). A refusal rolls everything back: nothing stored, no plan number consumed."""
    gate_action = ex.ENTRY if body.action == PLACE else ex.EXIT
    try:
        stored = await store.load(db, user_ref, strategy_id)  # 404 before anything else
        if session is None:
            raise ex.refuse("gate_broker_unconfirmed")
        req = ex.PipelineRequest(db, user_ref, strategy_id, gate_action, session, quotes, clock(), clock, rates,
                                 decide=_decide(body.action))
        built = await ex.run_pipeline(req, stored)
        await db.commit()
    except ex.Declined as declined:
        await db.rollback()
        return RecoveryOut.model_validate({"action": body.action, "refusal": declined.refusal, "line": declined.line,
                                           "execute": None})
    except store.StrategyStoreError as exc:
        await db.rollback()
        if exc.code == store.NOT_FOUND:
            raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND) from None
        raise ex.refuse("strategy_stored_unreadable") from None
    except Exception:
        await db.rollback()
        raise
    return RecoveryOut.model_validate({"action": body.action, "refusal": None, "line": None, "execute": built})


__all__ = ["RecoveryIn", "RecoveryOut"]
