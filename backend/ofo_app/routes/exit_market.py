"""GET /api/market/exit-state: the Exit dialog's market-closed answer (ADR-330 (60)). See ``ofo_app.exit_market``."""
from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from ofo_app.api_models import ApiModel, CatalogueText
from ofo_app.errors import ClosedRoute
from ofo_app.exit_market import exit_market_answer
from ofo_app.routes.outcome import AnswerClock, MarketContext, get_answer_clock, get_market_context

router = APIRouter(route_class=ClosedRoute)


class ExitMarketOut(ApiModel):
    closed: bool
    sentence: CatalogueText | None
    next_open_at: datetime.datetime | None


@router.get("/api/market/exit-state", response_model=ExitMarketOut)
async def market_exit_state(ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                            now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> ExitMarketOut:
    closed, sentence, opens = exit_market_answer(ctx, now())
    return ExitMarketOut(closed=closed, sentence=sentence, next_open_at=opens)
