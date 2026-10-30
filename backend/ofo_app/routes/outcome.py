# ruff: noqa: E501, PLC0415, RUF003, RUF012
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
from typing import Annotated, Awaitable, Callable, Iterable, Literal, Mapping, Optional, Union

from fastapi import APIRouter, Depends
from ofo.charges import ChargeRates
from ofo.engine.legs import Action
from ofo.instruments.models import InstrumentId as ContractKey
from ofo.instruments.models import ListedContract
from ofo.limits import INTEGER_MAX
from ofo.marketdata.feed_health import awaiting_first_price_for, market_closed_for
from ofo.marketdata.provider import MarketDataProvider
from ofo.marketdata.quote import NormalizedQuote
from ofo.marketdata.shared_compute import FeedScope, SharedCompute
from ofo.outcome import (
    OutcomeState,
    PlannedLeg,
    StrategyDefinition,
    build_outcome,
    from_entries,
    not_connected,
    not_live,
    read_snapshot,
)
from ofo.outcome.money import with_funds
from ofo.outcome.price_text import price_text
from ofo.outcome.serialize import outcome_to_dict
from ofo.outcome.service import PAYOFF_TABLE_STEPS, Margin, waiting_first_price
from ofo.outcome.target import TargetAsk
from ofo.scenario.config import ScenarioConfig, ScenarioSettings
from ofo.scenario.levels import RangeOverride, resolve_range
from ofo.scenario.views import View
from ofo.timeutil import IST
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from ofo_app import charge_rates_store, db
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, InstrumentId, Money, echo_seq
from ofo_app.errors import ClosedRoute
from ofo_app.outcome_margin import OutcomeMargin, PlannedOrderIn, margin_answer
from ofo_app.underlying import Underlying

router = APIRouter(route_class=ClosedRoute)
#: The one process-wide cache of market-wide figures (REQ-050); keyed by feed owner, so one user's feed never serves
#: another's. Only market-wide figures go in; strategy maths never does (tests/marketdata/test_scale_classes.py).
SHARED_COMPUTE = SharedCompute()
log = logging.getLogger("ofo_app.outcome")

# A loaded rate set is reused for 300 s (rates change by a dated admin row, so a few minutes of lag is harmless and the
# live push asks every second); a FAILED load (no database, no table, no complete set) is remembered as "no rates" for
# 30 s and then retried, so a database outage costs one attempt per 30 s, not one per push.
_RATES_TTL, _RATES_RETRY = 300.0, 30.0
_rates_cache: dict = {"until": 0.0, "value": None, "flight": None}


async def _load_rates_once() -> ChargeRates | None:
    """The one database read behind the cache: success is remembered for the TTL, a failure as "no rates" for 30 s."""
    try:
        async with db.get_sessionmaker()() as session:
            value = await charge_rates_store.rates_in_force(session)
        _rates_cache.update(until=time.monotonic() + _RATES_TTL, value=value)
    except Exception:  # noqa: BLE001 - no database, table or set gives None (logged, never shown)
        log.warning("charge rates unavailable: outcome sentences stay before charges", exc_info=True)
        _rates_cache.update(until=time.monotonic() + _RATES_RETRY, value=None)
        value = None
    return value


async def load_charge_rates() -> ChargeRates | None:
    """The charge rates in force (ADR-082: the database clock picks the set), or None when none can be read. None is
    never an error here: the outcome then keeps ADR-071's "before charges and taxes" sentence (W-075 decision (b)).
    Works with or without a Zerodha session: the rates do not depend on one.

    Single-flight (GC-6 POOL-BUDGET): callers arriving after the TTL while a load is running wait for that one load
    instead of each opening a session (the role allows 5 connections, ADR-048). The load runs as its own task, so a
    caller that is cancelled does not cancel it for the others."""
    if time.monotonic() < _rates_cache["until"]:
        return _rates_cache["value"]
    loop = asyncio.get_running_loop()
    flight = _rates_cache.get("flight")
    if flight is None or flight.done() or flight.get_loop() is not loop:
        flight = loop.create_task(_load_rates_once())
        _rates_cache["flight"] = flight
    return await asyncio.shield(flight)


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
    #: whose Zerodha feed this is (ADR-053): part of every shared-cache key, so two users' feeds never share. None (a
    #: test or replay context with no owner) means nothing is shared: every reader computes for itself.
    feed_owner: str | None = None


@dataclass(frozen=True)
class MarketState:
    """REQ-114 AC-7 / ADR-177: what every price answer carries about the market. ``closed``: the ADR-119 calendar says
    the market is not open at the answer's time (a date it cannot answer reads closed); ``last_price_at``: when the
    feed's last PRICE frame arrived (never a heartbeat), the time the market-closed and reconnecting texts show."""

    closed: bool
    last_price_at: datetime.datetime | None


def market_state(ctx: MarketContext | None, at: datetime.datetime) -> MarketState:
    """The ONE market-state read behind the outcome, chain and index answers (class market-state-decided-per-surface):
    the provider's own feed answers (``FeedState.market_closed``, which also sets every quote's health); a provider
    with no feed state, or no context at all, gets the same calendar function the feed defaults to (fail closed)."""
    provider = None if ctx is None else ctx.provider
    return MarketState(closed=market_closed_for(provider, at),
                       last_price_at=getattr(getattr(provider, "feed", None), "last_price_at", None))


