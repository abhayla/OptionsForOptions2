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
5. the reconciliation rows from the final stored state; the strategy's state and the fills' realised P&L. Other
   strategies are keyed by THEIR own underlying; a contract one of them touches through an open or drifted plan is
   undecidable here (reconciliation required, reason named).
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.audit.catalogue import EventType
from ofo.errors import render
from ofo.instruments.models import ZERODHA, InstrumentId
from sqlalchemy import text

from ofo_app import eligibility_from_zerodha as elig
from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app import execution_return as er
from ofo_app import order_audit
from ofo_app import order_book_store as books
from ofo_app import return_book as rb
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.catalogue_store import load_catalogue
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.kite_reads import KiteReadError, unconfirmed_template
from ofo_app.kite_replies import ContractIndex, KiteReplyError, log_ignored, positions_from_reply
from ofo_app.order_path_switch import require_order_path
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute, dependencies=[Depends(require_order_path)])  # W-121: runs first

_OTHER_STRATEGIES = text(
    "SELECT DISTINCT p.strategy_id FROM public.execution_plans p JOIN public.strategies s ON s.id = p.strategy_id "
    "WHERE s.user_ref = :u AND p.strategy_id <> :s ORDER BY p.strategy_id")
PlanState = Literal["waiting", "filled", "exited", "nothing_placed", "partial", "reconciliation_required",
                    "unresolved_from_positions"]  # the last: a stored close reason (migration 0019, #380 step 2.1)


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
    mismatch: Optional[Literal["recon_missing_platform_position", "recon_side_mismatch",  # noqa: UP045
                               "recon_quantity_mismatch"]]
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
            raise _refuse("gate_broker_not_connected")
        await store.lock_strategy(db, user_ref, strategy_id)  # held to commit: one return closes a plan once
        req = _Request(db, user_ref, strategy_id, session, clocks.now(), await clocks.today_of(db))
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
    net: Mapping[tuple, int]


def _read_zerodha(req: _Request, catalogue: Any) -> _Read:
    """ONE fresh read of each; any failure refuses the whole return (nothing changes on a half read)."""
    reads = req.session.reads
    try:
        orders, trades = reads.fetch_orders(), reads.fetch_trades()
        positions = positions_from_reply(reads.fetch_positions(), ContractIndex.from_catalogue(catalogue))
    except (KiteReadError, KiteReplyError, ValueError) as exc:
        raise _refuse(unconfirmed_template(exc)) from None
    log_ignored(positions, f"return strategy {req.strategy_id}")
    return _Read(orders, trades, positions.net)


def _iid(text_id: str) -> InstrumentId:
    segment, token = text_id.split(":")
    return InstrumentId(segment, int(token))


def _listed(catalogue: Any, instrument_id: str) -> Any:
    """The catalogue entry of a stored contract; one the catalogue no longer resolves is the catalogue refusal, never
    a 500 (an adopted contract has no plan order to fall back on)."""
    entry = catalogue.get(_iid(instrument_id))
    if entry is None:
        raise _refuse("strategy_contract_not_in_catalogue")
    return entry


def _keyed(units: Mapping[str, int], catalogue: Any, underlying: str) -> dict[tuple, int]:
    """``execute_plan.held_units`` (per stored instrument id) -> per reconcile contract key."""
    out: dict[tuple, int] = {}
    for instrument_id, n in units.items():
        _listed(catalogue, instrument_id)
        key = ep.contract_key(catalogue, _iid(instrument_id), underlying)
        out[key] = out.get(key, 0) + n
    return out


async def _others(req: _Request, catalogue: Any, zerodha: _Read) -> tuple[dict[tuple, int], frozenset]:
    """Units every OTHER stored strategy of this user holds, per contract (the same ``held_units``, keyed by THAT
    strategy's underlying), and the contracts it touches through an open or drifted plan (undecidable here: its
    filled units are not known, so they are never counted as 0)."""
    total: dict[tuple, int] = {}
    unknown: set[tuple] = set()
    ids = [int(r[0]) for r in (await req.db.execute(_OTHER_STRATEGIES, {"u": req.user_ref, "s": req.strategy_id}))]
    for other in ids:
        underlying = (await store.load(req.db, req.user_ref, other)).saved.definition.underlying
        history = await plans.plans_for(req.db, req.user_ref, other)
        tags = frozenset(o.tag for p in history for o in p.orders)
        try:
            book = rb.read_book(zerodha.orders, zerodha.trades, other, tags)
        except ValueError:  # that strategy's rows unreadable: never guessed
            raise _refuse("gate_broker_unconfirmed") from None
        unknown.update(ep.contract_key(catalogue, _iid(o.instrument_id), underlying)
                       for o in er.unsettled_orders(history, book))
        adopted = await books.adopted_for(req.db, req.user_ref, other)
        for key, n in _keyed(ep.held_units(history, adopted), catalogue, underlying).items():
            total[key] = total.get(key, 0) + n
    return total, frozenset(unknown)


