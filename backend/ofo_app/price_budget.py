"""One time budget for the price reads of a screen check (REQ-119 AC-4; ADR-016 to ADR-019).

Real case (Lane Q2, 27 Nov): the adjustment check awaited its Zerodha index quote with no limit, so one stalled quote
held the page for as long as Zerodha took; plan watch already cut its reads at 4 s. One capability, one module: the two
price readers of a check (the market read and the REST index quote) under ONE shared deadline measured from the first
read. A read that has not answered by then is cancelled and replaced by the NOT LIVE answer, never a guessed price:
the market as when not connected (no chain, no feed spot), the REST quote as FAILED. Once the market read is cut, or
no budget is left, the REST reader is not called at all (a STATED spot beside a not-connected market would break the
figures). Each cut is logged once with its cause. The caller says what not live means for it (``not_live_market``).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Final

from ofo.marketdata.spot_source import SourceReading, SourceState

log = logging.getLogger(__name__)

PRICE_BUDGET_S: Final = 4.0


def budgeted(market_reader: Callable[[Any, Any], Awaitable[Any]],
             rest_reader: Callable[[str], Awaitable[SourceReading]], *, budget_s: float | None = None,
             not_live_market: Callable[[Any, Any], Awaitable[Any]]) -> tuple[Callable[..., Awaitable[Any]],
                                                                             Callable[..., Awaitable[SourceReading]]]:
    """The two readers under one shared deadline (module docstring). ``not_live_market(tracked, None)`` is the answer
    for a market read that was cut."""
    budget_s = PRICE_BUDGET_S if budget_s is None else budget_s  # read at call time (a test sets a short one)
    loop = asyncio.get_running_loop()
    started: list[float] = []
    market_cut: list[bool] = []

    def left() -> float:
        if not started:
            started.append(loop.time())
        return started[0] + budget_s - loop.time()

    async def market(tracked: Any, ctx: Any) -> Any:
        try:
            async with asyncio.timeout(max(left(), 0)):
                return await market_reader(tracked, ctx)
        except TimeoutError:
            market_cut.append(True)
            log.warning("price budget: market read over %.1f s, answered as not live", budget_s)
            return await not_live_market(tracked, None)

    async def rest(underlying: str) -> SourceReading:
        if market_cut or left() <= 0:
            log.warning("price budget: no budget left for the index quote, answered as not live")
            return SourceReading(SourceState.FAILED)
        try:
            async with asyncio.timeout(max(left(), 0)):
                return await rest_reader(underlying)
        except TimeoutError:
            log.warning("price budget: index quote over the budget, answered as not live")
            return SourceReading(SourceState.FAILED)
    return market, rest
