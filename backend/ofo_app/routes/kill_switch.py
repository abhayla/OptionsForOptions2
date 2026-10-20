"""ADR-127 (4): the owner's way to flip the kill switch. Owner-only and audited.

Spec basis: ADR-127 "One server setting, changed only by the platform owner ... Turning it on or off is an audited
event." There is no sign-in yet (stage 5), so the owner check is one secret, ``OFO_OWNER_KEY`` (``config.owner_key``),
sent in the ``X-Owner-Key`` header and compared in constant time. A missing or wrong key, or a server with no key set,
answers exactly as an unknown path does (404): a normal user learns nothing, and the route cannot be reached by
accident. ``current_user_ref`` is NOT the check (in v1 it names the owner for everyone).
"""
from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from ofo_app import kill_switch
from ofo_app.api_models import ApiModel
from ofo_app.config import owner_key
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)


class KillSwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    paused: bool
    reason: str = Field(min_length=1, max_length=kill_switch.REASON_MAX)


class KillSwitchOut(ApiModel):
    paused: bool


def require_owner(x_owner_key: Annotated[str | None, Header()] = None) -> None:
    """Refuses (404) unless the header equals the server's owner key. Constant-time compare; no key set = refuse."""
    expected = owner_key()
    if expected is None or x_owner_key is None or not hmac.compare_digest(
            x_owner_key.encode("utf-8"), expected.encode("utf-8")):
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)


@router.put("/admin/kill-switch", response_model=KillSwitchOut)
async def set_kill_switch(
    body: KillSwitchIn, _owner: Annotated[None, Depends(require_owner)], db: Annotated[Any, Depends(get_db)],
) -> KillSwitchOut:
    """Turns the switch on or off and appends ONE audit event, in one transaction (the event is the state)."""
    try:
        await kill_switch.set_paused(db, body.paused, reason=body.reason)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return KillSwitchOut(paused=body.paused)


__all__ = ["KillSwitchIn", "KillSwitchOut", "require_owner", "router", "set_kill_switch"]
