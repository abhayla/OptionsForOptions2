"""W-095 Execute route: a saved strategy -> the pre-execution gate -> a read-only Kite basket, the plan stored first.

Spec basis: REQ-073 AC-1 ("Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders
marked read-only"); REQ-073 AC-4 (no order-placement call: nothing here places an order, the user's browser posts the
basket to Kite's page); ADR-050 item 4 "(b) persist the order intent before sending"; ADR-080 (3) (each LIMIT from the
5-level depth); REQ-055 AC-3 (Zerodha's margin figure is authoritative); REQ-060 AC-7 (a position in no strategy blocks
no strategy; a mismatch blocks only the strategy whose contract quantity disagrees).

One request = one transaction, in this order (any refusal rolls back: nothing stored, no plan number consumed):
1. the strategy (404 for a missing or another user's one); 2. Zerodha's order book: the floor plan number of THIS
strategy's tags and any still-open order (refused); ``next_plan_number`` (its lock is held to commit); 2b. W-107: that
same order book (no second Zerodha read) as THIS strategy's ``TodaysBook`` (``return_book.read_book``):
``execution_return.drifted`` on the stored plans refuses with ``gate_reconciliation_mismatch`` before any other check
(``_executable``, positions), ENTRY, EXIT and adjustment alike (REQ-060 AC-6); untagged rows are never read as
drift (AC-7); 3. what the strategy holds = ``ep.held_units`` (ADR-105: the net of filled units over ALL its plans),
the one source of the exit
legs (exactly the net, opposite side), the active legs + hash, the version state and the reconciliation platform side;
an EXIT at net 0 and an ENTRY while held are refused (``_executable``); 4. each leg priced
from its depth; 5. the ``ExecutionContext`` from real sources only; 6. the fresh eligibility registry straight into
``check_pre_execution``; 7. freeze limits; 8. ``checked_basket`` (Zerodha's margin again, inside the basket);
9. ``record_plan`` with the basket's own tags, commit, return the exact form text (``BasketPost``).

Answer states of each outside system (B4 (d)): Zerodha session absent -> 409 broker unconfirmed; any Zerodha read
error (orders, positions, funds, basket margin) -> 409 / the gate's None, nothing stored; an order status word not in
the terminal allow-list -> treated as open (refused); a positions reply the W-091 adapter refuses -> reconciliation
unknown (blocks); no depth / thin depth / off-tick depth / outside a known band -> that leg refused; no band known ->
the gate's own band-unknown block (entry) or exit confirmation (refused here); no list load -> the gate's message;
an unreadable entitlement history -> ``pro_entitled`` None (the gate blocks where it asks).
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal, Optional, Protocol

from fastapi import APIRouter, Depends
from ofo.charges.calculator import ChargeOrder
from ofo.charges.rates import ChargeRates
from ofo.engine import Action, Instrument, Leg
from ofo.engine.product import Product
from ofo.entitlements.engine import access_at
from ofo.entitlements.events import AccessLevel
from ofo.errors import UserFacingError, render
from ofo.errors.explanations import render_explanation
from ofo.execution.basket import BasketRefused, KiteOrder, parse_tag, zerodha_exchange
from ofo.execution.context import (
    EXECUTABLE_VERSION_STATES,
    DataHealth,
    DataInput,
    ExecutionAction,
    ExecutionContext,
    VersionState,
    active_legs_hash,
    product_key,
)
from ofo.execution.cost import basket_cost
from ofo.execution.freeze import freeze_check
from ofo.execution.safety import check_pre_execution
from ofo.instruments.models import ZERODHA, InstrumentId
from ofo.marketdata.health import HealthThresholds
from ofo.money import PAISE
from ofo.timeutil import IST, SESSION_CLOSE, SESSION_OPEN
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from ofo_app import eligibility_from_zerodha as elig
from ofo_app import entitlement_store, live_market, order_audit
from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.basket_post import BasketPost
from ofo_app.catalogue_store import load_catalogue
from ofo_app.checked_basket import checked_basket, is_checked_basket
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.execution_return import drifted
from ofo_app.freeze_store import review_freeze_limits
from ofo_app.kite_margin import BasketOrder, KiteMargin
from ofo_app.kite_reads import KiteReadError, KiteReads
from ofo_app.kite_replies import ContractIndex, KiteReplyError, PositionsRead, log_ignored, positions_from_reply
from ofo_app.return_book import read_book
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import load_charge_rates
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)

ENTRY, EXIT = "ENTRY", "EXIT"
#: the product every basket order carries (``KiteOrder.product``): what an exit's orders are sent with (ADR-080)
BASKET_PRODUCT = Product(KiteOrder.__dataclass_fields__["product"].default)
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
    price: Money  # 2-decimal string ("3.35"), display only
    readonly: bool
    tag: Identifier


class CostOut(ApiModel):
    """W-102 (ADR-097 "a final yes on the exact contract, side, quantity, limit price and cost"): what the basket costs,
    every figure computed on the server (one engine, ADR-008); the browser only shows it."""

    net_premium: Money  # quantity x LIMIT per order, BUY paid (negative), SELL received (positive)
    charges: Optional[Money]  # noqa: UP045 - ofo.charges.calculator at the stored rates; None = no rate set read
    charges_note: Optional[CatalogueText]  # noqa: UP045 - set exactly when charges is None
    funds_available: Optional[Money]  # noqa: UP045 - Zerodha's equity.net from the gate's one read
    margin_required: Optional[Money]  # noqa: UP045 - the gate's margin (ADR-094) from the same read
    figures_read_at: datetime.datetime  # the route clock read right after Zerodha's figures


class ExecuteOut(ApiModel):
    plan_number: int
    tags: list[Identifier]
    basket: BasketPost  # {"url", "api_key", "data"}: the browser POSTs exactly these (basket_post.py)
    orders: list[BasketOrderOut]  # display only
    cost: CostOut


# ---- dependencies (each a seam a test replaces with recorded replies) ----------------------------------------------

class KiteSession(Protocol):
    api_key: str
    reads: KiteReads
    margin: KiteMargin


@dataclass(frozen=True)
class _Session:
    api_key: str
    reads: KiteReads
    margin: KiteMargin


async def get_kite_session() -> Optional[KiteSession]:  # noqa: UP045
    """The owner's Zerodha session (the stored token, as ``owner_margin_client``), or None (not connected)."""
    margin = await live_market.owner_margin_client()
    reads = await live_market.owner_kite_reads()
    if margin is None or reads is None:
        return None
    return _Session(reads[0], reads[1], margin)


