"""POST /api/strategies/outcome (W-063; REQ-034 AC-1, AC-8; ADR-008, ADR-068).

The browser sends a draft strategy (legs with their planned entry and its capture time) and gets back the one table,
the scenario levels, the payoff points, the plain-language summary and the margin state, all from
:func:`ofo.outcome.build_outcome`: the screen does no maths. Every money/points value is a string from the Decimal,
never a JSON float. The market data comes through :func:`get_market_context`, a dependency: tests inject the replay
provider; with no provider configured the response is the "Draft - Live data not connected" state, not an error.
Errors go through the app's generic error handler (ofo_app.main).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ofo.engine.legs import Action
from ofo.marketdata.provider import MarketDataProvider
from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.views import View
from ofo.table import UXLevel

router = APIRouter()


@dataclass(frozen=True)
class MarketContext:
    """What the outcome needs from the running app: a provider, the valuation clock and the risk-free rate."""

    provider: MarketDataProvider
    clock: Callable[[], datetime.datetime]
    rate: Decimal


def get_market_context() -> Optional[MarketContext]:
    """The live context (W-065) when LIVE_MARKET is on and the owner has an active session, else None: the route
    answers "not connected". Tests and the replay mode override this dependency."""
    from ofo_app import live_market  # late: live_market imports MarketContext from this module
    return live_market.current_context()


# ---- request --------------------------------------------------------------------------------------------------------

class LegIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: str = Field(min_length=1, examples=["NSE_FO:44624"])
    action: Literal["BUY", "SELL"]
    lots: int = Field(gt=0, le=10000)
    planned_entry: str = Field(pattern=r"^\d+(\.\d{1,2})?$", examples=["104.65"],
                               description="the planned entry price, a decimal string (never a float)")
    captured_at: datetime.datetime = Field(description="when the planned entry was captured (ADR-068)")


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Literal["NIFTY", "SENSEX"]
    legs: list[LegIn] = Field(min_length=1, max_length=20)
    ux_level: Literal["guided", "standard", "advanced"] = "standard"
    view: Literal["at_expiry", "estimated_now"] = "at_expiry"


# ---- response (every number a string) ---------------------------------------------------------------------------

class CellOut(BaseModel):
    value: Optional[str]
    display: str
    kind: str
    reason: Optional[str]
    side: Optional[str]
    per_unit: Optional[str]
    vendor: Optional[str]


class ColumnOut(BaseModel):
    id: str
    label: str
    kind: str
    is_scenario_level: bool
    markers: list[str]
    visible: bool


class RowOut(BaseModel):
    row_id: str
    cells: dict[str, CellOut]


class TableOut(BaseModel):
    underlying: str
    spot_level: Optional[str]
    spot_at: Optional[str]
    output_label: Optional[str]
    columns: list[ColumnOut]
    rows: list[RowOut]


class LevelOut(BaseModel):
    level: str
    current: bool
    zero_pnl: bool


class ScenarioOut(BaseModel):
    view: str
    label: str
    kind: str
    available: bool
    unavailable_reason: Optional[str]
    output_label: Optional[str]
    levels: list[LevelOut]
    totals: Optional[list[str]]
    step: str
    start: str
    end: str


class PointOut(BaseModel):
    level: str
    pnl: str


class PayoffOut(BaseModel):
    view: str
    points: list[PointOut]


class SummaryOut(BaseModel):
    what_can_i_lose: str
    what_can_i_make: str
    where_do_i_start_losing: str
    max_profit: Optional[str]
    max_loss: Optional[str]
    max_profit_unlimited: bool
    max_loss_unlimited: bool
    breakevens: list[str]
    lower_be: Optional[str]
    upper_be: Optional[str]
    risk_boundaries: list[str]


class MarginOut(BaseModel):
    state: Literal["NOT_AVAILABLE_YET"]
    reason: str


class LegOut(BaseModel):
    instrument_id: str
    symbol: Optional[str]
    action: str
    instrument: Optional[str]
    strike: Optional[str]
    expiry: Optional[str]
    lots: int
    lot_size: Optional[int]
    quantity: Optional[int]
    planned_entry: str
    captured_at: str
    ltp: Optional[str]
    iv: Optional[str]
    health: Optional[str]
    label: Optional[str]


class AdvancedLegOut(BaseModel):
    """REQ-035 AC-5: Bid/Ask appear only in Advanced Details. Taken from the same snapshot as the table (one read)."""
    instrument_id: str
    symbol: Optional[str]
    bid: Optional[str]
    ask: Optional[str]
    health: Optional[str]


class OutcomeResponse(BaseModel):
    state: Literal["COMPUTED", "NOT_CONNECTED", "REFUSED"]
    underlying: str
    ux_level: str
    status_label: Optional[str]
    reason: Optional[str]
    output_label: Optional[str]
    valuation: Optional[str]
    spot_level: Optional[str]
    spot_at: Optional[str]
    legs: list[LegOut]
    margin: MarginOut
    table: Optional[TableOut]
    scenario: Optional[ScenarioOut]
    payoff: Optional[PayoffOut]
    summary: Optional[SummaryOut]
    #: present ONLY at ux_level=advanced (absent, not empty, at guided/standard) and only when a snapshot was read
    advanced_details: Optional[list[AdvancedLegOut]] = None


def _advanced_details(snapshot, definition: StrategyDefinition, symbols: dict[str, Optional[str]]) -> list[dict]:
    rows = []
    for leg in definition.legs:
        lm = snapshot.legs.get(leg.instrument_id)
        q = None if lm is None else lm.quote
        rows.append({"instrument_id": leg.instrument_id,
                     "symbol": symbols.get(leg.instrument_id),
                     "bid": None if q is None or q.bid is None else f"{q.bid:f}",
                     "ask": None if q is None or q.ask is None else f"{q.ask:f}",
                     "health": None if q is None else q.health.value})
    return rows


def _definition(req: OutcomeRequest) -> StrategyDefinition:
    legs = []
    for leg in req.legs:
        try:
            entry = Decimal(leg.planned_entry)
        except InvalidOperation as exc:  # the pattern already refuses this; kept fail-closed
            raise HTTPException(status_code=422, detail="planned_entry is not a decimal") from exc
        if leg.captured_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="captured_at needs a timezone offset")
        legs.append(PlannedLeg(leg.instrument_id, Action(leg.action), leg.lots, entry, leg.captured_at))
    return StrategyDefinition(req.underlying, tuple(legs))


def outcome_response(req: OutcomeRequest, ctx: Optional[MarketContext]) -> OutcomeResponse:
    """The one computation behind the REST route and the live push (W-065): both send exactly this."""
    definition = _definition(req)
    ux = UXLevel(req.ux_level)
    if ctx is None:
        out = build_outcome(definition, None, ux)
    else:
        valuation = ctx.clock()
        snapshot = read_snapshot(ctx.provider, req.underlying, [leg.instrument_id for leg in definition.legs],
                                 valuation, ctx.rate)
        out = build_outcome(definition, snapshot, ux, valuation, view=View(req.view))
    body = outcome_to_dict(out)
    if ctx is not None and ux is UXLevel.ADVANCED:  # the UX gate: nothing else ever carries bid/ask
        body["advanced_details"] = _advanced_details(snapshot, definition, {l["instrument_id"]: l["symbol"] for l in body["legs"]})
    return OutcomeResponse.model_validate(body)


@router.post("/api/strategies/outcome", response_model=OutcomeResponse, response_model_exclude_unset=True)
def strategy_outcome(req: OutcomeRequest,
                     ctx: Optional[MarketContext] = Depends(get_market_context)) -> OutcomeResponse:
    return outcome_response(req, ctx)
