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
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool

from ofo.engine.legs import Action
from ofo.marketdata.provider import MarketDataProvider
from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, not_live, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.views import View
from ofo.table import UXLevel
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, InstrumentId, Money
from ofo_app.errors import ClosedRoute

router = APIRouter(route_class=ClosedRoute)


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
    fallback: StrictBool = Field(
        default=False,
        description="true when this is the REST refresh of a screen whose own live socket dropped (ADR-077): the answer "
                    "is then the not-live state whoever else subscribes to the same contracts")


# ---- response (typed, W-066): text is catalogue text, numbers are Money strings, codes are closed ----------------------
#: Closed codes: Literals of the domain enums' values (W-069 door: an Enum is not a closed leaf). A test pins each to its
#: enum (tests_app/test_outcome_split_loss.py), so a new enum member cannot drift away from the response.
CellKindCode = Literal["money", "points", "percent", "greek", "iv", "quantity", "text"]
ViewCode = Literal["at_expiry", "estimated_now"]
HealthCode = Literal["available", "stale", "delayed", "unhealthy", "unavailable"]
#: A scenario column's marker as a closed code (the column's own label already reads "CURRENT 23,047" / "0-P&L 22,909");
#: an unknown marker is a KeyError, answered by the error boundary, never passed through.
MARKER_CODES = {"CURRENT": "CURRENT", "0-P&L": "ZERO_PNL"}


class CellOut(ApiModel):
    value: Optional[Union[Money, CatalogueText]]
    display: CatalogueText
    kind: CellKindCode
    reason: Optional[CatalogueText]
    side: Optional[Literal["Cr", "Dr"]]
    per_unit: Optional[Money]
    vendor: Optional[Money]


class ColumnOut(ApiModel):
    id: Identifier
    label: CatalogueText
    kind: CellKindCode
    is_scenario_level: bool
    markers: list[Literal["CURRENT", "ZERO_PNL"]]
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
    view: ViewCode
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
    view: ViewCode
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
    action: Literal["BUY", "SELL"]
    instrument: Optional[Literal["CE", "PE", "FUT"]]
    strike: Optional[Money]
    expiry: Optional[datetime.date]
    lots: int
    lot_size: Optional[int]
    quantity: Optional[int]
    planned_entry: Money
    captured_at: datetime.datetime
    ltp: Optional[Money]
    iv: Optional[Money]
    health: Optional[HealthCode]
    label: Optional[CatalogueText]


class AdvancedLegOut(ApiModel):
    """REQ-035 AC-5: Bid/Ask appear only in Advanced Details. Taken from the same snapshot as the table (one read)."""
    instrument_id: InstrumentId
    symbol: Optional[Identifier]
    bid: Optional[Money]
    ask: Optional[Money]
    health: Optional[HealthCode]


class OutcomeResponse(ApiModel):
    state: Literal["COMPUTED", "NOT_CONNECTED", "REFUSED"]
    underlying: Literal["NIFTY", "SENSEX"]
    ux_level: Literal["guided", "standard", "advanced"]
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


def get_streaming() -> Optional[Callable[[str], bool]]:
    """Issue #206: in the running app with live market data, "is this instrument streaming?" = it has a subscriber on
    the ONE shared fan-out (only a strategy socket subscribes). None when there is no live feed (not connected, the test
    replay, a test's own context): then every input the provider holds is used as it is."""
    from ofo_app import live_market  # late: live_market imports MarketContext from this module
    feed = live_market.current_feed()
    if feed is None:
        return None
    return lambda instrument_id: feed.fanout.subscriber_count(instrument_id) > 0


def _not_streaming(req: OutcomeRequest, ctx: MarketContext, streaming: Optional[Callable[[str], bool]]) -> bool:
    if streaming is None:
        return False
    owner = getattr(streaming, "ctx", None)  # the replay's predicate names its own context (ofo_app.replay_mode)
    if ctx is not (owner if owner is not None else live_context()):
        return False
    index_id = getattr(ctx.provider, "index_id", lambda _u: None)(req.underlying)
    ids = [leg.instrument_id for leg in req.legs] + ([index_id] if index_id else [])
    return not all(streaming(i) for i in ids)


def live_context() -> Optional[MarketContext]:
    from ofo_app import live_market
    return live_market.current_context()


def outcome_response(req: OutcomeRequest, ctx: Optional[MarketContext],
                     streaming: Optional[Callable[[str], bool]] = None) -> OutcomeResponse:
    """The one computation behind the REST route and the live push (W-065): both send exactly this. ``streaming``
    (REST only, issue #206): when the live market's inputs for this strategy are not all streaming, the answer is the
    not-live state (REQ-049 AC-5's message, no numbers shown as live; ADR-068 (2)), not a computation on missing or
    frozen quotes."""
    definition = _definition(req)
    ux = UXLevel(req.ux_level)
    live_blocked = False
    if ctx is None:
        out = build_outcome(definition, None, ux)
    else:
        valuation = ctx.clock()
        snapshot = read_snapshot(ctx.provider, req.underlying, [leg.instrument_id for leg in definition.legs],
                                 valuation, ctx.rate)
        # ADR-077: the not-live answer follows the browser's OWN socket. A fallback request says this page's socket is
        # down, so it is not live even if another socket still holds every contract (shared fan-out count > 0).
        live_blocked = (req.fallback or _not_streaming(req, ctx, streaming)) and not snapshot.status.session_ended
        if live_blocked:
            out = not_live(definition, snapshot, ux)
        else:
            out = build_outcome(definition, snapshot, ux, valuation, view=View(req.view))
    body = outcome_to_dict(out)
    for column in (body.get("table") or {}).get("columns", ()):
        column["markers"] = [MARKER_CODES[m] for m in column["markers"]]
    if ctx is not None and ux is UXLevel.ADVANCED and not live_blocked:  # not live: no frozen bid/ask either  # the UX gate: nothing else ever carries bid/ask
        body["advanced_details"] = _advanced_details(snapshot, definition,
                                                     {l["instrument_id"]: l["symbol"] for l in body["legs"]})
    return OutcomeResponse.model_validate(body)


@router.post("/api/strategies/outcome", response_model=OutcomeResponse, response_model_exclude_unset=True)
def strategy_outcome(req: OutcomeRequest,
                     ctx: Optional[MarketContext] = Depends(get_market_context),
                     streaming: Optional[Callable[[str], bool]] = Depends(get_streaming)) -> OutcomeResponse:
    return outcome_response(req, ctx, streaming)
