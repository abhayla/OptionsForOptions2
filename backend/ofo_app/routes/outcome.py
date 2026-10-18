"""POST /api/strategies/outcome (W-063; REQ-034 AC-1, AC-8; ADR-008, ADR-068).

The browser sends a draft strategy (legs with their planned entry and its capture time) and gets back the one table,
the scenario levels, the payoff points, the plain-language summary and the margin state, all from
:func:`ofo.outcome.build_outcome`: the screen does no maths. Every money/points value is a string from the Decimal,
never a JSON float. The market data comes through :func:`get_market_context`, a dependency: tests inject the replay
provider; with no provider configured the response is the "Draft — Live data not connected" state, not an error.
Text is catalogue text and errors go through the error boundary (ofo_app.errors): no exemption from the W-024
guards (W-066, issue #151).
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Awaitable, Callable, Literal, Mapping, Optional, Union

from fastapi import APIRouter, Depends
from ofo.charges import ChargeRates
from ofo.engine.legs import Action
from ofo.instruments.models import InstrumentId as ContractKey
from ofo.instruments.models import ListedContract
from ofo.marketdata.provider import MarketDataProvider
from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, not_connected, not_live, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.outcome.service import Margin
from ofo.scenario.config import ScenarioConfig, ScenarioSettings
from ofo.scenario.levels import RangeOverride, resolve_choice
from ofo.scenario.views import View
from ofo.table import UXLevel
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

from ofo_app import charge_rates_store, db
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, InstrumentId, Money
from ofo_app.errors import ClosedRoute
from ofo_app.outcome_margin import OutcomeMargin, PlannedOrderIn, margin_answer

router = APIRouter(route_class=ClosedRoute)
log = logging.getLogger("ofo_app.outcome")

# A loaded rate set is reused for 300 s (rates change by a dated admin row, so a few minutes of lag is harmless and the
# live push asks every second); a FAILED load (no database, no table, no complete set) is remembered as "no rates" for
# 30 s and then retried, so a database outage costs one attempt per 30 s, not one per push.
_RATES_TTL, _RATES_RETRY = 300.0, 30.0
_rates_cache: dict = {"until": 0.0, "value": None}


async def load_charge_rates() -> Optional[ChargeRates]:
    """The charge rates in force (ADR-082: the database clock picks the set), or None when none can be read. None is
    never an error here: the outcome then keeps ADR-071's "before charges and taxes" sentence (W-075 decision (b)).
    Works with or without a Zerodha session: the rates do not depend on one."""
    now = time.monotonic()
    if now < _rates_cache["until"]:
        return _rates_cache["value"]
    try:
        async with db.get_sessionmaker()() as session:
            value = await charge_rates_store.rates_in_force(session)
        _rates_cache.update(until=now + _RATES_TTL, value=value)
    except Exception:  # noqa: BLE001 - no database, table or set gives None (logged, never shown)
        log.warning("charge rates unavailable: outcome sentences stay before charges", exc_info=True)
        _rates_cache.update(until=now + _RATES_RETRY, value=None)
        value = None
    return value


#: The longest the no-provider answer waits for the stored catalogue (#259): a hanging database host must not delay the
#: "not connected" answer up to the driver's connect timeout. On timeout the legs stay unnamed, like any unreadable read.
CATALOGUE_READ_TIMEOUT_SECONDS = 2.0

#: A whole number of index points as the browser sends it (a string, never a float).
POINTS_PATTERN = r"^[1-9]\d{0,5}$"

AnswerClock = Callable[[], datetime.datetime]
ContractLookup = Callable[[list[str]], Awaitable[Mapping[str, ListedContract]]]


def server_now() -> datetime.datetime:
    """The moment the server produces an answer (ADR-088): UTC, timezone-aware. The browser's clock is never used."""
    return datetime.datetime.now(datetime.timezone.utc)


def get_answer_clock() -> AnswerClock:
    """The answer-time seam: tests override this dependency with a fixed clock."""
    return server_now


