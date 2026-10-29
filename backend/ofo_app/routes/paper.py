"""GET /paper/strategies, GET /paper/strategies/{id}, POST /paper/strategies/{id}/orders: the paper book (GC-TP 1b).

Spec basis: REQ-109 AC-1 (typed paper prices), AC-4 ("The one engine derives the net position per contract from the
orders"), AC-5 (a stale or missing price pauses unbooked and total); ADR-207 (paper trading the Sensibull Draft
Portfolio way, Net Positions | Orderbook, screens 274-279); ADR-008 (the browser formats nothing: every money field
goes out as an exact Decimal string beside the server's own text).

- The figures come only from ofo.tracking.orderbook.net_positions over the stored orders (paper_store). This module
  adds no arithmetic of its own. An average that does not divide out evenly is exact in the engine and SHOWN rounded to
  the paisa (``average`` and ``average_text``); booked / unbooked / total are the engine's exact values.
- Prices of open contracts come from the same market context as the tracking routes, through
  ofo_app.tracked_contracts.resolve (a stored contract id reaches a feed key only there). A contract that is not live,
  or whose price is stale or missing, has no unbooked figure, and the strategy's unbooked and total are absent with
  the pause reason (AC-5). Booked is always known.
- POST takes typed prices (AC-1): each must be above 0 and a multiple of 0.05; an exit may not exceed the open
  quantity; only the kinds open, add and exit are accepted from a request (settle and stop are server-only). All
  orders of one call are stored in one transaction (paper_store.place) or none are.
- Answer states: no such strategy or another user's -> 404; a strategy with no orders -> 404 on GET; an empty order
  list, a bad price or kind -> 422 with the reason text.
- This module imports nothing from the order path (tests_app/test_paper_order_door.py walks its import graph).
The user comes from the session (``current_user_ref``), never from the request.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.engine.book_totals import book_totals
from ofo.engine.extremes import UNLIMITED, ContractTerms, ExtremesReason, book_extremes
from ofo.engine.legs import Instrument
from ofo.errors.explanations import render_explanation, restore_explanation
from ofo.instruments.models import FUTURE_TYPE
from ofo.limits import INTEGER_MAX
from ofo.money import PAISE
from ofo.outcome import read_snapshot
from ofo.outcome.price_text import price_text
from ofo.strategy import stored_form as sf
from ofo.strategy.definition import describe_contract
from ofo.tracking import paper, paper_decay
from ofo.tracking.orderbook import NetPosition, PaperOrder, is_typed_price, net_positions
from pydantic import BaseModel, ConfigDict, Field

from ofo_app import paper_monitor, paper_store, paper_trigger_store, tracked_contracts
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.live_push import LiveFeed
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import AnswerClock, MarketContext, feed_scope, get_answer_clock, get_market_context
from ofo_app.routes.planned_entry import get_live_feed, hold_until_priced
from ofo_app.routes.strategies import StrategyRefused, refused_answer
from ofo_app.underlying import Underlying

router = APIRouter(route_class=ClosedRoute)

#: The order kinds a request may carry; settle and stop are written by the server only (ADR-207).
REQUEST_KINDS = ("open", "add", "exit")
RequestKind = Literal["open", "add", "exit"]
BookState = Literal["LIVE", "PAUSED", "NOT_CONNECTED", "EXITED"]
SIGNED_PAISA = "summary_paisa_signed"
#: GC-TP step 3a: the text of a side with no bound (a net short call above every strike); existing catalogue words.
NO_FIXED_LIMIT = "summary_reward_risk_none"
Extreme = Money | Literal["unlimited"] | None


class PaperOrderIn(BaseModel):
    """One typed paper order (REQ-109 AC-1). The price is checked by the route (its own reason text), not here."""
    model_config = ConfigDict(extra="forbid")
    contract_id: int = Field(gt=0, le=INTEGER_MAX)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, le=INTEGER_MAX, description="units (lots x lot size)")
    price: Decimal = Field(allow_inf_nan=False)
    kind: RequestKind


class PaperOrdersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orders: list[PaperOrderIn] = Field(min_length=1, max_length=64)


class PaperNetOut(ApiModel):
    """One contract's net position (screens 274-279: Lots / Avg / LTP / Booked / Unbooked)."""
    contract_id: int
    contract_text: CatalogueText
    instrument: Literal["CE", "PE", "FUT"]
    strike: Money | None
    expiry: datetime.date
    net_quantity: int  # signed: above 0 long, below 0 short, 0 flat
    average: Money | None  # rounded to the paisa for display; None when flat
    average_text: CatalogueText | None
    ltp: Money | None  # the live price; None when flat or not live
    ltp_text: CatalogueText | None
    price_state: paper.LegState | None  # None when flat
    price_at: datetime.datetime | None
    booked: Money
    booked_text: CatalogueText
    unbooked: Money | None  # None (never 0) when open and not live
    unbooked_text: CatalogueText | None
    total: Money | None
    total_text: CatalogueText | None