def label_time(state: MarketState, quote_times: Iterable[datetime.datetime | None]) -> datetime.datetime | None:
    """ADR-200 (4): the time a market-closed answer is labelled with ("Market closed. Prices are from <time>.") is the
    quotes' OWN last-price time, the latest ``at`` among the quotes the answer used, never the feed's last frame time (a
    21:05 reconnect frame is not a price from the session that closed). An older-session price (a holiday before) is
    kept and labelled with its own time. No usable quote time: None (no time is invented). In market hours the
    answer's ``last_price_at`` stays the feed's last price frame, unchanged (the reconnecting text reads it)."""
    if not state.closed:
        return state.last_price_at
    times = [t for t in quote_times if isinstance(t, datetime.datetime) and t.utcoffset() is not None]
    return max(times) if times else None


def feed_scope(ctx: MarketContext) -> FeedScope | None:
    """The shared-cache scope of ``ctx``'s feed (REQ-050 AC-1/AC-3, ADR-053), or None when there is no feed owner. Every
    route that reads a market snapshot takes its scope here, so none bypasses the shared cache."""
    return FeedScope(SHARED_COMPUTE, ctx.feed_owner) if ctx.feed_owner else None


def get_market_context() -> MarketContext | None:
    """The live context (W-065) when LIVE_MARKET is on and the owner has an active session, else None: the route
    answers "not connected". Tests and the replay mode override this dependency."""
    from ofo_app import live_market  # late: live_market imports MarketContext from this module
    return live_market.current_context()


# ---- request --------------------------------------------------------------------------------------------------------

class LegIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: InstrumentId = Field(examples=["NSE_FO:44624"])
    action: Literal["BUY", "SELL"]
    lots: int = Field(strict=True, gt=0, le=10000)  # true, 1.0 and "2" are a malformed request, never coerced
    planned_entry: str = Field(pattern=r"^\d+(\.\d{1,2})?$", examples=["104.65"],
                               description="the planned entry price, a decimal string (never a float)")
    captured_at: AwareDatetime = Field(description="when the planned entry was captured (ADR-068)")


#: the one request key a client may still send after ADR-168; it is dropped, never read
RETIRED_LEVEL_KEY = "ux_level"

#: REQ-119 AC-1: a builder-screen request's sequence id, echoed unchanged as ``seq`` in its reply (absent in the request
#: -> absent in the reply). Strict: a bool, a string or a float is a malformed request, never coerced.
RequestSeq = Annotated[int, Field(strict=True, ge=0, le=INTEGER_MAX,
                                  description="the request's sequence id; the reply echoes it unchanged as seq")]


@dataclasses.dataclass(frozen=True)
class Booked:
    """ADR-209: the booked P&L of the paper strategy a what-if request names (amount None, unreadable False: nothing to add)."""

    amount: Decimal | None = None
    unreadable: bool = False


BookedReader = Callable[[int], Awaitable[Decimal | None]]  # strategy id -> booked P&L; None: the book could not be read


async def read_booked(strategy_id: int) -> Decimal | None:
    """The strategy's booked P&L from the paper order book (the one engine's net_positions, the figure GET
    /paper/strategies/{id} returns). None for a strategy that is not this user's, has no orders, or a read that fails."""
    from ofo.tracking.orderbook import (
        net_positions,  # late: the DB-free outcome route imports nothing of tracking at load
    )

    from ofo_app import paper_book  # not paper_store: that one reaches order code (REQ-073 AC-6)
    from ofo_app.db import get_sessionmaker
    from ofo_app.routes.broker import current_user_ref
    try:
        async with get_sessionmaker()() as db:
            orders = await paper_book.load_owned(db, current_user_ref(), strategy_id)  # owner check in the query
    except Exception:  # noqa: BLE001 - any read failure is the one answer "could not be read", never a 0
        return None
    return net_positions([o.order.as_paper() for o in orders], {}).booked if orders else None


def get_booked_reader() -> BookedReader:
    return read_booked


