"""WebSocket /api/strategies/live (W-065; REQ-035 AC-4, REQ-048 AC-1/AC-4/AC-5, ADR-068 (2)).

The browser opens this socket and sends the same body it would POST to /api/strategies/outcome. The server subscribes
that strategy's legs and the index on the ONE shared fan-out (never a vendor connection per browser) and pushes the
outcome from :func:`ofo_app.routes.outcome.outcome_response` - the REST route's own function, so one engine - at most
once a second and only when an input changed (:class:`ofo_app.live_push.StrategyPush`). Every message is minted by the
response door (`ClosedWebSocketRoute`): an `OutcomeResponse` or a catalogue message, nothing else. No token, key or
session value travels on this socket or in its URL.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from ofo_app.errors import ClosedSocket, ClosedWebSocketRoute
from ofo_app.live_push import LiveFeed, StrategyPush
from ofo_app.routes.outcome import OutcomeResponse

PATH = "/api/strategies/live"

#: The replay feed builder (W-064 test mode, APP_ENV=test only; ofo_app.replay_mode.ReplayFeeds), set by create_app;
#: None otherwise. It builds one feed per connection, so a reconnecting browser gets prices again (W-065 phase 3).
_replay_feed: Optional[Callable[[], LiveFeed]] = None


def set_replay_feed(builder: Optional[Callable[[], LiveFeed]]) -> None:
    global _replay_feed
    _replay_feed = builder


def current_feed() -> Optional[LiveFeed]:
    """The running app's shared live feed (LIVE_MARKET with a session), a new test replay feed for this connection, or
    None (not connected)."""
    if _replay_feed is not None:
        return _replay_feed()
    from ofo_app import live_market  # late: live_market imports this package's outcome module
    return live_market.current_feed()


async def strategy_live(socket: ClosedSocket) -> None:
    await StrategyPush(socket, current_feed(), monotonic=time.monotonic).run()


def socket_route() -> ClosedWebSocketRoute:
    """The door socket route; create_app adds it with ``errors.add_socket_route`` (not ``include_router``, which would
    rebuild it as a plain APIWebSocketRoute)."""
    return ClosedWebSocketRoute(PATH, strategy_live, message_models=(OutcomeResponse,), name="strategy_live")
