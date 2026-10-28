"""Settings -> Broker & Market Data: the four Zerodha statuses and Disconnect (W-089, REQ-015 AC-4, AC-8; REQ-051 AC-1).

Basis: REQ-015 AC-4 (four separate statuses - account connection, live market data, position/account sync,
order-execution readiness - each Connected, Partially connected (naming what to fix) or Disconnected; "Last successful
sync"), AC-8 (Disconnect keeps strategies, history, entitlements and the account); REQ-051 AC-1 (history is not
available in V1: the reply says so in a closed word).

Copy from: legacy-reuse row for src/components/settings/KiteSettings.vue (ADAPT: the status comes from the server, no
token anywhere in a URL or reply).

Every status is read from real state, never defaulted to Connected:
- account connection: the owner's active, unexpired row in ``broker_sessions`` (read-only, the database clock decides);
- live market data: Connected only when prices are arriving (the provider's feed phase is healthy: connected and a
  price frame inside the REQ-049 window), not merely when the socket task runs; a running socket with no frame yet is
  Partially connected (live_feed_waiting), one in backoff live_feed_reconnecting; with no running feed it names the
  fix (the feed needs LIVE_MARKET on and a subscribed screen);
- position/account sync: Connected only when a Zerodha read succeeded after this session started (``broker_sync``);
- order-execution readiness: Connected only when all three above are, otherwise Partially connected naming what is
  missing; Disconnected without a session.
The reply holds closed words and one time; the page maps each ``fix`` code to its reviewed text. Disconnect ends the
active session with reason 'disconnected' (``broker_token_store.end_session``) and touches no other table.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.broker.session import EndReason
from ofo.market_calendar import price_time
from ofo.marketdata.disconnect import market_closed_error
from ofo.marketdata.feed_health import (
    FEED_CAPPED,
    FEED_ENDED,
    FEED_HEALTHY,
    FEED_IDLE,
    FEED_MARKET_CLOSED,
    FEED_RECONNECTING,
    FEED_WAITING,
)

from ofo_app import broker_sync, live_market
from ofo_app.api_models import ApiModel, CatalogueText
from ofo_app.broker_token_store import active_session_status, end_session
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import get_execute_clock

router = APIRouter(route_class=ClosedRoute)

Level = Literal["connected", "partial", "disconnected"]
Fix = Literal["connect_zerodha", "session_expired", "live_feed_off", "live_feed_not_running", "live_feed_session_ended",
              "no_read_yet", "live_data_not_connected", "positions_not_synced", "live_feed_waiting",
              "live_feed_reconnecting", "live_feed_idle", "live_feed_market_closed", "live_feed_capped"]


class StatusOut(ApiModel):
    state: Level
    fix: Optional[Fix]  # noqa: UP045 - what to fix when not connected; None when connected


class BrokerStatusOut(ApiModel):
    account_connection: StatusOut
    live_market_data: StatusOut
    position_sync: StatusOut
    order_execution: StatusOut
    last_successful_sync: Optional[datetime.datetime]  # noqa: UP045 - None until a read succeeded this session
    # REQ-114 AC-7 (ADR-177): "Market closed. Prices are from <time>." - set only when the live row reads market closed
    # and a price ever arrived (the last price's time, IST); None otherwise, never an invented time
    live_market_closed: Optional[CatalogueText] = None  # noqa: UP045
    historical_data: Literal["not_available"]  # REQ-051 AC-1: the page says history is not available in V1


class DisconnectOut(ApiModel):
    disconnected: bool  # False when there was no active session to end


#: Phases that read "market closed" when the market is closed - an allow-list; ended, capped and healthy keep their own.
_CLOSED_READS = frozenset({FEED_WAITING, FEED_RECONNECTING, FEED_IDLE, FEED_MARKET_CLOSED})


def _status(state: Level, fix: Fix | None = None) -> StatusOut:
    return StatusOut(state=state, fix=fix)


def _live_status(live_state: str, phase: str | None, market_is_open: bool = True) -> StatusOut:
    """``phase`` is the provider's feed phase while the socket runs, None when it does not. Connected only when prices
    are arriving (``healthy``); a running socket with no frame yet, or frames stopped, is waiting; a socket in backoff
    is reconnecting; a socket up with nothing subscribed is idle; never from the socket task being alive.
    Outside market hours (REQ-049 AC-4, #513 item 3; REQ-114 AC-7) a quiet, backing-off or not-running feed is the
    market being closed, not a fault: ``live_feed_market_closed`` says so in every phase except a session Zerodha ended
    (log in again), a capped feed and prices that are arriving, and never advises Reconnect."""
    closed = not market_is_open
    if closed and (phase in _CLOSED_READS or (phase is None and live_state not in (
            live_market.SESSION_ENDED, live_market.NOT_STARTED))):
        return _status("partial", "live_feed_market_closed")
    by_phase = {FEED_HEALTHY: _status("connected"), FEED_WAITING: _status("partial", "live_feed_waiting"),
                FEED_RECONNECTING: _status("partial", "live_feed_reconnecting"),
                FEED_ENDED: _status("partial", "live_feed_session_ended"),
                FEED_IDLE: _status("partial", "live_feed_idle"),
                FEED_CAPPED: _status("partial", "live_feed_capped"),
                FEED_MARKET_CLOSED: _status("partial", "live_feed_market_closed")}
    if phase in by_phase:
        return by_phase[phase]
    if live_state == live_market.SESSION_ENDED:
        return _status("partial", "live_feed_session_ended")
    if live_state == live_market.NOT_STARTED:
        return _status("partial", "live_feed_off")
    return _status("partial", "live_feed_not_running")


def build_status(session: tuple[datetime.datetime, bool] | None, last_read: datetime.datetime | None,  # noqa: PLR0913
                 live_state: str, live_phase: str | None, market_is_open: bool = True,
                 last_price_at: datetime.datetime | None = None) -> BrokerStatusOut:
    """Pure: the four statuses from the session row (started_at, past expiry), the last successful read, and the live
    market's state and its feed phase (None = no socket running); ``last_price_at`` is the last price frame's time, used
    only for the market-closed text. Exercised directly by the state tests."""
    if session is None or session[1]:
        fix: Fix = "session_expired" if session is not None else "connect_zerodha"
        down = _status("disconnected", fix)
        return BrokerStatusOut(account_connection=down, live_market_data=down, position_sync=down,
                               order_execution=down, last_successful_sync=None, historical_data="not_available")
    started = session[0]
    synced = last_read if last_read is not None and last_read >= started else None
    live = _live_status(live_state, live_phase, market_is_open)
    sync = _status("connected") if synced is not None else _status("partial", "no_read_yet")
    if live.state != "connected":
        execution = _status("partial", "live_data_not_connected")
    elif sync.state != "connected":
        execution = _status("partial", "positions_not_synced")
    else:
        execution = _status("connected")
    return BrokerStatusOut(account_connection=_status("connected"), live_market_data=live, position_sync=sync,
                           order_execution=execution, last_successful_sync=synced, historical_data="not_available",
                           live_market_closed=_closed_text(live, last_price_at))


def _closed_text(live: StatusOut, last_price_at: datetime.datetime | None) -> Any:
    if live.fix != "live_feed_market_closed" or last_price_at is None:
        return None
    # ADR-200 (2): the label is when that price was made (the session close), never the frame's arrival time
    made_at = price_time(last_price_at)
    return None if made_at is None else market_closed_error(made_at)


@router.get("/api/broker/status", response_model=BrokerStatusOut)
async def broker_status(db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)],
                        clock: Annotated[Callable[[], datetime.datetime], Depends(get_execute_clock)],
                        ) -> BrokerStatusOut:
    session = await active_session_status(db, user_ref)
    return build_status(session, broker_sync.last_read(), live_market.current_state(),
                        live_market.feed_phase(), live_market.market_open_at(clock()),
                        live_market.last_price_time())


@router.post("/api/broker/disconnect", response_model=DisconnectOut)
async def broker_disconnect(db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> DisconnectOut:
    """Ends the signed-in owner's active session. Strategies, history, entitlements and the account are not touched."""
    async with db.begin():
        ended = await end_session(db, user_ref, EndReason.DISCONNECTED)
    await live_market.stop_current()  # the stored token is gone; the socket must not keep streaming on it
    if ended is not None:
        broker_sync.forget()
    return DisconnectOut(disconnected=ended is not None)
