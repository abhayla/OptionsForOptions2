"""GET /paper/strategies, GET /paper/strategies/{id}, POST /paper/strategies/{id}/orders: the paper order book (GC-TP 1b).

Spec basis: REQ-109 AC-1 (typed paper prices), AC-4 ("The one engine derives the net position per contract from the
orders"), AC-5 (a stale or missing price pauses unbooked and total); ADR-207 (paper trading the Sensibull Draft Portfolio
way, Net Positions | Orderbook, screens 274-279); ADR-008 (the browser formats nothing: every money field goes out as
an exact Decimal string beside the server's own text).

- The figures come only from ofo.tracking.orderbook.net_positions over the stored orders (paper_store). This module adds
  no arithmetic of its own. An average that does not divide out evenly is exact in the engine and SHOWN rounded to the
  paisa (``average`` and ``average_text``); booked / unbooked / total are the engine's exact values.
- Prices of open contracts come from the same market context as the tracking routes, through
  ofo_app.tracked_contracts.resolve (a stored contract id reaches a feed key only there). A contract that is not live,
  or whose price is stale or missing, has no unbooked figure, and the strategy's unbooked and total are absent with the
  pause reason (AC-5). Booked is always known.
- POST takes typed prices (AC-1): each must be above 0 and a multiple of 0.05; an exit may not exceed the open quantity;
  only the kinds open, add and exit are accepted from a request (settle and stop are server-only). All orders of one call
  are stored in one transaction (paper_store.place) or none are.
- Answer states: no such strategy or another user's -> 404; a strategy with no orders -> 404 on GET; an empty order list,
  a bad price or kind -> 422 with the reason text.
- This module imports nothing from the order path (tests_app/test_paper_order_door.py walks its import graph).
The user comes from the session (``current_user_ref``), never from the request.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.engine.legs import Instrument
from ofo.errors.explanations import render_explanation
from ofo.instruments.models import FUTURE_TYPE
from ofo.limits import INTEGER_MAX
from ofo.money import PAISE
from ofo.outcome import read_snapshot
from ofo.outcome.price_text import price_text
from ofo.strategy import stored_form as sf
from ofo.strategy.definition import describe_contract
from ofo.tracking import paper
from ofo.tracking.orderbook import NetPosition, PaperOrder, net_positions
from pydantic import BaseModel, ConfigDict, Field

from ofo_app import paper_store, tracked_contracts
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

#: REQ-109 AC-1: a typed paper price is a multiple of this and above 0 (the exchange's tick for these contracts).
TYPED_PRICE_TICK = Decimal("0.05")
#: The largest typed price (the column is NUMERIC(14,2); no option or future trades near this).
TYPED_PRICE_MAX = Decimal("10000000")
#: The order kinds a request may carry; settle and stop are written by the server only (ADR-207).
REQUEST_KINDS = ("open", "add", "exit")
RequestKind = Literal["open", "add", "exit"]
BookState = Literal["LIVE", "PAUSED", "NOT_CONNECTED", "EXITED"]
SIGNED_PAISA = "summary_paisa_signed"


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


class PaperStrategyOut(PaperFigures):
    strategy_id: int
    name: CatalogueText
    underlying: Underlying


class PaperListOut(ApiModel):
    strategies: list[PaperStrategyOut]  # newest strategy first
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
    """The contracts with a non-zero net quantity (priced without any live price: the quantity does not depend on it)."""
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
    return {"contract_id": found.contract_id, "contract_text": describe_contract((underlying, instrument, strike, expiry)),
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


async def _book(db: Any, stored: Any, orders: Sequence[paper_store.StoredOrder], ctx: MarketContext | None,
                feed: LiveFeed | None, answered_at: datetime.datetime) -> PaperBookOut:
    ids = sorted({o.order.contract_id for o in orders})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    open_ids = _open_ids(orders)
    connected = _connected(ctx)
    underlying = stored.saved.definition.underlying  # fixed for the strategy's life
    snapshot = None
    keys = [k for k in (found[c].feed_key for c in open_ids) if k is not None]
    if connected and keys:
        snapshot = await _snapshot(ctx, feed, underlying, keys)  # type: ignore[arg-type]
    figures = _figures(orders, found, _prices(open_ids, found, snapshot), connected)
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
async def list_paper_strategies(db: Annotated[Any, Depends(get_db)],  # noqa: PLR0913 - FastAPI dependencies
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
    out = []
    for b in reversed(books):
        open_ids = _open_ids(b.orders)
        figures = _figures(b.orders, found, _prices(open_ids, found, snapshots.get(b.underlying)), connected)
        out.append(figures | {"strategy_id": b.strategy_id, "name": sf.shown_name(b.name), "underlying": b.underlying})
    return PaperListOut.model_validate({"strategies": out, "answered_at": now()})


def _check_price(price: Decimal) -> None:
    """REQ-109 AC-1: above 0, a multiple of 0.05, within the column (the reason text is the catalogue's)."""
    if not (0 < price <= TYPED_PRICE_MAX) or price % TYPED_PRICE_TICK != 0:
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
