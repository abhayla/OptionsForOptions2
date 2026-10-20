"""W-096 return route: read Zerodha back by tag, close the open plan from Zerodha's answer, reconcile per strategy.

Spec basis: REQ-073 AC-3; REQ-057 AC-2; REQ-058 AC-2/AC-5/AC-6; REQ-060 AC-7; ADR-050 item 4(d); ADR-102; ADR-105.
Stateless per call: everything is rebuilt from the database (stored plans and their filled quantities) plus ONE fresh
Zerodha read (orders, trades, positions). One request = one transaction, in this order (any refusal rolls back):
1. the strategy (404 for a missing or another user's one) and its row lock (two returns never close a plan twice);
2. Zerodha's orders, trades and positions (any read or reply error -> 409, nothing changed);
3. the open plan classified (``execution_return.classify``; a plan created before today's session, on the database's
   India date - the eligibility code's "today" - is never closed from the book); a close reason closes it with
   Zerodha's filled quantities, an EXIT reading ``exited`` only when the strategy is flat and Zerodha agrees;
   ``waiting`` and ``reconciliation_required`` leave it open; nothing is ever sent to Zerodha (no Kite write exists
   here);
4. orders tagged for the strategy with no stored plan: listed and written to the audit log once per (order, status,
   filled) as ``broker_response_recorded``; the stored plans' own orders likewise, and each of their trades once per
   (order id, trade id) as ``execution_recorded`` (W-103, ``order_audit``; database clock);
5. the contract rows and the block from the ONE reconciliation (#380-2, ``route_reconciliation.reconcile_account``,
   also called by the Execute route; run after step 2 under the per-user lock taken before step 1's strategy lock,
   blocking mismatches stored as ``after_execution``); the strategy's state and the fills' realised P&L. A contract
   another strategy's open/drifted plan or stored mismatch touches is undecidable here (reason named).
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.audit.catalogue import EventType
from ofo.errors import render
from ofo.instruments.models import InstrumentId
from ofo.reconciliation.compare import ReconciliationError

from ofo_app import eligibility_from_zerodha as elig
from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app import execution_return as er
from ofo_app import order_audit
from ofo_app import reconcile_attribution as ra
from ofo_app import return_book as rb
from ofo_app import route_reconciliation as rr
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.catalogue_store import load_catalogue
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.kite_reads import KiteReadError
from ofo_app.kite_replies import KiteReplyError
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)

MismatchCode = Literal[tuple(rr.MISMATCH_CODES.values())]  # type: ignore[valid-type]  # closed: one per compare kind
PlanState = Literal["waiting", "filled", "exited", "nothing_placed", "partial", "reconciliation_required",
                    "unresolved_from_positions"]  # the last: a stored close reason (migration 0018, #380 step 2.1)


class ReturnPlanOut(ApiModel):
    plan_number: int
    action: Literal["ENTRY", "EXIT"]
    state: PlanState
    choices: list[Identifier]  # REQ-058 AC-2's four choices for a partial plan, in order; empty otherwise
    reason: Optional[Literal["plan_from_earlier_session"]]  # noqa: UP045 - why reconciliation, beyond the book


class ReturnContractOut(ApiModel):
    tradingsymbol: Identifier
    platform_units: int
    zerodha_units: int
    other_strategies_units: int
    unexplained_units: int  # beyond every stored strategy: listed, blocking nothing (REQ-060 AC-7)
    mismatch: Optional[MismatchCode]  # noqa: UP045 - compare's kind, as its catalogue template id (#380-2)
    reconciliation_reason: Optional[Literal["another_strategy_plan_unsettled"]]  # noqa: UP045 - undecidable here


class ReturnExternalOut(ApiModel):
    tag: Identifier
    order_id: Identifier
    tradingsymbol: Identifier
    transaction_type: Literal["BUY", "SELL"]
    quantity: int
    filled_quantity: int
    terminal: bool


class ReturnOut(ApiModel):
    strategy_id: int
    read_at: datetime.datetime
    strategy_state: Literal["exited", "plan_open", "holding", "flat"]
    plans: list[ReturnPlanOut]
    contracts: list[ReturnContractOut]
    mismatches: int
    blocked: bool
    external_orders: list[ReturnExternalOut]
    realised_pnl: Optional[Money]  # noqa: UP045 - the fills' P&L when they leave every contract flat (ADR-102)


@dataclasses.dataclass(frozen=True)
class _Request:
    db: Any
    user_ref: str
    strategy_id: int
    session: KiteSession
    now: datetime.datetime
    today: datetime.date  # the database's India date: the session a plan must belong to, to close from the book
    now_clock: Callable[[], datetime.datetime]  # the request clock compare checks ``at`` against


def _refuse(template: str) -> StrategyRefused:
    return StrategyRefused(template, Failure.CONFLICT, message=render(template))


@dataclasses.dataclass(frozen=True)
class _Clocks:
    now: Callable[[], datetime.datetime]
    today_of: elig.TodayReader


def get_return_clocks(
    clock: Annotated[Callable[[], datetime.datetime], Depends(get_execute_clock)],
    today_of: Annotated[elig.TodayReader, Depends(elig.get_eligibility_today)],
) -> _Clocks:
    """The request clock and the eligibility code's "today" (the database's India date), one seam each."""
    return _Clocks(clock, today_of)


@router.post("/strategies/{strategy_id}/execution/return", response_model=ReturnOut)
async def return_from_kite(
    strategy_id: int,
    session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045
    clocks: Annotated[_Clocks, Depends(get_return_clocks)],
    db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
) -> ReturnOut:
    try:
        stored = await store.load(db, user_ref, strategy_id)  # 404 before anything else
        if session is None:
            raise _refuse("gate_broker_unconfirmed")
        await rr.lock_user(db, user_ref)  # #380-2 / Q224: the per-user lock FIRST, before any strategy row lock
        await store.lock_strategy(db, user_ref, strategy_id)  # held to commit: one return closes a plan once
        req = _Request(db, user_ref, strategy_id, session, clocks.now(), await clocks.today_of(db), clocks.now)
        out = await _return(req, stored.saved.definition.underlying)
        await db.commit()
    except store.StrategyStoreError as exc:
        await db.rollback()
        if exc.code == store.NOT_FOUND:
            raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND) from None
        raise _refuse("strategy_stored_unreadable") from None
    except Exception:
        await db.rollback()
        raise
    return out


@dataclasses.dataclass(frozen=True)
class _Read:
    orders: list
    trades: list
    positions: object  # the raw positions reply: parsed only inside the one reconciler (#423)


def _read_zerodha(req: _Request) -> _Read:
    """ONE fresh read of each; any failure refuses the whole return (nothing changes on a half read)."""
    reads = req.session.reads
    try:
        return _Read(reads.fetch_orders(), reads.fetch_trades(), reads.fetch_positions())
    except KiteReadError:
        raise _refuse("gate_broker_unconfirmed") from None


def _iid(text_id: str) -> InstrumentId:
    segment, token = text_id.split(":")
    return InstrumentId(segment, int(token))


@dataclasses.dataclass(frozen=True)
class _World:
    catalogue: Any
    underlying: str
    verdict: rr.Verdict  # the ONE reconciliation of this request (#380-2), read before the open plan closes


async def _reconcile(req: _Request, catalogue: Any, zerodha: _Read) -> rr.Verdict:
    """#380-2 (T3): the reconciler the Execute route also calls, as the "after execution" trigger (Q196): blocking
    mismatches are stored (sticky until a settling resolution, Q222). An open plan whose orders are all final counts
    with Zerodha's fills here already (ADR-110), so the verdict holds after the close below. Unreadable reply ->
    broker unconfirmed; unreadable stored data -> reconciliation required (409); nothing guessed."""
    try:
        return await rr.reconcile_account(req.db, req.user_ref, catalogue, zerodha.positions, zerodha.orders,
                                          at=req.now, clock=req.now_clock, source="after_execution")
    except ra.AttributionError:
        raise _refuse("gate_reconciliation_mismatch") from None
    except (KiteReplyError, ReconciliationError, ValueError):
        raise _refuse("gate_broker_unconfirmed") from None


def _keys(history: Sequence[plans.StoredPlan], world: _World) -> dict[tuple, str]:
    """Every contract the strategy's plans touch -> its trading symbol."""
    return {ep.contract_key(world.catalogue, _iid(o.instrument_id), world.underlying): o.tradingsymbol
            for p in history for o in p.orders}