class QuoteReader(Protocol):
    def leg_quote(self, instrument_id: InstrumentId, broker_token: str) -> ep.LegQuote | None: ...

    def underlying_price(self, underlying: str) -> tuple[Decimal, datetime.datetime] | None: ...


def _feed_key(instrument_id: InstrumentId) -> str:
    return f"{instrument_id.exchange_segment}:{instrument_id.exchange_token}"  # the live feed's key (kite_provider)


class LiveDepthQuotes:
    """Production: ``live_market.latest_depth`` (W-097; None unless the feed is healthy and the last packet was a full
    frame), read at the server clock, with the feed's last price when it holds one. The live feed carries no circuit
    band, so ``band`` is None here: the route adds Zerodha's own quote band (``_banded``); where that is absent the gate
    blocks an entry leg as band-unknown (never a made-up band)."""

    def __init__(self, clock: Callable[[], datetime.datetime]) -> None:
        self._clock = clock

    def leg_quote(self, instrument_id: InstrumentId, broker_token: str) -> ep.LegQuote | None:
        key = _feed_key(instrument_id)
        depth = live_market.latest_depth(key)
        if depth is None:
            return None
        quote = _feed_quote(key, self._clock())
        if quote is None:
            return None  # no frame time to judge freshness by: the leg is refused, never stamped with the read time
        ltp, at = quote
        return ep.LegQuote(depth, at, ltp, None)

    def underlying_price(self, underlying: str) -> tuple[Decimal, datetime.datetime] | None:
        """The live market context's index quote (``underlying_quote``) and its own time, or None."""
        ctx = live_market.current_context()
        reader = getattr(getattr(ctx, "provider", None), "underlying_quote", None)
        return None if reader is None else price_and_time(reader(underlying))


