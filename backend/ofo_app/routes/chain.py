"""The Option Chain reads (W-116; REQ-029 AC-1/AC-2/AC-4/AC-6/AC-8, REQ-049 AC-2, ADR-077). Read-only.

- WebSocket ``/api/market/chain/live``: the client sends ``{underlying, expiry, strikes_each_side}``; the server
  subscribes that expiry's contracts around ATM and the index on the ONE shared fan-out (never a vendor connection per
  browser) and pushes :class:`ofo_app.chain_push.ChainOut` at most once a second when a shown value changed
  (:class:`ofo_app.chain_push.ChainPush`). Every message is minted by the response door (`ClosedWebSocketRoute`); no
  token, key or session value travels on it or in its URL. The test replay (APP_ENV=test, OUTCOME_REPLAY) gives each
  connection its own replay feed through the strategy socket's builder (``routes.live.current_feed``).
- ``POST /api/market/chain/preview`` (W-124, REQ-031): the selected legs in, the outcome route's own summary numbers
  out (net premium, max profit / loss, breakevens, payoff points, the matched template's name); read-only.
- ``GET /api/market/chain``: the screen's first paint, and with ``fallback=true`` the refresh of a screen whose own
  socket is down: then the answer is NOT_CONNECTED whoever else holds the contracts (finding
  liveness-from-shared-subscribers). No live feed: NOT_CONNECTED.

No order, basket, margin or execute call is reachable from here (REQ-029 AC-6). V1 has one fixed owner and no login;
like ``/api/strategies/live`` these reads carry no user value.
"""
from __future__ import annotations

import datetime
import time
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from ofo_app.chain_push import (
    DEFAULT_STRIKES_EACH_SIDE,
    MAX_STRIKES_EACH_SIDE,
    ChainCatalogue,
    ChainOut,
    ChainPush,
    ChainReader,
    ChainRequest,
    chain_answer,
    index_id_of,
    pick_window,
    stored_chain,
    window_ids,
)
from ofo_app.chain_preview import PreviewOut, PreviewRequest, preview_answer
from ofo_app.errors import ClosedRoute, ClosedSocket, ClosedWebSocketRoute
from ofo_app.routes import live, outcome
from ofo_app.routes.outcome import (
    AnswerClock,
    MarketContext,
    get_answer_clock,
    get_market_context,
    get_streaming,
    inputs_streaming,
)

PATH = "/api/market/chain/live"
REST_PATH = "/api/market/chain"
PREVIEW_PATH = REST_PATH + "/preview"

router = APIRouter(route_class=ClosedRoute)


def get_chain_reader() -> ChainReader:
    """The stored-catalogue seam: tests override this dependency with a fake catalogue."""
    return stored_chain


def chain_read(ctx: MarketContext | None, streaming: Callable[[str], bool] | None, req: ChainRequest,  # noqa: PLR0913
               catalogue: ChainCatalogue, *, fallback: bool, now: AnswerClock) -> ChainOut:
    """The REST answer. ``fallback``: this screen's own socket is down, so it is not live whatever other sockets hold.
    Otherwise live only while every shown contract and the index are held by a socket (issue #206's rule)."""
    window = pick_window(ctx, req, catalogue)
    live_now = False
    if ctx is not None and not fallback:
        index_id = index_id_of(ctx, req.underlying)
        ids = window_ids(catalogue, window) + ([index_id] if index_id else [])
        live_now = inputs_streaming(ctx, streaming, ids)
    return chain_answer(ctx, req, catalogue, window, live=live_now, now=now)


@router.get(REST_PATH, response_model=ChainOut)
async def market_chain(  # noqa: PLR0913 - one query parameter or seam each
        underlying: Annotated[Literal["NIFTY", "SENSEX"], Query()],
        expiry: Annotated[datetime.date, Query()],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        streaming: Annotated[Callable[[str], bool] | None, Depends(get_streaming)],
        now: Annotated[AnswerClock, Depends(get_answer_clock)],
        reader: Annotated[ChainReader, Depends(get_chain_reader)],
        strikes_each_side: Annotated[int, Query(ge=1, le=MAX_STRIKES_EACH_SIDE)] = DEFAULT_STRIKES_EACH_SIDE,
        fallback: Annotated[bool, Query(description="true when the screen's own chain socket is down (ADR-077): the "
                                                    "answer is then not live whoever else subscribes")] = False,
) -> ChainOut:
    req = ChainRequest(underlying=underlying, expiry=expiry, strikes_each_side=strikes_each_side)
    return chain_read(ctx, streaming, req, await reader(underlying, expiry), fallback=fallback, now=now)


@router.post(PREVIEW_PATH, response_model=PreviewOut)
def market_chain_preview(  # noqa: PLR0913 - one request body or seam each
        req: PreviewRequest,
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        streaming: Annotated[Callable[[str], bool] | None, Depends(get_streaming)],
        now: Annotated[AnswerClock, Depends(get_answer_clock)],
) -> PreviewOut:
    return preview_answer(req, ctx, streaming, now=now)


async def chain_live(socket: ClosedSocket) -> None:
    await ChainPush(socket, live.current_feed(), monotonic=time.monotonic, now=outcome.server_now).run()


def socket_route() -> ClosedWebSocketRoute:
    """The door socket route; create_app adds it with ``errors.add_socket_route``."""
    return ClosedWebSocketRoute(PATH, chain_live, message_models=(ChainOut,), name="chain_live")