def _held(history: Sequence[plans.StoredPlan], world: _World) -> dict[tuple, int]:
    """The strategy's stored fills per contract (``held_units``, the same count the reconciler makes)."""
    out: dict[tuple, int] = {}
    for instrument_id, n in ep.held_units(history).items():
        key = ep.contract_key(world.catalogue, _iid(instrument_id), world.underlying)
        out[key] = out.get(key, 0) + n
    return out


def _kind(world: _World, sid: str, key: tuple) -> str | None:
    """Compare's blocking mismatch on ``key`` for this strategy, as its catalogue code."""
    for mismatch in world.verdict.attribution.report.mismatches:
        if sid in mismatch.strategy_ids and any(contract == key for contract, _ in mismatch.difference):
            return rr.MISMATCH_CODES[mismatch.kind]
    return None


def _undecided(world: _World, sid: str, key: tuple) -> str | None:
    """A contract left out of compare because ANOTHER strategy's plan or stored mismatch is unsettled there."""
    attribution = world.verdict.attribution
    entries = (*attribution.pending.get(key, ()), *attribution.unresolved.get(key, ()))
    others = {e.strategy_id for e in entries} | set(attribution.stored.get(key, ()))
    return er.OTHER_UNSETTLED if others - {sid} else None


def _exit_clean(req: _Request, history: Sequence[plans.StoredPlan], world: _World) -> bool:
    """An EXIT reads ``exited`` only when the one reconciliation does not block the strategy, it holds nothing,
    Zerodha holds no outside lots on its contracts (Zerodha still holding units is not an exit), and no other
    strategy's plan or stored mismatch is unsettled on them (Zerodha's units there are unknown, so "Zerodha agrees"
    cannot be read; review round 1 MAJOR 1, kept from the deleted parallel exit check)."""
    sid, attribution = str(req.strategy_id), world.verdict.attribution
    keys = _keys(history, world)
    return (not world.verdict.blocks(req.strategy_id) and not any(attribution.held.get(sid, {}).values())
            and not any(attribution.outside.get(key) for key in keys)
            and not any(_undecided(world, sid, key) for key in keys))