def price_and_time(quote: object) -> tuple[Decimal, datetime.datetime] | None:
    """A feed quote's last price and its OWN time (the frame's), or None when either is unreadable."""
    ltp, at = getattr(quote, "ltp", None), getattr(quote, "timestamp", None)
    if type(ltp) is not Decimal or not isinstance(at, datetime.datetime):
        return None
    return ltp, at


def _feed_quote(key: str, now: datetime.datetime) -> tuple[Decimal, datetime.datetime] | None:
    """The feed book's quote of the same instrument: its last price and the frame's own time."""
    ctx = live_market.current_context()
    getter = getattr(getattr(getattr(ctx, "provider", None), "book", None), "get", None)
    return None if getter is None else price_and_time(getter(key, now))


def server_clock() -> datetime.datetime:
    return datetime.datetime.now(IST)


def get_execute_clock() -> Callable[[], datetime.datetime]:
    return server_clock


def get_quote_reader() -> QuoteReader:
    return LiveDepthQuotes(server_clock)


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


def _health(times: tuple[datetime.datetime, ...], checked_at: datetime.datetime) -> DataHealth:
    """Each frame time judged on ``checked_at``, a clock read AFTER the quotes were read (never the request-start
    ``req.now``: a tick that arrived while the route read Zerodha is newer than it). A frame up to the clock-skew
    tolerance ahead is fresh; further ahead (a bad clock or packet) or older than ``stale_after`` is STALE."""
    if not times:
        return DataHealth.UNAVAILABLE
    limits = HealthThresholds()
    fresh = all(-limits.clock_skew_tolerance <= checked_at - t <= limits.stale_after for t in times)
    return DataHealth.HEALTHY if fresh else DataHealth.STALE


def _iid(text_id: str) -> InstrumentId:
    segment, token = text_id.split(":")
    return InstrumentId(segment, int(token))


def _plan_orders(basket: Any) -> tuple[plans.PlanOrder, ...]:
    return tuple(plans.PlanOrder(leg_index=parse_tag(o.tag).leg_index, tag=o.tag,
                                 instrument_id=_feed_key(o.instrument_id), tradingsymbol=o.tradingsymbol,
                                 transaction_type=o.transaction_type, quantity=o.quantity, price=o.price)
                 for o in basket.orders)


# ---- the route ------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Request:
    db: Any
    user_ref: str
    strategy_id: int
    action: str
    session: KiteSession
    quotes: QuoteReader
    now: datetime.datetime
    clock: Callable[[], datetime.datetime]
    rates: ChargeRates | None


@router.post("/strategies/{strategy_id}/execute", response_model=ExecuteOut)
async def execute_strategy(  # noqa: PLR0913 - FastAPI dependencies
    strategy_id: int, body: ExecuteIn,
    session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045
    quotes: Annotated[QuoteReader, Depends(get_quote_reader)],
    clock: Annotated[Callable[[], datetime.datetime], Depends(get_execute_clock)],
    db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
    rates: Annotated[Optional[ChargeRates], Depends(load_charge_rates)],  # noqa: UP045
) -> ExecuteOut:
    try:
        stored = await store.load(db, user_ref, strategy_id)  # 404 before anything else
        if session is None:
            raise _refuse("gate_broker_unconfirmed")
        out = await _execute(_Request(db, user_ref, strategy_id, body.action, session, quotes, clock(), clock, rates),
                             stored)
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


async def _reserve_number(req: _Request) -> tuple[int, list[object]]:
    """Zerodha's book first (floor + still-open refusal), then the store's number under the strategy lock. Returns the
    number and the order rows it read (W-107: the drift check reuses them, no second read)."""
    try:
        book = await asyncio.to_thread(req.session.reads.fetch_orders)
        floor, still_open = ep.book_floor(book, req.strategy_id)
    except (KiteReadError, ValueError):
        raise _refuse("gate_broker_unconfirmed") from None
    if still_open:
        raise _refuse("gate_dependencies_unsatisfied")
    try:
        return await plans.next_plan_number(req.db, req.user_ref, req.strategy_id, floor=floor), book
    except plans.PlanStoreError:
        raise _refuse("gate_dependencies_unsatisfied") from None


