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
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from ofo.timeutil import days_to_expiry

from ofo_app import catalogue_picker as picker
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute
from ofo_app.underlying import Underlying, require_supported

router = APIRouter(route_class=ClosedRoute)


class ExpiryDaysOut(ApiModel):
    expiry: datetime.date
    days: int | None  # calendar days from today (IST, the database clock) to the expiry; 0 on expiry day


class ExpiriesOut(ApiModel):
    underlying: Underlying
    expiries: list[datetime.date]
    expiry_days: list[ExpiryDaysOut]  # REQ-135 AC-2: the same expiries, 1:1 and in the same order, with days left


class ContractOut(ApiModel):
    contract_id: int  # the catalogue's internal id; a saved strategy leg links to it (ADR-057)
    exchange_segment: Identifier
    exchange_token: int
    instrument_type: Literal["CE", "PE", "FUT"]
    expiry: datetime.date
    strike: Optional[Money]
    lot_size: int
    symbol: Identifier


class ContractsOut(ApiModel):
    underlying: Underlying
    contracts: list[ContractOut]


async def get_today(db: Any = Depends(get_db)) -> datetime.date:
    """The database clock's date in India: the one clock every not-expired judgement uses."""
    return await picker.database_today(db)


@router.get("/api/catalogue/{underlying}/expiries", response_model=ExpiriesOut)
async def expiries(underlying: str, db: Any = Depends(get_db),
                   today: datetime.date = Depends(get_today)) -> ExpiriesOut:
    require_supported(underlying)
    listed = await picker.pickable_expiries(db, underlying, today)
    return ExpiriesOut.model_validate({
        "underlying": underlying, "expiries": listed,
        "expiry_days": [{"expiry": e, "days": days_to_expiry(e, today)} for e in listed]})  # REQ-135 AC-2


@router.get("/api/catalogue/{underlying}/contracts", response_model=ContractsOut)
async def contracts(underlying: str, expiry: datetime.date = Query(), db: Any = Depends(get_db),
                    today: datetime.date = Depends(get_today)) -> ContractsOut:
    require_supported(underlying)
    rows = await picker.pickable_contracts(db, underlying, today, expiry)
    return ContractsOut.model_validate({"underlying": underlying, "contracts": [
        {"contract_id": r.contract_id, "exchange_segment": r.exchange_segment, "exchange_token": r.exchange_token,
         "instrument_type": r.instrument_type, "expiry": r.expiry, "strike": r.strike, "lot_size": r.lot_size,
         "symbol": r.symbol} for r in rows]})
