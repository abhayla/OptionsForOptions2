"""W-095 Execute route: a saved strategy -> the pre-execution gate -> a read-only Kite basket, the plan stored first.

Spec basis: REQ-073 AC-1 ("Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders
marked read-only"); REQ-073 AC-4 (no order-placement call: nothing here places an order, the user's browser posts the
basket to Kite's page); ADR-050 item 4 "(b) persist the order intent before sending"; ADR-080 (3) (each LIMIT from the
5-level depth); REQ-055 AC-3 (Zerodha's margin figure is authoritative).

One request = one transaction, in this order (any refusal rolls back: nothing stored, no plan number consumed):
1. the strategy (404 for a missing or another user's one); 2. Zerodha's order book: the floor plan number of THIS
strategy's tags and any still-open order (refused); ``next_plan_number`` (its lock is held to commit); 3. EXIT: the
held legs = the orders of the latest plan closed ``filled`` when it is an ENTRY (none -> refused); 4. each leg priced
from its depth quote; 5. the ``ExecutionContext`` from real sources only (table in the W-095 report); 6. the fresh
eligibility registry straight into ``check_pre_execution``; 7. freeze limits; 8. ``checked_basket`` (Zerodha's margin
again, inside the basket); 9. ``record_plan`` with the basket's own tags, commit, return.

Answer states of each outside system (B4 (d)): Zerodha session absent -> 409 broker unconfirmed; any Zerodha read
error (orders, positions, funds, basket margin) -> 409, nothing stored; an order status word not in the terminal
allow-list -> treated as open (refused); a positions reply the W-091 adapter refuses -> reconciliation unknown
(blocks); no quote / thin depth / off-tick depth / outside the band -> that leg refused; no list load -> every leg
unconfirmed (the gate's own message).
"""
from __future__ import annotations

import datetime
import functools
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, Protocol

from fastapi import APIRouter, Depends
from ofo.engine import Action, Instrument, Leg
from ofo.engine.product import Product
from ofo.errors import UserFacingError, render
from ofo.execution.basket import BasketRefused, KiteBasket, zerodha_exchange
from ofo.execution.context import (
    DataHealth,
    DataInput,
    ExecutionAction,
    ExecutionContext,
    VersionState,
    active_legs_hash,
    product_key,
)
from ofo.execution.freeze import freeze_check
from ofo.execution.safety import check_pre_execution
from ofo.instruments.models import ZERODHA, InstrumentId
from ofo.marketdata.health import HealthThresholds
from ofo.timeutil import IST, SESSION_CLOSE, SESSION_OPEN
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from ofo_app import eligibility_from_zerodha as elig
from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app import live_market
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.catalogue_store import load_catalogue
from ofo_app.checked_basket import checked_basket
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.freeze_store import review_freeze_limits
from ofo_app.kite_margin import BasketOrder, KiteMargin, urllib_transport
from ofo_app.kite_reads import KiteReadError, KiteReads
from ofo_app.kite_replies import ContractIndex, KiteReplyError, positions_from_reply
from ofo_app.outcome_margin import CALL_TIMEOUT_SECONDS
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)

FILLED = "filled"
_IDS = text("SELECT id, exchange_segment, exchange_token FROM public.catalogue_contracts "
            "WHERE id = ANY(CAST(:ids AS BIGINT[]))")


class ExecuteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["ENTRY", "EXIT"]


class BasketOrderOut(ApiModel):
    exchange: Identifier
    tradingsymbol: Identifier
    transaction_type: Literal["BUY", "SELL"]
    order_type: Literal["LIMIT"]
    product: Literal["NRML"]
    variety: Literal["regular"]
    quantity: int
    price: Money  # 2-decimal string ("3.35")
    readonly: bool
    tag: Identifier


class ExecuteOut(ApiModel):
    plan_number: int
    tags: list[Identifier]
    api_key: Identifier
    orders: list[BasketOrderOut]


# ---- dependencies (each a seam a test replaces with recorded replies) ----------------------------------------------

class KiteSession(Protocol):
    api_key: str
    reads: KiteReads
    margin: KiteMargin


class _Session:
    def __init__(self, api_key: str, reads: KiteReads, margin: KiteMargin) -> None:
        self.api_key, self.reads, self.margin = api_key, reads, margin


