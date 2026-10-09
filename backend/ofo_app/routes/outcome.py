"""POST /api/strategies/outcome (W-063; REQ-034 AC-1, AC-8; ADR-008, ADR-068).

The browser sends a draft strategy (legs with their planned entry and its capture time) and gets back the one table,
the scenario levels, the payoff points, the plain-language summary and the margin state, all from
:func:`ofo.outcome.build_outcome`: the screen does no maths. Every money/points value is a string from the Decimal,
never a JSON float. The market data comes through :func:`get_market_context`, a dependency: tests inject the replay
provider; with no provider configured the response is the "Draft - Live data not connected" state, not an error.
Text is catalogue text and errors go through the error boundary (ofo_app.errors): no exemption from the W-024
guards (W-066, issue #151).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Literal, Optional, Union

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ofo.engine.legs import Action, Instrument
from ofo.marketdata.provider import MarketDataProvider
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.rules.inputs import DataHealth
from ofo.scenario.views import View
from ofo.table import CellKind, UXLevel
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, InstrumentId, Money

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
    instrument_id: InstrumentId = Field(examples=["NSE_FO:44624"])
    action: Literal["BUY", "SELL"]
    lots: int = Field(gt=0, le=10000)
    planned_entry: str = Field(pattern=r"^\d+(\.\d{1,2})?$", examples=["104.65"],
                               description="the planned entry price, a decimal string (never a float)")
    captured_at: AwareDatetime = Field(description="when the planned entry was captured (ADR-068)")


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Literal["NIFTY", "SENSEX"]
    legs: list[LegIn] = Field(min_length=1, max_length=20)
    ux_level: Literal["guided", "standard", "advanced"] = "standard"
    view: Literal["at_expiry", "estimated_now"] = "at_expiry"


# ---- response (typed, W-066): text is catalogue text, numbers are Money strings, codes are closed ----------------------

class CellOut(ApiModel):
    value: Optional[Union[Money, CatalogueText]]
    display: CatalogueText
    kind: CellKind
    reason: Optional[CatalogueText]
    side: Optional[Literal["Cr", "Dr"]]
    per_unit: Optional[Money]
    vendor: Optional[Money]


class ColumnOut(ApiModel):
    id: Identifier
    label: CatalogueText
    kind: CellKind
    is_scenario_level: bool
    markers: list[Literal["CURRENT", "0-P&L"]]
    visible: bool


class RowOut(ApiModel):
    row_id: Identifier
    cells: dict[Identifier, CellOut]


class TableOut(ApiModel):
    underlying: Literal["NIFTY", "SENSEX"]
    spot_level: Optional[Money]
    spot_at: Optional[datetime.datetime]
    output_label: Optional[CatalogueText]
    columns: list[ColumnOut]
    rows: list[RowOut]


class LevelOut(ApiModel):
    level: Money
    current: bool
    zero_pnl: bool


class ScenarioOut(ApiModel):
    view: View
    label: CatalogueText
    kind: Literal["exact", "estimate"]
    available: bool
    unavailable_reason: Optional[CatalogueText]
    output_label: Optional[CatalogueText]
    levels: list[LevelOut]
    totals: Optional[list[Money]]
    step: Money
    start: Money
    end: Money


class PointOut(ApiModel):
    level: Money
    pnl: Money


class PayoffOut(ApiModel):
    view: View
    points: list[PointOut]


class SummaryOut(ApiModel):
    what_can_i_lose: CatalogueText
    what_can_i_make: CatalogueText
    where_do_i_start_losing: CatalogueText
    max_profit: Optional[Money]
    max_loss: Optional[Money]
    max_profit_unlimited: bool
    max_loss_unlimited: bool
    breakevens: list[Money]
    lower_be: Optional[Money]
    upper_be: Optional[Money]
    risk_boundaries: list[Money]


class MarginOut(ApiModel):
    state: Literal["NOT_AVAILABLE_YET"]
    reason: CatalogueText


class LegOut(ApiModel):
    instrument_id: InstrumentId
    symbol: Optional[Identifier]
    action: Action
    instrument: Optional[Instrument]
    strike: Optional[Money]
    expiry: Optional[datetime.date]
    lots: int
    lot_size: Optional[int]
    quantity: Optional[int]
    planned_entry: Money
    captured_at: datetime.datetime
    ltp: Optional[Money]
    iv: Optional[Money]
    health: Optional[DataHealth]
    label: Optional[CatalogueText]


class AdvancedLegOut(ApiModel):
    """REQ-035 AC-5: Bid/Ask appear only in Advanced Details. Taken from the same snapshot as the table (one read)."""
    instrument_id: InstrumentId
    symbol: Optional[Identifier]
    bid: Optional[Money]
    ask: Optional[Money]
    health: Optional[DataHealth]


class OutcomeResponse(ApiModel):
    state: OutcomeState
    underlying: Literal["NIFTY", "SENSEX"]
    ux_level: UXLevel
    status_label: Optional[CatalogueText]
    reason: Optional[CatalogueText]
    output_label: Optional[CatalogueText]
    valuation: Optional[datetime.datetime]
    spot_level: Optional[Money]
    spot_at: Optional[datetime.datetime]
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
    """The domain definition. Every value was validated by the request model (decimal pattern, aware datetime); a
    request the model refuses is answered by the error boundary (ofo_app.errors), never by a message built here."""
    legs = [PlannedLeg(leg.instrument_id, Action(leg.action), leg.lots, Decimal(leg.planned_entry), leg.captured_at)
            for leg in req.legs]
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
        body["advanced_details"] = _advanced_details(snapshot, definition,
                                                     {l["instrument_id"]: l["symbol"] for l in body["legs"]})
    return OutcomeResponse.model_validate(body)


@router.post("/api/strategies/outcome", response_model=OutcomeResponse, response_model_exclude_unset=True)
def strategy_outcome(req: OutcomeRequest,
                     ctx: Optional[MarketContext] = Depends(get_market_context)) -> OutcomeResponse:
    return outcome_response(req, ctx)