def _final_reason(req: _Request, history: Sequence[plans.StoredPlan], plan: plans.StoredPlan,
                  answer: er.PlanAnswer, world: _World) -> str:
    if plan.action != "EXIT" or answer.state != er.FILLED:
        return answer.state
    return er.EXITED if _exit_clean(req, history, world) else er.FILLED


async def _settle_open_plan(req: _Request, history: tuple[plans.StoredPlan, ...], book: er.TodaysBook,
                            world: _World) -> dict[int, er.PlanAnswer]:
    open_plans = [p for p in history if p.status == "open"]
    if not open_plans:
        return {}
    plan = open_plans[0]
    answer = er.classify(plan, book, req.today)
    if answer.state in (er.WAITING, er.RECONCILE):
        return {plan.plan_number: answer}  # stays open: nothing changes (REQ-057 AC-2)
    reason = _final_reason(req, history, plan, answer, world)
    await plans.close_plan(req.db, req.user_ref, req.strategy_id, plan.plan_number, reason=reason,
                           filled=dict(answer.filled))
    return {}


def _correlation(strategy_id: int, row: Mapping[str, object]) -> str:
    return f"external:{strategy_id}:{row.get('order_id')}:{row.get('status')}:{row.get('filled_quantity')}"


async def _record_externals(req: _Request, book: er.TodaysBook) -> None:
    """ADR-050 item 4(d): every external order recorded once per (order, status, filled) - a replay adds nothing."""
    for row in book.external:
        await order_audit.record_once(req.db, EventType.BROKER_RESPONSE_RECORDED, _correlation(req.strategy_id, row),
                                      row)


def _plan_out(plan: plans.StoredPlan, live: Mapping[int, er.PlanAnswer]) -> dict[str, object]:
    now = live.get(plan.plan_number)
    state = now.state if now is not None else plan.close_reason or er.WAITING
    return {"plan_number": plan.plan_number, "action": plan.action, "state": state,
            "choices": list(er.PARTIAL_CHOICES) if state == er.PARTIAL else [],
            "reason": now.reason if now is not None else None}


