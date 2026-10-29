"""GET /strategies/{id}/tracking, GET /tracking, POST /strategies/{id}/tracking/exit: paper tracking of a saved strategy
and one platform detection (W-122). Orders are placed through POST /paper/strategies/{id}/orders (GC-TP step 2: the
old start route is gone).

Spec basis: REQ-109 AC-1 (a paper entry per leg at the leg's live price, with time and price health; no account-wide
switch), AC-2 (paper P&L from the one engine, exact Decimal, never mixed with real P&L), AC-3 (tracking never reaches
Execute: this module imports nothing from the order path), AC-5 (stale or missing prices pause paper P&L); REQ-045 Q253
condition 1 and AC-1/AC-2 (ofo.adjustment.detection); REQ-046 AC-1 (each detection's Layer 1 numbers).

- View: the paper order book (public.paper_orders, GC-TP 1a part 4) shown as one leg per contract
  (ofo.tracking.book), current prices, paper P&L from the one engine on the orders
  (ofo.engine.orderbook.net_positions) or the paused state, and the detections. Exit writes
  paper orders (ofo_app.paper_store); the old tracking tables are read-only since migration 0028.
- Contract identity (round 3 redesign): every stored contract id reaches a feed key ONLY through
  ofo_app.tracked_contracts.resolve, which gives a key only for a live contract still holding its own exchange token.
  A retired, delisted, token-reassigned or missing contract refuses the start (tracking_contract_not_live) and pauses
  the view with that reason (pause_reason; no paper P&L, no detection) - never a price from another contract.
The user comes from the session (``current_user_ref``), never from the request.
"""
from __future__ import annotations

import datetime
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment.detection import NEAR_LEVEL_THRESHOLD_PERCENT, PLATFORM_DETECTION, check_threshold
from ofo.engine.legs import Action, Instrument
from ofo.engine.orderbook import BookView
from ofo.errors.explanations import render_explanation
from ofo.instruments.models import FUTURE_TYPE
from ofo.limits import INTEGER_MAX
from ofo.money import PAISE
from ofo.outcome import read_snapshot
from ofo.outcome.price_text import price_text
from ofo.strategy import stored_form as sf
from ofo.tracking import book, paper
from ofo.tracking.orderbook import PaperOrder, net_positions
from pydantic import BaseModel, ConfigDict, Field

from ofo_app import paper_store, tracked_contracts
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, InstrumentId, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.live_push import LiveFeed
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import AnswerClock, MarketContext, feed_scope, get_answer_clock, get_market_context
from ofo_app.routes.planned_entry import get_live_feed, hold_until_priced
from ofo_app.routes.strategies import StrategyRefused, refused_answer
from ofo_app.underlying import Underlying

router = APIRouter(route_class=ClosedRoute)

PriceStateCode = paper.PriceState


def get_near_level_threshold() -> Decimal:
    """Q253 condition 1's threshold (an admin setting; the admin screen is Step 6). Tests override this dependency."""
    return NEAR_LEVEL_THRESHOLD_PERCENT


class TrackingExitIn(BaseModel):
    """REQ-109 AC-4: the legs to exit by index; no price (the server reads it). "All open legs" = send them all."""
    model_config = ConfigDict(extra="forbid")
    legs: list[Annotated[int, Field(ge=0, le=INTEGER_MAX)]] = Field(min_length=1, max_length=64)


class TrackingLegOut(ApiModel):
    leg_index: int
    instrument_id: InstrumentId
    action: Literal["BUY", "SELL"]
    instrument: Literal["CE", "PE", "FUT"]
    strike: Money | None
    expiry: datetime.date
    quantity: int
    entry_price: Money
    entry_price_display: CatalogueText  # GC-UI D-PX (REQ-152 AC-2): two-decimal text of the price beside it
    entry_at: datetime.datetime
    current_price: Money | None
    current_price_display: CatalogueText | None = None
    price_state: paper.LegState
    price_at: datetime.datetime | None
    exit_price_display: CatalogueText | None = None
    exit_price: Money | None  # REQ-109 AC-4: set once the leg is paper-exited (then price_state is "exited")
    exited_at: datetime.datetime | None
    # GC-UI D-B48 (REQ-109 AC-2/AC-4, ADR-008): this leg's paper P&L from the one engine, exact to the paisa. Booked for
    # an exited leg (at its exit price, frozen), unbooked for an open live leg. All three are None - never 0 - when the
    # leg has no figure (price not live, view paused, contract not live, not connected). Legs with a figure add up to
    # booked + unbooked = the strategy's total.
    pnl: Money | None
    pnl_text: CatalogueText | None  # REQ-152 text of pnl: to the paisa, signed ("+5,053.75")
    pnl_kind: Literal["booked", "unbooked"] | None


