"""The Option Chain's per-user display preference (W-124; REQ-087 AC-3). Read-only to the market; no order reachable.

``GET/PUT /api/user-settings/chain-strikes``: how many strikes either side of ATM the chain shows (10, 20, 30 or 40;
default 10). The user is the session's (``current_user_ref``), never a value the browser sends. Other preferences (the
margin preference, the strategy preferences) add their own typed route over the same store.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ofo_app import user_setting_store as store
from ofo_app.api_models import ApiModel
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute
from ofo_app.routes.broker import current_user_ref

PATH = "/api/user-settings/chain-strikes"

router = APIRouter(route_class=ClosedRoute)


class ChainStrikesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strikes_each_side: Literal[10, 20, 30, 40]


class ChainStrikesOut(ApiModel):
    strikes_each_side: Literal[10, 20, 30, 40]
    is_default: bool  # true when the user never chose: the default is shown


def _out(value: Any, is_default: bool) -> ChainStrikesOut:
    return ChainStrikesOut(strikes_each_side=value, is_default=is_default)


@router.get(PATH, response_model=ChainStrikesOut)
async def read_chain_strikes(db: Annotated[Any, Depends(get_db)],
                             user_ref: Annotated[str, Depends(current_user_ref)]) -> ChainStrikesOut:
    return _out(*await store.read(db, user_ref, store.CHAIN_STRIKES_EACH_SIDE))


@router.put(PATH, response_model=ChainStrikesOut)
async def write_chain_strikes(body: ChainStrikesIn, db: Annotated[Any, Depends(get_db)],
                              user_ref: Annotated[str, Depends(current_user_ref)]) -> ChainStrikesOut:
    try:
        await store.write(db, user_ref, store.CHAIN_STRIKES_EACH_SIDE, body.strikes_each_side)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _out(body.strikes_each_side, False)
