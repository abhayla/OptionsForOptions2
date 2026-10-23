"""Settings -> Zerodha account block: the masked client id and Zerodha's own available margin (REQ-015 AC-13, RD-013).

Basis: ADR-016 (Zerodha is the authority on margin): the figure is ``KiteMargin.fetch_available_funds`` (``GET
/user/margins`` ``equity.net``) exactly as read, with the time it was read; it is never computed here, never summed,
never defaulted. REQ-117: the margin is read only while the ``funds_read`` flag is on. REQ-118 AC-7: both reads go
through ``kite_period_reads`` (at most one each per 30 s per user), so many tabs never make a read storm.

Answer states (standing item d), each a closed word the page maps to its own sentence, the figure null in every one
but ``available`` (never 0):
- no stored Zerodha session                       -> ``not_connected`` (no read is made);
- ``funds_read`` off, unknown or its file broken -> ``not_offered`` (no margin read is made);
- answered with a usable ``equity.net``           -> ``available`` + the figure as a string + its read time;
- answered without a usable figure (absent, empty, not a number, not ``status: success``) -> ``empty``;
- 429 / the limiter refused                       -> ``busy``;
- 403 / TokenException                            -> ``session_expired``;
- network, 5xx, junk body, any other refusal      -> ``read_failed``.
The user id is masked on the server (``kite_period_reads.mask_user_id``): the full id never reaches the browser. A
failed profile read gives a null id; the margin answer is independent of it.
"""
from __future__ import annotations

import asyncio
import datetime
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.broker import kite_flags
from ofo.broker.flags import BrokerFlag, flags_or_off, is_supported

from ofo_app import kite_period_reads
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.errors import ClosedRoute
from ofo_app.kite_margin import MARGIN_BUSY_CODE, KiteMarginError
from ofo_app.kite_reads import KiteReadError
from ofo_app.routes.execute import KiteSession, get_kite_session

router = APIRouter(route_class=ClosedRoute)

MarginState = Literal["available", "not_connected", "not_offered", "empty", "busy", "session_expired", "read_failed"]
#: KiteMargin's codes -> the page's closed word (an allow-list: any other code reads as a failed read)
_MARGIN_STATES: dict[str, MarginState] = {"kite_margin_no_figure": "empty", MARGIN_BUSY_CODE: "busy",
                                          "kite_margin_token": "session_expired"}


class MarginOut(ApiModel):
    state: MarginState
    available: Optional[Money]  # noqa: UP045 - Zerodha's figure as read; null in every state but "available"
    read_at: Optional[datetime.datetime]  # noqa: UP045 - when Zerodha answered; null without a figure


class MaskedUserIdOut(ApiModel):
    """The page shows ``start`` + ``hidden`` stars + ``end`` (``AB**34``); start/end are null for a short id."""

    start: Optional[Identifier]  # noqa: UP045
    hidden: int
    end: Optional[Identifier]  # noqa: UP045


class BrokerAccountOut(ApiModel):
    user_id: Optional[MaskedUserIdOut]  # noqa: UP045 - null when not connected or the profile read failed
    margin: MarginOut


def _margin(session: KiteSession) -> MarginOut:
    try:
        answer = kite_period_reads.available_margin(session.reads, session.margin)
    except KiteMarginError as exc:
        return MarginOut(state=_MARGIN_STATES.get(exc.code, "read_failed"), available=None, read_at=None)
    return MarginOut(state="available", available=answer.value, read_at=answer.read_at)


def _user_id(session: KiteSession) -> MaskedUserIdOut | None:
    try:
        start, hidden, end = kite_period_reads.masked_user_id(session.reads).value
    except (KiteReadError, ValueError):
        return None
    return MaskedUserIdOut(start=start, hidden=hidden, end=end)


def _account(session: KiteSession, funds_on: bool) -> BrokerAccountOut:
    margin = _margin(session) if funds_on else MarginOut(state="not_offered", available=None, read_at=None)
    return BrokerAccountOut(user_id=_user_id(session), margin=margin)


@router.get("/api/broker/account", response_model=BrokerAccountOut)
async def broker_account(
    session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045
) -> BrokerAccountOut:
    if session is None:
        return BrokerAccountOut(user_id=None,
                                margin=MarginOut(state="not_connected", available=None, read_at=None))
    funds_on = is_supported(flags_or_off(kite_flags.load_zerodha_flags), BrokerFlag.FUNDS_READ)
    return await asyncio.to_thread(_account, session, funds_on)


__all__ = ["BrokerAccountOut", "MarginOut", "MaskedUserIdOut", "broker_account"]