class PaperOrderOut(ApiModel):
    """One row of the orderbook: time, side, contract text, quantity, price, kind."""
    id: int
    placed_at: datetime.datetime
    side: Literal["BUY", "SELL"]
    contract_id: int
    contract_text: CatalogueText
    quantity: int
    price: Money
    price_text: CatalogueText
    kind: Literal["open", "add", "exit", "settle", "stop"]


class PaperFigures(ApiModel):
    state: BookState
    pause_reason: paper.PauseReason | None
    booked: Money
    unbooked: Money | None
    total: Money | None
    booked_text: CatalogueText
    unbooked_text: CatalogueText | None
    total_text: CatalogueText | None
    positions: list[PaperNetOut]


class PaperBookOut(PaperFigures):
    """GET /paper/strategies/{id} and the answer of POST .../orders."""
    strategy_id: int
    name: CatalogueText  # REQ-134: quoted user text
    underlying: Underlying
    answered_at: datetime.datetime
    orders: list[PaperOrderOut]
    # GC-TP step 3a (REQ-109 AC-9, Drafts Mode summary 278-279): ofo.engine.extremes; absent with extremes_reason
    profit_left: Extreme
    loss_left: Extreme
    max_profit: Extreme
    max_loss: Extreme
    profit_left_text: CatalogueText | None
    loss_left_text: CatalogueText | None
    max_profit_text: CatalogueText | None
    max_loss_text: CatalogueText | None
    extremes_reason: ExtremesReason | None


class PaperStrategyOut(PaperFigures):
    strategy_id: int
    name: CatalogueText
    underlying: Underlying
    open_count: int  # GC-TP step 4a: positions with a non-zero net quantity ("N of M positions")
    position_count: int


TotalsReason = paper.PauseReason | paper_decay.DecayReason


class PaperTotalsOut(ApiModel):
    """GC-TP step 4a (screens 050-053 totals strip): the sums over every paper strategy of the user, from the server."""
    booked: Money
    booked_text: CatalogueText
    unbooked: Money | None  # None (never a partial sum) when any strategy's unbooked is absent (REQ-109 AC-5)
    unbooked_text: CatalogueText | None
    total: Money | None
    total_text: CatalogueText | None
    totals_reason: paper.PauseReason | None
    decay: Money | None  # REQ-145 AC-2: rupees to the next market open over every open contract, rounded once
    decay_text: CatalogueText | None
    decay_reason: TotalsReason | None


class PaperListOut(ApiModel):
    strategies: list[PaperStrategyOut]  # newest strategy first (first order time, then id)
    totals: PaperTotalsOut
    answered_at: datetime.datetime


def _connected(ctx: MarketContext | None) -> bool:
    return ctx is not None and ctx.provider.status().connected


async def _snapshot(ctx: MarketContext, feed: LiveFeed | None, underlying: str, ids: list[str]):
    """One market read (the tracking routes' rule): with a live feed, contracts nobody holds are held until their first
    live quote or the planned-entry wait passes."""
    snapshot = read_snapshot(ctx.provider, underlying, ids, ctx.clock(), ctx.rate, feed_scope(ctx))
    unpriced = [i for i in ids if paper.leg_price(snapshot, i).state != paper.LIVE]
    if unpriced and feed is not None:
        _, snapshot, _ = await hold_until_priced(feed, ctx, underlying, ids, unpriced)
    return snapshot