def _plan_drift(req: _Request, history: tuple[plans.StoredPlan, ...], order_rows: list[object]) -> bool:
    """W-107: True when a closed plan of THIS strategy differs from today's book (still working, or filled other than
    stored at close). Only the strategy's own tags are read; an unreadable row is the broker-unconfirmed refusal."""
    tags = frozenset(o.tag for p in history for o in p.orders)
    try:
        book = read_book(order_rows, (), req.strategy_id, tags)  # drift reads order rows only: no trades needed
    except ValueError:  # KiteReplyError included
        raise _refuse("gate_broker_unconfirmed") from None
    return bool(drifted(history, book))


def _executable(action: str, held: Mapping[str, int]) -> VersionState:
    """ADR-105: an EXIT with nothing held would open a position; an ENTRY while units are held would add to one."""
    state = ep.version_state(action, held)
    allowed = EXECUTABLE_VERSION_STATES[ExecutionAction.EXIT if action == EXIT else ExecutionAction.NEW_ENTRY]
    if state not in allowed:
        if action == EXIT:
            raise _refuse("gate_exit_adds_position")
        raise _refuse("gate_version_not_executable", state=state, allowed=allowed)
    return state


async def _wanted(req: _Request, stored: Any, held: Mapping[str, int]) -> list[ep.LegToPrice]:
    if req.action == EXIT:
        return ep.exit_legs(held, _iid)
    rows = (await req.db.execute(_IDS, {"ids": sorted(set(stored.saved.contract_ids))})).all()
    ids = {int(r.id): InstrumentId(r.exchange_segment, int(r.exchange_token)) for r in rows}
    if any(cid not in ids for cid in stored.saved.contract_ids):
        raise _refuse("strategy_contract_not_in_catalogue")
    entries = stored.saved.entries or (None,) * len(stored.saved.contract_ids)
    return [ep.LegToPrice(ids[cid], leg.action, leg.quantity, None if e is None else e.price)
            for cid, leg, e in zip(stored.saved.contract_ids, stored.saved.definition.legs, entries, strict=True)]


@dataclass(frozen=True)
class _Held:
    """What the strategy holds, from ``ep.held_units`` over every stored plan (the one source), and its version."""

    units: Mapping[str, int]
    state: VersionState
    plan_number: int | None
    history: tuple[plans.StoredPlan, ...]


async def _execute(req: _Request, stored: Any) -> ExecuteOut:
    plan_number, order_rows = await _reserve_number(req)
    history = await plans.plans_for(req.db, req.user_ref, req.strategy_id)
    units = ep.held_units(history)
    if _plan_drift(req, history, order_rows):  # W-107: before any other refusal, so the owner sees the true reason
        raise _refuse("gate_reconciliation_mismatch")
    held = _Held(units, _executable(req.action, units), ep.latest_filled_plan(history), history)
    catalogue = await load_catalogue(req.db)
    underlying = stored.saved.definition.underlying
    try:
        wanted = await _wanted(req, stored, units)
        quote_of = await _banded(req, wanted, catalogue)
        priced = ep.price_legs(str(req.strategy_id), underlying, wanted, catalogue, quote_of)
        context, figures = await _context(req, stored, priced, held, catalogue)
    except ep.LegRefused as refused:
        raise _refuse_with(refused.message) from None
    except (KeyError, ValueError):  # a contract the catalogue cannot resolve: the catalogue refusal, never a 500
        raise _refuse("strategy_contract_not_in_catalogue") from None
    await _gate(req, priced, context, catalogue, underlying)
    basket = await _basket(req, priced, catalogue, plan_number)
    try:
        plan = await plans.record_plan(req.db, req.user_ref, req.strategy_id, plan_number, req.action,
                                       _plan_orders(basket))
    except plans.PlanStoreError:
        raise _refuse("gate_dependencies_unsatisfied") from None
    await order_audit.record_prepared(req.db, plan, actor=req.user_ref)  # same transaction: rolls back with the plan
    return _answer(plan_number, basket, req.session.api_key, cost_out(basket.orders, req.rates, figures))


