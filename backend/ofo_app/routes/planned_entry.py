"""POST /api/strategies/planned-entry (W-068 step 3; ADR-068 item 1, ADR-020 Q185/Q186, ADR-008).

Spec basis: ADR-068 (1) "A draft leg's entry price is its planned entry: the leg's LTP captured when the leg is added
(or the mid of bid and ask when no LTP exists)"; ADR-020 Q185 "no fake prices": without a live price the answer is
``planned_entry: null`` with a reason code, NEVER a default, last-known or zero price.

Prices are read only through ``ofo.outcome.read_snapshot`` with the same provider dependency the outcome route uses
(``get_market_context``), so replay mode (APP_ENV=test + OUTCOME_REPLAY=1) works here too. LTP first (a positive value);
the mid of bid and ask only when the quote carries no LTP; only a quote whose health is AVAILABLE counts as live.
The browser computes nothing: the price is a string from a Decimal, rounded half-up to the 0.01 the outcome route takes.
"""

from __future__ import annotations

import datetime
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ofo.outcome import read_snapshot
from ofo.outcome.planned_entry import planned_entry_of
from ofo_app.api_models import ApiModel, Identifier, Money
from ofo_app.routes.outcome import MarketContext, get_market_context

router = APIRouter()

InstrumentIdIn = Annotated[str, StringConstraints(pattern=r"^[A-Z_]{1,20}:[0-9]{1,12}$")]

Reason = Literal["not_connected", "no_live_price", "unknown_instrument", "wrong_underlying", "expired"]


class PlannedEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Literal["NIFTY", "SENSEX"]
    instrument_ids: list[InstrumentIdIn] = Field(min_length=1, max_length=20)


class PlannedEntryOut(ApiModel):
    exchange_segment: Identifier
    exchange_token: int
    planned_entry: Optional[Money]
    captured_at: Optional[datetime.datetime]
    source: Optional[Literal["ltp", "mid"]]
    reason_code: Optional[Reason]


class PlannedEntriesOut(ApiModel):
    entries: list[PlannedEntryOut]


def _entry(instrument_id: str, **fields: Any) -> dict[str, Any]:
    segment, _, token = instrument_id.partition(":")
    return {"exchange_segment": segment, "exchange_token": int(token), "planned_entry": None, "captured_at": None,
            "source": None, "reason_code": None, **fields}


@router.post("/api/strategies/planned-entry", response_model=PlannedEntriesOut)
def planned_entry(body: PlannedEntryIn,
                  ctx: Optional[MarketContext] = Depends(get_market_context)) -> PlannedEntriesOut:
    ids = list(dict.fromkeys(body.instrument_ids))
    if ctx is None or not ctx.provider.status().connected:
        return PlannedEntriesOut.model_validate({"entries": [_entry(i, reason_code="not_connected") for i in ids]})
    valuation = ctx.clock()
    snapshot = read_snapshot(ctx.provider, body.underlying, ids, valuation, ctx.rate)
    entries = []
    for iid in ids:
        leg = snapshot.legs[iid]
        if leg.problem is not None:
            reason = ("unknown_instrument" if leg.problem == "unknown instrument"
                      else "expired" if leg.problem == "expired" else "wrong_underlying")
            entries.append(_entry(iid, reason_code=reason))
            continue
        priced = planned_entry_of(leg.quote)  # the domain rule (ofo.outcome.planned_entry); the route only calls it
        if priced is None:
            entries.append(_entry(iid, reason_code="no_live_price"))
        else:
            entries.append(_entry(iid, planned_entry=priced.price, captured_at=valuation, source=priced.source))
    return PlannedEntriesOut.model_validate({"entries": entries})
