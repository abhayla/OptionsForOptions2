"""GET / PUT /api/strategies/{id}/alert-style: the strategy's alert style, automatic or pinned (REQ-170 Q-AD-2).

Spec basis: REQ-170 Q-AD-2 "the style is taken from the strategy and changes by itself as expiry nears (0-1 day to
expiry = intraday rules, a weekly expiry = weekly, a monthly expiry = monthly) ... the user may pin a style per
strategy"; REQ-168 AC-3 (keyed by the user). Finding engine-input-chosen-per-caller: the style shown is
``alert_presets.style_for``'s answer, read here on the strategy's own legs; the screen never computes it.

- GET: {pinned: style | null, automatic: style | null, in_force: style | null, reason_text, choices}. ``automatic`` is
  ``style_for(expiry kind, days left, None)`` on the strategy's own legs (the expiry kind from the market reader's
  ``expiry_kind_of``, days from ``ofo.timeutil.days_to_expiry`` at the reader's clock); ``in_force`` is the pin when
  pinned, else ``automatic``.
- PUT {style: null | intraday | weekly | monthly}: the pin from now (null = automatic again), then the GET reply.
- Answer states: pinned / automatic (no row or a NULL row); legs on several expiries -> automatic null with
  ``alert_style_several_expiries``; an expiry kind or days the resolver refuses, no open leg, or a market read that
  fails -> automatic null with ``alert_style_expiry_unknown`` (never a guessed style); another user's or a missing
  strategy -> 404; a style outside the list -> 422 with ``alert_style_refused_unknown``; the same instant twice -> 409.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment import alert_presets
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.timeutil import days_to_expiry
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app import strategy_alert_style_store as store
from ofo_app.api_models import ApiModel, CatalogueText
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure, respond
from ofo_app.routes.adjustment import MarketReader, TrackedReader, get_market_reader, get_tracked_reader
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import MarketContext, get_market_context
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
Db = Annotated[AsyncSession, Depends(get_db)]
StyleName = Literal["intraday", "weekly", "monthly"]
_NOT_AVAILABLE = "user_input_request_not_available"
SEVERAL = "alert_style_several_expiries"
UNKNOWN = "alert_style_expiry_unknown"


class StyleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: str | None


class ChoiceOut(ApiModel):
    value: StyleName | None  # None: automatic
    label: CatalogueText


class AlertStyleOut(ApiModel):
    strategy_id: int
    label: CatalogueText
    pinned: StyleName | None
    automatic: StyleName | None
    in_force: StyleName | None
    reason_text: CatalogueText | None
    choices: list[ChoiceOut]


class RefusedOut(ApiModel):
    reason: CatalogueText


def style_name(style: str) -> ExplanationText:
    return render_explanation(f"alert_style_name_{style}")


async def automatic_style(strategy_id: int, tracked_reader: TrackedReader, market_reader: MarketReader,
                          ctx: MarketContext | None) -> tuple[alert_presets.Style | None, str | None]:
    """(the automatic style, None) or (None, the catalogue id of why it cannot be told)."""
    from ofo_app.adjustment_readers import TrackedUnreadable, ist_today  # noqa: PLC0415 - it imports routes.adjustment
    try:
        tracked = await tracked_reader(strategy_id, None)
    except TrackedUnreadable as exc:
        log.warning("alert style: strategy %s unreadable: %s", strategy_id, exc)
        return None, UNKNOWN
    if tracked is None:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND)
    expiries = {leg.expiry for leg in tracked.position.legs}
    if len(expiries) != 1:
        return None, SEVERAL
    try:
        market = await market_reader(tracked, ctx)
    except (ValueError, LookupError) as exc:
        log.warning("alert style: strategy %s market read refused: %s", strategy_id, exc)
        return None, UNKNOWN
    days = days_to_expiry(next(iter(expiries)), ist_today(market.now))
    try:
        return alert_presets.style_for(market.expiry_kind, days, None), None
    except alert_presets.StyleRefused:
        return None, UNKNOWN


async def _reply(db: AsyncSession, user: str, strategy_id: int, tracked_reader: TrackedReader,  # noqa: PLR0913
                 market_reader: MarketReader, ctx: MarketContext | None) -> AlertStyleOut:
    try:
        pin = await store.pin_of(db, user, strategy_id)
    except store.StyleNotFound:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND) from None
    auto, reason = await automatic_style(strategy_id, tracked_reader, market_reader, ctx)
    auto_label = (render_explanation("alert_style_automatic_unknown") if auto is None
                  else render_explanation("alert_style_automatic_now", style=style_name(auto)))
    choices = [ChoiceOut(value=None, label=auto_label)]
    choices += [ChoiceOut(value=s, label=style_name(s)) for s in alert_presets.STYLES]
    return AlertStyleOut(strategy_id=strategy_id, label=render_explanation("alert_style_label"), pinned=pin.style,
                         automatic=auto, in_force=pin.style if pin.style is not None else auto,
                         reason_text=None if reason is None else render_explanation(reason), choices=choices)


@router.get("/api/strategies/{strategy_id}/alert-style", response_model=AlertStyleOut)
async def read_alert_style(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, db: Db, user: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)]) -> AlertStyleOut:
    return await _reply(db, user, strategy_id, tracked_reader, market_reader, ctx)


@router.put("/api/strategies/{strategy_id}/alert-style", response_model=AlertStyleOut)
async def pin_alert_style(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, body: StyleIn, db: Db, user: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)]) -> Any:
    try:
        await store.set_pin(db, user, strategy_id, body.style)
        await db.commit()
    except store.StyleNotFound:
        await db.rollback()
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND) from None
    except store.StyleSameTime:
        await db.rollback()
        return respond(RefusedOut(reason=render_explanation("settings_refused_same_time")), 409)
    except store.AlertStyleError:
        await db.rollback()
        return respond(RefusedOut(reason=render_explanation("alert_style_refused_unknown")), 422)
    except Exception:
        await db.rollback()
        raise
    return await _reply(db, user, strategy_id, tracked_reader, market_reader, ctx)