def _paper(orders: Sequence[paper_store.StoredOrder]) -> list[PaperOrder]:
    return [o.order.as_paper() for o in orders]


def _open_ids(orders: Sequence[paper_store.StoredOrder]) -> list[int]:
    """The contracts with a non-zero net quantity (the quantity does not depend on any live price)."""
    if not orders:
        return []  # net_positions refuses an empty book
    return [int(p.instrument_id) for p in net_positions(_paper(orders), {}).positions if p.net_quantity != 0]


def _identity(found: tracked_contracts.TrackedContract) -> tuple[str, Instrument, Any, datetime.date]:
    if found.stored is None:
        raise RuntimeError(f"paper order contract id {found.contract_id} has no stored contract row ({found.state})")
    contract = found.stored.listed.contract
    instrument = Instrument(contract.instrument_type)
    strike = None if contract.instrument_type == FUTURE_TYPE else contract.strike
    return contract.name, instrument, strike, contract.expiry


def _exact(value: Decimal | None) -> Decimal | None:
    """The engine's exact value; a value that is a whole number of paise goes out with its two decimals."""
    if value is None:
        return None
    paisa = value.quantize(PAISE)
    return paisa if paisa == value else value


def _signed(value: Decimal | None) -> str | None:
    return None if value is None else render_explanation(SIGNED_PAISA, amount=value)


def _position(p: NetPosition, found: tracked_contracts.TrackedContract, price: paper.Price | None) -> dict:
    underlying, instrument, strike, expiry = _identity(found)
    average = None if p.average is None else p.average.quantize(PAISE, rounding=ROUND_HALF_UP)
    live = price is not None and paper.is_live(price)
    text_ = describe_contract((underlying, instrument, strike, expiry))
    return {"contract_id": found.contract_id, "contract_text": text_,
            "instrument": instrument.value, "strike": strike, "expiry": expiry, "net_quantity": p.net_quantity,
            "average": average, "average_text": price_text(average),
            "ltp": price.price if live and price is not None else None,
            "ltp_text": price_text(price.price) if live and price is not None else None,
            "price_state": None if price is None else price.state, "price_at": None if price is None else price.at,
            "booked": _exact(p.booked), "booked_text": _signed(p.booked),
            "unbooked": _exact(p.unbooked), "unbooked_text": _signed(p.unbooked),
            "total": _exact(p.total), "total_text": _signed(p.total)}


def _prices(open_ids: Sequence[int], found: dict[int, tracked_contracts.TrackedContract],
            snapshot: Any) -> dict[int, paper.Price]:
    """Per open contract: a contract reason (never priced), else the snapshot's answer; no snapshot = missing."""
    out: dict[int, paper.Price] = {}
    for cid in open_ids:
        contract = found[cid]
        key = contract.feed_key
        if contract.state != tracked_contracts.LIVE or key is None:
            out[cid] = paper.Price(contract.identity or str(cid), contract.state, None, None)  # type: ignore[arg-type]
        elif snapshot is None:
            out[cid] = paper.Price(key, "missing", None, None)
        else:
            out[cid] = paper.leg_price(snapshot, key)
    return out


def _figures(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],
             prices: dict[int, paper.Price], connected: bool) -> dict:
    """The strategy's figures from the one engine at the live prices of its open contracts."""
    live = {str(cid): p.price for cid, p in prices.items() if paper.is_live(p) and p.price is not None}
    view = net_positions(_paper(orders), live)
    positions = [_position(p, found[int(p.instrument_id)], prices.get(int(p.instrument_id))) for p in view.positions]
    reason = next((found[c].state for c in prices if found[c].state != tracked_contracts.LIVE), None)
    paused = view.unbooked is None
    if not prices:
        state, pause = "EXITED", None
    elif not connected:
        state, pause = "NOT_CONNECTED", reason
    elif paused:
        state, pause = "PAUSED", reason or paper.PRICES_NOT_LIVE
    else:
        state, pause = "LIVE", None
    return {"state": state, "pause_reason": pause, "booked": _exact(view.booked), "unbooked": _exact(view.unbooked),
            "total": _exact(view.total), "booked_text": _signed(view.booked), "unbooked_text": _signed(view.unbooked),
            "total_text": _signed(view.total), "positions": positions}