async def get_kite_session() -> Optional[KiteSession]:  # noqa: UP045
    """The owner's Zerodha session (the stored token, as ``owner_margin_client``), or None (not connected)."""
    margin = await live_market.owner_margin_client()
    market = live_market._current
    if margin is None or market is None or market._config is None:
        return None
    token = await market._stored_token(market._config)
    if token is None:
        return None
    transport = functools.partial(urllib_transport, timeout=CALL_TIMEOUT_SECONDS)
    return _Session(market._config.api_key,
                    KiteReads(api_key=market._config.api_key, access_token=token, transport=transport),
                    margin)


class QuoteReader(Protocol):
    def leg_quote(self, broker_token: str) -> Mapping[str, object] | None: ...

    def underlying_price(self, underlying: str) -> tuple[Decimal, datetime.datetime] | None: ...


class _NoQuotes:
    """Production today: the live feed keeps best bid/ask only, never Kite's 5-level depth (kite_provider F-29), and
    no REST quote call is on the allow-list, so there is no depth source: every leg is refused (never a made-up price)."""

    def leg_quote(self, broker_token: str) -> None:
        return None

    def underlying_price(self, underlying: str) -> None:
        return None


def get_quote_reader() -> QuoteReader:
    return _NoQuotes()


def server_clock() -> datetime.datetime:
    return datetime.datetime.now(IST)


def get_execute_clock() -> Callable[[], datetime.datetime]:
    return server_clock


# ---- helpers --------------------------------------------------------------------------------------------------------

def _refuse(template: str, **slots: object) -> StrategyRefused:
    return StrategyRefused(template, Failure.CONFLICT, message=render(template, **slots))


def _refuse_with(message: UserFacingError) -> StrategyRefused:
    return StrategyRefused("gate_dependencies_unsatisfied", Failure.CONFLICT, message=message)


def market_open(now: datetime.datetime) -> bool:
    """Weekday inside the session (ofo/timeutil). No holiday calendar exists yet: a holiday reads as open and Zerodha
    refuses the order on its page (reported gap)."""
    local = now.astimezone(IST)
    return local.weekday() < 5 and SESSION_OPEN <= local.time() < SESSION_CLOSE


def _health(times: tuple[datetime.datetime, ...], now: datetime.datetime) -> DataHealth:
    if not times:
        return DataHealth.UNAVAILABLE
    stale_after = HealthThresholds().stale_after
    return DataHealth.HEALTHY if all(datetime.timedelta(0) <= now - t <= stale_after for t in times) \
        else DataHealth.STALE


async def _instrument_ids(db: Any, contract_ids: list[int]) -> dict[int, InstrumentId]:
    rows = (await db.execute(_IDS, {"ids": sorted(set(contract_ids))})).all()
    return {int(r.id): InstrumentId(r.exchange_segment, int(r.exchange_token)) for r in rows}


def _held(stored: list[Any]) -> list[Any]:
    """The orders the strategy holds: those of the latest plan closed ``filled``, when that plan is an ENTRY."""
    filled = [p for p in stored if p.closed_reason == FILLED]
    if not filled:
        return []
    latest = max(filled, key=lambda p: p.plan_number)
    return list(latest.orders) if latest.action == "ENTRY" else []


def _plan_orders(basket: KiteBasket) -> list[Any]:
    return [plans.PlanOrder(tag=o.tag, exchange=o.exchange, tradingsymbol=o.tradingsymbol, side=o.transaction_type,
                            quantity=o.quantity, price=o.price) for o in basket.orders]


# ---- the route ------------------------------------------------------------------------------------------------------

@router.post("/strategies/{strategy_id}/execute", response_model=ExecuteOut)
async def execute_strategy(
    strategy_id: int, body: ExecuteIn,
    session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045
    quotes: Annotated[QuoteReader, Depends(get_quote_reader)],
    clock: Annotated[Callable[[], datetime.datetime], Depends(get_execute_clock)],
    db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
) -> ExecuteOut:
    try:
        out = await _execute(db, user_ref, strategy_id, body.action, session, quotes, clock)
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