class TrackingIndexOut(ApiModel):
    underlying: Underlying
    level: Money | None
    state: PriceStateCode
    at: datetime.datetime | None


class DetectionOut(ApiModel):
    kind: Literal["platform_detection"]  # REQ-045 AC-1: the screen labels it 'Adjustment opportunity detected'
    condition: Literal["near_short_strike", "near_breakeven"]
    level: Money
    index_level: Money
    distance_points: Money
    distance_percent: Money
    threshold_percent: Money
    at: datetime.datetime | None
    price_health: PriceStateCode


TrackingState = Literal["LIVE", "PAUSED", "NOT_CONNECTED", "EXITED"]


class TrackingOut(ApiModel):
    strategy_id: int
    started_at: datetime.datetime
    prices_at: datetime.datetime
    state: TrackingState
    pause_reason: paper.PauseReason | None
    paper_pnl: Money | None  # the total = booked + unbooked; None when unbooked is unknown
    booked: Money  # REQ-109 AC-4 / ADR-201 (2): exited legs at their exit prices; "0.00" when nothing exited
    unbooked: Money | None  # open legs at live prices; None when paused or not connected
    # REQ-152 AC-4: the server's own signed text of each figure (the same template as the list rows and the legs)
    paper_pnl_text: CatalogueText | None = None
    booked_text: CatalogueText | None = None
    unbooked_text: CatalogueText | None = None
    as_of: datetime.datetime | None
    answered_at: datetime.datetime
    legs: list[TrackingLegOut]
    index: TrackingIndexOut | None
    breakevens: list[Money] | None
    detections: list[DetectionOut]


class TrackedStrategyOut(ApiModel):
    """One row of GET /tracking (GC-BP step 4): the paper figures of one tracked strategy, no detections."""
    strategy_id: int
    name: CatalogueText  # REQ-134: quoted user text
    underlying: Underlying
    started_at: datetime.datetime
    state: TrackingState
    pause_reason: paper.PauseReason | None
    as_of: datetime.datetime | None
    total: Money | None
    booked: Money
    unbooked: Money | None
    # REQ-109 AC-2 / REQ-152 AC-4: the server's own text of each figure, to the paisa, signed; a true zero is "0.00"
    # with no sign. The browser prints these as sent and forms no money text (ADR-008).
    total_text: CatalogueText | None
    booked_text: CatalogueText | None
    unbooked_text: CatalogueText | None
    legs: list[TrackingLegOut]


class TrackingListOut(ApiModel):
    strategies: list[TrackedStrategyOut]
    answered_at: datetime.datetime


async def _snapshot(ctx: MarketContext, feed: LiveFeed | None, underlying: str, ids: list[str]):
    """One market read for the legs and the index. With a live feed, legs nobody holds are held until their first live
    quote or the planned-entry wait passes (the same rule and helper as the planned-entry route)."""
    snapshot = read_snapshot(ctx.provider, underlying, ids, ctx.clock(), ctx.rate, feed_scope(ctx))
    unpriced = [i for i in ids if paper.leg_price(snapshot, i).state != paper.LIVE]
    if unpriced and feed is not None:
        _, snapshot, _ = await hold_until_priced(feed, ctx, underlying, ids, unpriced)
    return snapshot


def _connected(ctx: MarketContext | None) -> bool:
    return ctx is not None and ctx.provider.status().connected


async def _load(db: Any, user_ref: str, strategy_id: int):
    try:
        return await store.load(db, user_ref, strategy_id)
    except store.StrategyStoreError as exc:
        raise refused_answer(exc, 409) from None


