"""The Underlying/index view's reads (W-114; REQ-072 AC-2, REQ-049 AC-2/AC-4, ADR-077).

- WebSocket ``/api/market/indices/live``: read-only. The server subscribes the NIFTY 50 and SENSEX index instruments on
  the ONE shared fan-out (never a vendor connection per browser) and pushes :class:`ofo_app.index_push.IndicesOut` at
  most once a second when a row changed (:class:`ofo_app.index_push.IndexPush`). Every message is minted by the response
  door (`ClosedWebSocketRoute`); no token, key or session value travels on it or in its URL. The test replay
  (APP_ENV=test, OUTCOME_REPLAY) gives each connection its own replay feed, through the strategy socket's builder
  (``routes.live.current_feed``), so both sockets read the same feed in every mode.
- ``GET /api/market/indices``: the page's first paint, and with ``fallback=true`` the refresh of a page whose own socket
  is down: then the answer is NOT_CONNECTED with each index's last value time, whoever else holds the indices (finding
  liveness-from-shared-subscribers). No live feed: NOT_CONNECTED, every value null.

V1 has one fixed owner and no login (``routes/broker.py`` ``current_user_ref``); like ``/api/strategies/live`` these
reads carry no user value.
"""
from __future__ import annotations

import time
from typing import Annotated, Callable, Optional

from fastapi import APIRouter, Depends, Query

from ofo_app.errors import ClosedRoute, ClosedSocket, ClosedWebSocketRoute
from ofo_app.index_push import IndexPush, IndicesOut, index_ids, indices_answer
from ofo_app.routes import live, outcome
from ofo_app.routes.outcome import AnswerClock, MarketContext, get_answer_clock, get_market_context, get_streaming

PATH = "/api/market/indices/live"
REST_PATH = "/api/market/indices"

router = APIRouter(route_class=ClosedRoute)


def held_by_a_socket(ctx: MarketContext, streaming: Optional[Callable[[str], bool]]) -> bool:
    """True when every known index id is streaming on the shared feed (the outcome route's rule, issue #206). No
    predicate (no live feed: a test's own context) or a predicate of another context: the provider's quotes are used as
    they are, like the outcome route."""
    if streaming is None:
        return True
    owner = getattr(streaming, "ctx", None)  # the replay's predicate names its own context (ofo_app.replay_mode)
    if ctx is not (owner if owner is not None else outcome.live_context()):
        return True
    return all(streaming(i) for i in index_ids(ctx).values() if i is not None)


def indices_read(ctx: Optional[MarketContext], streaming: Optional[Callable[[str], bool]], *, fallback: bool,
                 now: AnswerClock) -> IndicesOut:
    """The REST answer. ``fallback``: this page's own socket is down, so it is not live whatever other sockets hold."""
    live_now = ctx is not None and not fallback and held_by_a_socket(ctx, streaming)
    return indices_answer(ctx, live=live_now, now=now)


@router.get(REST_PATH, response_model=IndicesOut)
def market_indices(ctx: Annotated[Optional[MarketContext], Depends(get_market_context)],
                   streaming: Annotated[Optional[Callable[[str], bool]], Depends(get_streaming)],
                   now: Annotated[AnswerClock, Depends(get_answer_clock)],
                   fallback: Annotated[bool, Query(description="true when the page's own index socket is down "
                                                               "(ADR-077): the answer is then not live whoever else "
                                                               "subscribes")] = False) -> IndicesOut:
    return indices_read(ctx, streaming, fallback=fallback, now=now)


async def indices_live(socket: ClosedSocket) -> None:
    await IndexPush(socket, live.current_feed(), monotonic=time.monotonic, now=outcome.server_now).run()


def socket_route() -> ClosedWebSocketRoute:
    """The door socket route; create_app adds it with ``errors.add_socket_route``."""
    return ClosedWebSocketRoute(PATH, indices_live, message_models=(IndicesOut,), name="indices_live")