async def _execute(db: Any, user_ref: str, strategy_id: int, action: str, session: KiteSession | None,
                   quotes: QuoteReader, clock: Callable[[], datetime.datetime]) -> ExecuteOut:
    stored = await store.load(db, user_ref, strategy_id)  # 404 before anything else
    sid = str(strategy_id)
    if session is None:
        raise _refuse("gate_broker_unconfirmed")
    try:
        book = session.reads.fetch_orders()
        floor, still_open = ep.book_floor(book, strategy_id)
    except (KiteReadError, ValueError):
        raise _refuse("gate_broker_unconfirmed") from None
    if still_open:
        raise _refuse("gate_dependencies_unsatisfied")
    try:
        plan_number = await plans.next_plan_number(db, user_ref, strategy_id, floor=floor)
        history = await plans.plans_for(db, user_ref, strategy_id)
    except plans.PlanStoreError:
        raise _refuse("gate_dependencies_unsatisfied") from None

    catalogue = await load_catalogue(db)
    underlying = stored.saved.definition.underlying
    held_orders = _held(history)
    if action == "ENTRY":
        ids = await _instrument_ids(db, list(stored.saved.contract_ids))
        entries = stored.saved.entries or (None,) * len(stored.saved.contract_ids)
        wanted = [ep.LegToPrice(ids[cid], leg.action, leg.quantity, None if e is None else e.price)
                  for cid, leg, e in zip(stored.saved.contract_ids, stored.saved.definition.legs, entries,
                                         strict=True)]
    else:
        if not held_orders:
            raise _refuse("gate_exit_unverified")
        wanted = []
        for o in held_orders:
            (entry,) = catalogue.entries_for_broker_symbol(ZERODHA, o.tradingsymbol)
            wanted.append(ep.LegToPrice(entry.id, Action.SELL if o.side == "BUY" else Action.BUY, o.quantity, None))
    try:
        priced = ep.price_legs(sid, underlying, wanted, catalogue, quotes.leg_quote)
    except ep.LegRefused as refused:
        raise _refuse_with(refused.message) from None

    now = clock()
    context = await _context(db, sid, stored, action, priced, held_orders, history, catalogue, session, quotes, now)
    eligibility = await elig.fresh_registry(db, underlying=underlying)
    result = check_pre_execution(priced.strategy, context, catalogue, eligibility, strategy_id=sid)
    if result.blocked:
        raise _refuse_with(result.failures[0].message)
    if result.requires_confirmation:  # an exit on stale data: no confirmation step exists yet, so refuse (fail closed)
        raise _refuse("gate_data_unhealthy", data_input=DataInput.LEG_PRICES, state=DataHealth.STALE)
    limits = await review_freeze_limits(db, priced.plan)
    today = now.astimezone(IST).date()
    frozen = freeze_check(priced.plan, limits, today=today)
    if frozen.blocks:
        raise _refuse_with(frozen.blocks[0].message)
    try:
        basket = checked_basket(priced.plan, catalogue, plan_number, margin_client=session.margin,
                                freeze_check=lambda p: freeze_check(p, limits, today=today))
    except BasketRefused as exc:
        raise _refuse_with(exc.user_message or render("gate_margin_unconfirmed")) from None
    assert type(basket) is KiteBasket  # noqa: S101 - the one production path to a basket
    try:
        await plans.record_plan(db, user_ref, strategy_id, plan_number, action, _plan_orders(basket))
    except plans.PlanStoreError:
        raise _refuse("gate_dependencies_unsatisfied") from None
    return ExecuteOut.model_validate({
        "plan_number": plan_number, "tags": [o.tag for o in basket.orders], "api_key": session.api_key,
        "orders": [{"exchange": o.exchange, "tradingsymbol": o.tradingsymbol, "transaction_type": o.transaction_type,
                    "order_type": o.order_type, "product": o.product, "variety": o.variety, "quantity": o.quantity,
                    "price": o.price.quantize(Decimal("0.01")), "readonly": o.readonly, "tag": o.tag}
                   for o in basket.orders]})