@dataclass(frozen=True)
class _Book:
    """One strategy's paper order book as the tracking reply reads it (GC-TP 1a part 4): its orders, one leg per
    contract (ofo.tracking.book) and that leg's stored contract id. started_at = the first order's time; prices_at =
    the oldest leg's first order time (the old entry's oldest quote time)."""

    strategy_id: int
    orders: tuple[PaperOrder, ...]
    legs: tuple[book.ContractLeg, ...]

    @property
    def contract_ids(self) -> list[int]:
        return [int(leg.instrument_id) for leg in self.legs]

    @property
    def started_at(self) -> datetime.datetime:
        return self.orders[0].placed_at

    @property
    def prices_at(self) -> datetime.datetime:
        return min(leg.entry_at for leg in self.legs)

    @property
    def exit_prices(self) -> dict[int, Decimal]:
        return {i: leg.exit_price for i, leg in enumerate(self.legs) if leg.exit_price is not None}


def _book(strategy_id: int, stored: Sequence[paper_store.StoredOrder]) -> _Book | None:
    """None when the strategy has no paper order (not tracked)."""
    if not stored:
        return None
    orders = tuple(o.order.as_paper() for o in stored)
    return _Book(strategy_id, orders, book.contract_legs(orders))


async def _load_book(db: Any, strategy_id: int) -> _Book | None:
    return _book(strategy_id, await paper_store.load(db, strategy_id))


def _money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(PAISE)


def _book_figures(bk: _Book, view: paper.TrackingView | None) -> tuple[BookView, list[Decimal | None]]:
    """REQ-109 AC-4: every figure from the one engine on the orders (ofo.engine.orderbook.net_positions), exact. The
    open legs are priced only when the view is live (not paused, connected): a paused or unconnected view gives no
    open leg a figure and no unbooked / total (AC-5); an exited leg keeps its booked figure."""
    live = {} if view is None or view.paused else {
        leg.instrument_id: view.legs[i].price for i, leg in enumerate(bk.legs)
        if not leg.exited and view.legs[i].price is not None}
    figures = net_positions(bk.orders, live)
    by_id = {p.instrument_id: p for p in figures.positions}
    pnls: list[Decimal | None] = [by_id[leg.instrument_id].booked if leg.exited else by_id[leg.instrument_id].unbooked
                                  for leg in bk.legs]
    return figures, pnls


def _figures(bk: _Book, legs: list[paper.TrackedLeg], view: paper.TrackingView | None,
             reasons: list[paper.ContractReason | None]) -> dict:
    """The per-leg rows and the paper figures shared by GET /strategies/{id}/tracking and GET /tracking. ``view`` None
    = not connected: booked is still known (the closing orders are stored), unbooked and total are not."""
    figures, pnls = _book_figures(bk, view)
    rows = []
    for i, (leg, held) in enumerate(zip(legs, bk.legs, strict=True)):
        price = None if view is None else view.legs[i]
        done = held.exited
        state = price.state if price is not None else paper.EXITED if done else (reasons[i] or "missing")
        rows.append({"leg_index": i, "instrument_id": leg.instrument_id, "action": leg.action.value,
                     "instrument": leg.instrument.value, "strike": leg.strike, "expiry": leg.expiry,
                     "quantity": leg.quantity, "entry_price": leg.entry_price,
                     "entry_price_display": price_text(leg.entry_price), "entry_at": leg.price_at,
                     "current_price": None if price is None else price.price,
                     "current_price_display": None if price is None else price_text(price.price), "price_state": state,
                     "price_at": None if price is None else price.at,
                     "exit_price": held.exit_price,
                     "exit_price_display": None if held.exit_price is None else price_text(held.exit_price),
                     "exited_at": held.exited_at,
                     "pnl": _money(pnls[i]),
                     "pnl_text": None if pnls[i] is None else
                     render_explanation("summary_paisa_signed", amount=pnls[i]),
                     "pnl_kind": None if pnls[i] is None else "booked" if done else "unbooked"})
    if view is None:
        open_reasons = [r for i, r in enumerate(reasons) if not bk.legs[i].exited]
        return {"legs": rows, "state": "NOT_CONNECTED", "pause_reason": next((r for r in open_reasons if r), None),
                "as_of": None, "total": None, "unbooked": None, "booked": _money(figures.booked)}
    state = "EXITED" if view.exited else "PAUSED" if view.paused else "LIVE"
    return {"legs": rows, "state": state, "pause_reason": view.pause_reason, "as_of": view.as_of,
            "total": _money(figures.total), "booked": _money(figures.booked), "unbooked": _money(figures.unbooked)}