async def stored_contracts(instrument_ids: list[str]) -> Mapping[str, ListedContract]:
    """#249: the stored catalogue's entry for each leg's contract identity (one lookup per leg), for the no-provider
    answer. An unknown contract is simply absent; a catalogue that cannot be read gives nothing (the legs stay unnamed,
    the page's fixed wording), never an error: this state must always answer. Only the exception class is logged."""
    from ofo_app import catalogue_store
    from ofo_app.db import get_sessionmaker

    found: dict[str, ListedContract] = {}
    try:
        async with get_sessionmaker()() as session:
            conn = await session.connection()
            for iid in dict.fromkeys(instrument_ids):
                segment, _, token = iid.partition(":")
                contract_id = await catalogue_store.live_contract_id(conn, ContractKey(segment, int(token)))
                if contract_id is not None:
                    found[iid] = (await catalogue_store.load_contract(conn, contract_id)).listed
    except Exception as exc:
        log.warning("no-provider leg names: the catalogue could not be read: %s", type(exc).__name__)
        return {}
    return found


def get_contract_lookup() -> ContractLookup:
    return stored_contracts



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
    step: str | None = Field(default=None, pattern=POINTS_PATTERN, examples=["50"],
                                description="the column step in index points (REQ-034 AC-4); one of the index's list")
    range_start: str | None = Field(default=None, pattern=POINTS_PATTERN, examples=["22800"],
                                       description="the first scenario level in index points; sent with range_end")
    range_end: str | None = Field(default=None, pattern=POINTS_PATTERN, examples=["23600"],
                                     description="the last scenario level in index points; sent with range_start")
    fallback: StrictBool = Field(
        default=False,
        description="true when this is the REST refresh of a screen whose own live socket dropped (ADR-077): the answer "
                    "is then the not-live state whoever else subscribes to the same contracts")

    @model_validator(mode="after")
    def _choice_is_allowed(self) -> OutcomeRequest:
        """REQ-034 AC-4: refuse a step or range off the allow-list (ofo.scenario.levels.resolve_choice) before any
        computation; the error boundary answers 422 with the catalogue text and logs no value."""
        self.scenario_choice()
        return self

    def scenario_choice(self) -> tuple[ScenarioConfig, RangeOverride | None]:
        """The scenario config and range override this request asks for (the default config when it asks for none)."""
        base = ScenarioSettings().for_index(self.underlying)
        pick = [None if v is None else Decimal(v) for v in (self.step, self.range_start, self.range_end)]
        return resolve_choice(base, *pick)