async def get_booked(req: OutcomeRequest, reader: Annotated[BookedReader, Depends(get_booked_reader)]) -> Booked:
    """ADR-209: nothing for a plan or the switch off; else the paper strategy's booked P&L or "could not be read"."""
    if req.paper_strategy_id is None or not req.include_booked:
        return Booked()
    amount = await reader(req.paper_strategy_id)
    return Booked(None, True) if amount is None else Booked(amount)


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _ignore_retired_level(cls, data):
        """ADR-168: there is one level. A client still sending the retired `level` key is not refused; the key is
        dropped here (the only key ever dropped), every other unknown key still fails."""
        if isinstance(data, dict) and RETIRED_LEVEL_KEY in data:
            return {k: v for k, v in data.items() if k != RETIRED_LEVEL_KEY}
        return data
    underlying: Underlying
    legs: list[LegIn] = Field(min_length=1, max_length=20)
    view: Literal["at_expiry", "estimated_now"] = "at_expiry"
    range_start: str | None = Field(default=None, pattern=POINTS_PATTERN, examples=["22800"],
                                    description="the first scenario level in index points; sent with range_end")
    range_end: str | None = Field(default=None, pattern=POINTS_PATTERN, examples=["23600"],
                                  description="the last scenario level in index points; sent with range_start")
    fallback: StrictBool = Field(
        default=False,
        description="true when this is the REST refresh of a screen whose own live socket dropped (ADR-077): the answer "
                    "is then the not-live state whoever else subscribes to the same contracts")
    seq: RequestSeq | None = None  # REQ-119 AC-1 (REST) / REQ-133 AC-2 (the live push): echoed unchanged
    both_views: StrictBool = Field(
        default=False,
        description="REQ-083 AC-1: true asks for both curves (At Expiry and Estimated Now) over the same levels in "
                    "`curves`, and the other view's totals in `scenario.other`; false keeps today's reply exactly")
    payoff_step: StrictInt | None = Field(
        default=None, examples=[50],
        description="REQ-137 AC-1: the payoff table's interval in index points, one of 10, 25, 50, 100; the reply then "
                    "carries `payoff_table` (also sent with both_views; absent: the strike step, NIFTY 50, SENSEX 100)")
    sd_bands: StrictBool = Field(
        default=False,
        description="REQ-083 AC-4 / REQ-137 AC-3: true adds `standard_deviation` (1 SD and 2 SD on a fixed 7-day "
                    "horizon, the days to expiry when fewer)")
    open_interest: StrictBool = Field(
        default=False,
        description="REQ-083 AC-5 / AC-6: true adds `open_interest`: each listed strike inside the reply's scenario "
                    "range with its call and put OI for the strategy's expiry (a calendar: the nearest) and the time "
                    "read, or the reason OI is not available; false keeps today's reply exactly. Today's OI change "
                    "is not offered (D-B18, Later)")
    target_level: str | None = Field(
        default=None, pattern=POINTS_PATTERN, examples=["23000"],
        description="REQ-084 AC-1: the what-if index level in points; the server clamps it to `target.limits` (spot "
                    "-10% .. +10%, snapped to the strike step). Analysis only: never saved, never feeds margin (AC-6)")
    target_at: AwareDatetime | None = Field(
        default=None,
        description="REQ-084 AC-2: the what-if date-time; the server clamps it between now and the strategy's first "
                    "expiry at 15:30 IST (`target.at_clamped`, `target.clamp`). Analysis only (AC-6)")
    paper_strategy_id: StrictInt | None = Field(
        default=None, ge=1, le=INTEGER_MAX,
        description="ADR-209: the paper strategy these legs are the net position of (Drafts Mode); the server reads its "
                    "booked P&L from the paper order book. Absent: a plan, nothing is added")
    include_booked: StrictBool = Field(
        default=True,
        description="ADR-209: the chart card's Add Booked P&L switch. true (default) adds the paper strategy's booked P&L "
                    "to the target P&L, the badge and the target curve; false shows the open legs only")

    @model_validator(mode="after")
    def _choice_is_allowed(self) -> OutcomeRequest:
        """REQ-034 AC-4: refuse a range off the allow-list (ofo.scenario.levels.resolve_range) before any
        computation; the error boundary answers 422 with the catalogue text and logs no value."""
        self.scenario_choice()
        if self.payoff_step is not None and Decimal(self.payoff_step) not in PAYOFF_TABLE_STEPS:
            raise ValueError("payoff_step must be one of 10, 25, 50, 100")
        return self

    def target_ask(self, booked: Booked | None = None) -> TargetAsk | None:
        """REQ-084 AC-4: the what-if inputs (None when neither was sent: today's reply exactly). ``booked`` is the paper
        strategy's booked P&L the route read (ADR-209); None: a plan, or the switch off."""
        if self.target_level is None and self.target_at is None:
            return None
        booked = booked or Booked()
        return TargetAsk(None if self.target_level is None else Decimal(self.target_level), self.target_at,
                         booked.amount, booked.unreadable)

    def table_step(self) -> Decimal | None:
        """REQ-137 AC-1: the payoff table's interval as index points (None: the underlying's strike step)."""
        return None if self.payoff_step is None else Decimal(self.payoff_step)

    def scenario_choice(self) -> tuple[ScenarioConfig, RangeOverride | None]:
        """The ONE config (Admin step and anchor) and the range override this request asks for (None: the computed
        default range). The same pair is checked here and handed to build_outcome."""
        base = ScenarioSettings().for_index(self.underlying)
        pick = [None if v is None else Decimal(v) for v in (self.range_start, self.range_end)]
        return base, resolve_range(base, *pick)


async def stored_legs_for(req: OutcomeRequest, ctx: MarketContext | None,
                          lookup: ContractLookup) -> Mapping[str, ListedContract] | None:
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


async def get_stored_legs(req: OutcomeRequest, ctx: MarketContext | None = Depends(get_market_context),
                          lookup: ContractLookup = Depends(get_contract_lookup)) -> Mapping[str, ListedContract] | None:
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
    value: Union[Money, CatalogueText] | None
    display: CatalogueText
    kind: CellKindCode
    reason: CatalogueText | None
    side: Literal["Cr", "Dr"] | None
    per_unit: Money | None
    per_unit_display: CatalogueText | None
    vendor: Money | None


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
    underlying: Underlying
    spot_level: Money | None
    spot_at: datetime.datetime | None
    output_label: CatalogueText | None
    scenario_heading: list[CatalogueText]  # AC-7: [left, right]
    columns: list[ColumnOut]
    rows: list[RowOut]