def _texts(figures: dict) -> dict:
    return {f"{k}_text": None if figures[k] is None else render_explanation("summary_paisa_signed", amount=figures[k])
            for k in ("total", "booked", "unbooked")}


def _view(bk: _Book, legs: list[paper.TrackedLeg], underlying: str,  # noqa: PLR0913
          view: paper.TrackingView | None, answered_at: datetime.datetime,
          reasons: list[paper.ContractReason | None]) -> TrackingOut:
    figures = _figures(bk, legs, view, reasons)
    texts = _texts(figures)
    texts["paper_pnl_text"] = texts.pop("total_text")
    body: dict = {"strategy_id": bk.strategy_id, "started_at": bk.started_at,
                  "prices_at": bk.prices_at, "answered_at": answered_at, "detections": [],
                  "paper_pnl": figures.pop("total")} | figures | texts
    if view is None or view.index is None:
        return TrackingOut.model_validate(body | {"index": None, "breakevens": None})
    index = view.index
    body |= {"index": {"underlying": underlying, "level": index.price, "state": index.state, "at": index.at},
             "breakevens": None if view.breakevens is None else list(view.breakevens)}
    body["detections"] = [{"kind": PLATFORM_DETECTION, "condition": d.condition, "level": d.level,
                           "index_level": d.index_level, "distance_points": d.distance_points,
                           "distance_percent": d.distance_percent, "threshold_percent": d.threshold_percent,
                           "at": index.at, "price_health": index.state} for d in view.detections]
    return TrackingOut.model_validate(body)


async def _entry_legs(db: Any, bk: _Book) -> tuple[list[paper.TrackedLeg], list[paper.ContractReason | None]]:
    """The one book's legs (``_legs_of``), its contracts resolved in one batch."""
    contracts = await tracked_contracts.resolve(db, bk.contract_ids)
    return _legs_of(bk, contracts)


def _legs_of(bk: _Book, contracts: Sequence[tracked_contracts.TrackedContract]) \
        -> tuple[list[paper.TrackedLeg], list[paper.ContractReason | None]]:
    """REQ-109 AC-2/AC-4: the tracked legs come ONLY from the paper orders - one per contract, its side, open quantity
    and average (shown to the paisa; the figures use the engine's exact values, _book_figures). The strategy as saved
    now is never read here, so an edit after the start changes nothing in the tracked figures. Each contract went
    through tracked_contracts.resolve: a leg whose contract is not live keeps its stored terms and its own (old)
    exchange identity for display, is left out of the market read, and carries its reason, so paper.tracking_view
    never prices it. A contract row that is missing (contract_missing; the foreign key and the never-delete catalogue
    forbid it) has no terms to show and fails closed: an error, never invented terms."""
    legs = []
    for held, found in zip(bk.legs, contracts, strict=True):
        if found.stored is None or found.identity is None:
            raise RuntimeError(f"tracked contract id {held.instrument_id} has no stored contract row ({found.state})")
        contract = found.stored.listed.contract
        future = contract.instrument_type == FUTURE_TYPE
        legs.append(paper.TrackedLeg(found.identity, Action(held.side), Instrument(contract.instrument_type),
                                     None if future else contract.strike, contract.expiry, held.quantity,
                                     held.average.quantize(PAISE), held.entry_at))
    return legs, tracked_contracts.reasons(contracts)


