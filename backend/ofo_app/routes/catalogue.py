"""GET /api/catalogue/{underlying}/expiries and /contracts (W-068; REQ-035 AC-8, ADR-068 item 4).

Spec basis: REQ-035 AC-8 ("a picker that offers only listed, not-expired contracts of the chosen underlying"); ADR-003
Q226 (every user-facing message from the template catalogue: an unsupported underlying is ``gate_underlying_unsupported``,
USER_INPUT_101); ADR-012 (the browser never talks to Zerodha: it reads our catalogue); ADR-008 (strike is a string).

Read-only. "Not expired" is judged on the DATABASE clock in Asia/Kolkata (``get_today``); a test overrides that
dependency. A past or unknown expiry answers an empty list, not an error. A contract is identified for the outcome route
as ``<exchange_segment>:<exchange_token>``; the segment and token are separate fields here because an ApiModel
``Identifier`` cannot hold ':' (the browser joins them).
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query

from ofo.errors import UserFacing, UserFacingError, render
from ofo_app import catalogue_picker as picker
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.db import get_db

router = APIRouter()

SUPPORTED = ("NIFTY", "SENSEX")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9]{0,19}")


class CatalogueRefused(UserFacing, Exception):
    """A refused picker call: carries only its `render()` message; the error boundary shows it (422)."""

    def __init__(self, template: str, **slots: Any) -> None:
        self.message: UserFacingError = render(template, **slots)
        super().__init__(template)


class ExpiriesOut(ApiModel):
    underlying: Literal["NIFTY", "SENSEX"]
    expiries: list[datetime.date]


class ContractOut(ApiModel):
    exchange_segment: Identifier
    exchange_token: int
    instrument_type: Literal["CE", "PE", "FUT"]
    expiry: datetime.date
    strike: Optional[Money]
    lot_size: int
    symbol: Identifier


class ContractsOut(ApiModel):
    underlying: Literal["NIFTY", "SENSEX"]
    contracts: list[ContractOut]


async def get_today(db: Any = Depends(get_db)) -> datetime.date:
    """The database clock's date in India: the one clock every not-expired judgement uses."""
    return await picker.database_today(db)


def check_underlying(underlying: str) -> str:
    if underlying in SUPPORTED:
        return underlying
    if _SYMBOL.fullmatch(underlying):
        raise CatalogueRefused("gate_underlying_unsupported", symbol=underlying)
    raise CatalogueRefused("user_input_request_invalid")  # not even a symbol shape: the fixed input error, never echoed


@router.get("/api/catalogue/{underlying}/expiries", response_model=ExpiriesOut)
async def expiries(underlying: str, db: Any = Depends(get_db),
                   today: datetime.date = Depends(get_today)) -> ExpiriesOut:
    check_underlying(underlying)
    return ExpiriesOut.model_validate({"underlying": underlying,
                                       "expiries": await picker.pickable_expiries(db, underlying, today)})


@router.get("/api/catalogue/{underlying}/contracts", response_model=ContractsOut)
async def contracts(underlying: str, expiry: datetime.date = Query(), db: Any = Depends(get_db),
                    today: datetime.date = Depends(get_today)) -> ContractsOut:
    check_underlying(underlying)
    rows = await picker.pickable_contracts(db, underlying, today, expiry)
    return ContractsOut.model_validate({"underlying": underlying, "contracts": [
        {"exchange_segment": r.exchange_segment, "exchange_token": r.exchange_token,
         "instrument_type": r.instrument_type, "expiry": r.expiry, "strike": r.strike, "lot_size": r.lot_size,
         "symbol": r.symbol} for r in rows]})