class LevelOut(ApiModel):
    level: Money
    current: bool
    zero_pnl: bool


class ScenarioOtherOut(ApiModel):
    """REQ-083 AC-1 (both views asked for): the other view's totals on the scenario table's own levels."""
    view: ViewCode
    label: CatalogueText
    kind: Literal["exact", "estimate"]
    available: bool
    unavailable_reason: CatalogueText | None
    output_label: CatalogueText | None
    totals: list[Money] | None



class ScenarioOut(ApiModel):
    view: ViewCode
    label: CatalogueText
    kind: Literal["exact", "estimate"]
    available: bool
    unavailable_reason: CatalogueText | None
    output_label: CatalogueText | None
    levels: list[LevelOut]
    totals: list[Money] | None
    step: Money
    start: Money
    end: Money
    customised: bool  # true when the user's range was used, false for the computed default range
    other: ScenarioOtherOut | None = None  # both_views only (absent otherwise)


class PointOut(ApiModel):
    level: Money
    pnl: Money
    display: CatalogueText  # GC-BM F-8: the point's rupee text, in the table cells' format (e.g. "₹6,366.75")


class PayoffOut(ApiModel):
    view: ViewCode
    points: list[PointOut]


class CurveOut(ApiModel):
    """REQ-083 AC-1/AC-3: one view's curve over the shared levels; unavailable -> no points and the reason."""
    view: ViewCode
    label: CatalogueText
    kind: Literal["exact", "estimate"]
    available: bool
    unavailable_reason: CatalogueText | None
    output_label: CatalogueText | None
    points: list[PointOut]


class CurvesOut(ApiModel):
    """REQ-083 AC-1: both curves of one answer, on the same levels (``both_views``)."""
    at_expiry: CurveOut
    estimated_now: CurveOut


class PayoffCellOut(ApiModel):
    pnl: Money
    display: CatalogueText


class PayoffRowOut(ApiModel):
    level: Money
    level_display: CatalogueText
    nearest_spot: bool
    move_pct: Money | None  # D-B26 / REQ-137 AC-2: (level - spot) x 100 / spot; None without a live index price
    move_pct_display: CatalogueText | None  # "+2.1%" (signed, one decimal; a true zero "0.0%"), from the server
    estimated_now: PayoffCellOut | None  # None: that view is unavailable (its column carries the reason)
    at_expiry: PayoffCellOut | None


class PayoffColumnOut(ApiModel):
    view: ViewCode
    label: CatalogueText
    kind: Literal["exact", "estimate"]
    available: bool
    unavailable_reason: CatalogueText | None


class PayoffTableOut(ApiModel):
    step: Money
    available: bool
    unavailable_reason: CatalogueText | None
    columns: list[PayoffColumnOut]
    rows: list[PayoffRowOut]


class SdRowOut(ApiModel):
    sd: Literal[1, 2]
    label: CatalogueText
    move: Money
    percent: Money
    lower: Money
    upper: Money
    move_display: CatalogueText
    lower_display: CatalogueText
    upper_display: CatalogueText


class SdBandOut(ApiModel):
    sd: Literal[-2, -1, 1, 2]
    label: CatalogueText
    level: Money
    display: CatalogueText


class StandardDeviationOut(ApiModel):
    available: bool
    reason: CatalogueText | None
    horizon_days: int | None
    iv: Money | None
    spot: Money | None
    rows: list[SdRowOut]
    bands: list[SdBandOut]


class NetPremiumOut(ApiModel):
    """REQ-081 AC-1: the net premium at the planned entries. ``amount`` / ``side`` are null (with a ``reason``) when a
    leg has no planned price or a leg is a future; ``side`` is null for exactly zero; ``per_unit`` is null when the
    legs' quantities differ."""
    amount: Money | None
    amount_display: CatalogueText | None = None  # REQ-152: whole rupees, Indian grouping, no sign ("5,707"); null = absent
    side: Literal["get", "pay"] | None
    per_unit: Money | None
    per_unit_display: CatalogueText | None = None  # GC-UI D-PX (REQ-152 AC-2): "1.50", two decimals; null = absent
    text: CatalogueText | None
    reason: CatalogueText | None


class FundsShareOut(ApiModel):
    """REQ-081 AC-9/AC-10 (ADR-207 (8)): max profit / max loss as a percent, one decimal, of the margin needed the Funds &
    Margins block shows. The whole block is null (never estimated, never of available funds) unless the margin read is
    CHECKED with a positive margin needed; a side that is Unlimited has null percent/text."""
    margin_needed: Money
    read_at: datetime.datetime
    max_profit_percent: Money | None
    max_loss_percent: Money | None
    max_profit_text: CatalogueText | None
    max_loss_text: CatalogueText | None


class ChargesBreakdownOut(ApiModel):
    """ADR-167 (2): the round trip by component, from the engine (Decimal strings); null on the outcome if unpriced."""
    brokerage: Money
    stt: Money
    exchange_transaction: Money
    gst: Money
    stamp: Money
    sebi: Money
    total: Money
    rates_read_on: datetime.date
    label: CatalogueText
    exercise_stt_rate: Money | None = None  # ADR-167 (4): only with a bought option; rate and condition, no amount
    exercise_stt_note: CatalogueText | None = None