async def _banded(req: _Request, wanted: list[ep.LegToPrice], catalogue: Any) -> ep.QuoteOf:
    """ADR-080: the day's circuit band of every leg from Zerodha's own quote (``fetch_circuit_bands``, one call, off the
    event loop), never from the depth source. The returned reader gives each leg's depth quote the band Zerodha stated;
    a contract absent from the reply, or a whole-reply ``KiteReadError``, leaves the band None, so the gate blocks an
    ENTRY leg (``gate_price_band_unknown``) and refuses an EXIT that would need confirming (fail closed)."""
    names: dict[InstrumentId, str] = {}
    for want in wanted:
        entry = catalogue.get(want.instrument_id)
        names[want.instrument_id] = (f"{zerodha_exchange(entry.id.exchange_segment)}:"
                                     f"{entry.ref(ZERODHA).broker_symbol}")
    try:
        bands = await asyncio.to_thread(req.session.reads.fetch_circuit_bands, list(names.values()))
    except KiteReadError:
        bands = {}

    def quote_of(instrument_id: InstrumentId, broker_token: str) -> ep.LegQuote | None:
        quote = req.quotes.leg_quote(instrument_id, broker_token)
        if quote is None:
            return None
        return dataclasses.replace(quote, band=bands.get(names.get(instrument_id, "")))

    return quote_of


async def _gate(req: _Request, priced: ep.PricedPlan, context: ExecutionContext, catalogue: Any,
                underlying: str) -> None:
    eligibility = await elig.fresh_registry(req.db, underlying=underlying)
    result = check_pre_execution(priced.strategy, context, catalogue, eligibility, strategy_id=str(req.strategy_id))
    if result.blocked:
        raise _refuse_with(result.failures[0].message)
    if result.requires_confirmation:  # an exit on unchecked data: no confirmation step exists yet (fail closed)
        raise _refuse("gate_data_unhealthy", data_input=DataInput.LEG_PRICES, state=DataHealth.STALE)


async def _basket(req: _Request, priced: ep.PricedPlan, catalogue: Any, plan_number: int) -> Any:
    limits = await review_freeze_limits(req.db, priced.plan)
    today = req.now.astimezone(IST).date()
    frozen = freeze_check(priced.plan, limits, today=today)
    if frozen.blocks:
        raise _refuse_with(frozen.blocks[0].message)
    try:
        basket = await asyncio.to_thread(checked_basket, priced.plan, catalogue, plan_number,
                                         margin_client=req.session.margin,
                                         freeze_check=lambda p: freeze_check(p, limits, today=today))
    except BasketRefused as exc:
        raise _refuse_with(exc.user_message or render("gate_margin_unconfirmed")) from None
    if not is_checked_basket(basket):  # the one production path to a basket
        raise TypeError("checked_basket returned something other than its sealed basket")
    return basket


@dataclass(frozen=True)
class Figures:
    """Zerodha's funds and the gate's margin from ``_zerodha_margin``'s ONE read (None = not confirmed), and the route
    clock read right after it."""

    funds_available: Decimal | None
    margin_required: Decimal | None
    read_at: datetime.datetime