def _extreme(value: Any) -> tuple[Decimal | str | None, Any]:
    """One extreme figure and its text: the exact Decimal, "unlimited" with the no-fixed-limit words, or absent."""
    if value is None:
        return None, None
    if value is UNLIMITED:
        return "unlimited", render_explanation(NO_FIXED_LIMIT)
    return _exact(value), _signed(value)


def _extremes(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],
              prices: dict[int, paper.Price]) -> dict:
    """Profit left / Loss left and the original Max Profit / Max Loss from the one engine (ofo.engine.extremes)."""
    live = {str(cid): p.price for cid, p in prices.items() if paper.is_live(p) and p.price is not None}
    terms = {}
    for cid in {o.order.contract_id for o in orders}:
        _, instrument, strike, expiry = _identity(found[cid])
        terms[str(cid)] = ContractTerms(instrument, strike, expiry)
    got = book_extremes(net_positions(_paper(orders), live), terms, live)
    figures = {"profit_left": got.profit_left, "loss_left": got.loss_left, "max_profit": got.max_profit,
               "max_loss": got.max_loss}
    out: dict[str, Any] = {"extremes_reason": got.reason}
    for name, value in figures.items():
        out[name], out[f"{name}_text"] = _extreme(value)
    return out


def _order_rows(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract]) -> list:
    rows = []
    for stored in orders:
        o = stored.order
        rows.append({"id": stored.id, "placed_at": o.placed_at, "side": o.side, "contract_id": o.contract_id,
                     "contract_text": describe_contract(_identity(found[o.contract_id])), "quantity": o.quantity,
                     "price": o.price, "price_text": price_text(o.price), "kind": o.kind})
    return rows


async def _load_strategy(db: Any, user_ref: str, strategy_id: int):
    try:
        return await store.load(db, user_ref, strategy_id)
    except store.StrategyStoreError as exc:
        raise refused_answer(exc, 409) from None


async def _book(db: Any, stored: Any, orders: Sequence[paper_store.StoredOrder],  # noqa: PLR0913
                ctx: MarketContext | None, feed: LiveFeed | None, answered_at: datetime.datetime) -> PaperBookOut:
    ids = sorted({o.order.contract_id for o in orders})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    open_ids = _open_ids(orders)
    connected = _connected(ctx)
    underlying = stored.saved.definition.underlying  # fixed for the strategy's life
    snapshot = None
    keys = [k for k in (found[c].feed_key for c in open_ids) if k is not None]
    if connected and keys:
        snapshot = await _snapshot(ctx, feed, underlying, keys)  # type: ignore[arg-type]
    prices = _prices(open_ids, found, snapshot)
    figures = _figures(orders, found, prices, connected) | _extremes(orders, found, prices)
    return PaperBookOut.model_validate(figures | {
        "strategy_id": stored.id, "name": sf.shown_name(stored.name), "underlying": underlying,
        "answered_at": answered_at, "orders": _order_rows(orders, found)})