async def _context(db: Any, sid: str, stored: Any, action: str, priced: ep.PricedPlan, held_orders: list[Any],
                   history: list[Any], catalogue: Any, session: KiteSession, quotes: QuoteReader,
                   now: datetime.datetime) -> ExecutionContext:
    underlying = stored.saved.definition.underlying
    # Reconciliation: Zerodha's positions vs what the stored filled plans say this strategy holds.
    held_legs, held_units = [], {}
    for o in held_orders:
        (entry,) = catalogue.entries_for_broker_symbol(ZERODHA, o.tradingsymbol)
        c = entry.contract
        leg = Leg(Action(o.side), Instrument(c.instrument_type), c.strike, c.expiry, o.quantity, o.price)
        held_legs.append(leg)
        key = ep.contract_key(catalogue, entry.id, underlying)
        held_units[key] = held_units.get(key, 0) + (o.quantity if o.side == "BUY" else -o.quantity)
    contracts = [(underlying, leg.instrument, None if leg.strike is None else leg.strike, leg.expiry)
                 for leg in priced.strategy.legs]
    try:
        positions = positions_from_reply(session.reads.fetch_positions(), ContractIndex.from_catalogue(catalogue))
        blocked: frozenset[str] | None = frozenset({sid}) if ep.broker_mismatch(positions.net, held_units,
                                                                                 contracts) else frozenset()
    except (KiteReadError, KiteReplyError, ValueError):
        blocked = None  # unknown: the gate blocks
    try:
        available = KiteMargin.fetch_available_funds(session.margin)
        required = KiteMargin.fetch_basket_margin(session.margin, _margin_orders(priced, catalogue)).required_total
    except Exception:  # noqa: BLE001 - any failure to read Zerodha's figures is "not confirmed" (None blocks)
        available = required = None
    spot = quotes.underlying_price(underlying)
    loaded = await elig._loaded_at(db)
    is_exit = action == "EXIT"
    active_version = None
    if is_exit:
        filled = max((p for p in history if p.closed_reason == FILLED), key=lambda p: p.plan_number)
        active_version = f"plan-{filled.plan_number}"
    products = {product_key(leg): Product.NRML for leg in held_legs} if is_exit else None
    return ExecutionContext(
        strategy_id=sid, version_id=f"revision-{stored.revision}", actor="user", underlying=underlying,
        action=ExecutionAction.EXIT if is_exit else ExecutionAction.NEW_ENTRY, as_of=now,
        market_open=market_open(now),
        broker_connected=True,  # today's order book was just read with the stored session (else refused above)
        session_valid=True,  # the same read: Zerodha accepted the session's token
        pro_entitled=None,  # no entitlement source wired here; the gate asks it only for a risk-adding adjustment
        version_state=VersionState.ACTIVE,  # the strategy's current stored revision is the version executed
        rules_valid=True if stored.saved.definition.rules_ref is None else None,  # no rules: nothing to validate
        dependencies_satisfied=True,  # no open basket at Zerodha and no open stored plan (both refused above)
        data_health={
            DataInput.LEG_PRICES: _health(priced.quote_times, now),
            DataInput.UNDERLYING_PRICE: DataHealth.UNAVAILABLE if spot is None else _health((spot[1],), now),
            DataInput.INSTRUMENT_LIST: DataHealth.UNAVAILABLE if loaded is None
            else (DataHealth.HEALTHY if loaded.astimezone(IST).date() == now.astimezone(IST).date()
                  else DataHealth.STALE),
        },
        margin_available=available, margin_required=required,
        reconciliation_blocked_strategy_ids=blocked,
        active_legs=tuple(held_legs) if is_exit else None,
        active_version_id=active_version,
        active_legs_hash=active_legs_hash(sid, active_version, tuple(held_legs)) if is_exit else None,
        active_products=products, exit_products=products,
        price_bands=priced.price_bands,
    )


def _margin_orders(priced: ep.PricedPlan, catalogue: Any) -> list[BasketOrder]:
    out = []
    for p in priced.plan.legs:
        (entry,) = catalogue.entries_for_broker_symbol(ZERODHA, p.contract)
        out.append(BasketOrder(zerodha_exchange(entry.id.exchange_segment), p.contract, p.leg.action.value, "NRML",
                               "LIMIT", p.leg.quantity, p.leg.entry_price))
    return out


__all__ = ["ExecuteIn", "ExecuteOut", "get_execute_clock", "get_kite_session", "get_quote_reader",
           "market_open", "router"]