class SummaryOut(ApiModel):
    what_can_i_lose: CatalogueText
    what_can_i_make: CatalogueText
    where_do_i_start_losing: CatalogueText
    max_profit: Money | None
    max_loss: Money | None
    # REQ-152 AC-1/AC-3/AC-4: the server's whole-rupee text (half-up, Indian grouping, "+" profit, U+2212 loss); null =
    # absent/unlimited (the reason or the unlimited flag is beside it); the exact value stays in the field above
    max_profit_display: CatalogueText | None = None
    max_loss_display: CatalogueText | None = None
    breakevens_display: list[CatalogueText] = []  # REQ-153 AC-1: "22,688 (−0.1%)", same order as ``breakevens``
    max_profit_unlimited: bool
    max_loss_unlimited: bool
    breakevens: list[Money]
    lower_be: Money | None
    upper_be: Money | None
    risk_boundaries: list[Money]
    charges: Money | None = None  # W-075: the round-trip charges inside max_profit / max_loss
    charges_unavailable: bool = False
    # REQ-135 AC-4: present for a strategy of one futures leg (and the reason for any unlimited side); else null
    reward_risk: Money | None = None
    reward_risk_reason: CatalogueText | None = None
    time_value: Money | None = None
    time_value_display: CatalogueText | None = None
    intrinsic_value: Money | None = None
    intrinsic_value_display: CatalogueText | None = None
    # REQ-081 (W-154): null = absent; the reason text says why (never "0.00" for an absent figure)
    risk_reward: Money | None = None
    value_label: CatalogueText | None = None
    value_reason: CatalogueText | None = None
    net_premium: NetPremiumOut | None = None
    funds_share: FundsShareOut | None = None


class MarginOut(ApiModel):
    """ADR-099: Zerodha's margin for the planned orders. The figures are present only in the CHECKED state."""
    state: Literal["NOT_AVAILABLE_YET", "CHECKED", "UNREADABLE", "NO_BASKET"]
    reason: CatalogueText
    needed: Money | None = None  # OUR figure: Zerodha's basket figure + the ADR-094 top-up, to the paisa
    broker_needed: Money | None = None  # Zerodha's own final.total (0 for a closing basket); only when CHECKED
    available: Money | None = None  # Zerodha's available funds, to the paisa
    # REQ-152 AC-1: whole rupees, Indian grouping, unsigned; null whenever the matching figure is null
    needed_display: CatalogueText | None = None
    broker_needed_display: CatalogueText | None = None
    available_display: CatalogueText | None = None
    checked_at: datetime.datetime | None = None  # when Zerodha was read (ADR-088)
    shortfall: bool = False  # available < needed, compared as Decimal on the server (the browser never compares money)
    shortfall_reason: CatalogueText | None = None  # REQ-055 AC-4: only when CHECKED and short, with the ways forward


class LegOut(ApiModel):
    instrument_id: InstrumentId
    symbol: Identifier | None
    action: Literal["BUY", "SELL"]
    instrument: Literal["CE", "PE", "FUT"] | None
    strike: Money | None
    expiry: datetime.date | None
    days_to_expiry: int | None = None  # REQ-135 AC-2: days left from the answer's IST date (0 on expiry day)
    lots: int
    lot_size: int | None
    quantity: int | None
    planned_entry: Money | None  # None only for a leg saved without a price (ADR-085)
    planned_entry_display: CatalogueText | None = None  # GC-UI D-PX (REQ-152 AC-2): two-decimal text, null = absent
    captured_at: datetime.datetime
    ltp: Money | None
    ltp_display: CatalogueText | None = None  # GC-UI D-PX: "99.80" for an ltp of 99.8
    iv: Money | None
    health: HealthCode | None
    label: CatalogueText | None


class LegQuoteOut(ApiModel):
    """REQ-035 AC-5 / ADR-168 (5): Bid/Ask for everyone, in the leg quotes. Taken from the same snapshot as the table (one read)."""
    instrument_id: InstrumentId
    symbol: Identifier | None
    bid: Money | None
    ask: Money | None
    bid_display: CatalogueText | None = None  # GC-UI D-PX: two-decimal text
    ask_display: CatalogueText | None = None
    health: HealthCode | None


class OiRowOut(ApiModel):
    """One strike's bars: a side with no usable OI is null with a dash, never 0; a real 0 is 0 / "0"."""
    strike: Money
    call_oi: int | None
    call_oi_display: CatalogueText
    put_oi: int | None
    put_oi_display: CatalogueText


class OpenInterestOut(ApiModel):
    """REQ-083 AC-5 / AC-6 (``open_interest``): the OI bars for ``expiry`` over the scenario range, or ONE reason."""
    available: bool
    unavailable_reason: CatalogueText | None  # "OI not available for this expiry: ..." (AC-6); None when available
    expiry: datetime.date | None
    expiry_note: CatalogueText | None  # a calendar: which expiry the bars are for (the nearest); None otherwise
    read_at: datetime.datetime | None  # the oldest time among the quotes used
    read_at_display: CatalogueText | None  # "OI data at 09:20 IST"
    contracts: int  # the contracts the bars read (two per listed strike in range)
    rows: list[OiRowOut]