def _paise(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(PAISE, rounding=ROUND_HALF_UP) + 0


def cost_out(orders: Any, rates: ChargeRates | None, figures: Figures) -> CostOut:
    """The basket's cost from its own sealed orders (side, quantity, LIMIT, segment) through the one domain function
    (``ofo.execution.cost.basket_cost``), quantized to the paisa only here, at the API boundary. No rates -> charges
    None plus the catalogue note, never a default rate set."""
    cost = basket_cost([ChargeOrder(o.instrument_id.exchange_segment, o.transaction_type, o.quantity, o.price)
                        for o in orders], rates)
    note = render_explanation("execute_cost_charges_not_included") if cost.charges is None else None
    return CostOut.model_validate({
        "net_premium": _paise(cost.net_premium), "charges": _paise(cost.charges), "charges_note": note,
        "funds_available": _paise(figures.funds_available), "margin_required": _paise(figures.margin_required),
        "figures_read_at": figures.read_at})


def _answer(plan_number: int, basket: Any, api_key: str, cost: CostOut) -> ExecuteOut:
    return ExecuteOut.model_validate({
        "plan_number": plan_number, "tags": [o.tag for o in basket.orders], "basket": BasketPost.of(basket, api_key),
        "orders": [{"exchange": o.exchange, "tradingsymbol": o.tradingsymbol, "transaction_type": o.transaction_type,
                    "order_type": o.order_type, "product": o.product, "variety": o.variety, "quantity": o.quantity,
                    "price": o.price.quantize(PAISE), "readonly": o.readonly, "tag": o.tag}
                   for o in basket.orders],
        "cost": cost})


# ---- the ExecutionContext, one real source per field ---------------------------------------------------------------

async def _positions(req: _Request, catalogue: Any) -> PositionsRead | None:
    """Zerodha's positions reply, read once per request; unreadable -> None (reconciliation unknown, products
    unread: both block)."""
    try:
        reply = await asyncio.to_thread(req.session.reads.fetch_positions)
        read = positions_from_reply(reply, ContractIndex.from_catalogue(catalogue))
    except (KiteReadError, KiteReplyError, ValueError):
        return None
    log_ignored(read, f"execute strategy {req.strategy_id}")
    return read


def _reconciliation(req: _Request, held: _Held, positions: PositionsRead | None, catalogue: Any,
                    underlying: str) -> frozenset[str] | None:
    """REQ-060 AC-7 through ``ep.strategy_blocked``: PLATFORM side = ``held.units`` (all plans' net) per reconcile
    key; an unreadable positions reply is unknown (None blocks)."""
    if positions is None:
        return None
    platform: dict[tuple, int] = {}
    for contract, units in held.units.items():
        key = ep.contract_key(catalogue, _iid(contract), underlying)
        platform[key] = platform.get(key, 0) + units
    blocked = ep.strategy_blocked(positions.net, platform)
    return frozenset({str(req.strategy_id)}) if blocked else frozenset()


def _margin_orders(priced: ep.PricedPlan, catalogue: Any) -> list[BasketOrder]:
    out = []
    for p in priced.plan.legs:
        (entry,) = catalogue.entries_for_broker_symbol(ZERODHA, p.contract)
        out.append(BasketOrder(zerodha_exchange(entry.id.exchange_segment), p.contract, p.leg.action.value,
                               BASKET_PRODUCT.value, "LIMIT", p.leg.quantity, p.leg.entry_price))
    return out


async def _zerodha_margin(req: _Request, priced: ep.PricedPlan,
                          catalogue: Any) -> tuple[Decimal | None, Decimal | None]:
    orders = _margin_orders(priced, catalogue)
    try:
        available = await asyncio.to_thread(KiteMargin.fetch_available_funds, req.session.margin)
        basket = await asyncio.to_thread(KiteMargin.fetch_basket_margin, req.session.margin, orders)
    except Exception:  # noqa: BLE001 - any failure to read Zerodha's figures is "not confirmed" (None blocks)
        return None, None
    return available, basket.required_total


async def _pro_entitled(req: _Request, db_now: datetime.datetime) -> bool | None:
    """Pro at the DATABASE clock (ADR-023): a grant's ``granted_at`` is stamped by the database, so it is judged on
    that clock, never on the request's market clock ``req.now`` (a pinned or skewed request clock would read a grant
    made moments ago as "not yet")."""
    try:
        ledger = await entitlement_store.load(req.db, req.user_ref)
    except entitlement_store.EntitlementStoreError:
        return None
    return access_at(ledger, db_now).level is AccessLevel.PRO


def _list_health(loaded: datetime.datetime | None, db_now: datetime.datetime) -> DataHealth:
    """Instrument-list freshness on the database clock's own India date: ``last_seen_at`` is stamped by
    ``clock_timestamp()``, so both sides of the comparison come from the same clock."""
    if loaded is None:
        return DataHealth.UNAVAILABLE
    same_day = loaded.astimezone(IST).date() == db_now.astimezone(IST).date()
    return DataHealth.HEALTHY if same_day else DataHealth.STALE


async def _data_health(req: _Request, priced: ep.PricedPlan, underlying: str,
                       db_now: datetime.datetime) -> dict[DataInput, DataHealth]:
    spot = req.quotes.underlying_price(underlying)
    listing = _list_health(await elig.list_loaded_at(req.db), db_now)
    checked_at = req.clock()  # read after every quote (legs priced earlier, the index just now): the judging clock
    return {DataInput.LEG_PRICES: _health(priced.quote_times, checked_at),
            DataInput.UNDERLYING_PRICE: DataHealth.UNAVAILABLE if spot is None else _health((spot[1],), checked_at),
            DataInput.INSTRUMENT_LIST: listing}


_NO_ACTIVE_LEGS: Mapping[str, None] = {"active_legs": None, "active_version_id": None, "active_legs_hash": None,
                                       "active_products": None, "exit_products": None}


def held_products(legs: tuple[Leg, ...], symbols: Mapping[tuple, str],
                  positions: PositionsRead | None) -> dict[tuple, Product]:
    """ADR-080 (1): each held contract's product as Zerodha's positions reply reports it. A contract with no row, an
    unread product, or rows of two products is left out, so the gate blocks its exit (never a guessed NRML)."""
    out: dict[tuple, Product] = {}
    for leg in legs:
        key = product_key(leg)
        seen = {line.product for line in (positions.lines if positions else ()) if line.contract == symbols.get(key)}
        (only,) = seen if len(seen) == 1 else (None,)
        if isinstance(only, Product):
            out[key] = only
    return out


def _exit_fields(sid: str, held: _Held, priced: ep.PricedPlan, positions: PositionsRead | None,
                 catalogue: Any) -> dict[str, Any]:
    """The held position as the gate's active legs: the NET of all plans (``held.units``), its version = the latest
    plan with a fill, hashed by the domain function; products from Zerodha (held) and the basket (exit)."""
    if not held.units or held.plan_number is None:
        return dict(_NO_ACTIVE_LEGS)
    prices = {o.instrument_id: o.price for p in sorted(held.history, key=lambda p: p.plan_number) for o in p.orders
              if o.filled_quantity}
    legs, symbols = [], {}
    for contract, units in sorted(held.units.items()):
        entry = catalogue.get(_iid(contract))
        c = entry.contract
        leg = Leg(Action.BUY if units > 0 else Action.SELL, Instrument(c.instrument_type), c.strike, c.expiry,
                  abs(units), prices[contract])
        legs.append(leg)
        symbols[product_key(leg)] = entry.ref(ZERODHA).broker_symbol
    version = f"plan-{held.plan_number}"
    return {"active_legs": tuple(legs), "active_version_id": version,
            "active_legs_hash": active_legs_hash(sid, version, tuple(legs)),
            "active_products": held_products(tuple(legs), symbols, positions),
            "exit_products": {product_key(leg): BASKET_PRODUCT for leg in priced.strategy.legs}}


async def _context(req: _Request, stored: Any, priced: ep.PricedPlan, held: _Held,
                   catalogue: Any) -> tuple[ExecutionContext, Figures]:
    sid, underlying = str(req.strategy_id), stored.saved.definition.underlying
    available, required = await _zerodha_margin(req, priced, catalogue)
    figures = Figures(available, required, req.clock())  # the same one read, shown in the reply (W-102)
    positions = await _positions(req, catalogue)
    is_exit = req.action == EXIT
    db_now = await elig.database_now(req.db)  # the clock that stamped the grants and the list load (ADR-023)
    return ExecutionContext(
        strategy_id=sid, version_id=f"revision-{stored.revision}", actor="user", underlying=underlying,
        action=ExecutionAction.EXIT if is_exit else ExecutionAction.NEW_ENTRY, as_of=req.now,
        market_open=market_open(req.now),
        broker_connected=True,  # today's order book was just read with the stored session (else refused above)
        session_valid=True,  # the same read: Zerodha accepted the session's token
        pro_entitled=await _pro_entitled(req, db_now),
        version_state=held.state,  # derived from the net of all plans (ep.version_state), never hard-coded
        rules_valid=True if stored.saved.definition.rules_ref is None else None,  # no rules: nothing to validate
        dependencies_satisfied=True,  # no open basket at Zerodha and no open stored plan (both refused above)
        data_health=await _data_health(req, priced, underlying, db_now),
        margin_available=available, margin_required=required,
        reconciliation_blocked_strategy_ids=_reconciliation(req, held, positions, catalogue, underlying),
        price_bands=priced.price_bands,
        **(_exit_fields(sid, held, priced, positions, catalogue) if is_exit else _NO_ACTIVE_LEGS),
    ), figures


__all__ = ["BASKET_PRODUCT", "CostOut", "ExecuteIn", "ExecuteOut", "Figures", "LiveDepthQuotes", "cost_out",
           "get_execute_clock", "get_kite_session", "get_quote_reader", "held_products", "market_open",
           "price_and_time"]
