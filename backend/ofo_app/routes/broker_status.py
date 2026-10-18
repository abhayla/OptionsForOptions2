"""Settings -> Broker & Market Data: the four Zerodha statuses and Disconnect (W-089, REQ-015 AC-4, AC-8; REQ-051 AC-1).

Basis: REQ-015 AC-4 (four separate statuses - account connection, live market data, position/account sync,
order-execution readiness - each Connected, Partially connected (naming what to fix) or Disconnected; "Last successful
sync"), AC-8 (Disconnect keeps strategies, history, entitlements and the account); REQ-051 AC-1 (history is not
available in V1: the reply says so in a closed word).

Copy from: legacy-reuse row for src/components/settings/KiteSettings.vue (ADAPT: the status comes from the server, no
token anywhere in a URL or reply).

Every status is read from real state, never defaulted to Connected:
- account connection: the owner's active, unexpired row in ``broker_sessions`` (read-only, the database clock decides);
- live market data: Connected only when the live feed is running; with a session but no running feed it is Partially
  connected and names the fix (the feed needs LIVE_MARKET on and a subscribed screen);
- position/account sync: Connected only when a Zerodha read succeeded after this session started (``broker_sync``);
- order-execution readiness: Connected only when all three above are, otherwise Partially connected naming what is
  missing; Disconnected without a session.
The reply holds closed words and one time; the page maps each ``fix`` code to its reviewed text. Disconnect ends the
active session with reason 'disconnected' (``broker_token_store.end_session``) and touches no other table.
"""
from __future__ import annotations

import datetime
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.broker.session import EndReason
from sqlalchemy import text

from ofo_app import broker_sync, live_market
from ofo_app.api_models import ApiModel
from ofo_app.broker_token_store import end_session
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute
from ofo_app.routes.broker import current_user_ref

router = APIRouter(route_class=ClosedRoute)

Level = Literal["connected", "partial", "disconnected"]
Fix = Literal["connect_zerodha", "session_expired", "live_feed_off", "live_feed_not_running", "live_feed_session_ended",
              "no_read_yet", "live_data_not_connected", "positions_not_synced"]

_ACTIVE = text(
    "SELECT started_at, expected_expiry <= clock_timestamp() AS past FROM public.broker_sessions "
    "WHERE user_ref = :user_ref AND broker = 'zerodha' AND ended_at IS NULL")


class StatusOut(ApiModel):
    state: Level
    fix: Optional[Fix]  # noqa: UP045 - what to fix when not connected; None when connected


class BrokerStatusOut(ApiModel):
    account_connection: StatusOut
    live_market_data: StatusOut
    position_sync: StatusOut
    order_execution: StatusOut
    last_successful_sync: Optional[datetime.datetime]  # noqa: UP045 - None until a read succeeded this session
    historical_data: Literal["not_available"]  # REQ-051 AC-1: the page says history is not available in V1


class DisconnectOut(ApiModel):
    disconnected: bool  # False when there was no active session to end


def _status(state: Level, fix: Fix | None = None) -> StatusOut:
    return StatusOut(state=state, fix=fix)


def _live_status(live_state: str, running: bool) -> StatusOut:
    if running:
        return _status("connected")
    if live_state == live_market.SESSION_ENDED:
        return _status("partial", "live_feed_session_ended")
    if live_state == live_market.NOT_STARTED:
        return _status("partial", "live_feed_off")
    return _status("partial", "live_feed_not_running")


def build_status(session: tuple[datetime.datetime, bool] | None, last_read: datetime.datetime | None,
                 live_state: str, live_running: bool) -> BrokerStatusOut:
    """Pure: the four statuses from the session row (started_at, past expiry), the last successful read, and the live
    market's state. Exercised directly by the state tests."""
    if session is None or session[1]:
        fix: Fix = "session_expired" if session is not None else "connect_zerodha"
        down = _status("disconnected", fix)
        return BrokerStatusOut(account_connection=down, live_market_data=down, position_sync=down,
                               order_execution=down, last_successful_sync=None, historical_data="not_available")
    started = session[0]
    synced = last_read if last_read is not None and last_read >= started else None
    live = _live_status(live_state, live_running)
    sync = _status("connected") if synced is not None else _status("partial", "no_read_yet")
    if live.state != "connected":
        execution = _status("partial", "live_data_not_connected")
    elif sync.state != "connected":
        execution = _status("partial", "positions_not_synced")
    else:
        execution = _status("connected")
    return BrokerStatusOut(account_connection=_status("connected"), live_market_data=live, position_sync=sync,
                           order_execution=execution, last_successful_sync=synced, historical_data="not_available")


@router.get("/api/broker/status", response_model=BrokerStatusOut)
async def broker_status(db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)]) -> BrokerStatusOut:
    row = (await db.execute(_ACTIVE, {"user_ref": user_ref})).one_or_none()
    session = None if row is None else (row[0], bool(row[1]))
    return build_status(session, broker_sync.last_read(), live_market.current_state(),
                        live_market.current_session() is not None)


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