async def _answer(db: Any, stored, bk: _Book, ctx: MarketContext | None,  # noqa: PLR0913
                  feed: LiveFeed | None, threshold: Decimal, answered_at: datetime.datetime) -> TrackingOut:
    legs, reasons = await _entry_legs(db, bk)
    underlying = stored.saved.definition.underlying  # fixed for the strategy's life (strategy_store UNDERLYING_FIXED)
    exits = bk.exit_prices
    if len(exits) == len(legs):  # every leg exited: frozen at its exit prices, no market read (EXITED)
        return _view(bk, legs, underlying, paper.tracking_view(None, legs, threshold, reasons, exits),
                     answered_at, reasons)
    if not _connected(ctx):
        return _view(bk, legs, underlying, None, answered_at, reasons)
    snapshot = await _snapshot(ctx, feed, underlying, _open_keys(bk, legs, reasons))
    view = paper.tracking_view(snapshot, legs, check_threshold(threshold), reasons, exits)
    return _view(bk, legs, underlying, view, answered_at, reasons)


def _open_keys(bk: _Book, legs: list[paper.TrackedLeg], reasons: list[paper.ContractReason | None]) -> list[str]:
    """The feed keys to read: open legs whose contract is live (an exited leg is never priced again)."""
    return [leg.instrument_id for leg, reason, held in zip(legs, reasons, bk.legs, strict=True)
            if reason is None and not held.exited]


def _opposite(side: str) -> str:
    return "SELL" if side == "BUY" else "BUY"


async def _write(db: Any, strategy_id: int, writing: Coroutine[Any, Any, Sequence[paper_store.StoredOrder]],
                 refused_code: str, refused_as: str) -> _Book:
    """Awaits the paper store write and commits; the store's ``refused_code`` answers ``refused_as`` (409), any other
    store refusal its own answer; nothing is stored on any refusal or error (rolled back)."""
    try:
        written = await writing
        await db.commit()
    except store.StrategyStoreError as exc:
        await db.rollback()
        if exc.code == refused_code:
            raise StrategyRefused(refused_as, Failure.CONFLICT) from None
        raise refused_answer(exc, 409) from None
    except Exception:
        await db.rollback()
        raise
    bk = _book(strategy_id, written)
    if bk is None:
        raise RuntimeError(f"strategy {strategy_id}: the paper orders just written cannot be read back")
    return bk


@router.get("/strategies/{strategy_id}/tracking", response_model=TrackingOut)
async def get_tracking(strategy_id: int,  # noqa: PLR0913 - FastAPI dependencies
                       db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                       ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                       feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                       now: Annotated[AnswerClock, Depends(get_answer_clock)],
                       threshold: Annotated[Decimal, Depends(get_near_level_threshold)]) -> TrackingOut:
    stored = await _load(db, user_ref, strategy_id)
    bk = await _load_book(db, strategy_id)
    if bk is None:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    return await _answer(db, stored, bk, ctx, feed, threshold, now())