@router.get("/paper/strategies/{strategy_id}", response_model=PaperBookOut)
async def get_paper_strategy(strategy_id: int,  # noqa: PLR0913 - FastAPI dependencies
                             db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                             ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                             feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                             now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> PaperBookOut:
    stored = await _load_strategy(db, user_ref, strategy_id)
    orders = await paper_store.load(db, strategy_id)
    if not orders:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    return await _book(db, stored, orders, ctx, feed, now())


@router.get("/paper/strategies", response_model=PaperListOut)
async def list_paper_strategies(db: Annotated[Any, Depends(get_db)],
                                user_ref: Annotated[str, Depends(current_user_ref)],
                                ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                                feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                                now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> PaperListOut:
    """Every paper strategy of the signed-in user, newest first: fixed cost whatever the count (finding F-3): one orders
    query, one contract batch (two queries) and ONE market read per underlying for every open contract together."""
    books = await paper_store.load_all(db, user_ref)
    ids = sorted({o.order.contract_id for b in books for o in b.orders})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    connected = _connected(ctx)
    keys: dict[str, list[str]] = {}
    for b in books:
        for cid in _open_ids(b.orders):
            key = found[cid].feed_key
            if key is not None and key not in keys.setdefault(b.underlying, []):
                keys[b.underlying].append(key)
    snapshots = {}
    if connected:
        for underlying, wanted in keys.items():
            snapshots[underlying] = await _snapshot(ctx, feed, underlying, wanted)  # type: ignore[arg-type]
    out, decays = [], []
    for b in sorted(books, key=_newest_first, reverse=True):
        snapshot = snapshots.get(b.underlying)
        figures = _figures(b.orders, found, _prices(_open_ids(b.orders), found, snapshot), connected)
        decays.append(_decay(figures, found, snapshot, b.underlying))
        held = sum(1 for p in figures["positions"] if p["net_quantity"] != 0)
        out.append(figures | {"strategy_id": b.strategy_id, "name": sf.shown_name(b.name), "underlying": b.underlying,
                              "open_count": held, "position_count": len(figures["positions"])})
    return PaperListOut.model_validate({"strategies": out, "totals": _totals(out, decays), "answered_at": now()})


def _newest_first(book: paper_store.UserBook) -> tuple[datetime.datetime, int]:
    """The sort key of the list (reversed): the book's first order time, then the strategy id."""
    return min(o.order.placed_at for o in book.orders), book.strategy_id


def _decay(figures: dict, found: dict[int, tracked_contracts.TrackedContract], snapshot: Any,
           underlying: str) -> paper_decay.Decay:
    """One book's Decay (ofo.tracking.paper_decay): absent with the book's pause reason when an open contract is not
    live; a fully exited book decays 0."""
    if figures["unbooked"] is None:
        return paper_decay.Decay(None, figures["pause_reason"] or paper.PRICES_NOT_LIVE)
    contracts = [paper_decay.OpenContract(found[p["contract_id"]].feed_key or "", Instrument(p["instrument"]),
                                          p["strike"], p["expiry"], p["net_quantity"], p["ltp"])
                 for p in figures["positions"] if p["net_quantity"] != 0]
    return paper_decay.book_decay(snapshot, underlying, contracts)


def _totals(strategies: Sequence[dict], decays: Sequence[paper_decay.Decay]) -> dict:
    """The exact sums over every strategy. Unbooked and total are absent with the first absent strategy's reason, and
    Decay with the first absent book's reason: never a partial sum shown as a total (REQ-109 AC-5)."""
    got = book_totals([(s["booked"], s["unbooked"]) for s in strategies], [d.value for d in decays])
    paused = next((s for s in strategies if s["unbooked"] is None), None)
    missing = next((d for d in decays if d.value is None), None)
    booked, unbooked, total, decay = got.booked, got.unbooked, got.total, got.decay
    return {"booked": _exact(booked), "booked_text": _signed(booked), "unbooked": _exact(unbooked),
            "unbooked_text": _signed(unbooked), "total": _exact(total), "total_text": _signed(total),
            "totals_reason": None if paused is None else (paused["pause_reason"] or paper.PRICES_NOT_LIVE),
            "decay": decay, "decay_text": _signed(decay), "decay_reason": None if missing is None else missing.reason}


def _check_price(price: Decimal) -> None:
    """REQ-109 AC-1: above 0, a multiple of 0.05, within the column (the reason text is the catalogue's)."""
    if not is_typed_price(price):
        raise StrategyRefused("paper_price_invalid")


@router.post("/paper/strategies/{strategy_id}/orders", status_code=201, response_model=PaperBookOut)
async def place_paper_orders(strategy_id: int, body: PaperOrdersIn,  # noqa: PLR0913 - FastAPI dependencies
                             db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                             ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                             feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                             now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> PaperBookOut:
    stored = await _load_strategy(db, user_ref, strategy_id)
    for order in body.orders:
        _check_price(order.price)
    contracts = await tracked_contracts.resolve(db, sorted({o.contract_id for o in body.orders}))
    state = {c.contract_id: c for c in contracts}
    # a contract unknown to the catalogue never reaches the store; a new position needs a live contract (an exit of one
    # that expired is allowed: it only closes what is open)
    if any(state[o.contract_id].stored is None or (o.kind != "exit" and state[o.contract_id].state != "live")
           for o in body.orders):
        raise StrategyRefused("paper_contract_not_tradable")
    placed_at = now()
    try:
        await paper_store.place(db, user_ref, strategy_id, [
            paper_store.NewOrder(o.contract_id, o.side, o.quantity, o.price, o.kind, placed_at) for o in body.orders])
        await db.commit()
    except store.StrategyStoreError as exc:
        await db.rollback()
        if exc.code == paper_store.EXIT_EXCEEDS_OPEN:
            raise StrategyRefused("paper_exit_exceeds_open") from None
        raise refused_answer(exc, 409) from None
    except Exception:
        await db.rollback()
        raise
    return await _book(db, stored, await paper_store.load(db, strategy_id), ctx, feed, placed_at)


# --- stop triggers and alerts (GC-TP step 7a; REQ-109 AC-8; ADR-207 (5); screens 221-224) -----------------------------
TriggerKind = Literal["conditional_exit", "leg_stop"]
Direction = Literal["above", "below"]
TriggerState = Literal["armed", "fired", "cancelled"]


class TriggerIn(BaseModel):
    """conditional_exit: ``above`` and / or ``below`` (an index level each, one trigger per direction); leg_stop:
    ``contract_id`` with ONE ``direction`` and ``level``."""
    model_config = ConfigDict(extra="forbid")
    kind: TriggerKind
    above: Decimal | None = Field(default=None, allow_inf_nan=False)
    below: Decimal | None = Field(default=None, allow_inf_nan=False)
    contract_id: int | None = Field(default=None, gt=0, le=INTEGER_MAX)
    direction: Direction | None = None
    level: Decimal | None = Field(default=None, allow_inf_nan=False)


class TriggerOut(ApiModel):
    id: int
    strategy_id: int
    kind: TriggerKind
    direction: Direction
    level: Money
    level_text: CatalogueText
    contract_id: int | None
    contract_text: CatalogueText | None
    underlying: Underlying | None
    state: TriggerState
    created_at: datetime.datetime
    fired_at: datetime.datetime | None
    cancelled_at: datetime.datetime | None


class TriggersOut(ApiModel):
    triggers: list[TriggerOut]  # newest first


class AlertOut(ApiModel):
    id: int
    strategy_id: int
    strategy_name: CatalogueText  # GC-TP step 4a: the strategy's saved name, the paper replies' quoted name slot
    trigger_id: int
    created_at: datetime.datetime
    title: CatalogueText
    body: CatalogueText
    read: bool


class AlertsOut(ApiModel):
    alerts: list[AlertOut]  # newest first
    unread: int


def _state(row: paper_trigger_store.TriggerRow) -> TriggerState:
    if row.fired_at is not None:
        return "fired"
    return "armed" if row.cancelled_at is None else "cancelled"


async def _triggers_out(db: Any, strategy_id: int) -> TriggersOut:
    rows = list(reversed(await paper_trigger_store.list_for(db, strategy_id)))
    ids = sorted({r.trigger.contract_id for r in rows if r.trigger.contract_id is not None})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    return TriggersOut.model_validate({"triggers": [{
        "id": r.trigger.id, "strategy_id": r.trigger.strategy_id, "kind": r.trigger.kind,
        "direction": r.trigger.direction, "level": r.trigger.level,
        "level_text": render_explanation("paper_trigger_level", level=r.trigger.level),
        "contract_id": r.trigger.contract_id,
        "contract_text": None if r.trigger.contract_id is None else describe_contract(
            _identity(found[r.trigger.contract_id])),
        "underlying": r.trigger.underlying, "state": _state(r), "created_at": r.created_at,
        "fired_at": r.fired_at, "cancelled_at": r.cancelled_at} for r in rows]})


@router.get("/paper/strategies/{strategy_id}/triggers", response_model=TriggersOut)
async def list_paper_triggers(strategy_id: int, db: Annotated[Any, Depends(get_db)],
                              user_ref: Annotated[str, Depends(current_user_ref)]) -> TriggersOut:
    await _load_strategy(db, user_ref, strategy_id)
    return await _triggers_out(db, strategy_id)


def _new_triggers(body: TriggerIn, underlying: str, open_ids: Sequence[int]) -> list[paper_trigger_store.NewTrigger]:
    new: list[paper_trigger_store.NewTrigger] = []
    if body.kind == "conditional_exit":
        if body.contract_id is not None or body.direction is not None or body.level is not None:
            raise StrategyRefused("user_input_request_invalid")
        new = [paper_trigger_store.NewTrigger("conditional_exit", d, lvl, underlying=underlying)
               for d, lvl in (("above", body.above), ("below", body.below)) if lvl is not None]
    elif (body.above is None and body.below is None and body.contract_id is not None and body.direction
          and body.level is not None):
        new = [paper_trigger_store.NewTrigger("leg_stop", body.direction, body.level, contract_id=body.contract_id)]
    if not new:
        raise StrategyRefused("user_input_request_invalid")
    for n in new:
        if not is_typed_price(n.level):
            raise StrategyRefused("paper_trigger_level_invalid")
        if n.contract_id is not None and n.contract_id not in open_ids:
            raise StrategyRefused("paper_trigger_leg_not_open")
    return new


@router.post("/paper/strategies/{strategy_id}/triggers", status_code=201, response_model=TriggersOut)
async def add_paper_triggers(strategy_id: int, body: TriggerIn, db: Annotated[Any, Depends(get_db)],
                             user_ref: Annotated[str, Depends(current_user_ref)]) -> TriggersOut:
    stored = await _load_strategy(db, user_ref, strategy_id)
    open_ids = _open_ids(await paper_store.load(db, strategy_id))
    if not open_ids:
        raise StrategyRefused("paper_trigger_nothing_open")
    new = _new_triggers(body, stored.saved.definition.underlying, open_ids)
    try:
        for n in new:
            await paper_trigger_store.add(db, strategy_id, n)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    paper_monitor.notify()
    return await _triggers_out(db, strategy_id)


@router.delete("/paper/strategies/{strategy_id}/triggers/{trigger_id}", response_model=TriggersOut)
async def cancel_paper_trigger(strategy_id: int, trigger_id: int, db: Annotated[Any, Depends(get_db)],
                               user_ref: Annotated[str, Depends(current_user_ref)]) -> TriggersOut:
    await _load_strategy(db, user_ref, strategy_id)
    rows = {r.trigger.id: r for r in await paper_trigger_store.list_for(db, strategy_id)}
    if trigger_id not in rows:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    if rows[trigger_id].fired_at is not None:
        raise StrategyRefused("paper_trigger_already_fired", Failure.CONFLICT)
    try:
        await paper_trigger_store.cancel(db, strategy_id, trigger_id)  # already cancelled: nothing to change
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    paper_monitor.notify()
    return await _triggers_out(db, strategy_id)


async def _alerts_out(db: Any, user_ref: str) -> AlertsOut:
    rows, unread = await paper_trigger_store.alerts(db, user_ref)
    return AlertsOut.model_validate({"unread": unread, "alerts": [{
        "id": a.id, "strategy_id": a.strategy_id, "strategy_name": sf.shown_name(a.strategy_name),
        "trigger_id": a.trigger_id, "created_at": a.created_at,
        "title": restore_explanation("paper_alert_title", a.title),
        "body": restore_explanation("paper_alert_body", a.body), "read": a.read_at is not None} for a in rows]})


@router.get("/paper/alerts", response_model=AlertsOut)
async def list_paper_alerts(db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> AlertsOut:
    return await _alerts_out(db, user_ref)


@router.post("/paper/alerts/read", response_model=AlertsOut)
async def read_paper_alerts(db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> AlertsOut:
    await paper_trigger_store.mark_all_read(db, user_ref)
    await db.commit()
    return await _alerts_out(db, user_ref)
