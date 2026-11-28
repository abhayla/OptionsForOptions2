"""GET /api/market/exit-state: the Exit dialog's market-closed answer (ADR-330 (60)). See ``ofo_app.exit_market``."""
from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from ofo_app.api_models import ApiModel, CatalogueText
from ofo_app.errors import ClosedRoute
from ofo_app.exit_market import entries_sentence, exit_market_answer
from ofo_app.routes.outcome import AnswerClock, MarketContext, get_answer_clock, get_market_context

router = APIRouter(route_class=ClosedRoute)


class ExitMarketOut(ApiModel):
    closed: bool
    sentence: CatalogueText | None
    entries_sentence: CatalogueText | None  # FD4 item 5: the same day, for ENTRIES
    next_open_at: datetime.datetime | None
    server_time: datetime.datetime  # FD2 item 4: the server's own aware clock (the dialog's price age is against it)


@router.get("/api/market/exit-state", response_model=ExitMarketOut)
async def market_exit_state(ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                            now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> ExitMarketOut:
    at = now()
    closed, sentence, opens = exit_market_answer(ctx, at)
    return ExitMarketOut(closed=closed, sentence=sentence, entries_sentence=entries_sentence(opens) if closed else None,
                         next_open_at=opens, server_time=at)