class TargetLimitsOut(ApiModel):
    min: Money
    max: Money
    step: Money
    at_min: datetime.datetime | None  # the date range: now ..
    at_max: datetime.datetime | None  # .. the first expiry's 15:30 IST (null: no estimate, see ``at_refused_reason``)


class TargetPnlOut(ApiModel):
    value: Money
    display: CatalogueText


class GreeksOut(ApiModel):
    delta: Money
    gamma: Money
    theta: Money
    vega: Money


class TargetGreeksOut(ApiModel):
    """Position Greeks at the target, one row per leg in leg order (null: that leg has no time left) and the total
    (null unless every leg has a value; ``unavailable`` names why)."""
    legs: list[GreeksOut | None]
    total: GreeksOut | None
    unavailable: Literal["no_time_left"] | None
    unavailable_text: CatalogueText | None  # REQ-084 AC-2: "No Greeks at expiry: the options have no time left."
    dividend_yields: dict[Identifier, Money] = {}  # expiry date -> the q the engine priced it with (checker input, not shown)


class TargetBadgeOut(ApiModel):
    """GC-TP R-19a (REQ-144 AC-1..AC-4): the Projected profit / loss badge. ``state`` profit (above 0), loss (below 0),
    zero (exactly 0) or unavailable (``reason`` says why). The amount is the absolute value in ``amount_display``; the
    signed exact figure is ``amount``. The percent is of margin needed (REQ-081 AC-9); absent with ``percent_reason``."""
    state: Literal["profit", "loss", "zero", "unavailable"]
    label: CatalogueText
    reason: CatalogueText | None = None
    amount: Money | None = None
    amount_display: CatalogueText | None = None
    percent: Money | None = None
    percent_text: CatalogueText | None = None
    percent_reason: CatalogueText | None = None
    output_label: CatalogueText | None = None


class TargetOut(ApiModel):
    """REQ-084 AC-1/AC-2/AC-4/AC-7 (``target_level`` / ``target_at``): the clamped inputs and every engine figure at
    the target. ``kind`` "estimate" (the pricing model, ``model``) or "exact" (At Expiry only: no IV or no live data,
    the time refused with ``at_refused_reason``). With no target asked the block is ``limits`` alone (and
    ``at_refused_reason`` when the date range cannot be offered): every other key is absent, nothing is computed."""
    limits: TargetLimitsOut
    level: Money | None = None
    level_clamped: bool = False
    level_clamp_text: CatalogueText | None = None  # REQ-084 AC-2: "Target moved to the nearest allowed value: <level>."
    at: datetime.datetime | None = None
    at_clamped: bool = False
    clamp: Literal["before_now", "after_first_expiry"] | None = None
    at_clamp_text: CatalogueText | None = None  # REQ-084 AC-2: "Target moved to the nearest allowed value: <IST date-time>."
    at_refused_reason: CatalogueText | None = None
    kind: Literal["estimate", "exact"] | None = None
    model: CatalogueText | None = None
    output_label: CatalogueText | None = None
    pnl: TargetPnlOut | None = None
    breakevens: list[Money] | None = None
    breakevens_display: list[CatalogueText] | None = None  # GC-TPD R-33: "22,578 (+0.1%)", same order as ``breakevens``
    breakevens_reason: CatalogueText | None = None
    stale_text: CatalogueText | None = None  # ADR-210 (7): the sentence for these figures if they go stale
    curve: CurveOut | None = None
    greeks: TargetGreeksOut | None = None
    #: R-19a (Sensibull 020): the level's move from the live spot ("+6.1%"), absent with its reason when no spot is known
    move_pct: Money | None = None
    move_pct_display: CatalogueText | None = None
    move_pct_reason: CatalogueText | None = None
    #: R-19a: whole IST calendar days from the target date to the first expiry ("4D to expiry"), 0 on expiry day
    days_to_expiry: int | None = None
    days_to_expiry_display: CatalogueText | None = None
    badge: TargetBadgeOut | None = None  # REQ-144 AC-1..AC-4
    #: GC-TP R-18 (ADR-209): present only when a paper strategy's booked P&L is in ``pnl``, ``badge`` and ``curve``
    booked: Money | None = None
    booked_display: CatalogueText | None = None  # "+962.00"
    includes_booked_text: CatalogueText | None = None  # "includes +Rs 962.00 booked"
    booked_unreadable_text: CatalogueText | None = None  # the book could not be read: open legs only