def _strategy_state(history: Sequence[plans.StoredPlan], held: Mapping[tuple, int]) -> str:
    """Derived (no status column): ``exited`` when the latest plan that changed position is an EXIT closed exited."""
    if any(p.status == "open" for p in history):
        return "plan_open"
    moved = [p for p in history if p.close_reason not in (None, er.NOTHING_PLACED, plans.UNRESOLVED)]
    if moved and moved[-1].close_reason == er.EXITED:
        return "exited"
    return "holding" if any(held.values()) else "flat"


def _external_out(book: er.TodaysBook) -> list[dict[str, object]]:
    return [{"tag": r["tag"], "order_id": r.get("order_id"), "tradingsymbol": r.get("tradingsymbol"),
             "transaction_type": r.get("transaction_type"), "quantity": r.get("quantity"),
             "filled_quantity": r.get("filled_quantity"), "terminal": r.get("status") in ep.TERMINAL_ORDER_STATUSES}
            for r in book.external]


def _contracts(req: _Request, history: Sequence[plans.StoredPlan], world: _World) -> list[dict[str, object]]:
    """One row per contract the strategy traded, every Zerodha-side number and verdict from the one reconciliation."""
    sid, attribution = str(req.strategy_id), world.verdict.attribution
    held = _held(history, world)
    rows = []
    for key, symbol in sorted(_keys(history, world).items(), key=lambda item: repr(item[0])):
        others = sum(units.get(key, 0) for other, units in attribution.held.items() if other != sid)
        rows.append({"tradingsymbol": symbol, "platform_units": held.get(key, 0),
                     "zerodha_units": attribution.raw_net.get(key, 0), "other_strategies_units": others,
                     "unexplained_units": attribution.outside.get(key, 0), "mismatch": _kind(world, sid, key),
                     "reconciliation_reason": _undecided(world, sid, key)})
    return rows


def _answer(req: _Request, history: tuple[plans.StoredPlan, ...], live: Mapping[int, er.PlanAnswer],
            book: er.TodaysBook, world: _World) -> ReturnOut:
    contracts = _contracts(req, history, world)
    drift = er.drifted(history, book)
    flagged = sum(1 for c in contracts if c["mismatch"] or c["reconciliation_reason"])
    blocked = (bool(drift) or world.verdict.blocks(req.strategy_id)
               or any(a.state == er.RECONCILE for a in live.values()))
    drifted_answer = er.PlanAnswer(er.RECONCILE, {})
    return ReturnOut.model_validate({
        "strategy_id": req.strategy_id, "read_at": req.now,
        "strategy_state": _strategy_state(history, _held(history, world)),
        "plans": [_plan_out(p, {**live, **dict.fromkeys(drift, drifted_answer)}) for p in history],
        "contracts": contracts, "mismatches": flagged + len(drift), "blocked": blocked,
        "external_orders": _external_out(book), "realised_pnl": er.pnl_or_none(book.fills)})


async def _return(req: _Request, underlying: str) -> ReturnOut:
    history = await plans.plans_for(req.db, req.user_ref, req.strategy_id)
    catalogue = await load_catalogue(req.db)
    zerodha = _read_zerodha(req)
    tags = frozenset(o.tag for p in history for o in p.orders)
    try:
        book = rb.read_book(zerodha.orders, zerodha.trades, req.strategy_id, tags)
    except ValueError:  # KiteReplyError included: a row we cannot read is never guessed
        raise _refuse("gate_broker_unconfirmed") from None
    world = _World(catalogue, underlying, await _reconcile(req, catalogue, zerodha))
    live = await _settle_open_plan(req, history, book, world)
    await _record_externals(req, book)
    await order_audit.record_broker_book(req.db, zerodha.orders, zerodha.trades, tags)  # W-103: our orders + trades
    history = await plans.plans_for(req.db, req.user_ref, req.strategy_id)
    return _answer(req, history, live, book, world)


__all__ = ["ReturnOut", "return_from_kite"]