@dataclasses.dataclass(frozen=True)
class _World:
    catalogue: Any
    underlying: str
    zerodha: _Read
    others: Mapping[tuple, int]
    undecidable: frozenset  # contracts another strategy's open or drifted plan touches
    adopted: tuple  # this strategy's adopted holdings (ADR-096: counted as fills)


def _symbols(history: Sequence[plans.StoredPlan], world: _World) -> dict[tuple, str]:
    """The contracts reconciled for this strategy: every plan-order contract UNION every adopted contract (ADR-096:
    an adopted lot is held like a fill, so Zerodha is compared on it too), one entry per contract key."""
    out: dict[tuple, str] = {}
    for h in world.adopted:
        symbol = _listed(world.catalogue, h.instrument_id).ref(ZERODHA).broker_symbol  # refused before any key read
        out[ep.contract_key(world.catalogue, _iid(h.instrument_id), world.underlying)] = symbol
    out.update({ep.contract_key(world.catalogue, _iid(o.instrument_id), world.underlying): o.tradingsymbol
                for p in history for o in p.orders})
    return out


def _checks(history: Sequence[plans.StoredPlan], world: _World) -> tuple[er.ContractCheck, ...]:
    symbols = _symbols(history, world)
    held = _keyed(ep.held_units(history, world.adopted), world.catalogue, world.underlying)
    return er.reconcile(sorted(symbols, key=repr), held, world.others, world.zerodha.net, world.undecidable)


def _as_closed(plan: plans.StoredPlan, filled: Mapping[str, int]) -> plans.StoredPlan:
    orders = tuple(dataclasses.replace(o, filled_quantity=filled[o.tag]) for o in plan.orders)
    return dataclasses.replace(plan, status="closed", orders=orders)


def _final_reason(history: Sequence[plans.StoredPlan], plan: plans.StoredPlan, answer: er.PlanAnswer,
                  world: _World) -> str:
    """An EXIT filled in full reads ``exited`` only when the strategy, with this plan applied, is flat and Zerodha
    agrees; otherwise ``filled`` and the mismatch is reported."""
    if plan.action != "EXIT" or answer.state != er.FILLED:
        return answer.state
    after = [_as_closed(p, answer.filled) if p.plan_number == plan.plan_number else p for p in history]
    return er.EXITED if er.exit_is_clean(_checks(after, world)) else er.FILLED


async def _settle_open_plan(req: _Request, history: tuple[plans.StoredPlan, ...], book: er.TodaysBook,
                            world: _World) -> dict[int, er.PlanAnswer]:
    open_plans = [p for p in history if p.status == "open"]
    if not open_plans:
        return {}
    plan = open_plans[0]
    answer = er.classify(plan, book, req.today)
    if answer.state in (er.WAITING, er.RECONCILE):
        return {plan.plan_number: answer}  # stays open: nothing changes (REQ-057 AC-2)
    reason = _final_reason(history, plan, answer, world)
    try:  # #313b: the plan's trades are stored with the close, in this transaction
        await plans.close_plan(req.db, req.user_ref, req.strategy_id, plan.plan_number, reason=reason,
                               filled=dict(answer.filled), fills=er.plan_fills(plan, book))
    except plans.PlanStoreError:  # trades that cannot be stored exactly: nothing closes (fail closed, rolled back)
        raise _refuse("gate_broker_unconfirmed") from None
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