class OutcomeResponse(ApiModel):
    state: Literal["COMPUTED", "FROM_ENTRIES", "NOT_CONNECTED", "REFUSED"]
    underlying: Underlying
    status_label: CatalogueText | None
    reason: CatalogueText | None
    output_label: CatalogueText | None
    valuation: datetime.datetime | None
    #: ADR-088: when the server produced THIS answer (aware, UTC) in every state; the page shows it as "Checked at"
    answered_at: datetime.datetime
    #: REQ-114 AC-7 / ADR-177: the market is closed at ``answered_at`` (the page shows the one market-closed banner)
    market_closed: bool
    #: when the feed's last price frame arrived (None: none yet); the market-closed and reconnecting texts show it
    last_price_at: datetime.datetime | None
    spot_level: Money | None
    spot_at: datetime.datetime | None
    legs: list[LegOut]
    margin: MarginOut
    table: TableOut | None
    scenario: ScenarioOut | None
    payoff: PayoffOut | None
    summary: SummaryOut | None
    #: present whenever a snapshot was read and the answer is live (absent, not empty, when not connected or not live)
    leg_quotes: list[LegQuoteOut] | None = None
    #: GC-LIVE: the dividend yield q each option expiry was priced with (expiry date -> q); a read-only echo for the checker
    dividend_yields: dict[Identifier, Money] | None = None
    #: FROM_ENTRIES only (REQ-077 AC-9): where the level grid is centred when there is no live index price, and why
    centre_label: CatalogueText | None = None
    charges_breakdown: ChargesBreakdownOut | None = None  # REQ-081 AC-2 / ADR-167 (2)
    #: GC-UI step 4 (REQ-083 AC-1): both curves on the same levels, keyed by view; absent unless ``both_views``
    curves: CurvesOut | None = None
    payoff_table: PayoffTableOut | None = None  # REQ-137 AC-1: absent unless payoff_step or both_views
    standard_deviation: StandardDeviationOut | None = None  # REQ-083 AC-4 / REQ-137 AC-3: absent unless sd_bands
    open_interest: OpenInterestOut | None = None  # REQ-083 AC-5 / AC-6: absent unless open_interest
    target: TargetOut | None = None  # REQ-084 AC-1/AC-4: limits alone unless target_level or target_at
    #: REQ-119 AC-1 / REQ-133 AC-2: the request's (or the socket follow message's) ``seq``, unchanged; absent when none
    seq: int | None = None


def _leg_quotes(snapshot, definition: StrategyDefinition, symbols: dict[str, str | None]) -> list[dict]:
    rows = []
    for leg in definition.legs:
        lm = snapshot.legs.get(leg.instrument_id)
        q = None if lm is None else lm.quote
        rows.append({"instrument_id": leg.instrument_id,
                     "symbol": symbols.get(leg.instrument_id),
                     "bid": None if q is None or q.bid is None else f"{q.bid:f}",
                     "ask": None if q is None or q.ask is None else f"{q.ask:f}",
                     "bid_display": None if q is None else price_text(q.bid),
                     "ask_display": None if q is None else price_text(q.ask),
                     "health": None if q is None else q.health.value})
    return rows


def _definition(req: OutcomeRequest) -> StrategyDefinition:
    """The domain definition. Every value was validated by the request model (decimal pattern, aware datetime); a
    request the model refuses is answered by the error boundary (ofo_app.errors), never by a message built here."""
    legs = [PlannedLeg(leg.instrument_id, Action(leg.action), leg.lots, Decimal(leg.planned_entry), leg.captured_at)
            for leg in req.legs]
    return StrategyDefinition(req.underlying, tuple(legs))


def get_streaming() -> Callable[[str], bool] | None:
    """Issue #206: in the running app with live market data, "is this instrument streaming?" = it has a subscriber on
    the ONE shared fan-out (only a strategy socket subscribes). None when there is no live feed (not connected, the test
    replay, a test's own context): then every input the provider holds is used as it is."""
    from ofo_app import live_market  # late: live_market imports MarketContext from this module
    feed = live_market.current_feed()
    if feed is None:
        return None
    return lambda instrument_id: feed.fanout.subscriber_count(instrument_id) > 0


def inputs_streaming(ctx: MarketContext, streaming: Callable[[str], bool] | None, ids: Iterable[str]) -> bool:
    """Issue #206's rule for any REST read of live inputs: True when every id is held by a socket on the shared feed.
    No predicate (no live feed: a test's own context) or a predicate of another context: the provider's quotes are used
    as they are. The chain read (ofo_app.routes.chain) uses it too."""
    if streaming is None:
        return True
    owner = getattr(streaming, "ctx", None)  # the replay's predicate names its own context (ofo_app.replay_mode)
    if ctx is not (owner if owner is not None else live_context()):
        return True
    return all(streaming(i) for i in ids)


def _not_streaming(req: OutcomeRequest, ctx: MarketContext, streaming: Callable[[str], bool] | None) -> bool:
    index_id = getattr(ctx.provider, "index_id", lambda _u: None)(req.underlying)
    ids = [leg.instrument_id for leg in req.legs] + ([index_id] if index_id else [])
    return not inputs_streaming(ctx, streaming, ids)


def _live_market():
    """The live market module, imported late: it imports MarketContext from this module."""
    from ofo_app import live_market
    return live_market


def live_context() -> MarketContext | None:
    return _live_market().current_context()