@router.post("/strategies/{strategy_id}/tracking/exit", response_model=TrackingOut)
async def exit_tracking(strategy_id: int, body: TrackingExitIn,  # noqa: PLR0913 - FastAPI dependencies
                        db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                        feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                        now: Annotated[AnswerClock, Depends(get_answer_clock)],
                        threshold: Annotated[Decimal, Depends(get_near_level_threshold)]) -> TrackingOut:
    """REQ-109 AC-4 / AC-5 (GC-BP step 5): paper-exit the named legs at their live price now, read by the server from
    the same market context as the start: one `exit` order per named leg for its whole open quantity. Any named leg
    not live refuses the whole exit (nothing stored): a contract no longer live answers
    tracking_exit_contract_not_live (it never comes back), a live contract whose price is stale or missing answers
    tracking_exit_prices_not_live (AC-5: try again when prices update). The store re-checks under the strategy's row
    lock that each exit reduces and never exceeds the open quantity, so a leg exits once even when two exits race."""
    stored = await _load(db, user_ref, strategy_id)
    bk = await _load_book(db, strategy_id)
    if bk is None:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    if len(set(body.legs)) != len(body.legs) or any(i >= len(bk.legs) for i in body.legs):
        raise StrategyRefused("tracking_exit_legs_invalid")
    if set(body.legs) & set(bk.exit_prices):
        raise StrategyRefused("tracking_leg_already_exited", Failure.CONFLICT)
    if not _connected(ctx):
        raise StrategyRefused("tracking_not_connected", Failure.CONFLICT)
    legs, reasons = await _entry_legs(db, bk)
    if any(reasons[i] is not None for i in body.legs):
        # Review M2: a retired / delisted / token-reassigned contract never comes back, so "try again" cannot work;
        # the exit's own contract-not-live refusal (never priced from another contract), nothing stored.
        raise StrategyRefused("tracking_exit_contract_not_live", Failure.CONFLICT)
    named = [legs[i] for i in body.legs]
    snapshot = await _snapshot(ctx, feed, stored.saved.definition.underlying, [leg.instrument_id for leg in named])
    try:
        prices = paper.exit_prices_now(snapshot, named)
    except paper.PricesNotLive:
        raise StrategyRefused("tracking_exit_prices_not_live", Failure.CONFLICT) from None
    answered = now()
    orders = [paper_store.NewOrder(bk.contract_ids[i], _opposite(bk.legs[i].side), bk.legs[i].quantity,
                                   p.price, "exit", p.at or answered)  # type: ignore[arg-type] - live: price set
              for i, p in zip(body.legs, prices, strict=True)]
    # a racing exit that closed the leg first makes this one exceed the open quantity: refused as already exited
    after = await _write(db, strategy_id, paper_store.place(db, user_ref, strategy_id, orders),
                         paper_store.EXIT_EXCEEDS_OPEN, "tracking_leg_already_exited")
    return await _answer(db, stored, after, ctx, feed, threshold, answered)


@router.get("/tracking", response_model=TrackingListOut)
async def list_tracking(db: Annotated[Any, Depends(get_db)],  # noqa: PLR0913 - FastAPI dependencies
                        user_ref: Annotated[str, Depends(current_user_ref)],
                        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                        feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                        now: Annotated[AnswerClock, Depends(get_answer_clock)],
                        threshold: Annotated[Decimal, Depends(get_near_level_threshold)]) -> TrackingListOut:
    """GC-BP step 4: every tracked strategy (one with paper orders) of the signed-in user (never another user's: the
    store filters by the strategies table's owner) with total / booked / unbooked and per-leg figures. Fixed cost
    whatever the count (finding F-3): one order query, one contract batch (two queries), and ONE market read per
    underlying for all open legs together. A fully exited strategy needs no read. A read failure raises (the house
    refusal), never a partial list."""
    rows = [(r, _book(r.strategy_id, r.orders)) for r in await paper_store.load_all(db, user_ref)]
    books = [(r, bk) for r, bk in rows if bk is not None]
    contracts = await tracked_contracts.resolve(db, [cid for _, bk in books for cid in bk.contract_ids])
    built = []
    start = 0
    for r, bk in books:
        count = len(bk.legs)
        legs, reasons = _legs_of(bk, contracts[start:start + count])
        start += count
        built.append((r, bk, legs, reasons))
    connected = _connected(ctx)
    keys: dict[str, list[str]] = {}
    for r, bk, legs, reasons in built:
        keys.setdefault(r.underlying, [])
        keys[r.underlying] += [k for k in _open_keys(bk, legs, reasons) if k not in keys[r.underlying]]
    snapshots = {}
    if connected:
        for underlying, ids in keys.items():
            if ids or any(len(bk.exit_prices) < len(lg) for r, bk, lg, _ in built if r.underlying == underlying):
                snapshots[underlying] = await _snapshot(ctx, feed, underlying, ids)  # type: ignore[arg-type]
    out = []
    checked = check_threshold(threshold)
    for r, bk, legs, reasons in built:
        exits = bk.exit_prices
        if len(exits) == len(legs):
            view = paper.tracking_view(None, legs, checked, reasons, exits)
        elif connected:
            view = paper.tracking_view(snapshots[r.underlying], legs, checked, reasons, exits)
        else:
            view = None
        figures = _figures(bk, legs, view, reasons)
        out.append({"strategy_id": bk.strategy_id, "name": sf.shown_name(r.name), "underlying": r.underlying,
                    "started_at": bk.started_at} | figures | _texts(figures))
    return TrackingListOut.model_validate({"strategies": out, "answered_at": now()})
