"""POST/GET /strategies/{id}/tracking: paper tracking of a saved strategy and one platform detection (W-122).

Spec basis: REQ-109 AC-1 (a paper entry per leg at the leg's live price, with time and price health; no account-wide
switch), AC-2 (paper P&L from the one engine, exact Decimal, never mixed with real P&L), AC-3 (tracking never reaches
Execute: this module imports nothing from the order path), AC-5 (stale or missing prices pause paper P&L); REQ-045 Q253
condition 1 and AC-1/AC-2 (ofo.adjustment.detection); REQ-046 AC-1 (each detection's Layer 1 numbers).

- Start: the body carries only the strategy revision the user is looking at (extra keys - prices included - are
  refused, 422). The server reads every leg's price from the same market context as the outcome route
  (``get_market_context``: the live feed, or the test replay) and refuses the start when any is stale or missing, when
  no feed runs, when the strategy changed since that revision, or when it is already tracked. Nothing is stored then.
- View: the stored entry, current prices, paper P&L (engine) or the paused state, and the detections.
- Contract identity (round 3 redesign): every stored contract id reaches a feed key ONLY through
  ofo_app.tracked_contracts.resolve, which gives a key only for a live contract still holding its own exchange token.
  A retired, delisted, token-reassigned or missing contract refuses the start (tracking_contract_not_live) and pauses
  the view with that reason (pause_reason; no paper P&L, no detection) - never a price from another contract.
The user comes from the session (``current_user_ref``), never from the request.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment.detection import NEAR_LEVEL_THRESHOLD_PERCENT, PLATFORM_DETECTION, check_threshold
from ofo.engine.legs import Action, Instrument
from ofo.instruments.models import FUTURE_TYPE
from ofo.money import PAISE
from ofo.outcome import read_snapshot
from ofo.tracking import paper
from pydantic import BaseModel, ConfigDict, Field

from ofo_app import strategy_store as store
from ofo_app import tracked_contracts, tracking_store
from ofo_app.api_models import ApiModel, InstrumentId, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.live_push import LiveFeed
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import AnswerClock, MarketContext, get_answer_clock, get_market_context
from ofo_app.routes.planned_entry import get_live_feed, hold_until_priced
from ofo_app.routes.strategies import StrategyRefused, refused_answer
from ofo_app.underlying import Underlying

router = APIRouter(route_class=ClosedRoute)

PriceStateCode = paper.PriceState


def get_near_level_threshold() -> Decimal:
    """Q253 condition 1's threshold (an admin setting; the admin screen is Step 6). Tests override this dependency."""
    return NEAR_LEVEL_THRESHOLD_PERCENT


class TrackingStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(gt=0, le=2**31 - 1, description="the saved strategy revision the user started tracking from")


class TrackingLegOut(ApiModel):
    instrument_id: InstrumentId
    action: Literal["BUY", "SELL"]
    instrument: Literal["CE", "PE", "FUT"]
    strike: Money | None
    expiry: datetime.date
    quantity: int
    entry_price: Money
    entry_at: datetime.datetime
    current_price: Money | None
    price_state: paper.LegState
    price_at: datetime.datetime | None


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


class TrackingOut(ApiModel):
    strategy_id: int
    started_at: datetime.datetime
    prices_at: datetime.datetime
    state: Literal["LIVE", "PAUSED", "NOT_CONNECTED"]
    pause_reason: paper.PauseReason | None
    paper_pnl: Money | None
    as_of: datetime.datetime | None
    answered_at: datetime.datetime
    legs: list[TrackingLegOut]
    index: TrackingIndexOut | None
    breakevens: list[Money] | None
    detections: list[DetectionOut]


def _legs(saved, ids: list[str]) -> list[paper.TrackedLeg]:
    """The saved definition's legs as paper legs to price at the START only (their entry price is set by
    paper.capture_entry); the view never uses this (it reads the stored entry, _entry_legs)."""
    unset = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    return [paper.TrackedLeg(iid, leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity, Decimal(0), unset)
            for iid, leg in zip(ids, saved.definition.legs, strict=True)]


async def _snapshot(ctx: MarketContext, feed: LiveFeed | None, underlying: str, ids: list[str]):
    """One market read for the legs and the index. With a live feed, legs nobody holds are held until their first live
    quote or the planned-entry wait passes (the same rule and helper as the planned-entry route)."""
    snapshot = read_snapshot(ctx.provider, underlying, ids, ctx.clock(), ctx.rate)
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


def _money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(PAISE)


def _view(tracking: tracking_store.Tracking, legs: list[paper.TrackedLeg], underlying: str,  # noqa: PLR0913
          view: paper.TrackingView | None, answered_at: datetime.datetime,
          reasons: list[paper.ContractReason | None]) -> TrackingOut:
    rows = []
    for i, leg in enumerate(legs):
        price = None if view is None else view.legs[i]
        rows.append({"instrument_id": leg.instrument_id, "action": leg.action.value, "instrument": leg.instrument.value,
                     "strike": leg.strike, "expiry": leg.expiry, "quantity": leg.quantity,
                     "entry_price": leg.entry_price, "entry_at": leg.price_at,
                     "current_price": None if price is None else price.price,
                     "price_state": (reasons[i] or "missing") if price is None else price.state,
                     "price_at": None if price is None else price.at})
    body: dict = {"strategy_id": tracking.strategy_id, "started_at": tracking.started_at,
                  "prices_at": tracking.prices_at, "answered_at": answered_at, "legs": rows, "detections": []}
    if view is None:
        return TrackingOut.model_validate(body | {"state": "NOT_CONNECTED", "paper_pnl": None, "as_of": None,
                                                  "index": None, "breakevens": None,
                                                  "pause_reason": next((r for r in reasons if r), None)})
    index = view.index
    body["pause_reason"] = view.pause_reason
    body |= {"state": "PAUSED" if view.paused else "LIVE", "paper_pnl": _money(view.paper_pnl), "as_of": view.as_of,
             "index": {"underlying": underlying, "level": index.price, "state": index.state, "at": index.at},
             "breakevens": None if view.breakevens is None else list(view.breakevens)}
    body["detections"] = [{"kind": PLATFORM_DETECTION, "condition": d.condition, "level": d.level,
                           "index_level": d.index_level, "distance_points": d.distance_points,
                           "distance_percent": d.distance_percent, "threshold_percent": d.threshold_percent,
                           "at": index.at, "price_health": index.state} for d in view.detections]
    return TrackingOut.model_validate(body)