def outcome_response(req: OutcomeRequest, ctx: MarketContext | None,  # noqa: PLR0913 - one shared computation; rates is the sixth input
                     streaming: Callable[[str], bool] | None = None, *, now: AnswerClock = server_now,
                     stored: Mapping[str, ListedContract] | None = None,
                     rates: ChargeRates | None = None, margin: Margin | None = None,
                     seq: int | None = None, booked: Booked | None = None) -> OutcomeResponse:
    """The one computation behind the REST route and the live push (W-065): both send exactly this. ``streaming``
    (REST only, issue #206): when the live market's inputs for this strategy are not all streaming, the answer is the
    not-live state (REQ-049 AC-5's message, no numbers shown as live; ADR-068 (2)), not a computation on missing or
    frozen quotes. ``now`` stamps the answer time (ADR-088); ``stored`` names the legs when there is no provider (#249)."""
    definition = _definition(req)
    ask = req.target_ask(booked)  # ADR-209: the paper strategy's booked P&L rides on the what-if ask
    live_blocked = False
    used_quotes: list[NormalizedQuote | None] = []  # the quotes this answer used (ADR-200 (4): the closed label's time)
    if ctx is None:
        answered_at = now()
        config, override = req.scenario_choice()
        out = (from_entries(definition, None, stored, answered_at, view=View(req.view), rates=rates, config=config,
                            override=override, both_views=req.both_views, payoff_step=req.table_step(),
                            sd_bands=req.sd_bands, target=ask)  # REQ-077 AC-9: every leg priced -> At Expiry from the user's prices
               or not_connected(definition, None, stored))
    else:
        answered_at = ctx.clock()  # one clock reading: the push and the REST answer of one snapshot are equal
        shared = feed_scope(ctx)
        snapshot = read_snapshot(ctx.provider, req.underlying, [leg.instrument_id for leg in definition.legs],
                                 answered_at, ctx.rate, shared)
        used_quotes = [snapshot.spot, *(leg.quote for leg in snapshot.legs.values())]
        # ADR-077: the not-live answer follows the browser's OWN socket. A fallback request says this page's socket is
        # down, so it is not live even if another socket still holds every contract (shared fan-out count > 0).
        live_blocked = (req.fallback or _not_streaming(req, ctx, streaming)) and not snapshot.status.session_ended
        if not live_blocked and awaiting_first_price_for(ctx.provider, answered_at):
            out = waiting_first_price(definition, snapshot)  # REQ-133 AC-3: no number until the first price frame
        elif live_blocked:
            config, override = req.scenario_choice()
            out = (from_entries(definition, snapshot, None, snapshot.valuation, view=View(req.view), rates=rates,
                                config=config, override=override, both_views=req.both_views,
                                payoff_step=req.table_step(), sd_bands=req.sd_bands, target=ask)
                   or not_live(definition, snapshot))
        else:
            config, override = req.scenario_choice()
            out = build_outcome(definition, snapshot, snapshot.valuation, view=View(req.view), rates=rates,
                                config=config, override=override, shared=shared, both_views=req.both_views,
                                payoff_step=req.table_step(), sd_bands=req.sd_bands, target=ask)
    if ctx is not None and margin is not None:  # ADR-099: read by the caller (async, off the loop); no context = login
        out = dataclasses.replace(out, margin=margin, summary=with_funds(out.summary, margin))  # REQ-081 AC-9, AC-10
    body = outcome_to_dict(out, today=answered_at.astimezone(IST).date())  # REQ-135 AC-2
    body["answered_at"] = answered_at
    state = market_state(ctx, answered_at)
    body["market_closed"] = state.closed
    body["last_price_at"] = label_time(state, (q.price_at for q in used_quotes if q is not None))
    for column in (body.get("table") or {}).get("columns", ()):
        column["markers"] = [MARKER_CODES[m] for m in column["markers"]]
    if req.open_interest:  # REQ-083 AC-5 / AC-6: the bars, or the one reason (never a 0 in a missing place)
        from ofo_app.outcome_oi import oi_block  # late: outcome_oi's readers import this module
        body["open_interest"] = oi_block(
            None if ctx is None else ctx.provider, req.underlying, [leg.instrument_id for leg in req.legs], body,
            closed=state.closed, live_blocked=live_blocked,
            streams=None if ctx is None else (lambda ids: inputs_streaming(ctx, streaming, ids)))
    if out.state is OutcomeState.COMPUTED:  # only a live computed answer: never a held, refused or not-live one
        body["leg_quotes"] = _leg_quotes(snapshot, definition, {l["instrument_id"]: l["symbol"] for l in body["legs"]})
    # REQ-119 AC-1 / REQ-133 AC-2: the REST route and the live push pass the seq they were sent; none -> no key
    return echo_seq(OutcomeResponse.model_validate(body), seq)


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
                     ctx: MarketContext | None = Depends(get_market_context),
                     streaming: Callable[[str], bool] | None = Depends(get_streaming),
                     now: AnswerClock = Depends(get_answer_clock),
                     stored: Mapping[str, ListedContract] | None = Depends(get_stored_legs),
                     rates: ChargeRates | None = Depends(load_charge_rates), *,
                     margin: Annotated[Margin | None, Depends(get_outcome_margin)] = None,
                     booked: Annotated[Booked | None, Depends(get_booked)] = None) -> OutcomeResponse:
    # a direct call (a test, another module) skips dependency resolution and leaves the Depends marker here: no rates
    return outcome_response(req, ctx, streaming, now=now, stored=stored,
                            rates=rates if isinstance(rates, ChargeRates) else None,
                            margin=margin if isinstance(margin, Margin) else None, seq=req.seq,
                            booked=booked if isinstance(booked, Booked) else None)