async def stored_legs_for(req: OutcomeRequest, ctx: Optional[MarketContext],
                          lookup: ContractLookup) -> Optional[Mapping[str, ListedContract]]:
    """The stored catalogue entries for the legs, read ONLY when there is no provider (the no-provider answer, #249).
    The ONE helper behind both delivery paths (REST and the live socket, #259), so a field filled on one is filled on the
    other. The read is bounded by CATALOGUE_READ_TIMEOUT_SECONDS; a timeout gives no names (unnamed legs), never a hang."""
    if ctx is not None:
        return None
    try:
        return await asyncio.wait_for(lookup([leg.instrument_id for leg in req.legs]), CATALOGUE_READ_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.warning("no-provider leg names: the catalogue read timed out after %ss", CATALOGUE_READ_TIMEOUT_SECONDS)
        return {}


async def get_stored_legs(req: OutcomeRequest, ctx: Optional[MarketContext] = Depends(get_market_context),
                          lookup: ContractLookup = Depends(get_contract_lookup)) -> Optional[Mapping[str, ListedContract]]:
    return await stored_legs_for(req, ctx, lookup)


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
    charges: Optional[Money] = None  # W-075: the round-trip charges inside max_profit / max_loss
    charges_unavailable: bool = False


class MarginOut(ApiModel):
    """ADR-099: Zerodha's margin for the planned orders. The figures are present only in the CHECKED state."""
    state: Literal["NOT_AVAILABLE_YET", "CHECKED", "UNREADABLE", "NO_BASKET"]
    reason: CatalogueText
    needed: Money | None = None  # Zerodha's basket figure + the ADR-094 top-up, to the paisa
    available: Money | None = None  # Zerodha's available funds, to the paisa
    checked_at: datetime.datetime | None = None  # when Zerodha was read (ADR-088)
    shortfall: bool = False  # available < needed, compared as Decimal on the server (the browser never compares money)


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
    #: ADR-088: when the server produced THIS answer (aware, UTC) in every state; the page shows it as "Checked at"
    answered_at: datetime.datetime
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


def _live_market():
    """The live market module, imported late: it imports MarketContext from this module."""
    from ofo_app import live_market
    return live_market


def live_context() -> Optional[MarketContext]:
    return _live_market().current_context()


def outcome_response(req: OutcomeRequest, ctx: Optional[MarketContext],  # noqa: PLR0913 - one shared computation; rates is the sixth input
                     streaming: Optional[Callable[[str], bool]] = None, *, now: AnswerClock = server_now,
                     stored: Optional[Mapping[str, ListedContract]] = None,
                     rates: Optional[ChargeRates] = None, margin: Margin | None = None) -> OutcomeResponse:
    """The one computation behind the REST route and the live push (W-065): both send exactly this. ``streaming``
    (REST only, issue #206): when the live market's inputs for this strategy are not all streaming, the answer is the
    not-live state (REQ-049 AC-5's message, no numbers shown as live; ADR-068 (2)), not a computation on missing or
    frozen quotes. ``now`` stamps the answer time (ADR-088); ``stored`` names the legs when there is no provider (#249)."""
    definition = _definition(req)
    ux = UXLevel(req.ux_level)
    live_blocked = False
    if ctx is None:
        answered_at = now()
        out = not_connected(definition, ux, None, stored)
    else:
        valuation = answered_at = ctx.clock()  # one clock reading: the push and the REST answer of one snapshot are equal
        snapshot = read_snapshot(ctx.provider, req.underlying, [leg.instrument_id for leg in definition.legs],
                                 valuation, ctx.rate)
        # ADR-077: the not-live answer follows the browser's OWN socket. A fallback request says this page's socket is
        # down, so it is not live even if another socket still holds every contract (shared fan-out count > 0).
        live_blocked = (req.fallback or _not_streaming(req, ctx, streaming)) and not snapshot.status.session_ended
        if live_blocked:
            out = not_live(definition, snapshot, ux)
        else:
            config, override = req.scenario_choice()
            out = build_outcome(definition, snapshot, ux, valuation, view=View(req.view), rates=rates,
                                config=config, override=override)
    if ctx is not None and margin is not None:  # ADR-099: read by the caller (async, off the loop); no context = login
        out = dataclasses.replace(out, margin=margin)
    body = outcome_to_dict(out)
    body["answered_at"] = answered_at
    for column in (body.get("table") or {}).get("columns", ()):
        column["markers"] = [MARKER_CODES[m] for m in column["markers"]]
    if ctx is not None and ux is UXLevel.ADVANCED and not live_blocked:  # not live: no frozen bid/ask either  # the UX gate: nothing else ever carries bid/ask
        body["advanced_details"] = _advanced_details(snapshot, definition,
                                                     {l["instrument_id"]: l["symbol"] for l in body["legs"]})
    return OutcomeResponse.model_validate(body)


def get_margin_source() -> OutcomeMargin | None:
    """ADR-099: the running app's margin reader (one plan-keyed cache). Tests override it with a fake transport."""
    return _live_market().margin_source()


def margin_legs(req: OutcomeRequest) -> list[PlannedOrderIn]:
    """The plan as the margin cache keys it: instrument, side, lots, planned price (never a live price)."""
    return [PlannedOrderIn(leg.instrument_id, leg.action, leg.lots, Decimal(leg.planned_entry)) for leg in req.legs]


async def margin_for_request(req: OutcomeRequest, ctx: MarketContext | None,
                             source: OutcomeMargin | None) -> Margin:
    """The ONE margin step of both delivery paths (REST and the live push), so both show the same block."""
    return await margin_answer(source, ctx, margin_legs(req))


async def get_outcome_margin(req: OutcomeRequest,
                             ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                             source: Annotated[OutcomeMargin | None, Depends(get_margin_source)]) -> Margin:
    return await margin_for_request(req, ctx, source)


@router.post("/api/strategies/outcome", response_model=OutcomeResponse, response_model_exclude_unset=True)
def strategy_outcome(req: OutcomeRequest,  # noqa: PLR0913 - FastAPI dependencies, one per input
                     ctx: Optional[MarketContext] = Depends(get_market_context),
                     streaming: Optional[Callable[[str], bool]] = Depends(get_streaming),
                     now: AnswerClock = Depends(get_answer_clock),
                     stored: Optional[Mapping[str, ListedContract]] = Depends(get_stored_legs),
                     rates: Optional[ChargeRates] = Depends(load_charge_rates), *,
                     margin: Annotated[Margin | None, Depends(get_outcome_margin)] = None) -> OutcomeResponse:
    # a direct call (a test, another module) skips dependency resolution and leaves the Depends marker here: no rates
    return outcome_response(req, ctx, streaming, now=now, stored=stored,
                            rates=rates if isinstance(rates, ChargeRates) else None,
                            margin=margin if isinstance(margin, Margin) else None)