async def _entry_legs(db: Any, tracking: tracking_store.Tracking) \
        -> tuple[list[paper.TrackedLeg], list[paper.ContractReason | None]]:
    """REQ-109 AC-2 ("from the paper entry prices"): the tracked legs come ONLY from the stored paper entry - each row's
    catalogue contract, side, quantity, entry price and time. The strategy as saved now is never read here, so an edit
    after the start changes nothing in the tracked figures. Each contract goes through tracked_contracts.resolve: a
    leg whose contract is not live keeps its stored terms and its own (old) exchange identity for display, is left out
    of the market read, and carries its reason, so paper.tracking_view never prices it. A tracked row whose contract
    row is missing (contract_missing; the foreign key and the never-delete catalogue forbid it) has no terms to show
    and fails closed: an error, never invented terms."""
    legs = []
    contracts = await tracked_contracts.resolve(db, [row.contract_id for row in tracking.legs])
    for row, found in zip(tracking.legs, contracts, strict=True):
        if found.stored is None or found.identity is None:
            raise RuntimeError(f"tracked contract id {row.contract_id} has no stored contract row ({found.state})")
        contract = found.stored.listed.contract
        future = contract.instrument_type == FUTURE_TYPE
        legs.append(paper.TrackedLeg(found.identity, Action(row.side),
                                     Instrument(contract.instrument_type),
                                     None if future else contract.strike, contract.expiry, row.quantity,
                                     row.entry_price, row.price_at))
    return legs, tracked_contracts.reasons(contracts)


async def _answer(db: Any, stored, tracking: tracking_store.Tracking, ctx: MarketContext | None,  # noqa: PLR0913
                  feed: LiveFeed | None, threshold: Decimal, answered_at: datetime.datetime) -> TrackingOut:
    legs, reasons = await _entry_legs(db, tracking)
    underlying = stored.saved.definition.underlying  # fixed for the strategy's life (strategy_store UNDERLYING_FIXED)
    if not _connected(ctx):
        return _view(tracking, legs, underlying, None, answered_at, reasons)
    keys = [leg.instrument_id for leg, reason in zip(legs, reasons, strict=True) if reason is None]
    snapshot = await _snapshot(ctx, feed, underlying, keys)
    view = paper.tracking_view(snapshot, legs, check_threshold(threshold), reasons)
    return _view(tracking, legs, underlying, view, answered_at, reasons)


@router.post("/strategies/{strategy_id}/tracking", status_code=201, response_model=TrackingOut)
async def start_tracking(strategy_id: int, body: TrackingStartIn,  # noqa: PLR0913 - FastAPI dependencies
                         db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                         ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                         feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                         now: Annotated[AnswerClock, Depends(get_answer_clock)],
                         threshold: Annotated[Decimal, Depends(get_near_level_threshold)]) -> TrackingOut:
    stored = await _load(db, user_ref, strategy_id)
    if stored.revision != body.revision:
        raise StrategyRefused("strategy_revision_conflict", Failure.CONFLICT)
    if await tracking_store.load(db, strategy_id) is not None:
        raise StrategyRefused("tracking_already_started", Failure.CONFLICT)
    if not _connected(ctx):
        raise StrategyRefused("tracking_not_connected", Failure.CONFLICT)
    contracts = await tracked_contracts.resolve(db, stored.saved.contract_ids)
    ids = [c.feed_key for c in contracts if c.feed_key is not None]
    if len(ids) != len(contracts):
        raise StrategyRefused("tracking_contract_not_live", Failure.CONFLICT)
    snapshot = await _snapshot(ctx, feed, stored.saved.definition.underlying, ids)
    try:
        entry = paper.capture_entry(snapshot, _legs(stored.saved, ids))
    except paper.PricesNotLive:
        raise StrategyRefused("tracking_prices_not_live", Failure.CONFLICT) from None
    try:
        tracking = await tracking_store.start(db, user_ref, strategy_id, body.revision, stored.saved.contract_ids,
                                              entry)
        await db.commit()
    except store.StrategyStoreError as exc:
        await db.rollback()
        if exc.code == tracking_store.ALREADY_TRACKED:
            raise StrategyRefused("tracking_already_started", Failure.CONFLICT) from None
        raise refused_answer(exc, 409) from None
    except Exception:
        await db.rollback()
        raise
    return await _answer(db, stored, tracking, ctx, feed, threshold, now())


@router.get("/strategies/{strategy_id}/tracking", response_model=TrackingOut)
async def get_tracking(strategy_id: int,  # noqa: PLR0913 - FastAPI dependencies
                       db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                       ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                       feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                       now: Annotated[AnswerClock, Depends(get_answer_clock)],
                       threshold: Annotated[Decimal, Depends(get_near_level_threshold)]) -> TrackingOut:
    stored = await _load(db, user_ref, strategy_id)
    tracking = await tracking_store.load(db, strategy_id)
    if tracking is None:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    return await _answer(db, stored, tracking, ctx, feed, threshold, now())