def _strategy_state(history: Sequence[plans.StoredPlan], checks: Sequence[er.ContractCheck]) -> str:
    """Derived (no status column): ``exited`` when the latest plan that changed position is an EXIT closed exited."""
    if any(p.status == "open" for p in history):
        return "plan_open"
    moved = [p for p in history if p.close_reason not in (None, er.NOTHING_PLACED, plans.UNRESOLVED)]
    if moved and moved[-1].close_reason == er.EXITED:
        return "exited"
    return "holding" if any(c.platform_units for c in checks) else "flat"


def _external_out(book: er.TodaysBook) -> list[dict[str, object]]:
    return [{"tag": r["tag"], "order_id": r.get("order_id"), "tradingsymbol": r.get("tradingsymbol"),
             "transaction_type": r.get("transaction_type"), "quantity": r.get("quantity"),
             "filled_quantity": r.get("filled_quantity"), "terminal": r.get("status") in ep.TERMINAL_ORDER_STATUSES}
            for r in book.external]


def _answer(req: _Request, history: tuple[plans.StoredPlan, ...], live: Mapping[int, er.PlanAnswer],
            book: er.TodaysBook, world: _World) -> ReturnOut:
    checks = _checks(history, world)
    symbols = _symbols(history, world)
    drift = er.drifted(history, book)
    blocked = bool(drift) or any(c.blocks for c in checks) or any(a.state == er.RECONCILE for a in live.values())
    drifted_answer = er.PlanAnswer(er.RECONCILE, {})
    return ReturnOut.model_validate({
        "strategy_id": req.strategy_id, "read_at": req.now, "strategy_state": _strategy_state(history, checks),
        "plans": [_plan_out(p, {**live, **dict.fromkeys(drift, drifted_answer)}) for p in history],
        "contracts": [{"tradingsymbol": symbols[c.key], "platform_units": c.platform_units,
                       "zerodha_units": c.zerodha_units, "other_strategies_units": c.other_units,
                       "unexplained_units": c.unexplained, "mismatch": c.kind,
                       "reconciliation_reason": c.undecidable} for c in checks],
        "mismatches": sum(1 for c in checks if c.blocks) + len(drift), "blocked": blocked,
        "external_orders": _external_out(book), "realised_pnl": er.pnl_or_none(book.fills)})


async def _return(req: _Request, underlying: str) -> ReturnOut:
    history = await plans.plans_for(req.db, req.user_ref, req.strategy_id)
    catalogue = await load_catalogue(req.db)
    zerodha = _read_zerodha(req, catalogue)
    tags = frozenset(o.tag for p in history for o in p.orders)
    try:
        book = rb.read_book(zerodha.orders, zerodha.trades, req.strategy_id, tags)
    except ValueError:  # KiteReplyError included: a row we cannot read is never guessed
        raise _refuse("gate_broker_unconfirmed") from None
    world = _World(catalogue, underlying, zerodha, *await _others(req, catalogue, zerodha),
                   await books.adopted_for(req.db, req.user_ref, req.strategy_id))
    live = await _settle_open_plan(req, history, book, world)
    await _record_externals(req, book)
    await order_audit.record_broker_book(req.db, zerodha.orders, zerodha.trades, tags)  # W-103: our orders + trades
    history = await plans.plans_for(req.db, req.user_ref, req.strategy_id)
    await store.settle_versions(req.db, req.user_ref, req.strategy_id, history, _broker_share(history, book, world))
    return _answer(req, history, live, book, world)


def _broker_share(history: Sequence[plans.StoredPlan], book: er.TodaysBook, world: _World) -> dict[tuple, int] | None:
    """W-144 (REQ-038 AC-4): this strategy's actual units per contract it traded, the position a proposed version is
    judged by. Where Zerodha agrees with the strategy's own fills (no blocking mismatch) that is its fills: a
    same-direction surplus is outside lots, never this strategy's (ADR-109). Where Zerodha disagrees (shortfall, side)
    the broker wins: Zerodha's net minus every other strategy's units. None - the version is not judged and the
    strategy is flagged - when a contract is undecidable (another strategy's open or drifted plan) or this strategy's
    own book has drifted."""
    checks = _checks(history, world)
    if er.drifted(history, book) or any(c.undecidable for c in checks):
        return None
    return {c.key: c.platform_units if c.kind is None else c.zerodha_units - c.other_units for c in checks}


__all__ = ["ReturnOut", "return_from_kite"]
