"""GET /paper/strategies, GET /paper/strategies/{id}, POST /paper/strategies/{id}/orders: the paper book (GC-TP 1b).

Spec basis: REQ-109 AC-1 (typed paper prices), AC-4 ("The one engine derives the net position per contract from the
orders"), AC-5 (a stale or missing price pauses unbooked and total); ADR-207 (paper trading the Sensibull Draft
Portfolio way, Net Positions | Orderbook, screens 274-279); ADR-008 (the browser formats nothing: every money field
goes out as an exact Decimal string beside the server's own text).

- The figures come only from ofo.tracking.orderbook.net_positions over the stored orders (paper_store). This module
  adds no arithmetic of its own. An average that does not divide out evenly is exact in the engine and SHOWN rounded to
  the paisa (``average`` and ``average_text``); booked / unbooked / total are the engine's exact values.
- Prices of open contracts come from the same market context as the tracking routes, through
  ofo_app.tracked_contracts.resolve (a stored contract id reaches a feed key only there). A contract that is not live,
  or whose price is stale or missing, has no unbooked figure, and the strategy's unbooked and total are absent with
  the pause reason (AC-5). Booked is always known.
- POST takes typed prices (AC-1): each must be above 0 and a multiple of 0.05; an exit may not exceed the open
  quantity; only the kinds open, add and exit are accepted from a request (settle and stop are server-only). All
  orders of one call are stored in one transaction (paper_store.place) or none are.
- Answer states: no such strategy or another user's -> 404; a strategy with no orders -> 404 on GET; an empty order
  list, a bad price or kind -> 422 with the reason text.
- This module imports nothing from the order path (tests_app/test_paper_order_door.py walks its import graph).
The user comes from the session (``current_user_ref``), never from the request.
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Any, Literal, get_args

from fastapi import APIRouter, Depends, Query
from ofo.adjustment.approaches import EntryFacts
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, charges_sum, paper_charges
from ofo.charges.round_trip import ChargesNotComputable
from ofo.engine import adjust_history as ah
from ofo.engine.book_totals import book_totals
from ofo.engine.duplicate_leg import paper_duplicate_leg
from ofo.engine.extremes import (
    UNLIMITED,
    ContractTerms,
    ExitRisk,
    ExtremesReason,
    book_breakevens,
    book_extremes,
    book_pnl_at_zero,
    exit_risk,
)
from ofo.engine.extremes_charges import (
    AfterSplit,
    BookAfterCharges,
    after_split,
    book_after_charges,
    expiry_hold,
    max_after_charges,
    open_exit_charges,
    open_round_trip_charges,
    sum_after_charges,
    sum_booked_after,
)
from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors import render
from ofo.errors.explanations import render_explanation, restore_explanation
from ofo.instruments.models import FUTURE_TYPE, is_lot_aligned
from ofo.limits import INTEGER_MAX
from ofo.market_calendar import after_close_before_settlement
from ofo.money import PAISE, shown_price
from ofo.outcome import read_snapshot
from ofo.outcome.price_text import price_text
from ofo.outcome.serialize import breakevens_display
from ofo.outcome.snapshot import forward_strike_ids
from ofo.settings import calc
from ofo.strategy import stored_form as sf
from ofo.strategy.definition import describe_contract, display_contract
from ofo.table.model import display_number
from ofo.timeutil import IST
from ofo.tracking import paper, paper_decay, paper_greeks, stops
from ofo.tracking.closing import open_legs_to_close
from ofo.tracking.orderbook import ClosedLeg, NetPosition, PaperOrder, is_typed_price, net_positions
from ofo.tracking.paper_alert import restore_alert_body, restore_order_reason, settle_history_body
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from ofo_app import (
    alert_title,
    held_entry_store,
    market_read,
    may_act,
    paper_exit,
    paper_leg_stops,
    paper_limit,
    paper_monitor,
    paper_store,
    paper_trigger_store,
    plan_ending,
    playbook_store,
    tracked_contracts,
)
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Money
from ofo_app.db import get_db, release_connection
from ofo_app.errors import ClosedRoute, Failure, refuse_request
from ofo_app.live_push import POLL_SECONDS, LiveFeed
from ofo_app.paper_reasons import (
    breakevens_reason_text,
    extremes_reason_text,
    greeks_reason_text,
    no_price_text,
    reason_text,
    unpriced_text,
)
from ofo_app.read_door import NO_TOKEN, read_quotes
from ofo_app.routes.adjustment import TrackedReader, get_tracked_reader
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.catalogue import get_shown_date
from ofo_app.routes.outcome import (
    AnswerClock,
    MarketContext,
    feed_scope,
    get_answer_clock,
    get_calc_settings,
    get_market_context,
    load_charge_rates,
)
from ofo_app.routes.planned_entry import get_live_feed
from ofo_app.routes.strategies import StrategyRefused, refused_answer
from ofo_app.scenario_guard import guard_paper_order
from ofo_app.strategy_money import strategy_money_view
from ofo_app.underlying import Underlying

_LOG = logging.getLogger(__name__)
_UNREADABLE = may_act.TRIGGER_PRICE_UNREADABLE  # ADR-327 (2)

router = APIRouter(route_class=ClosedRoute)
#: REQ-163 AC-1: a basket naming a suggestion record it may not link (the opportunities routes' own answers)
_LINK_REFUSAL = {playbook_store.SUGGESTION_NOT_FOUND: Failure.NOT_FOUND,
                 playbook_store.SUGGESTION_NOT_OPEN: Failure.CONFLICT}

#: The order kinds a request may carry; settle and stop are written by the server only (ADR-207).
REQUEST_KINDS = ("open", "add", "exit")
RequestKind = Literal["open", "add", "exit"]
BookState = Literal["LIVE", "PAUSED", "NOT_CONNECTED", "EXITED"]
SIGNED_PAISA = "summary_paisa_signed"
#: GC-TP step 3a: the text of a side with no bound (a net short call above every strike); existing catalogue words.
NO_FIXED_LIMIT = "summary_reward_risk_none"
Extreme = Money | Literal["unlimited"] | None


class PaperOrderIn(BaseModel):
    """One typed paper order (REQ-109 AC-1). The price is checked by the route (its own reason text), not here."""
    model_config = ConfigDict(extra="forbid")
    contract_id: int = Field(gt=0, le=INTEGER_MAX)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, le=INTEGER_MAX, description="units (lots x lot size)")
    price: Decimal = Field(allow_inf_nan=False)
    kind: RequestKind


class HeldIn(BaseModel):
    """ADR-292 (2): a position the user already holds at their own broker. ``entry_at`` carries an offset (a naive
    time is refused); ``broker`` is optional free text, trimmed, blank -> None, at most 40 characters, one line.
    """
    model_config = ConfigDict(extra="forbid")
    entry_at: AwareDatetime
    broker: str | None = Field(default=None, max_length=40, pattern=r"^[^\r\n\x0b\x0c\x85\u2028\u2029]*$")

    @field_validator("broker", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value


class PaperOrdersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: ADR-292: the first basket only, every order `open`; stored with the basket (one held row, same transaction)
    held: HeldIn | None = None
    orders: list[PaperOrderIn] = Field(min_length=1, max_length=64)
    #: REQ-163 AC-1: the acted-on suggestion records this basket answers (Compare -> Open in builder); each must be
    #: of this strategy and user, acted on and not yet linked, or the whole basket is refused (nothing stored)
    suggestion_ids: list[Annotated[int, Field(gt=0, le=INTEGER_MAX)]] = Field(default_factory=list, max_length=16)
    #: REQ-112 (IC e2e 11): how many legs the prepared basket held; with it the linked records read completed (all
    #: placed) or partly completed (some); without it they stay acted on
    basket_legs: int | None = Field(default=None, gt=0, le=64)
    #: ADR-326 (1) (D-25): the approach this basket was prepared as; a Take profit (A-24, A-25) is refused at an
    #: after-charges loss by the build path that offers it (offered and accepted agree). Other ids: nothing checked
    approach_id: Literal["A-24", "A-25"] | None = None
    #: ADR-330 (28): the user ticked the "prices are not live" line; only then may the save start its rules from the
    #: last index value the app holds. Absent / false: a save without a live index price is refused.
    prices_not_live_confirmed: bool = False


class PaperNetOut(ApiModel):
    """One contract's net position (screens 274-279: Lots / Avg / LTP / Booked / Unbooked)."""
    contract_id: int
    contract_text: CatalogueText
    instrument: Literal["CE", "PE", "FUT"]
    strike: Money | None
    expiry: datetime.date
    net_quantity: int  # signed: above 0 long, below 0 short, 0 flat
    lot_size: int  # the catalogue contract's lot size: the Paper tab shows Lots = |net_quantity| / lot_size
    average: Money | None  # rounded to the paisa for display; None when flat
    average_text: CatalogueText | None
    ltp: Money | None  # the live price; None when flat or not live
    ltp_text: CatalogueText | None
    price_state: paper.LegState | None  # None when flat
    price_state_text: CatalogueText | None = None  # ADR-210: the sentence for a contract reason (retired, ...)
    price_at: datetime.datetime | None
    booked: Money
    booked_text: CatalogueText
    unbooked: Money | None  # None (never 0) when open and not live
    unbooked_text: CatalogueText | None
    total: Money | None
    total_text: CatalogueText | None
    no_price_text: CatalogueText | None = None  # ADR-311: "no price" on an open contract with no live price


class PaperClosedOut(ApiModel):
    """D-10 (ADR-207 (2)): one CLOSED lifecycle of a contract (open to flat) with its own entry, exit and booked P&L; a
    contract bought back and opened again has this row AND an open row whose booked starts at 0."""
    contract_id: int
    contract_text: CatalogueText
    instrument: Literal["CE", "PE", "FUT"]
    strike: Money | None
    expiry: datetime.date
    side: Literal["BUY", "SELL"]  # the side that opened it: SELL = a short that was bought back
    quantity: int
    lot_size: int
    lots: int | None  # None when the quantity is not whole lots
    average_entry: Money
    average_entry_text: CatalogueText
    average_exit: Money  # 0.00 for an option that expired worthless (settled)
    average_exit_text: CatalogueText  # "174.73 (avg of 2)" when over more than one exit (N-28, ADR-330 (27))
    exit_fills: int  # how many exit orders the average exit is over; the Orderbook keeps each fill
    booked: Money
    booked_text: CatalogueText
    opened_at: datetime.datetime
    closed_at: datetime.datetime
    #: D-22 / D-71: why it closed when a stop or an expiry settlement closed it (the reason with the index value at that
    #: moment, or the close it settled at); None for an exit the trader made
    reason_text: CatalogueText | None = None


class UnpricedLegOut(ApiModel):
    """ADR-311: an open leg with no live price, named by its contract; ``expired`` says the contract has expired."""
    leg_index: int
    contract_text: CatalogueText
    expired: bool


class UnpricedFields(ApiModel):
    """ADR-311: which open legs have no price. Totals stay paused whenever this is not empty; ``unpriced_text`` is the
    one line naming them (reviewed templates), absent when every open leg has a price."""
    unpriced_legs: list[UnpricedLegOut] = Field(default_factory=list)
    unpriced_text: CatalogueText | None = None
    # D-64: set after the close and before the settlement time while an open leg expires today (server clock, one place)
    after_close_text: CatalogueText | None = None


class PaperOrderOut(ApiModel):
    """One row of the orderbook: time, side, contract text, quantity, price, kind."""
    id: int
    placed_at: datetime.datetime
    side: Literal["BUY", "SELL"]
    contract_id: int
    contract_text: CatalogueText
    quantity: int
    #: ADR-330 (23): quantity in lots, units / the contract's catalogue lot size (as the Net Positions lots); None when
    #: the units are not whole lots or the lot size is not positive. The browser never divides.
    lots: int | None
    price: Money
    price_text: CatalogueText
    kind: Literal["open", "add", "exit", "settle", "stop"]
    #: D-22 / D-71: why a stop or settle order was recorded, with the index value at that moment (the stored reason read
    #: back through its reviewed wording); None for an order with no reason or a reason no wording fits
    reason_text: CatalogueText | None = None


#: Why a Charges figure is absent: no charge rate set could be read, or an order the rate table cannot price (a futures
#: order, an index without a known segment).
ChargesReason = Literal["rates_unavailable", "not_priced"]
RATES_UNAVAILABLE: ChargesReason = "rates_unavailable"
NOT_PRICED: ChargesReason = "not_priced"
PAPER_CHARGES = "paper_charges"
AfterChargesReason = Literal["rates_unavailable", "not_priced", "prices_not_live"]


class PaperFigures(UnpricedFields):
    expired_open: bool = False  # D-40 (ADR-324): an open leg is on an expired contract, whatever the connection state
    state: BookState
    pause_reason: paper.PauseReason | None
    as_of: datetime.datetime | None = None  # REQ-109 AC-5: PAUSED only: oldest known quote time of a contract not live
    booked: Money
    unbooked: Money | None
    total: Money | None
    booked_text: CatalogueText
    unbooked_text: CatalogueText | None
    total_text: CatalogueText | None
    positions: list[PaperNetOut]
    # D-10: every closed lifecycle; booked here + the open positions' booked = booked. A contract that went flat
    # appears in ``positions`` with net 0 AND here, so consumers sum the OPEN positions + closed, never all + closed
    closed: list[PaperClosedOut] = Field(default_factory=list)
    # GC-TP step 8a (REQ-109 AC-10, ADR-207 (7), Sensibull 050): the charges engine's sum over every paper order, BESIDE
    # the P&L above (never subtracted from it); absent with ``charges_reason`` (never 0) when it cannot be computed
    charges: Money | None = None
    charges_text: CatalogueText | None = None
    charges_reason: ChargesReason | None = None
    pause_reason_text: CatalogueText | None = None  # ADR-210: the sentence for ``pause_reason`` / ``charges_reason``
    charges_reason_text: CatalogueText | None = None
    # GC-ICFIX u122/u123 (ADR-263, ADR-008): the total AFTER charges = total - charges paid - estimated charges to close
    # what is open (ofo.engine.extremes_charges.book_after_charges); ``total`` above stays the before-charges figure.
    # Absent, with ``after_charges_reason``, when any part is unknown (never 0).
    total_after: Money | None = None
    total_after_text: CatalogueText | None = None
    charges_paid: Money | None = None
    charges_paid_text: CatalogueText | None = None
    charges_to_close: Money | None = None
    charges_to_close_text: CatalogueText | None = None
    after_charges_reason: AfterChargesReason | None = None
    after_charges_reason_text: CatalogueText | None = None
    # GC-ICFIX u123 (ADR-303): Booked after = booked - ALL charges paid; Unbooked after = open-leg P&L - the estimated
    # charges to close; the two add up to ``total_after`` exactly. Absent with ``after_charges_reason`` (never 0).
    booked_after: Money | None = None
    booked_after_text: CatalogueText | None = None
    booked_after_reason: AfterChargesReason | None = None  # ADR-311: why it is absent (charges paid unknown)
    booked_after_reason_text: CatalogueText | None = None
    unbooked_after: Money | None = None
    unbooked_after_text: CatalogueText | None = None


#: GC-TP R-19b: a figure the list leaves out because the whole strategy is exited (the Paper card says Exited).
EXITED = "exited"
FigureReason = ExtremesReason | Literal["exited"]
GreeksFigureReason = paper.PauseReason | paper_greeks.GreeksReason | Literal["exited"]


class PaperExtremes(ApiModel):
    # GC-TP step 3a (REQ-109 AC-9, Drafts Mode summary 278-279): ofo.engine.extremes; absent with extremes_reason
    profit_left: Extreme
    loss_left: Extreme
    max_profit: Extreme
    max_loss: Extreme
    profit_left_text: CatalogueText | None
    loss_left_text: CatalogueText | None
    max_profit_text: CatalogueText | None
    max_loss_text: CatalogueText | None
    extremes_reason: FigureReason | None
    extremes_reason_text: CatalogueText | None = None
    # F-94 (ADR-082 (2)): the round-trip charges inside Max Profit / Max Loss, and the sentence that says so
    extremes_charges: Money | None = None
    extremes_charges_text: CatalogueText | None = None
    # D-10 (ADR-306 (5)): a fully closed book: "Closed: result Rs X." beside (in place of) the two equal maxima
    closed_text: CatalogueText | None = None
    # ADR-330 (57): a fully closed book also says what its plan was and how it ended (None while any leg is open)
    plan_final_text: CatalogueText | None = None
    # ADR-306: Profit left / Loss left after = Max profit / Max loss after - Total after, not capped (ADR-302);
    # ``recover`` = minus Total after when negative. Absent when the book has no after total (see after_charges_reason).
    profit_left_after: Extreme = None
    loss_left_after: Extreme = None
    # ADR-320 (2), D-14: on the trade's expiry day only, Max profit / Profit left "If held to expiry" (paid charges
    # only, as settlement books it); the max_profit / profit_left above are then the "If exited now" pair. Else None.
    max_profit_hold: Extreme = None
    profit_left_hold: Extreme = None
    max_profit_hold_text: CatalogueText | None = None
    profit_left_hold_text: CatalogueText | None = None
    profit_left_after_text: CatalogueText | None = None
    loss_left_after_text: CatalogueText | None = None
    recover: Money | None = None
    recover_text: CatalogueText | None = None


class PaperBreakevens(ApiModel):
    """GC-TP R-19b (Sensibull 090): the at-expiry breakevens, exact; an empty list is a real answer, None is absent."""
    breakevens: list[Money] | None
    breakevens_display: list[CatalogueText] | None
    breakevens_reason: FigureReason | None
    breakevens_reason_text: CatalogueText | None = None  # ADR-211 (5): the sentence beside the dash
    # D-16 (ADR-263): booked P&L and charges are in the levels, or before charges
    breakevens_basis_text: CatalogueText | None = None
    # D-11 / D-16: the levels where the DRAWN curve (booked in, before charges: ADR-167 (1)) crosses zero; the chart's
    # triangles read these, the tiles read ``breakevens`` (after charges, with their basis line)
    breakevens_curve: list[Money] | None = None


class GreekFigures(ApiModel):
    """Position-level Greeks (per unit x quantity x sign), 4 dp, with the table's display text."""
    delta: Money
    gamma: Money
    theta: Money
    vega: Money
    delta_text: CatalogueText
    gamma_text: CatalogueText
    theta_text: CatalogueText
    vega_text: CatalogueText
    # D-12 (ADR-320 (1)): on expiry day, the time value left until the close in rupees, replacing theta on screen
    decay_left_today: Money | None = None
    decay_left_today_text: CatalogueText | None = None


class PaperLegGreeks(GreekFigures):
    contract_id: int


class PaperGreeksOut(ApiModel):
    legs: list[PaperLegGreeks]  # the open contracts, in the positions' order
    net: GreekFigures
    expiry_count: int = 1  # D-63: the distinct expiries the net adds across
    basis_text: CatalogueText | None = None  # D-63: "Greeks are summed across 2 expiries." only when expiry_count > 1


class PaperGreeksBlock(ApiModel):
    greeks: PaperGreeksOut | None
    greeks_reason: GreeksFigureReason | None
    greeks_reason_text: CatalogueText | None = None  # ADR-210: the sentence beside the dash


class HeldEntryOut(ApiModel):
    """ADR-292 (3): a strategy entered "held at my broker": the stated entry time, the broker's name as typed, and the
    moment its rules start (the stored basket-0 fill clock; None when no fill facts were stored)."""
    source: Literal["held_elsewhere"]
    entry_at: datetime.datetime
    broker: CatalogueText | None
    rules_start_at: datetime.datetime | None


def _held_out(row: Any) -> dict | None:
    if row is None:
        return None
    broker = None if row.broker_text is None else sf.shown_broker(row.broker_text)
    return {"source": "held_elsewhere", "entry_at": row.entry_at, "broker": broker,
            "rules_start_at": row.rules_start_at}


class PaperBookOut(PaperFigures, PaperExtremes, PaperBreakevens, PaperGreeksBlock):
    """GET /paper/strategies/{id} and the answer of POST .../orders."""
    strategy_id: int
    name: CatalogueText  # REQ-134: quoted user text
    underlying: Underlying
    answered_at: datetime.datetime
    orders: list[PaperOrderOut]
    status_word: Literal["Draft", "Running", "Completed", "Unknown"]  # ADR-299 (D-28): the same word /strategies says
    held: HeldEntryOut | None = None  # GC-TRACK1 k07


class PaperStrategyOut(PaperFigures, PaperExtremes, PaperBreakevens, PaperGreeksBlock):
    strategy_id: int
    name: CatalogueText
    underlying: Underlying
    status_word: Literal["Draft", "Running", "Completed", "Unknown"]  # ADR-299 (D-28): the same word /strategies says
    held: HeldEntryOut | None = None  # GC-TRACK1 k07
    open_count: int  # GC-TP step 4a: positions with a non-zero net quantity ("N of M positions")
    position_count: int


TotalsReason = paper.PauseReason | paper_decay.DecayReason


class PaperTotalsOut(ApiModel):
    """GC-TP step 4a (screens 050-053 totals strip): the sums over every paper strategy of the user, from the server."""
    total_after: Money | None = None  # GC-ICFIX: sum of every total_after; None (never partial) if one is absent
    total_after_text: CatalogueText | None = None
    charges_paid: Money | None = None  # the sum of every strategy's charges paid; None (never partial) if one absent
    charges_paid_text: CatalogueText | None = None
    charges_to_close: Money | None = None  # the sum of every strategy's estimated charges to close what is open
    charges_to_close_text: CatalogueText | None = None
    after_charges_reason: AfterChargesReason | None = None
    after_charges_reason_text: CatalogueText | None = None
    # GC-ICFIX u123: the sum of every booked_after; None (never partial) if one absent, with its reason
    booked_after: Money | None = None
    booked_after_text: CatalogueText | None = None
    booked_after_reason: AfterChargesReason | None = None
    booked_after_reason_text: CatalogueText | None = None
    unbooked_after: Money | None = None
    unbooked_after_text: CatalogueText | None = None
    booked: Money
    booked_text: CatalogueText
    unbooked: Money | None  # None (never a partial sum) when any strategy's unbooked is absent (REQ-109 AC-5)
    unbooked_text: CatalogueText | None
    total: Money | None
    total_text: CatalogueText | None
    totals_reason: paper.PauseReason | None
    totals_as_of: datetime.datetime | None = None  # the oldest as_of among the paused books (None: no known quote time)
    decay: Money | None  # REQ-145 AC-2: rupees to the next market open over every open contract, rounded once
    decay_text: CatalogueText | None
    decay_reason: TotalsReason | None
    charges: Money | None = None  # GC-TP step 8a: every strategy's Charges summed; None (never partial) if one absent
    charges_text: CatalogueText | None = None
    charges_reason: ChargesReason | None = None
    totals_reason_text: CatalogueText | None = None  # ADR-210: the sentence beside each dash above
    decay_reason_text: CatalogueText | None = None
    charges_reason_text: CatalogueText | None = None
    # D-40 (ADR-324): strategies whose open contract has expired are left out of every figure above, and counted here
    left_out_count: int = 0
    left_out_text: CatalogueText | None = None
    # P11 (ADR-330 (10)): how many closed strategies the figures include (the screen prints closed_text)
    closed_count: int = 0
    closed_text: CatalogueText | None = None


class PaperTodayOut(PaperTotalsOut):
    """D-68 (ADR-320 point 6): the header's "Today" total: the same sums as ``totals`` (one function,
    ``_totals``), over the real trades opened or closed today (IST) only. ``count`` 0 = nothing today
    (``empty_text`` says so; the figures are then not shown)."""
    count: int = 0
    empty_text: CatalogueText | None = None


class PaperListOut(ApiModel):
    strategies: list[PaperStrategyOut]  # newest strategy first (first order time, then id)
    totals: PaperTotalsOut
    today: PaperTodayOut | None = None
    answered_at: datetime.datetime
    # the server's shown date: a list label leaves the year off inside this year (ADR-330 (19))
    shown_date: datetime.date


def _connected(ctx: MarketContext | None) -> bool:
    return ctx is not None and ctx.provider.status().connected


#: GC-LIVE 30 Oct 2026: the longest the paper read waits for the index and the forward strikes' first live quotes.
FORWARD_WAIT_S = 3.0


def _iv_inputs_missing(snapshot) -> bool:
    """True when an IV cannot be solved yet for an option leg of a market that is open: no index reading, or an option
    expiry whose forward is missing or fell back to spot (ADR-061: parity needs the ATM call/put pairs, D-C33). A
    closed market waits for nothing (ADR-212: the figures are the last close)."""
    if snapshot.market_closed:
        return False
    expiries = {lm.contract.contract.expiry for lm in snapshot.legs.values()
                if lm.contract is not None and lm.contract.contract.instrument_type in ("CE", "PE")}
    if not expiries:
        return False
    return snapshot.spot is None or any(
        (f := snapshot.forwards.get(e)) is None or f.source != "parity" for e in expiries)


def _read_ready(snapshot, ids: list[str]) -> bool:
    """Every open contract has its display price and the IV inputs are there."""
    return (all(paper.display_price(snapshot, i).state == paper.LIVE for i in ids)
            and not _iv_inputs_missing(snapshot))


async def _hold_until_ready(feed: LiveFeed, ctx: MarketContext, underlying: str, ids: list[str], snapshot):
    """ONE hold for the whole read, released once at the end (GC-LIVE). Holds the open contracts nobody else holds, the
    index and ``forward_strike_ids`` (the outcome push's own D-C33 choice) until every contract is priced and an IV can
    be solved, or ``FORWARD_WAIT_S`` passes. RCA 1 (F-1, 'every paper book is no_iv'): the read held only the book's
    contracts, so with no other screen open the index had no quote and the chain no call/put pair. RCA 2 (F-3): the
    contracts' own hold was released before the IV inputs were read, and a released contract's quote is parked, so an
    unheld contract came back 'missing'. A provider that knows none of the ids leaves the read as it is."""
    provider = ctx.provider
    spot = provider.underlying_quote(underlying)
    live_spot = spot.ltp if spot is not None and spot.ltp is not None and spot.ltp > 0 else None
    index_id = getattr(provider, "index_id", lambda _u: None)(underlying)
    wanted = [*ids, *([index_id] if index_id else []),
              *forward_strike_ids(provider.instrument_master(), underlying, ids, live_spot)]
    held = await read_quotes(
        feed, wanted,
        lambda: read_snapshot(provider, underlying, ids, ctx.clock(), ctx.rate, feed_scope(ctx),
                              quality=ctx.forward_quality),
        lambda snap: _read_ready(snap, ids), lambda: provider.status().connected, FORWARD_WAIT_S, POLL_SECONDS)
    # NO_TOKEN: a contract the provider has no token for, the answer stands
    return snapshot if held is NO_TOKEN else held


async def _snapshot(ctx: MarketContext, feed: LiveFeed | None, underlying: str, ids: list[str]):
    """One market read (the tracking routes' rule): with a live feed, a read that is not ready (a contract unpriced, or
    no IV inputs) holds what it needs in one hold until it is, or the wait passes (GC-LIVE F-1, F-3)."""
    snapshot = read_snapshot(ctx.provider, underlying, ids, ctx.clock(), ctx.rate, feed_scope(ctx),
                             quality=ctx.forward_quality)
    if feed is not None and ids:
        snapshot = await _hold_until_ready(feed, ctx, underlying, ids, snapshot)
    return snapshot


def _paper(orders: Sequence[paper_store.StoredOrder]) -> list[PaperOrder]:
    return [o.order.as_paper() for o in orders]


def _open_ids(orders: Sequence[paper_store.StoredOrder]) -> list[int]:
    """The contracts with a non-zero net quantity (the quantity does not depend on any live price)."""
    if not orders:
        return []  # net_positions refuses an empty book
    return [int(p.instrument_id) for p in net_positions(_paper(orders), {}).positions if p.net_quantity != 0]


def _identity(found: tracked_contracts.TrackedContract) -> tuple[str, Instrument, Any, datetime.date]:
    if found.stored is None:
        raise RuntimeError(f"paper order contract id {found.contract_id} has no stored contract row ({found.state})")
    contract = found.stored.listed.contract
    instrument = Instrument(contract.instrument_type)
    strike = None if contract.instrument_type == FUTURE_TYPE else contract.strike
    return contract.name, instrument, strike, contract.expiry


identity_of = _identity  # the public name other routes import (plan_watch.py)


def _exact(value: Decimal | None) -> Decimal | None:
    """The engine's exact value; a value that is a whole number of paise goes out with its two decimals."""
    if value is None:
        return None
    paisa = value.quantize(PAISE)
    return paisa if paisa == value else value


def _signed(value: Decimal | None) -> str | None:
    return None if value is None else render_explanation(SIGNED_PAISA, amount=value)


def _position(p: NetPosition, found: tracked_contracts.TrackedContract, price: paper.Price | None) -> dict:
    underlying, instrument, strike, expiry = _identity(found)
    average = None if p.average is None else shown_price(p.average)
    live = price is not None and paper.is_live(price)
    text_ = describe_contract((underlying, instrument, strike, expiry))
    return {"contract_id": found.contract_id, "contract_text": text_,
            "instrument": instrument.value, "strike": strike, "expiry": expiry, "net_quantity": p.net_quantity,
            "lot_size": found.stored.listed.contract.lot_size,  # _identity above already refused a missing stored row
            "average": average, "average_text": price_text(average),
            "ltp": price.price if live and price is not None else None,
            "ltp_text": price_text(price.price) if live and price is not None else None,
            "price_state": None if price is None else price.state, "price_state_text": _state_text(price),
            "price_at": None if price is None else price.at,
            "booked": _exact(p.booked), "booked_text": _signed(p.booked),
            "unbooked": _exact(p.unbooked), "unbooked_text": _signed(p.unbooked),
            "total": _exact(p.total), "total_text": _signed(p.total),
            "no_price_text": no_price_text() if p.net_quantity != 0 and not live else None}


def _closing_reasons(orders: Sequence[paper_store.StoredOrder]) -> dict[tuple[int, datetime.datetime], str]:
    """The stored reason of each stop / settle order by (contract, time): the order that closed a lifecycle."""
    return {(o.order.contract_id, o.order.placed_at): o.order.reason for o in orders
            if o.order.kind in ("stop", "settle") and o.order.reason}


def _exit_text(exit_: Decimal, fills: int) -> Any:
    """N-28 (ADR-330 (27)): the bare price for one exit, "174.73 (avg of 2)" for an average over several exits."""
    if fills <= 1:
        return price_text(exit_)
    return render_explanation("closed_exit_average", value=exit_, count=fills)


def _closed_row(leg: ClosedLeg, found: tracked_contracts.TrackedContract, reason: str | None = None) -> dict:
    underlying, instrument, strike, expiry = _identity(found)
    lot = found.stored.listed.contract.lot_size
    entry = shown_price(leg.average_entry)
    exit_ = shown_price(leg.average_exit)
    text_ = describe_contract((underlying, instrument, strike, expiry))
    return {"contract_id": found.contract_id, "contract_text": text_,
            "instrument": instrument.value, "strike": strike, "expiry": expiry, "side": leg.side,
            "quantity": leg.quantity, "lot_size": lot,
            "lots": leg.quantity // lot if is_lot_aligned(leg.quantity, lot) else None,
            "average_entry": entry, "average_entry_text": price_text(entry),
            "average_exit": exit_, "average_exit_text": _exit_text(exit_, leg.exit_fills), "exit_fills": leg.exit_fills,
            "booked": _exact(leg.booked), "booked_text": _signed(leg.booked),
            "opened_at": leg.opened_at, "closed_at": leg.closed_at, "reason_text": restore_order_reason(reason)}


def _state_text(price: paper.Price | None) -> Any:
    """ADR-210: the sentence for a contract that is not shown (retired, delisted, ...); None for a price state."""
    if price is None or price.state not in get_args(paper.ContractReason):
        return None
    return reason_text(price.state)


def _prices(open_ids: Sequence[int], found: dict[int, tracked_contracts.TrackedContract],
            snapshot: Any) -> dict[int, paper.Price]:
    """Per open contract: a contract reason (never priced), else the snapshot's answer; no snapshot = missing."""
    out: dict[int, paper.Price] = {}
    for cid in open_ids:
        contract = found[cid]
        key = contract.feed_key
        if contract.state != tracked_contracts.LIVE or key is None:
            out[cid] = paper.Price(contract.identity or str(cid), contract.state, None, None)  # type: ignore[arg-type]
        elif snapshot is None:
            out[cid] = paper.Price(key, "missing", None, None)
        else:
            out[cid] = paper.display_price(snapshot, key)  # ADR-212: display only; fills use paper.leg_price
    return out


def _today(snapshot: Any) -> datetime.date | None:
    """The snapshot's India date (the tracking page's rule), None without a snapshot."""
    return None if snapshot is None else snapshot.valuation.astimezone(paper.IST).date()


def _book_day(snapshot: Any, answered_at: datetime.datetime) -> datetime.date:
    """D-40: the India date an expiry is judged against: the snapshot's, else the answer's own (no snapshot)."""
    return _today(snapshot) or answered_at.astimezone(paper.IST).date()


def _figures(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],
             prices: dict[int, paper.Price], connected: bool, today: datetime.date | None = None) -> dict:
    """The strategy's figures from the one engine at the live prices of its open contracts."""
    view = strategy_money_view(_paper(orders), prices).lifecycle()  # D-10: the book's totals, split at every flat point
    positions = [_position(p, found[int(p.instrument_id)], prices.get(int(p.instrument_id))) for p in view.positions]
    why = _closing_reasons(orders)
    closed = [_closed_row(leg, found[int(leg.instrument_id)], why.get((int(leg.instrument_id), leg.closed_at)))
              for leg in view.closed]
    reason = next((found[c].state for c in prices if found[c].state != tracked_contracts.LIVE), None)
    paused = view.unbooked is None
    as_of = None
    if not prices:
        state, pause = "EXITED", None
    elif not connected:
        state, pause = "NOT_CONNECTED", reason
    elif paused:
        state, pause = "PAUSED", reason or paper.PRICES_NOT_LIVE
        as_of = paper.paused_as_of(prices.values())  # the engine's own rule (ofo.tracking.paper), not a second way
    else:
        state, pause = "LIVE", None
    # ADR-311: a paused book names the contracts with no price (every total stays paused); expired = retired contract
    # leg_index = the leg's place among ALL the book's legs (closed ones count), as on the tracking page
    cids = [int(p.instrument_id) for p in view.positions]
    open_ = [(n, str(c), _identity(found[c])[3], prices[c]) for n, c in enumerate(cids) if c in prices]
    named = paper.unpriced_legs(open_, today)  # independent of the connection state
    expired_open = any(u.expired for u in named)
    gone = named if state == "PAUSED" else tuple(u for u in named if u.expired)  # not paused: only the expired legs
    names = [(display_contract(_identity(found[cids[u.index]])), u.expired) for u in gone]
    return {"unpriced_legs": [{"leg_index": u.index, "contract_text": n, "expired": u.expired}
                              for u, (n, _) in zip(gone, names, strict=True)], "unpriced_text": unpriced_text(names),
            "expired_open": expired_open, "state": state, "pause_reason": pause,
            "pause_reason_text": reason_text(pause), "as_of": as_of,
            "booked": _exact(view.booked), "unbooked": _exact(view.unbooked),
            "total": _exact(view.total), "booked_text": _signed(view.booked), "unbooked_text": _signed(view.unbooked),
            "total_text": _signed(view.total), "positions": positions, "closed": closed}


def _extreme(value: Any) -> tuple[Decimal | str | None, Any]:
    """One extreme figure and its text: the exact Decimal, "unlimited" with the no-fixed-limit words, or absent."""
    if value is None:
        return None, None
    if value is UNLIMITED:
        return "unlimited", render_explanation(NO_FIXED_LIMIT)
    return _exact(value), _signed(value)


def _extremes(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],  # noqa: PLR0913
              prices: dict[int, paper.Price], underlying: str = "", rates: ChargeRates | None = None,
              today: datetime.date | None = None) -> dict:
    """Max Profit / Max Loss from the one engine (ofo.engine.extremes_charges.max_after_charges) and Profit left / Loss
    left AFTER charges (ADR-306 (1)-(3), D-13): the ``after_split`` figures, the same ones as ``profit_left_after``, so
    Total after + Profit left = Max profit on the served fields. Absent with the after-charges reason when the book
    has no after total (ADR-306 (6): never a gross range beside a net maximum). ``today`` = the trade's nearest open
    expiry (ADR-320 (2), D-14): the "If held to expiry" pair (``max_profit_hold`` / ``profit_left_hold``) is served
    beside the usual figures, which are the "If exited now" pair; other days it is absent."""
    money = strategy_money_view(_paper(orders), prices)
    live, view = money.live, money.book
    terms = terms_of(orders, found)
    paid = paid_exact_of(orders, found, underlying, rates)  # ADR-263: the charges really paid on every filled order
    got = max_after_charges(view, terms, live, underlying, rates, paid) if paid is not None else \
        book_extremes(view, terms, live)  # unpriced: before charges, and says so
    charges = None if paid is None else open_round_trip_charges(view, terms, underlying, rates, paid, live)
    shown = _charges(orders, found, underlying, rates)
    after = after_charges(view, terms, live, shown["charges"], shown["charges_reason"], underlying, rates)
    split = after_split(view, terms, live, underlying, rates, after, paid)
    closed = not any(p.net_quantity for p in view.positions)  # ADR-306 (5): 0 and 0 on any basis
    left = (got.profit_left, got.loss_left) if closed else (split.profit_left_after, split.loss_left_after)
    figures = {"profit_left": left[0], "loss_left": left[1],
               "max_profit": got.max_profit, "max_loss": got.max_loss}
    out: dict[str, Any] = {"extremes_reason": got.reason, "extremes_reason_text": extremes_reason_text(got.reason)}
    for name, value in figures.items():
        out[name], out[f"{name}_text"] = _extreme(value)
    is_open = got.max_profit is not None  # open or fully closed: both carry the charges (or say "before charges")
    out["extremes_charges"] = charges if is_open else None
    out["extremes_charges_text"] = (
        None if not is_open else render_explanation("paper_extremes_before_charges") if charges is None else
        render_explanation("paper_extremes_with_charges", charges=charges))
    closed_id = "paper_closed_result" if paid is not None else "paper_closed_result_before"
    out["closed_text"] = (render_explanation(closed_id, result=got.max_profit)
                          if closed and isinstance(got.max_profit, Decimal) else None)
    held = None
    nearest = min((terms[p.instrument_id].expiry for p in view.positions if p.net_quantity), default=None)
    if today is not None and nearest == today and split.profit_left_after is not None:
        held = expiry_hold(book_extremes(view, terms, live), after)
    for i, name in enumerate(("max_profit_hold", "profit_left_hold")):
        out[name], out[f"{name}_text"] = _extreme(None if held is None else held[i])
    return out


def _breakevens(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],
                spot: Decimal | None, charges: Decimal | None = None) -> dict:
    """GC-TP R-19b: the book's at-expiry breakevens from the one engine (ofo.engine.extremes.book_breakevens), each with
    its level text and the signed percent from spot (REQ-153) when the spot is usable. Needs no live price.
    D-16 (ADR-263): on the same basis as Max Profit / Max Loss beside them: the booked P&L is in and so are the
    round-trip ``charges`` they carry (``extremes_charges``); None = those could not be priced, and
    ``breakevens_basis_text`` says the levels are before charges.
"""
    terms = {}
    for cid in {o.order.contract_id for o in orders}:
        _, instrument, strike, expiry = _identity(found[cid])
        terms[str(cid)] = ContractTerms(instrument, strike, expiry)
    view = net_positions(_paper(orders), {})
    got = book_breakevens(view, terms, charges or Decimal(0))
    if got.levels is None:
        return {"breakevens": None, "breakevens_display": None, "breakevens_reason": got.reason,
                "breakevens_reason_text": breakevens_reason_text(got.reason), "breakevens_basis_text": None,
                "breakevens_curve": None}
    curve = got.levels if not charges else book_breakevens(view, terms, Decimal(0)).levels
    texts = breakevens_display(got.levels, spot)  # GC-TPD R-34: the outcome summary's own function and shape
    basis = (render_explanation("paper_breakevens_before_charges") if charges is None else
             render_explanation("paper_breakevens_with_charges", charges=charges))
    return {"breakevens": [_exact(x) for x in got.levels], "breakevens_display": texts, "breakevens_reason": got.reason,
            "breakevens_reason_text": None, "breakevens_basis_text": basis,
            "breakevens_curve": None if curve is None else [_exact(x) for x in curve]}


def _open_contracts(figures: dict,
                    found: dict[int, tracked_contracts.TrackedContract]) -> list[paper_decay.OpenContract]:
    return [paper_decay.OpenContract(found[p["contract_id"]].feed_key or "", Instrument(p["instrument"]), p["strike"],
                                     p["expiry"], p["net_quantity"], p["ltp"])
            for p in figures["positions"] if p["net_quantity"] != 0]


def _greek_figures(g: Any, left: Decimal | None = None) -> dict:
    shown = None if left is None else left.quantize(PAISE, rounding=ROUND_HALF_EVEN)
    return {"decay_left_today": shown,
            "decay_left_today_text": None if shown is None else render_explanation("decay_left_today_text",
                                                                                    amount=shown),
            "delta": g.delta, "gamma": g.gamma, "theta": g.theta, "vega": g.vega,
            "delta_text": display_number(g.delta, 2), "gamma_text": display_number(g.gamma, 4),
            "theta_text": display_number(g.theta, 2), "vega_text": display_number(g.vega, 2)}


def _greeks(figures: dict, found: dict[int, tracked_contracts.TrackedContract], snapshot: Any,
            underlying: str) -> dict:
    """GC-TP R-19b: the open position's per-contract and net Greeks (ofo.tracking.paper_greeks, one snapshot). Absent
    with the book's pause reason when an open contract is not live, never stale numbers; nothing open: absent."""
    held = [p for p in figures["positions"] if p["net_quantity"] != 0]
    if not held:
        return {"greeks": None, "greeks_reason": None, "greeks_reason_text": None}
    if figures["unbooked"] is None or snapshot is None:
        why = figures["pause_reason"] or paper.PRICES_NOT_LIVE
        return {"greeks": None, "greeks_reason": why, "greeks_reason_text": greeks_reason_text(why)}
    got = paper_greeks.book_greeks(snapshot, underlying, _open_contracts(figures, found))
    if got.net is None or got.legs is None:
        return {"greeks": None, "greeks_reason": got.reason, "greeks_reason_text": greeks_reason_text(got.reason)}
    lefts = got.legs_left_today or (None,) * len(got.legs)
    legs = [{"contract_id": p["contract_id"]} | _greek_figures(g, x) for p, g, x in zip(held, got.legs, lefts,
                                                                                      strict=True)]
    expiries = len({p["expiry"] for p in held})
    basis = render_explanation("paper_greeks_across_expiries", count=expiries) if expiries > 1 else None
    return {"greeks": {"legs": legs, "net": _greek_figures(got.net, got.net_left_today), "expiry_count": expiries,
                       "basis_text": basis},
            "greeks_reason": None,
            "greeks_reason_text": None}


def _spot(snapshot: Any) -> Decimal | None:
    quote = None if snapshot is None else snapshot.spot
    return None if quote is None or quote.ltp is None else quote.ltp


_ABSENT = {"profit_left": None, "loss_left": None, "max_profit": None, "max_loss": None, "profit_left_text": None,
           "loss_left_text": None, "max_profit_text": None, "max_loss_text": None, "extremes_reason": EXITED,
           "extremes_reason_text": extremes_reason_text(EXITED),
           "extremes_charges": None, "extremes_charges_text": None, "max_profit_hold": None,
           "max_profit_hold_text": None, "profit_left_hold": None, "profit_left_hold_text": None,
           "breakevens": None, "breakevens_display": None, "breakevens_reason": EXITED,
           "breakevens_reason_text": breakevens_reason_text(EXITED), "breakevens_basis_text": None,
           "breakevens_curve": None, "greeks": None,
           "greeks_reason": EXITED, "greeks_reason_text": greeks_reason_text(EXITED)}


def _summary(orders: Sequence[paper_store.StoredOrder],  # noqa: PLR0913
             found: dict[int, tracked_contracts.TrackedContract],
             prices: dict[int, paper.Price], figures: dict, snapshot: Any, underlying: str, *,
             exited_absent: bool, rates: ChargeRates | None = None) -> dict:
    """Max Profit / Max Loss (and Profit / Loss left), Breakeven and net Greeks of one book: ONE function behind both
    the list and the single-strategy reply, so the two can never differ. ``exited_absent`` (the list): a fully exited
    strategy has every one of them absent with the reason ``exited`` (never 0)."""
    if exited_absent and figures["state"] == "EXITED":
        return dict(_ABSENT)
    spot = _spot(snapshot) if figures["state"] == "LIVE" else None  # no percent from a spot that is not live
    extremes = _extremes(orders, found, prices, underlying, rates, _today(snapshot))
    # D-16: the charges Max Profit carries
    return (extremes | _breakevens(orders, found, spot, extremes["extremes_charges"])
            | _greeks(figures, found, snapshot, underlying))


def _order_rows(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract]) -> list:
    rows = []
    for stored in orders:
        o = stored.order
        identity = _identity(found[o.contract_id])  # refuses a contract with no stored row
        lot = found[o.contract_id].stored.listed.contract.lot_size
        lots = o.quantity // lot if lot > 0 and is_lot_aligned(o.quantity, lot) else None  # ADR-330 (23)
        rows.append({"id": stored.id, "placed_at": o.placed_at, "side": o.side, "contract_id": o.contract_id,
                     "contract_text": describe_contract(identity), "quantity": o.quantity, "lots": lots,
                     "price": o.price, "price_text": price_text(o.price), "kind": o.kind,
                     "reason_text": restore_order_reason(o.reason)})
    return rows


def _charges(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],
             underlying: str, rates: ChargeRates | None) -> dict:
    """The strategy's Charges (ofo.charges.paper_charges), shown rounded up to the paisa; absent with its reason."""
    fills = [PaperFill(o.order.kind, o.order.side, o.order.quantity, o.order.price,
                       _identity(found[o.order.contract_id])[1] is not Instrument.FUT) for o in orders]
    shown, why = paid_charges(fills, underlying, rates)
    if shown is None:
        return {"charges": None, "charges_text": None, "charges_reason": why, "charges_reason_text": reason_text(why)}
    return {"charges": shown, "charges_text": render_explanation(PAPER_CHARGES, amount=shown), "charges_reason": None,
            "charges_reason_text": None}


def paid_exact_of(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],
                  underlying: str, rates: ChargeRates | None) -> Decimal | None:
    """The EXACT charges paid on every stored order (``paper_charges(...).total``, not yet rounded); None when no rates
    are set or an order cannot be priced. ``shown`` of the same call is the Charges figure."""
    if rates is None or not orders:
        return None
    fills = [PaperFill(o.order.kind, o.order.side, o.order.quantity, o.order.price,
                       _identity(found[o.order.contract_id])[1] is not Instrument.FUT) for o in orders]
    try:
        return paper_charges(fills, underlying, rates).total
    except ChargesNotComputable:
        return None


def paid_charges(fills: Sequence[PaperFill], underlying: str,
                 rates: ChargeRates | None) -> tuple[Decimal | None, ChargesReason | None]:
    """The charges already paid on ``fills`` (ofo.charges.paper_charges), shown rounded up; (None, reason) when no rates
    are set or an order cannot be priced."""
    if rates is None:
        return None, RATES_UNAVAILABLE
    try:
        return paper_charges(list(fills), underlying, rates).shown, None
    except ChargesNotComputable:
        return None, NOT_PRICED


def terms_of(orders: Sequence[paper_store.StoredOrder],
             found: dict[int, tracked_contracts.TrackedContract]) -> dict[str, ContractTerms]:
    """The instrument, strike and expiry of every contract the orders touch, keyed by the engine's instrument id."""
    out = {}
    for cid in {o.order.contract_id for o in orders}:
        _, instrument, strike, expiry = _identity(found[cid])
        out[str(cid)] = ContractTerms(instrument, strike, expiry)
    return out


def after_charges_fields(got: BookAfterCharges) -> dict:
    """The reply fields of one ``BookAfterCharges`` (shared by the paper book, tracking and the history routes)."""
    reason = got.reason
    return {"total_after": _exact(got.total_after), "total_after_text": _signed(got.total_after),
            "charges_paid": _exact(got.paid), "charges_paid_text": _paid_text(got.paid),
            "charges_to_close": _exact(got.open_exit),
            "charges_to_close_text": None if got.open_exit is None else render_explanation(PAPER_CHARGES,
                                                                                            amount=got.open_exit),
            "after_charges_reason": reason, "after_charges_reason_text": reason_text(reason)}


def _paid_text(paid: Decimal | None) -> str | None:
    """The sentence beside Charges paid: the same form as ``charges_to_close_text`` (one catalogue entry)."""
    return None if paid is None else render_explanation(PAPER_CHARGES, amount=paid)


def after_charges(view: Any, terms: Mapping[str, ContractTerms], live: Mapping[str, Decimal],  # noqa: PLR0913
                  paid: Decimal | None, paid_reason: str | None, underlying: str,
                  rates: ChargeRates | None) -> BookAfterCharges:
    """The one after-charges total of a book view: ``paid`` is the shown Charges (None + its reason when absent)."""
    open_exit, exit_reason = open_exit_charges(view, terms, live, underlying, rates)
    return book_after_charges(view, paid, open_exit, paid_reason if paid is None else exit_reason)


def split_fields(got: AfterSplit) -> dict:
    """The reply fields of Booked after / Unbooked after (paper book, list and tracking)."""
    return {"booked_after": _exact(got.booked_after), "booked_after_text": _signed(got.booked_after),
            "booked_after_reason": got.booked_reason, "booked_after_reason_text": reason_text(got.booked_reason),
            "unbooked_after": _exact(got.unbooked_after), "unbooked_after_text": _signed(got.unbooked_after)}


def left_fields(got: AfterSplit) -> dict:
    """The reply fields of Profit left / Loss left after charges and ``recover``."""
    out = {"recover": _exact(got.recover), "recover_text": _signed(got.recover)}
    for name, value in (("profit_left_after", got.profit_left_after), ("loss_left_after", got.loss_left_after)):
        out[name], out[f"{name}_text"] = _extreme(value)
    return out


def _after(orders: Sequence[paper_store.StoredOrder], found: dict[int, tracked_contracts.TrackedContract],  # noqa: PLR0913
           prices: dict[int, paper.Price], charges: dict, underlying: str, rates: ChargeRates | None) -> dict:
    money = strategy_money_view(_paper(orders), prices)
    live, view = money.live, money.book
    terms = terms_of(orders, found)
    got = after_charges(view, terms, live, charges["charges"], charges["charges_reason"], underlying, rates)
    split = after_split(view, terms, live, underlying, rates, got, paid_exact_of(orders, found, underlying, rates))
    return after_charges_fields(got) | split_fields(split) | left_fields(split)


async def _load_strategy(db: Any, user_ref: str, strategy_id: int):
    try:
        return await store.load(db, user_ref, strategy_id)
    except store.StrategyStoreError as exc:
        raise refused_answer(exc, 409) from None


async def _book(db: Any, stored: Any, orders: Sequence[paper_store.StoredOrder],  # noqa: PLR0913
                ctx: MarketContext | None, feed: LiveFeed | None, answered_at: datetime.datetime,
                rates: ChargeRates | None = None) -> PaperBookOut:
    ids = sorted({o.order.contract_id for o in orders})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    open_ids = _open_ids(orders)
    connected = _connected(ctx)
    underlying = stored.saved.definition.underlying  # fixed for the strategy's life
    snapshot = None
    keys = [k for k in (found[c].feed_key for c in open_ids) if k is not None]
    if connected and keys:
        await release_connection(db)  # D-36 (c): the feed hold below waits up to FORWARD_WAIT_S
        snapshot = await _snapshot(ctx, feed, underlying, keys)  # type: ignore[arg-type]
    prices = _prices(open_ids, found, snapshot)
    base = _figures(orders, found, prices, connected, _book_day(snapshot, answered_at))
    charges = _charges(orders, found, underlying, rates)
    figures = (base | _summary(orders, found, prices, base, snapshot, underlying, exited_absent=False, rates=rates)
               | charges | _after(orders, found, prices, charges, underlying, rates))
    figures |= await settle_line_after_close(db, answered_at, figures)
    figures["plan_final_text"] = await _plan_final(db, stored, orders, figures, _book_day(snapshot, answered_at))
    return PaperBookOut.model_validate(figures | {
        "strategy_id": stored.id, "name": sf.shown_name(stored.name), "underlying": underlying,
        "answered_at": answered_at, "orders": _order_rows(orders, found),
        "status_word": _paper_word(stored.status, figures["positions"]),
        "held": _held_out((await held_entry_store.read_many(db, [stored.id])).get(stored.id))})


async def _plan_final(db: Any, stored: Any, orders: Sequence[paper_store.StoredOrder], figures: Mapping[str, Any],
                      today: datetime.date) -> Any:
    """ADR-330 (57): the plan's final line of a fully closed book, else None. A failed read leaves the line out (the
    page then shows the closed sentence and the result alone, never a half line); the book reply never waits on it."""
    if figures.get("closed_text") is None:
        return None
    try:
        async with db.begin_nested():
            return await plan_ending.plan_final_text(db, stored.user_ref, stored.id, orders, today)
    except (SQLAlchemyError, ValueError):
        _LOG.error("plan final line of strategy %s left out", stored.id, exc_info=True)
        return None


@router.get("/paper/strategies/{strategy_id}", response_model=PaperBookOut)
async def get_paper_strategy(strategy_id: int,  # noqa: PLR0913 - FastAPI dependencies
                             db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                             ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                             feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                             now: Annotated[AnswerClock, Depends(get_answer_clock)],
                             rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> PaperBookOut:
    stored = await _load_strategy(db, user_ref, strategy_id)
    orders = await paper_store.load(db, strategy_id)
    if not orders:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    return await _book(db, stored, orders, ctx, feed, now(), rates)


@router.get("/paper/strategies", response_model=PaperListOut)
async def list_paper_strategies(db: Annotated[Any, Depends(get_db)],  # noqa: PLR0913 - FastAPI dependencies
                                user_ref: Annotated[str, Depends(current_user_ref)],
                                ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                                feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                                now: Annotated[AnswerClock, Depends(get_answer_clock)],
                                rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
                                shown_date: Annotated[datetime.date, Depends(get_shown_date)]) -> PaperListOut:
    """Every paper strategy of the signed-in user, newest first: fixed cost whatever the count (finding F-3): one orders
    query, one contract batch (two queries) and ONE market read per underlying for every open contract together."""
    books = await paper_store.load_all(db, user_ref)
    ids = sorted({o.order.contract_id for b in books for o in b.orders})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    connected = _connected(ctx)
    answered = now()
    keys: dict[str, list[str]] = {}
    for b in books:
        for cid in _open_ids(b.orders):
            key = found[cid].feed_key
            if key is not None and key not in keys.setdefault(b.underlying, []):
                keys[b.underlying].append(key)
    snapshots = {}
    if connected and keys:
        await release_connection(db)  # D-36 (c): the feed holds below wait; the session re-checks out afterwards
        for underlying, wanted in keys.items():
            snapshots[underlying] = await _snapshot(ctx, feed, underlying, wanted)  # type: ignore[arg-type]
    held_rows = await held_entry_store.read_many(db, [b.strategy_id for b in books])
    out, decays = [], []
    for b in sorted(books, key=_newest_first, reverse=True):
        snapshot = snapshots.get(b.underlying)
        prices = _prices(_open_ids(b.orders), found, snapshot)
        figures = _figures(b.orders, found, prices, connected, _book_day(snapshot, answered))
        summary = _summary(b.orders, found, prices, figures, snapshot, b.underlying, exited_absent=True, rates=rates)
        decays.append(_decay(figures, found, snapshot, b.underlying))
        open_legs = sum(1 for p in figures["positions"] if p["net_quantity"] != 0)
        charges = _charges(b.orders, found, b.underlying, rates)
        figures |= charges | summary | _after(b.orders, found, prices, charges, b.underlying, rates)
        figures |= await settle_line_after_close(db, answered, figures)
        out.append(figures | {"strategy_id": b.strategy_id, "name": sf.shown_name(b.name), "underlying": b.underlying,
                              "held": _held_out(held_rows.get(b.strategy_id)),
                              "status_word": _paper_word(b.status, figures["positions"]),
                              "open_count": open_legs, "position_count": len(figures["positions"])})
    live = [i for i, s in enumerate(out) if not _expired_open(s)]  # D-40: not expired
    kept = _priced(live, [out[i] for i in live], booked_alone=True)  # AC-R06 (ADR-324), ADR-330 (62)
    expired = len(out) - len(live)
    totals = _totals([out[i] for i in kept], [decays[i] for i in kept], expired, len(live) - len(kept),
                     sum(1 for s in out if s["open_count"] == 0 or s["state"] == "EXITED"))  # ADR-330 (15)
    sorted_books = sorted(books, key=_newest_first, reverse=True)
    day = today_day([snapshots.get(b.underlying) for b in sorted_books], answered)
    today = today_totals([_today_item(out[i], decays[i], sorted_books[i]) for i in live], day)
    return PaperListOut.model_validate({"strategies": out, "totals": totals, "today": today, "answered_at": now(),
                                       "shown_date": shown_date})


async def settle_line_after_close(db: Any, now: datetime.datetime, figures: Mapping[str, Any]) -> dict[str, Any]:
    """D-64: the line that replaces the raw "prices not live" / "cannot be used: expired" texts after the 15:30 close,
    while a leg expiring today is still open (the settlement at ``facts.paper_settle_from`` closes it). The market clock
    is ``ofo.market_calendar``; the legs are the book's own open positions."""
    from ofo_app import settings_store  # noqa: PLC0415 - one read, only when the clock says after close
    today = now.astimezone(IST).date()
    if not any(p["net_quantity"] != 0 and p["expiry"] == today for p in figures["positions"]):
        return {}
    settle_from = calc.paper_settle_from(await settings_store.settings_in_force(db))
    if not after_close_before_settlement(now, settle_from):
        return {}
    return {"after_close_text": render_explanation("market_closed_settles", time=settle_from),
            "unpriced_text": None}


def _expired_open(strategy: Mapping[str, Any]) -> bool:
    """D-40 (ADR-324): an open leg is on an expired contract (ADR-311: retired, or its expiry is past)."""
    return bool(strategy["expired_open"])


def _paper_word(status: str, positions: Sequence[Mapping[str, Any]]) -> str:
    """ADR-299 (1), D-28: a paper book has orders, so it is Running while at least one leg is open and Completed once
    every leg is closed, even before the strategy row is marked closed. An unknown status stays Unknown."""
    word = store.status_word(status, True)
    return word if word == "Unknown" or any(p["net_quantity"] != 0 for p in positions) else "Completed"


async def current_legs_many(db: Any, user_ref: str) -> dict[int, dict[str, Any]]:
    """GC-ICLIVE D-42 (ADR-299): per strategy with a paper book, the CURRENT legs and the status word, from the book
    the Positions page reads (open positions; a book with nothing open names the legs it traded) and the same
    ``_paper_word`` as the paper list. ``leg_count`` and ``first_leg`` replace the saved definition's legs on the My
    Strategies list; a strategy without a book is absent here (its saved legs stand).
    A book whose contract no longer resolves degrades
    only its own row: ``current_legs_text`` says so and the saved legs stand."""
    books = await paper_store.load_all(db, user_ref)
    found = {c.contract_id: c for c in await tracked_contracts.resolve(
        db, sorted({o.order.contract_id for b in books for o in b.orders}))}
    out: dict[int, dict[str, Any]] = {}
    for b in books:
        positions = net_positions(_paper(b.orders), {}).positions
        legs = [p for p in positions if p.net_quantity != 0] or list(positions)
        try:
            _, instrument, strike, expiry = _identity(found[int(legs[0].instrument_id)])
        except (KeyError, RuntimeError):
            out[b.strategy_id] = {"current_legs_text": render_explanation("current_legs_unreadable")}
            continue
        out[b.strategy_id] = {
            "leg_count": len(legs),
            "first_leg": {"instrument": instrument.value, "strike": None if strike is None else str(strike),
                          "expiry": expiry.isoformat()},
            "status_word": _paper_word(b.status, [{"net_quantity": p.net_quantity} for p in positions])}
        if out[b.strategy_id]["status_word"] == "Completed":
            # D-66: the close time is the last closing fill or settlement record of the book, never the last save
            out[b.strategy_id]["closed_at"] = max((o.order.placed_at for o in b.orders
                                                    if o.order.kind in paper_store.REDUCING_KINDS), default=None)
    return out


def _newest_first(book: paper_store.UserBook) -> tuple[datetime.datetime, int]:
    """The sort key of the list (reversed): the book's first order time, then the strategy id."""
    return min(o.order.placed_at for o in book.orders), book.strategy_id


def _decay(figures: dict, found: dict[int, tracked_contracts.TrackedContract], snapshot: Any,
           underlying: str) -> paper_decay.Decay:
    """One book's Decay (ofo.tracking.paper_decay): absent with the book's pause reason when an open contract is not
    live; a fully exited book decays 0."""
    if figures["unbooked"] is None:
        return paper_decay.Decay(None, figures["pause_reason"] or paper.PRICES_NOT_LIVE)
    contracts = [paper_decay.OpenContract(found[p["contract_id"]].feed_key or "", Instrument(p["instrument"]),
                                          p["strike"], p["expiry"], p["net_quantity"], p["ltp"])
                 for p in figures["positions"] if p["net_quantity"] != 0]
    return paper_decay.book_decay(snapshot, underlying, contracts)


def _priced(keys: Sequence[Any], strategies: Sequence[Mapping[str, Any]], booked_alone: bool = False) -> list[Any]:
    """AC-R06 / N-46 (ADR-324 (1) to (3)): the members of ``keys`` (parallel to ``strategies``) that CAN be priced, i.e.
    whose unbooked figure is present (a fully exited or settled book is). A strategy with no live price never pauses
    the whole total: it is left out and counted. When NONE can be priced the figure stays absent with its reason
    (every member kept), as before."""
    priced = [(k, s) for k, s in zip(keys, strategies, strict=True) if s["unbooked"] is not None]
    # ADR-330 (62) (amends (35); the HEADER total only, ``booked_alone``): a fully exited or settled
    # book has a booked result and needs no price, so when no running book can be priced the total is that booked result
    # and the unpriced ones are counted; absent with its reason only when NOTHING can be priced (every member stays).
    # Without ``booked_alone`` (the Today total, D-68, which has no left-out line on screen) the old rule stands: at
    # least one book with an open leg must be priced, else the figure is absent with its reason.
    if booked_alone:
        return [k for k, _ in priced] if priced else list(keys)
    return [k for k, _ in priced] if any(s["open_count"] for _, s in priced) else list(keys)


def _totals(strategies: Sequence[dict], decays: Sequence[paper_decay.Decay], expired: int = 0,
            unpriced: int = 0, closed: int = 0) -> dict:
    """The exact sums over every strategy that can be priced (the ``expired`` and ``unpriced`` ones left out are only
    counted, in one line). ``closed`` is the number of closed strategies the whole-paper total keeps (ADR-330 (15)).
    Unbooked and total are absent with the first absent strategy's reason, and Decay with the first absent book's
    reason: never a partial sum shown as a total (REQ-109 AC-5)."""
    got = book_totals([(s["booked"], s["unbooked"]) for s in strategies], [d.value for d in decays])
    paused = next((s for s in strategies if s["unbooked"] is None), None)
    missing = next((d for d in decays if d.value is None), None)
    booked, unbooked, total, decay = got.booked, got.unbooked, got.total, got.decay
    totals_reason = None if paused is None else (paused["pause_reason"] or paper.PRICES_NOT_LIVE)
    decay_reason = None if missing is None else missing.reason
    times = [s["as_of"] for s in strategies if s["unbooked"] is None and s.get("as_of") is not None]
    return {"totals_as_of": min(times) if times else None,
            "booked": _exact(booked), "booked_text": _signed(booked), "unbooked": _exact(unbooked),
            "unbooked_text": _signed(unbooked), "total": _exact(total), "total_text": _signed(total),
            "totals_reason": totals_reason, "totals_reason_text": reason_text(totals_reason),
            "decay": decay, "decay_text": _signed(decay), "decay_reason": decay_reason,
            "decay_reason_text": reason_text(decay_reason),
            "left_out_count": expired + unpriced, "left_out_text": _left_out_text(expired, unpriced),
            "closed_count": closed, "closed_text": _closed_text(closed),
            **_charges_total(strategies), **_after_total(strategies)}


@dataclass(frozen=True)
class TodayItem:
    """One strategy for the Today total: its figures (as the list builds them), decay, first and closing order times and
    its scenario marker. ``closed`` is None while any leg is open."""
    figures: dict
    decay: paper_decay.Decay
    opened: datetime.datetime
    closed: datetime.datetime | None
    scenario_id: str | None


def _today_item(figures: dict, decay: paper_decay.Decay, book: paper_store.UserBook) -> TodayItem:
    times = [o.order.placed_at for o in book.orders]
    return TodayItem(figures, decay, min(times), max(times) if figures["open_count"] == 0 else None, book.scenario_id)


def today_day(snapshots: Sequence[Any], answered: datetime.datetime) -> datetime.date:
    """D-68: "the current trading day in IST": the India date of the newest market snapshot (``_book_day``'s rule,
    so on a weekend or holiday it is the last session's day); with no snapshot, the answer's own India date."""
    days = [_today(s) for s in snapshots if s is not None]
    return max((d for d in days if d is not None), default=answered.astimezone(paper.IST).date())


def today_totals(items: Sequence[TodayItem], day: datetime.date) -> dict:
    """D-68 (ADR-320 point 6): the sums of ``_totals`` (the function the header already reads, so one reader; exact
    Decimal) over the REAL strategies opened or closed on ``day`` (the India date). A scenario strategy is left out;
    so is a trade opened on an earlier day that is still open or was closed on an earlier day. A paused strategy
    pauses the figure
    (REQ-109 AC-5: absent with the reason, never partial). Nothing today: count 0 and the sentence, no figure."""
    def on_day(at: datetime.datetime | None) -> bool:
        return at is not None and at.astimezone(paper.IST).date() == day
    chosen = [x for x in items if x.scenario_id is None and (on_day(x.opened) or on_day(x.closed))]
    kept = _priced(chosen, [x.figures for x in chosen])  # AC-R06: ADR-324's rule, not (62): Today has no left-out line
    out = _totals([x.figures for x in kept], [x.decay for x in kept], 0, len(chosen) - len(kept))
    return out | {"count": len(chosen), "empty_text": None if chosen else render_explanation("paper_today_none")}


def _left_out_text(expired: int, unpriced: int) -> Any:
    """The count line of the header (ADR-324 (1)): the reason is expiry, no live price, or both."""
    count = expired + unpriced
    if count == 0:
        return None
    if expired and unpriced:
        return render_explanation("paper_totals_left_out_mixed", count=count)
    if expired:
        return render_explanation("paper_totals_left_out_one") if count == 1 else render_explanation(
            "paper_totals_left_out_many", count=count)
    return render_explanation("paper_totals_left_out_unpriced_one") if count == 1 else render_explanation(
        "paper_totals_left_out_unpriced_many", count=count)


def _closed_text(count: int) -> Any:
    """P11: the sentence saying how many closed strategies the Paper totals include; absent when none."""
    if count == 0:
        return None
    return render_explanation("paper_totals_closed_one") if count == 1 else render_explanation(
        "paper_totals_closed_many", count=count)


def _after_total(strategies: Sequence[dict]) -> dict:
    """The sum of every strategy's after figure (ofo.engine.extremes_charges.sum_after_charges): absent with the first
    absent strategy's reason, never partial."""
    got = sum_after_charges([BookAfterCharges(s["total"], s["total_after"], s["charges_paid"], s["charges_to_close"],
                                              s["after_charges_reason"]) for s in strategies])
    unbooked = None if any(s["unbooked_after"] is None for s in strategies) else sum(
        (Decimal(s["unbooked_after"]) for s in strategies), Decimal(0))  # never a partial sum
    booked, booked_why = sum_booked_after([
        (None if s["booked_after"] is None else Decimal(s["booked_after"]),
         s.get("booked_after_reason") or s["after_charges_reason"]) for s in strategies])
    return {"total_after": _exact(got.total_after), "total_after_text": _signed(got.total_after),
            "booked_after": _exact(booked), "booked_after_text": _signed(booked),
            "booked_after_reason": booked_why, "booked_after_reason_text": reason_text(booked_why),
            "unbooked_after": _exact(unbooked), "unbooked_after_text": _signed(unbooked),
            "charges_paid": _exact(got.paid), "charges_paid_text": _paid_text(got.paid),
            "charges_to_close": _exact(got.open_exit),
            "charges_to_close_text": None if got.open_exit is None else render_explanation(PAPER_CHARGES,
                                                                                            amount=got.open_exit),
            "after_charges_reason": got.reason, "after_charges_reason_text": reason_text(got.reason)}


def _charges_total(strategies: Sequence[dict]) -> dict:
    """The sum of every strategy's shown Charges; absent with the first absent strategy's reason (never partial)."""
    total = charges_sum([s["charges"] for s in strategies])
    reason = next((s["charges_reason"] for s in strategies if s["charges"] is None), None)
    text_ = None if total is None else render_explanation(PAPER_CHARGES, amount=total)
    return {"charges": _exact(total), "charges_text": text_,
            "charges_reason": reason, "charges_reason_text": reason_text(reason)}


def _check_price(price: Decimal) -> None:
    """REQ-109 AC-1: above 0, a multiple of 0.05, within the column (the reason text is the catalogue's)."""
    if not is_typed_price(price):
        raise StrategyRefused("paper_price_invalid")


async def _server_exit_prices(ctx: MarketContext | None, feed: LiveFeed | None, underlying: str,
                              orders: Sequence[Any], state: Mapping[int, tracked_contracts.TrackedContract]
                              ) -> dict[int, Decimal]:
    """C10 (REQ-109 AC-4, ADR-008): order index -> the price the SERVER reads now for every `exit` order: the
    live price of that leg's OWN contract (``feed_key``; ``paper.leg_price``; ADR-212: never a closing price, an
    after-hours fill is refused before this runs). Answer states: no exit -> {} and no read; no market context ->
    tracking_not_connected; a contract not live (token reassigned, delisted, retired, missing) ->
    tracking_exit_contract_not_live; a leg with no live price (missing, failed read) ->
    tracking_exit_prices_not_live; nothing is written on any refusal. The browser's price is never used."""
    exits = [(i, state[o.contract_id]) for i, o in enumerate(orders) if o.kind == "exit"]
    if not exits:
        return {}
    keys = [c.feed_key for _, c in exits]
    # the one live exit read (paper_exit.live_exit_prices): the refusals and their order are the ones named above
    live = await paper_exit.live_exit_prices(
        ctx, feed, underlying, [None] if None in keys else sorted(set(keys)))  # type: ignore[type-var]
    if isinstance(live, may_act.Refused):
        may_act.require(live)
    return {i: live[c.feed_key].price for i, c in exits}  # type: ignore[index, misc] - priced: price set


async def entry_facts(ctx: MarketContext | None, underlying: str, orders: Sequence[Any],
                      state: Mapping[int, tracked_contracts.TrackedContract]) -> EntryFacts | None:
    """ADR-243 + ADR-270 (1): the entry facts this fill would store if it is the strategy's first
    (``paper_store.place`` decides), through the one first-fill reader ``adjustment_readers.entry_facts_now``: the
    index's live spot now, each side's sold strike among the opening orders and the entry ATM IV. Answer states: not
    connected, no quote, or a quote that is not a positive price -> None (nothing stored; "Entry distance" then refuses
    this strategy's rolls by name, never a guessed spot); no IV readable -> the facts with no IV."""
    from ofo_app.adjustment_readers import entry_facts_now  # noqa: PLC0415 - the readers import the route layer
    sold = [state[o.contract_id].stored.listed.contract for o in orders  # type: ignore[union-attr] - resolved above
            if o.side == "SELL" and o.kind != "exit"]
    return await entry_facts_now(ctx, underlying, sold)


async def _record_held(db: Any, strategy_id: int, held: HeldIn | None) -> None:
    if held is not None:
        await held_entry_store.record(db, strategy_id, held.entry_at, held.broker)


def _check_held(held: HeldIn | None, first: bool, orders: Sequence[Any], state: Mapping[int, Any],
                placed_at: datetime.datetime) -> None:
    """ADR-292 (2): a held entry is the first basket and all `open`; its time is not after now and not after the
    earliest leg expiry (its date in IST). Refused by name; nothing is stored. No held block: nothing to check."""
    if held is None:
        return
    if not first or any(o.kind != "open" for o in orders):
        raise StrategyRefused("held_entry_not_a_first_open_basket")
    if held.entry_at > placed_at:
        raise StrategyRefused("held_entry_later_than_now")
    earliest = min(state[o.contract_id].stored.listed.contract.expiry for o in orders)
    if held.entry_at.astimezone(IST).date() > earliest:
        raise StrategyRefused("held_entry_after_expiry", message=render("held_entry_after_expiry", expiry=earliest))


def _refuse_duplicate_legs(underlying: str, orders: Sequence[PaperOrderIn], state: Mapping[int, Any]) -> None:
    """ADR-319 (3): two opening orders on one contract and side are a kept duplicate leg; refused with the gate's own
    sentence (engine.duplicate_leg.paper_duplicate_leg). A buy and a sell of one contract stay two legs (REQ-030
    AC-11). Exits never count."""
    legs = []
    for o in orders:
        if o.kind == "exit":
            continue
        c = state[o.contract_id].stored.listed.contract
        legs.append(Leg(Action(o.side), Instrument(c.instrument_type), c.strike, c.expiry, o.quantity, o.price))
    failure = paper_duplicate_leg(legs, underlying)
    if failure is not None:
        raise StrategyRefused("gate_duplicate_leg", message=failure)


async def _refuse_take_profit_at_loss(db: Any, user_ref: str, strategy_id: int, approach_id: str,  # noqa: PLR0913
                                      ctx: MarketContext | None, rates: ChargeRates | None,
                                      tracked_reader: TrackedReader) -> None:
    """ADR-326 (1): the preferences and the default roll basis are read here only for a Take profit (the basis is not
    used by A-24 / A-25), then ``adjustment.refuse_take_profit_at_loss`` asks the offer's own build path."""
    from ofo.adjustment.preferences import from_values  # noqa: PLC0415 - only a Take profit basket needs it

    from ofo_app import adjustment_check as check  # noqa: PLC0415 - it imports the route layer
    from ofo_app.routes.adjustment import refuse_take_profit_at_loss  # noqa: PLC0415 - as above
    from ofo_app.user_preferences_store import values_for  # noqa: PLC0415 - as above
    prefs = from_values(await values_for(db, user_ref))
    await refuse_take_profit_at_loss(approach_id, strategy_id, tracked_reader, ctx,
                                     rates if isinstance(rates, ChargeRates) else None, prefs,
                                     check.basis_in_force(None, None, None))


@router.post("/paper/strategies/{strategy_id}/orders", status_code=201, response_model=PaperBookOut,
             dependencies=[Depends(guard_paper_order)])  # IC e2e 5: scenario mode = own scenario only
async def place_paper_orders(strategy_id: int, body: PaperOrdersIn,  # noqa: PLR0913, C901 - FastAPI dependencies
                             db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                             ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                             feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                             now: Annotated[AnswerClock, Depends(get_answer_clock)],
                             rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
                             tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
                             settings: Annotated[Mapping[str, Decimal], Depends(get_calc_settings)]) -> PaperBookOut:
    stored = await _load_strategy(db, user_ref, strategy_id)
    for order in body.orders:
        if order.kind != "exit" and order.price > 0:  # C10: exit prices are the server's; 0 or less: below
            _check_price(order.price)
    contracts = await tracked_contracts.resolve(db, sorted({o.contract_id for o in body.orders}))
    state = {c.contract_id: c for c in contracts}
    for order in body.orders:  # Lane K item 4 (T3-13): a price of 0 or below is refused naming the leg
        if order.kind != "exit" and order.price <= 0 and state[order.contract_id].stored is not None:
            raise StrategyRefused("paper_entry_price_not_above_zero", message=render(
                "paper_entry_price_not_above_zero", contract=display_contract(_identity(state[order.contract_id]))))
    # a contract unknown to the catalogue never reaches the store; a new position needs a live contract (an exit of one
    # that expired is allowed: it only closes what is open)
    if any(state[o.contract_id].stored is None or (o.kind != "exit" and state[o.contract_id].state != "live")
           for o in body.orders):
        raise StrategyRefused("paper_contract_not_tradable")
    _refuse_duplicate_legs(stored.saved.definition.underlying, body.orders, state)  # ADR-319 (3)
    if body.approach_id is not None:  # ADR-326 (1): the offer's own build path decides, before any price read
        await _refuse_take_profit_at_loss(db, user_ref, strategy_id, body.approach_id, ctx, rates, tracked_reader)
    placed_at = now()
    may_act.refuse_unless_allowed(ctx, "place", placed_at)  # ADR-212: before any price read
    await release_connection(db)  # only reads so far (the strategy row lock is taken in place_checked, below)
    exit_prices = await _server_exit_prices(ctx, feed, stored.saved.definition.underlying, body.orders, state)
    # only a strategy with no paper order yet can be at its first fill (a book never shrinks): a later fill reads no IV
    first = not await paper_store.tracked_ids(db, [strategy_id])
    _check_held(body.held, first, body.orders, state, placed_at)
    entry = await entry_facts(ctx, stored.saved.definition.underlying, body.orders, state) if first else None
    try:
        book = await paper_limit.place_checked(
            db, user_ref, strategy_id, [
                paper_store.NewOrder(o.contract_id, o.side, o.quantity, exit_prices.get(i, o.price), o.kind, placed_at)
                for i, o in enumerate(body.orders)],
            entry=entry, ctx=ctx, at=placed_at, reader=tracked_reader, rates=rates,
            settings=settings)  # ADR-243: entry only if first fill; the size check is the door's (Lane K)
        # #774: a leg stop whose contract this basket closes (a move: exit A + add A') goes now, in this transaction,
        # exactly as the confirm list said; nothing is re-pointed (its premium level means another thing on A')
        for gone in paper_leg_stops.leaving(
                [r.trigger for r in await paper_trigger_store.list_for(db, strategy_id) if _state(r) == "armed"],
                _open_ids(book)):
            await paper_trigger_store.cancel(db, strategy_id, gone.id)
        new_ids = [o.id for o in book][-len(body.orders):]  # place inserts in order under the strategy's row lock
        for suggestion_id in dict.fromkeys(body.suggestion_ids):  # REQ-163 AC-1: same transaction, or nothing
            await playbook_store.link_orders(db, user_ref, strategy_id, suggestion_id, new_ids,
                                           body.basket_legs)
        # ADR-283 (1): the market at this basket's fill = every rule's starting point, in this transaction
        from ofo_app.adjustment_readers import record_basket_facts  # noqa: PLC0415 - the readers import the routes
        await record_basket_facts(db, ctx, feed, strategy_id, (
            stored.saved.definition.underlying, book, placed_at,
            {o.contract_id: exit_prices.get(i, o.price) for i, o in enumerate(body.orders)},
            body.prices_not_live_confirmed))
        if body.held is not None and len(book) != len(body.orders):  # the store's own first-fill view, under its lock
            raise StrategyRefused("held_entry_not_a_first_open_basket")  # rolled back below: nothing stored
        await _record_held(db, strategy_id, body.held)  # ADR-292: the held row and its first basket: one transaction
        await db.commit()
    except store.StrategyStoreError as exc:
        await db.rollback()
        if exc.code == paper_store.EXIT_EXCEEDS_OPEN:
            raise StrategyRefused("paper_exit_exceeds_open") from None
        if exc.code in _LINK_REFUSAL:
            raise StrategyRefused(exc.code, _LINK_REFUSAL[exc.code], message=render(exc.code)) from None
        raise refused_answer(exc, 409) from None
    except Exception:
        await db.rollback()
        raise
    return await _book(db, stored, await paper_store.load(db, strategy_id), ctx, feed, placed_at, rates)


class ExitRiskOut(ApiModel):
    """ADR-256: the answer for a prepared basket in three states (``no`` only when proven), the book's Max Loss before /
    after when the answer is yes and they are known, and the one factual warning line."""
    state: Literal["yes", "no", "cannot_tell"]
    max_loss_before: Extreme
    max_loss_after: Extreme
    warning_text: CatalogueText | None
    #: ADR-330 (55): a leg stop that leaves a sold option bare answers three lines, each its own fact, built here (the
    #: page prints them as sent); ``warning_text`` is the same lines joined by newlines. None for every other answer.
    warning_lines: list[CatalogueText] | None = None


_UNPRICED = Decimal("0.05")  # placeholder order price only; the engine is told priced=False


def _exit_risk_answer(state: Literal["yes", "no", "cannot_tell"]) -> ExitRiskOut:
    return ExitRiskOut(state=state, max_loss_before=None, max_loss_after=None, warning_text=None)


def _stop_line(before: Decimal, after: Decimal | str) -> str:
    """ADR-330 (6): "If this stop fires, max loss becomes Rs X (now Rs Y)." A figure is negative for a loss; a figure
    that is >= 0 is a profit and has its own sentence (never abs). Unlimited after: no fixed maximum."""
    if after == "unlimited":
        return (render_explanation("paper_leg_stop_unlimited_from_profit", before=before) if before >= 0
                else render_explanation("paper_leg_stop_unlimited_loss", before=-before))
    figure = Decimal(after)
    if before >= 0 and figure >= 0:
        return render_explanation("paper_leg_stop_still_profit", before=before, after=figure)
    if before >= 0:
        return render_explanation("paper_leg_stop_from_profit", before=before, after=-figure)
    if figure >= 0:
        return render_explanation("paper_leg_stop_to_profit", before=-before, after=figure)
    return render_explanation("paper_leg_stop_widens_loss", before=-before, after=-figure)


def leg_stop_lines(risk: ExitRisk, names: Mapping[str, Any], terms: Mapping[str, Any],
                   underlying: str, at_zero: Decimal | None = None) -> list[Any] | None:
    """ADR-330 (55), ADR-008: the three lines for a stop that leaves a sold option bare, from the engine's figures
    (Decimal, never computed in the page). None when no sold option is left bare (the one-line sentence applies).
    The case the figure stands for is named only when it is true: "worst case: <index> at zero" when the engine's
    P&L at zero (``at_zero``) IS the max loss then; "no upper limit" when the engine's figure is unlimited (a sold
    call left bare); any other loss prints its amount with no case named. A figure the engine did not give prints no
    number. ``underlying`` is the trade's own index (NIFTY or SENSEX), never a literal."""
    if not risk.exposed:
        return None
    legs = [names[i] for i in risk.exposed]
    joined = legs[0]
    for other in legs[1:]:
        joined = render_explanation("paper_alert_legs", rest=joined, leg=other)
    first = (render_explanation("paper_leg_stop_bare_one", leg=joined) if len(legs) == 1
             else render_explanation("paper_leg_stop_bare_many", legs=joined))
    before, after = risk.max_loss_before, risk.max_loss_after
    if before is UNLIMITED:
        now = render_explanation("paper_leg_stop_now_unlimited")
    elif not isinstance(before, Decimal):
        now = render_explanation("paper_leg_stop_now_unknown")
    elif before >= 0:
        now = render_explanation("paper_leg_stop_now_profit", amount=before)
    else:
        now = render_explanation("paper_leg_stop_now_loss", amount=-before)
    if after is UNLIMITED:
        then = render_explanation("paper_leg_stop_then_unlimited", index=underlying)
    elif not isinstance(after, Decimal):
        then = render_explanation("paper_leg_stop_then_unknown")
    elif after >= 0:
        then = render_explanation("paper_leg_stop_then_profit", amount=after)
    elif at_zero == after:
        then = render_explanation("paper_leg_stop_then_zero", amount=-after, index=underlying)
    else:
        then = render_explanation("paper_leg_stop_then_loss", amount=-after)
    return [first, now, then]


def _exit_warning(risk: ExitRisk, names: Mapping[str, Any], leg_stop: bool = False,  # noqa: PLR0913
                  terms: Mapping[str, Any] | None = None, underlying: str = "",
                  at_zero: Decimal | None = None) -> ExitRiskOut:
    """The yes answer says only what is known: the Max Loss figures (the catalogue's "No fixed maximum" when unlimited)
    when the engine gave them, and the sold legs left with less cover. Nothing known to say -> cannot_tell.
    ``leg_stop``: the figures are worded as the leg-stop line (ADR-330 (6)) instead of the exit confirmation's."""
    if leg_stop and risk.exposed and terms is not None and underlying:  # ADR-330 (55): the three lines
        three = leg_stop_lines(risk, names, terms, underlying, at_zero)
        if three is not None:
            (before, _), (after, _) = _extreme(risk.max_loss_before), _extreme(risk.max_loss_after)
            return ExitRiskOut(state="yes", max_loss_before=before, max_loss_after=after,
                               warning_text=render_explanation("paper_leg_stop_three_lines", first=three[0],
                                                               second=three[1], third=three[2]),
                               warning_lines=three)
    (before, before_text), (after, after_text) = _extreme(risk.max_loss_before), _extreme(risk.max_loss_after)
    lines = []
    if before is not None and after is not None:
        lines.append(_stop_line(before, after) if leg_stop else render_explanation(
            "paper_exit_widens_loss", before=before_text, after=after_text))
    if risk.exposed:
        legs_text = names[risk.exposed[0]]
        for other in risk.exposed[1:]:
            legs_text = render_explanation("paper_alert_legs", rest=legs_text, leg=names[other])
        lines.append(render_explanation("paper_exit_less_protected", legs=legs_text))
    if not lines:
        return _exit_risk_answer("cannot_tell")
    warning = lines[0] if len(lines) == 1 else render_explanation("paper_exit_warning_join", first=lines[0],
                                                                  second=lines[1])
    return ExitRiskOut(state="yes", max_loss_before=before, max_loss_after=after, warning_text=warning)


@router.get("/paper/strategies/{strategy_id}/exit-risk", response_model=ExitRiskOut)
async def paper_exit_risk(strategy_id: int, orders: Annotated[str, Query(max_length=8000)],  # noqa: PLR0913
                          db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                          ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                          feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                          now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> ExitRiskOut:
    """Read only, nothing stored. The WHOLE prepared basket (exits and entries) is judged on the legs after all of it.
    Bad input is refused (422), an engine error is cannot_tell, never "no". When an exit price cannot be read the
    answer is judged without any Max Loss figure (never a stand-in price) and shows none."""
    stored = await _load_strategy(db, user_ref, strategy_id)
    try:  # the prepared orders as JSON, the same shape the order route takes
        basket = PaperOrdersIn.model_validate_json('{"orders":' + orders + "}").orders
    except ValueError:
        refuse_request(("query", "orders"), "invalid_orders")
    booked = await paper_store.load(db, strategy_id)
    if not booked:  # nothing is open: an exit is larger than what is open; a first basket leaves nothing unprotected
        return _exit_risk_answer("cannot_tell" if any(o.kind == "exit" for o in basket) else "no")
    state = {c.contract_id: c for c in await tracked_contracts.resolve(
        db, sorted({o.order.contract_id for o in booked} | {o.contract_id for o in basket}))}
    if any(state[o.contract_id].stored is None for o in basket):
        raise StrategyRefused("paper_contract_not_tradable")
    await release_connection(db)  # read-only route: the live exit read waits on the feed
    try:
        prices = await _server_exit_prices(ctx, feed, stored.saved.definition.underlying, basket, state)
    except StrategyRefused:
        prices = {}
    at = now()
    exits = sum(1 for o in basket if o.kind == "exit")
    terms = {}
    names = {}
    for cid, found in state.items():
        if found.stored is not None:
            _, instrument, strike, expiry = _identity(found)
            names[str(cid)] = describe_contract((stored.saved.definition.underlying, instrument, strike, expiry))
            terms[str(cid)] = ContractTerms(instrument, strike, expiry)
    try:
        legs = [PaperOrder(str(o.contract_id), o.side, o.quantity,
                           prices.get(i, _UNPRICED if o.kind == "exit" else o.price), o.kind, at)
                for i, o in enumerate(basket)]
    except ValueError:
        return _exit_risk_answer("cannot_tell")
    risk = exit_risk(_paper(booked), legs, terms, priced=len(prices) == exits)
    if risk.state != "yes":
        return _exit_risk_answer(risk.state)
    return _exit_warning(risk, names)


@router.get("/paper/strategies/{strategy_id}/leg-stop-risk", response_model=ExitRiskOut)
async def paper_leg_stop_risk(strategy_id: int, contract_id: Annotated[int, Query(gt=0, le=INTEGER_MAX)],  # noqa: PLR0913
                              level: Annotated[Decimal, Query(allow_inf_nan=False)],
                              db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                              now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> ExitRiskOut:
    """ADR-330 (6), read only, nothing stored, never blocks a save: what the book becomes if a stop on ``contract_id``
    fires at ``level``. The one-leg exit (the whole open quantity, the opposite side) is priced AT THE LEVEL, a given
    price and never a live read, and judged by the same ``exit_risk`` as the exit confirmation. Answer states: stated
    (yes, with the line) / no (proven not wider) / cannot_tell (the engine could not judge: no figure); another user's
    or a missing strategy -> 404; a level that is not above 0 and a multiple of 0.05, or a contract not open -> the
    save's own refusals (paper_trigger_level_invalid, paper_trigger_leg_not_open)."""
    stored = await _load_strategy(db, user_ref, strategy_id)
    if not is_typed_price(level):
        raise StrategyRefused("paper_trigger_level_invalid")
    booked = await paper_store.load(db, strategy_id)
    held = {p.instrument_id: p.net_quantity for p in net_positions(_paper(booked), {}).positions} if booked else {}
    if held.get(str(contract_id), 0) == 0:
        raise StrategyRefused("paper_trigger_leg_not_open")
    names, terms = await names_and_terms(db, stored.saved.definition.underlying, booked)
    net = held[str(contract_id)]  # the open quantity (signed); a key, not reply text
    return leg_stop_answer(booked, net, contract_id, level, names, terms, now(), stored.saved.definition.underlying)


async def names_and_terms(db: Any, underlying: str, booked: Sequence[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The shown name and engine terms of every contract the book holds (one reader for the routes and the monitor)."""
    found = {c.contract_id: c for c in await tracked_contracts.resolve(
        db, sorted({o.order.contract_id for o in booked}))}
    names: dict[str, Any] = {}
    terms: dict[str, Any] = {}
    for cid, one in found.items():
        if one.stored is not None:
            _, instrument, strike, expiry = _identity(one)
            # REQ-151: the screens' form ("NIFTY 1 Dec 25750 PE"), the same text the fired-stop body uses
            # (paper_monitor._contract_text); never the ISO record form (Lane M: "2028-12-01" read on screen 27 Nov)
            names[str(cid)] = display_contract((underlying, instrument, strike, expiry))
            terms[str(cid)] = ContractTerms(instrument, strike, expiry)
    return names, terms


def leg_stop_answer(booked: Sequence[Any], net: int, contract_id: int, level: Decimal,  # noqa: PLR0913
                     names: Mapping[str, Any], terms: Mapping[str, Any], at: datetime.datetime,
                     underlying: str) -> ExitRiskOut:
    """THE ADR-330 (6) answer for one leg stop (the route and the monitor's fired-stop message both call this, so the
    figure is computed one way): the one-leg exit of the whole open quantity ``net`` at ``level``."""
    # the close's side and quantity from the exit door's own rule (G2: no side flipped outside it); no order is built
    close = open_legs_to_close({str(contract_id): net})[0]
    try:
        leg = PaperOrder(str(close.key), close.side, close.quantity, level, "exit", at)
    except ValueError:
        return _exit_risk_answer("cannot_tell")
    risk = exit_risk(_paper(booked), [leg], terms, priced=True)
    if risk.state == "cannot_tell":
        return _exit_risk_answer("cannot_tell")
    # ADR-330 (6) has no threshold: the line shows whenever the engine prices both figures (ADR-256's "more than double"
    # is the exit confirmation's rule, whose figures exit_risk hides below it), so read the same engine's figures here
    at_zero = None
    try:
        loss0 = book_extremes(net_positions(_paper(booked), {}), terms, {}).max_loss
        after_view = net_positions([*_paper(booked), leg], {})
        loss1 = book_extremes(after_view, terms, {}).max_loss
        at_zero = book_pnl_at_zero(after_view, terms)
    except (ValueError, KeyError):
        loss0 = loss1 = None
    if risk.state == "yes" and risk.exposed:
        # ADR-330 (55): a bare sold option gets three lines from the engine's own figures as they are: an unlimited
        # or absent figure is said as such, never replaced by the exit judge's hidden ones
        risk = ExitRisk("yes", loss0, loss1, risk.exposed)
    elif isinstance(loss0, Decimal) and (loss1 is UNLIMITED or isinstance(loss1, Decimal)):
        risk = ExitRisk("yes", loss0, loss1, risk.exposed)
    elif risk.state != "yes":
        return _exit_risk_answer(risk.state)
    return _exit_warning(risk, names, leg_stop=True, terms=terms, underlying=underlying,
                         at_zero=at_zero)


def index_exit_answer(booked: Sequence[Any], exits: Mapping[int, Decimal], terms: Mapping[str, Any],
                      names: Mapping[str, Any], at: datetime.datetime) -> ExitRiskOut:
    """The same exit_risk / _exit_warning the exit confirmation uses, for an index exit that closes every open leg
    (``exits``: contract id -> the fill price). The confirmation's own rule: a line only when the engine says yes."""
    held = {p.instrument_id: p.net_quantity for p in net_positions(_paper(booked), {}).positions}
    try:
        legs = [PaperOrder(str(c.key), c.side, c.quantity, exits[int(c.key)], "exit", at)
                for c in open_legs_to_close({str(c): held[str(c)] for c in sorted(exits)})]
    except (ValueError, KeyError):
        return _exit_risk_answer("cannot_tell")
    risk = exit_risk(_paper(booked), legs, terms, priced=True)
    if risk.state != "yes":
        return _exit_risk_answer(risk.state)
    return _exit_warning(risk, names)


def _leg_name(state: Mapping[int, Any], stored: Any, trigger: Any) -> str:
    """The name of a leg stop's contract as the book words it; the bare id only if the contract row is unknown."""
    found = state.get(trigger.contract_id)
    if found is None or found.stored is None:
        return f"contract {trigger.contract_id}"
    _, instrument, strike, expiry = _identity(found)
    return display_contract((stored.saved.definition.underlying, instrument, strike, expiry))


class ArmedExitsOut(ApiModel):
    lines: list[CatalogueText]  # one per armed index exit, in the order above, below


@router.get("/paper/strategies/{strategy_id}/armed-exits", response_model=ArmedExitsOut)
async def paper_armed_exits(strategy_id: int, orders: Annotated[str, Query(max_length=8000)],
                            db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)],
                            now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> ArmedExitsOut:
    """D-03 part B (ADR-317 (7)): read only, nothing stored. For the prepared basket in the paper confirm list: one
    line per armed index exit naming the short strike on its side AS IT WILL BE after the basket (the exit stays at
    its level). No line when nothing is armed or the basket closes every leg (the exits are then cancelled)."""
    stored = await _load_strategy(db, user_ref, strategy_id)
    try:
        basket = PaperOrdersIn.model_validate_json('{"orders":' + orders + "}").orders
    except ValueError:
        refuse_request(("query", "orders"), "invalid_orders")
    rows = [r for r in await paper_trigger_store.list_for(db, strategy_id) if _state(r) == "armed"]
    armed = sorted((r.trigger for r in rows if r.trigger.kind == "conditional_exit"), key=lambda t: t.direction)
    leg_stops = [r.trigger for r in rows if r.trigger.kind == "leg_stop"]
    if not armed and not leg_stops:
        return ArmedExitsOut(lines=[])
    booked = await paper_store.load(db, strategy_id)
    state = {c.contract_id: c for c in await tracked_contracts.resolve(
        db, sorted({o.order.contract_id for o in booked} | {o.contract_id for o in basket}))}
    if any(state[o.contract_id].stored is None for o in basket):
        raise StrategyRefused("paper_contract_not_tradable")
    at = now()
    after = [*_paper(booked), *(PaperOrder(str(o.contract_id), o.side, o.quantity,
                                           _UNPRICED if o.kind == "exit" else o.price, o.kind, at) for o in basket)]
    positions = [p for p in net_positions(after, {}).positions if p.net_quantity]
    if not positions:
        return ArmedExitsOut(lines=[])
    gone = paper_leg_stops.leaving(leg_stops, {int(p.instrument_id) for p in positions})  # #774: what the route cancels
    shorts = [_identity(state[int(p.instrument_id)])[1:3] for p in positions if p.net_quantity < 0]
    calls = [k for kind, k in shorts if kind is Instrument.CE]
    puts = [k for kind, k in shorts if kind is Instrument.PE]
    lines = []
    for t in armed:
        side, strike = (("call", min(calls, default=None)) if t.direction == "above"
                        else ("put", max(puts, default=None)))
        lines.append(render_explanation(f"paper_exit_confirm_no_{side}", level=t.level) if strike is None else
                     render_explanation(f"paper_exit_confirm_{side}", level=t.level, strike=strike))
    # one line per leg stop that goes with its closed contract (ADR-330 (42); never silent)
    lines.extend(render_explanation("paper_leg_stop_removed_on_move", contract=_leg_name(state, stored, t))
                 for t in gone)
    return ArmedExitsOut(lines=lines)


# --- stop triggers and alerts (GC-TP step 7a; REQ-109 AC-8; ADR-207 (5); screens 221-224) -----------------------------
TriggerKind = Literal["conditional_exit", "leg_stop"]
Direction = Literal["above", "below"]
TriggerState = Literal["armed", "fired", "cancelled"]


class TriggerIn(BaseModel):
    """conditional_exit: ``above`` and / or ``below`` (an index level each, one trigger per direction); leg_stop:
    ``contract_id`` with ONE ``direction`` and ``level``."""
    model_config = ConfigDict(extra="forbid")
    kind: TriggerKind
    above: Decimal | None = Field(default=None, allow_inf_nan=False)
    below: Decimal | None = Field(default=None, allow_inf_nan=False)
    contract_id: int | None = Field(default=None, gt=0, le=INTEGER_MAX)
    direction: Direction | None = None
    level: Decimal | None = Field(default=None, allow_inf_nan=False)


class TriggerOut(ApiModel):
    id: int
    strategy_id: int
    kind: TriggerKind
    direction: Direction
    level: Money
    level_text: CatalogueText
    contract_id: int | None
    contract_text: CatalogueText | None
    underlying: Underlying | None
    state: TriggerState
    created_at: datetime.datetime
    fired_at: datetime.datetime | None
    cancelled_at: datetime.datetime | None
    set_before_adjustment: bool = False  # D-03 (ADR-317 (7)): armed index exit older than the latest paper adjustment
    adjustment_note: CatalogueText | None = None  # the server's sentence naming the new short strike on that side


class TriggersOut(ApiModel):
    triggers: list[TriggerOut]  # newest first
    already_set: bool = False  # D-05: true only on a save that stored NOTHING new (the identical trigger was armed)
    # D-05 r3: directions of the submitted levels NOT stored (an identical armed trigger existed)
    already_armed: list[Direction] = Field(default_factory=list)


class AlertOut(ApiModel):
    id: int
    strategy_id: int
    strategy_name: CatalogueText  # GC-TP step 4a: the strategy's saved name, the paper replies' quoted name slot
    trigger_id: int
    created_at: datetime.datetime
    title: CatalogueText
    body: CatalogueText
    read: bool


class AlertsOut(ApiModel):
    alerts: list[AlertOut]  # newest first
    unread: int


def _state(row: paper_trigger_store.TriggerRow) -> TriggerState:
    if row.fired_at is not None:
        return "fired"
    return "armed" if row.cancelled_at is None else "cancelled"


async def _adjustment_marks(db: Any, orders: Sequence[paper_store.StoredOrder],
                            rows: Sequence[paper_trigger_store.TriggerRow]) -> dict[int, Any]:
    """D-03 (ADR-317 (7)): trigger id -> the sentence for each ARMED index exit created before the latest change to the
    open legs: any ``adjust_history`` row that is not the entry and not the closing exit (an adjustment, a fired leg
    stop, a settlement, a partial exit) while a leg is still open. Nothing is moved or cancelled. The short strike is
    the nearest-the-money open short on that side (lowest call / highest put). A mark that cannot be worked out marks
    EVERY armed exit with a generic line (logged): the exits stay armed either way."""
    exits = [r for r in rows if _state(r) == "armed" and r.trigger.kind == "conditional_exit"]
    if not exits or not orders:
        return {}
    try:
        found = {c.contract_id: c for c in await tracked_contracts.resolve(
            db, sorted({o.order.contract_id for o in orders}))}
        who = {cid: _identity(c) for cid, c in found.items()}
        history = ah.adjustment_history(
            [ah.HistoryOrder(str(o.order.contract_id), o.order.side, o.order.quantity, o.order.price,  # type: ignore[arg-type]
                             o.order.kind, o.order.placed_at,  # type: ignore[arg-type]
                             is_option=who[o.order.contract_id][1] is not Instrument.FUT) for o in orders],
            {}, adjustments_max=None)
        times = [r.at for r in history.rows if r.step != "entry" and not r.is_exit]
        if not times:
            return {}
        latest = max(o.created_at for o in orders if o.order.placed_at == max(times))
        positions = [p for p in net_positions(_paper(orders), {}).positions if p.net_quantity]
        if not positions:  # every leg closed: the exits are cancelled, nothing to mark
            return {}
        shorts = [(who[int(p.instrument_id)][1], who[int(p.instrument_id)][2]) for p in positions if p.net_quantity < 0]
    except Exception:  # noqa: BLE001 - fail safe: every armed exit is marked, never silently unmarked
        _LOG.warning("trigger marks could not be read", exc_info=True)
        return {r.trigger.id: render_explanation("paper_exit_set_before_unchecked") for r in exits}
    calls = [k for kind, k in shorts if kind is Instrument.CE]
    puts = [k for kind, k in shorts if kind is Instrument.PE]
    out: dict[int, Any] = {}
    for r in exits:
        if r.created_at >= latest:
            continue
        up = r.trigger.direction == "above"
        strike = (min(calls) if calls else None) if up else (max(puts) if puts else None)
        if strike is None:
            out[r.trigger.id] = render_explanation(
                "paper_exit_set_before_no_call" if up else "paper_exit_set_before_no_put", level=r.trigger.level)
        else:
            out[r.trigger.id] = render_explanation(
                "paper_exit_set_before_call" if up else "paper_exit_set_before_put",
                level=r.trigger.level, strike=strike)
    return out


async def _triggers_out(db: Any, strategy_id: int, already_set: bool = False,
                        already_armed: Sequence[Direction] = ()) -> TriggersOut:
    rows = list(reversed(await paper_trigger_store.list_for(db, strategy_id)))
    ids = sorted({r.trigger.contract_id for r in rows if r.trigger.contract_id is not None})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    marks = await _adjustment_marks(db, await paper_store.load(db, strategy_id), rows)
    return TriggersOut.model_validate({"already_set": already_set, "already_armed": list(already_armed), "triggers": [{
        "id": r.trigger.id, "strategy_id": r.trigger.strategy_id, "kind": r.trigger.kind,
        "direction": r.trigger.direction, "level": r.trigger.level,
        "level_text": render_explanation("paper_trigger_level", level=r.trigger.level),
        "contract_id": r.trigger.contract_id,
        "contract_text": None if r.trigger.contract_id is None else describe_contract(
            _identity(found[r.trigger.contract_id])),
        "underlying": r.trigger.underlying, "state": _state(r), "created_at": r.created_at,
        "fired_at": r.fired_at, "cancelled_at": r.cancelled_at,
        "set_before_adjustment": r.trigger.id in marks, "adjustment_note": marks.get(r.trigger.id)} for r in rows]})


@router.get("/paper/strategies/{strategy_id}/triggers", response_model=TriggersOut)
async def list_paper_triggers(strategy_id: int, db: Annotated[Any, Depends(get_db)],
                              user_ref: Annotated[str, Depends(current_user_ref)]) -> TriggersOut:
    await _load_strategy(db, user_ref, strategy_id)
    return await _triggers_out(db, strategy_id)


def _new_triggers(body: TriggerIn, underlying: str, open_ids: Sequence[int]) -> list[paper_trigger_store.NewTrigger]:
    new: list[paper_trigger_store.NewTrigger] = []
    if body.kind == "conditional_exit":
        if body.contract_id is not None or body.direction is not None or body.level is not None:
            raise StrategyRefused("user_input_request_invalid")
        new = [paper_trigger_store.NewTrigger("conditional_exit", d, lvl, underlying=underlying)
               for d, lvl in (("above", body.above), ("below", body.below)) if lvl is not None]
    elif (body.above is None and body.below is None and body.contract_id is not None and body.direction
          and body.level is not None):
        new = [paper_trigger_store.NewTrigger("leg_stop", body.direction, body.level, contract_id=body.contract_id)]
    if not new:
        raise StrategyRefused("user_input_request_invalid")
    for n in new:
        if not is_typed_price(n.level):
            raise StrategyRefused("paper_trigger_level_invalid")
        if n.contract_id is not None and n.contract_id not in open_ids:
            raise StrategyRefused("paper_trigger_leg_not_open")
    return new


async def check_trigger_levels(db: Any, ctx: MarketContext | None, feed: LiveFeed | None, underlying: str,  # noqa: PLR0913
                               new: Sequence[paper_trigger_store.NewTrigger], now: AnswerClock,
                               wait: market_read.Wait = market_read.DEFAULT_WAIT) -> str | None:
    """The refusal template id when a new level cannot be saved, else None (ADR-317 (1), ADR-327), judged on the ONE
    price door ``market_read.read_market`` (the same price the monitor compares with: ``stops.crossed``, at the level
    counts; a conditional exit on the index, a leg stop only on its own contract's price).
    Answer states: market closed (the calendar, ``market_state``; no context uses ``now()``) -> None, saved, arms at the
    next live tick (ADR-327 (3)); market open and no context, a leg with no feed key, a read that raises, or a price not
    live after asking the feed and waiting up to 3 s (stale, missing) -> ``paper_trigger_price_unreadable`` (ADR-327
    (2)); a live price at or beyond a level -> ``paper_trigger_already_crossed`` / ``paper_trigger_leg_already_crossed``
    (a crossed level is reported before an unreadable one: the trader can act on it)."""
    if not may_act.market_open(ctx, now() if ctx is None else ctx.clock()):
        return None
    if ctx is None:
        return _UNREADABLE
    keys = {c.contract_id: c.feed_key for c in await tracked_contracts.resolve(
        db, sorted({n.contract_id for n in new if n.contract_id is not None}))}
    leg_keys = [keys.get(n.contract_id) for n in new if n.contract_id is not None]
    if any(k is None for k in leg_keys):
        return _UNREADABLE  # no feed key = no live leg price to check against (never the index)
    await release_connection(db)  # read-only so far, and both callers run this before the strategy row lock
    try:
        read = await market_read.read_market(ctx, feed, underlying, sorted({k for k in leg_keys if k is not None}),
                                             any(n.contract_id is None for n in new), "trigger_check", wait=wait)
        return _judge_levels(new, read, keys)
    except Exception:  # noqa: BLE001 - a read that fails is "cannot be checked": refused in market hours (ADR-327)
        _LOG.exception("paper trigger price read failed")
        return _UNREADABLE


def _judge_levels(new: Sequence[paper_trigger_store.NewTrigger], read: market_read.MarketRead,
                  keys: Mapping[int, str | None]) -> str | None:
    if read.market_closed:
        return None
    states: list[str] = []
    for n in new:
        answer = read.index if n.contract_id is None else read.legs[keys[n.contract_id]]  # type: ignore[index]
        states.append(may_act.MISSING if answer is None else answer.state)
        if answer is not None and answer.state == paper.LIVE and stops.crossed(
                stops.Trigger(0, 0, n.kind, n.direction, n.level, n.contract_id, n.underlying),  # type: ignore[arg-type]
                market_read.live_price(answer)):
            return "paper_trigger_already_crossed" if n.contract_id is None else "paper_trigger_leg_already_crossed"
    decision = may_act.prices_ok("set_trigger", states)
    return decision.reason if isinstance(decision, may_act.Refused) else None


async def _validated_triggers(db: Any, strategy_id: int, body: TriggerIn,
                              underlying: str) -> list[paper_trigger_store.NewTrigger]:
    open_ids = _open_ids(await paper_store.load(db, strategy_id))
    if not open_ids:
        raise StrategyRefused("paper_trigger_nothing_open")
    return _new_triggers(body, underlying, open_ids)


@router.post("/paper/strategies/{strategy_id}/triggers", status_code=201, response_model=TriggersOut,
             dependencies=[Depends(guard_paper_order)])  # IC e2e 5: scenario mode = own scenario only
async def add_paper_triggers(strategy_id: int, body: TriggerIn, db: Annotated[Any, Depends(get_db)],  # noqa: PLR0913
                             user_ref: Annotated[str, Depends(current_user_ref)],
                             ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                             feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                             now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> TriggersOut:
    stored = await _load_strategy(db, user_ref, strategy_id)
    underlying = stored.saved.definition.underlying
    # ADR-327: the price read (up to 3 s) happens BEFORE the strategy row lock, so a slow feed never holds the lock the
    # monitor's fire waits behind; what the read decided is re-validated under the lock below (D-05: the open legs)
    if crossed := await check_trigger_levels(db, ctx, feed, underlying,
                                             await _validated_triggers(db, strategy_id, body, underlying), now):
        raise StrategyRefused(crossed)
    # D-05: two saves at one instant cannot both pass the read below
    await store.lock_strategy(db, user_ref, strategy_id)
    new = await _validated_triggers(db, strategy_id, body, underlying)
    # ADR-317 (3): the same armed trigger is not stored twice (read under the strategy's row lock taken above)
    armed = {(r.trigger.kind, r.trigger.direction, r.trigger.level, r.trigger.contract_id)
             for r in await paper_trigger_store.list_for(db, strategy_id) if _state(r) == "armed"}
    fresh = [n for n in new if (n.kind, n.direction, n.level, n.contract_id) not in armed]
    duplicate = [n.direction for n in new if n not in fresh]
    try:
        for n in fresh:
            await paper_trigger_store.add(db, strategy_id, n)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    paper_monitor.notify()
    return await _triggers_out(db, strategy_id, already_set=not fresh, already_armed=duplicate)


@router.delete("/paper/strategies/{strategy_id}/triggers/{trigger_id}", response_model=TriggersOut,
             dependencies=[Depends(guard_paper_order)])  # IC e2e 5: scenario mode = own scenario only
async def cancel_paper_trigger(strategy_id: int, trigger_id: int, db: Annotated[Any, Depends(get_db)],
                               user_ref: Annotated[str, Depends(current_user_ref)]) -> TriggersOut:
    await _load_strategy(db, user_ref, strategy_id)
    rows = {r.trigger.id: r for r in await paper_trigger_store.list_for(db, strategy_id)}
    if trigger_id not in rows:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    if rows[trigger_id].fired_at is not None:
        raise StrategyRefused("paper_trigger_already_fired", Failure.CONFLICT)
    try:
        await paper_trigger_store.cancel(db, strategy_id, trigger_id)  # already cancelled: nothing to change
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    paper_monitor.notify()
    return await _triggers_out(db, strategy_id)


@router.post("/paper/strategies/{strategy_id}/triggers/{trigger_id}/keep", response_model=TriggersOut,
             dependencies=[Depends(guard_paper_order)])
async def keep_paper_trigger(strategy_id: int, trigger_id: int, db: Annotated[Any, Depends(get_db)],  # noqa: PLR0913
                             user_ref: Annotated[str, Depends(current_user_ref)],
                             ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                             feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                             now: Annotated[AnswerClock, Depends(get_answer_clock)]) -> TriggersOut:
    """D-03 "Keep this level": the trader has read the mark and keeps the exit. The same exit is stored again as a new
    armed row (created after the adjustment, so it is no longer marked) and the old row is cancelled, in ONE
    transaction under the strategy lock. The level is the same: nothing is moved (no silent substitution).
    #733 (ADR-317 (1)): keeping stores the exit again, so the SAME crossed-level check as the save route
    (``check_trigger_levels``) runs first, before the lock (the price read may wait up to 3 s): a level the live price
    has already reached is refused and the old exit stays as it is."""
    stored = await _load_strategy(db, user_ref, strategy_id)
    current = {r.trigger.id: r for r in await paper_trigger_store.list_for(db, strategy_id)}.get(trigger_id)
    if current is not None and current.trigger.kind == "conditional_exit" and _state(current) == "armed":
        again = paper_trigger_store.NewTrigger("conditional_exit", current.trigger.direction, current.trigger.level,
                                               underlying=current.trigger.underlying)
        if refusal := await check_trigger_levels(db, ctx, feed, stored.saved.definition.underlying, [again], now):
            raise StrategyRefused(refusal)
    try:
        await store.lock_strategy(db, user_ref, strategy_id)
        rows = {r.trigger.id: r for r in await paper_trigger_store.list_for(db, strategy_id)}
        if trigger_id not in rows or rows[trigger_id].trigger.kind != "conditional_exit":
            raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
        if _state(rows[trigger_id]) != "armed":
            raise StrategyRefused("paper_trigger_already_fired", Failure.CONFLICT)
        old = rows[trigger_id].trigger
        marks = await _adjustment_marks(db, await paper_store.load(db, strategy_id), [rows[trigger_id]])
        if trigger_id in marks:  # an exit that is not marked has nothing to keep: no churn
            if not await paper_trigger_store.cancel(db, strategy_id, trigger_id):  # the monitor fired it first
                raise StrategyRefused("paper_trigger_already_fired", Failure.CONFLICT)
            await paper_trigger_store.add(db, strategy_id, paper_trigger_store.NewTrigger(
                "conditional_exit", old.direction, old.level, underlying=old.underlying))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    paper_monitor.notify()
    return await _triggers_out(db, strategy_id)


async def _alerts_out(db: Any, user_ref: str) -> AlertsOut:
    rows, unread = await paper_trigger_store.alerts(db, user_ref)
    titles = await alert_title.labels(db, [(a.strategy_id, a.strategy_name) for a in rows])  # ADR-330 (19)(b)
    shown: list[dict[str, Any]] = []
    for a in rows:
        try:  # one unreadable row is left out of the list (and logged), never a 500 for every alert
            restore_explanation("paper_alert_title", a.title)  # the stored title must still fit; it is worded afresh
            title = render_explanation("paper_alert_title", name=titles[a.strategy_id])
            body = restore_alert_body(a.body)
        except ValueError:
            _LOG.warning("paper alert %s left out: stored text fits no alert template", a.id)
            continue
        shown.append({"id": a.id, "strategy_id": a.strategy_id, "strategy_name": titles[a.strategy_id],
                      "trigger_id": a.trigger_id, "created_at": a.created_at, "title": title, "body": body,
                      "read": a.read_at is not None})
    return AlertsOut.model_validate({"unread": unread, "alerts": shown})


@router.get("/paper/alerts", response_model=AlertsOut)
async def list_paper_alerts(db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> AlertsOut:
    return await _alerts_out(db, user_ref)


class HistoryRecordOut(ApiModel):
    """D-22 / D-71: one record of Alerts > History: a fired stop or an expiry settlement, with time, what happened, the
    index value at that moment and the prices (all in the stored wording's text)."""
    kind: Literal["stop", "settled"]
    strategy_id: int
    strategy_name: CatalogueText
    at: datetime.datetime
    title: CatalogueText
    body: CatalogueText


class HistoryOut(ApiModel):
    records: list[HistoryRecordOut]  # newest first


async def _settled_records(db: Any, user_ref: str) -> list[dict[str, Any]]:
    """One record per (strategy, settle time, reason): the legs the settlement closed, with each price."""
    rows = await paper_store.settlements(db, user_ref)
    ids = sorted({o.order.contract_id for _, o in rows})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    groups: dict[tuple[int, datetime.datetime, str | None], list[tuple[str | None, paper_store.StoredOrder]]] = {}
    for name, o in rows:
        groups.setdefault((o.strategy_id, o.order.placed_at, o.order.reason), []).append((name, o))
    out: list[dict[str, Any]] = []
    titles = await alert_title.labels(db, [(sid, items[0][0]) for (sid, _, _), items in groups.items()])
    for (sid, at, reason), items in groups.items():
        what = restore_order_reason(reason)
        if what is None:
            _LOG.warning("paper settlement of strategy %s left out of history: stored reason fits no wording", sid)
            continue
        name = items[0][0]
        legs = [(describe_contract(_identity(found[o.order.contract_id])), o.order.price) for _, o in items]
        out.append({"kind": "settled", "strategy_id": sid, "strategy_name": titles[sid], "at": at,
                    "title": render_explanation("paper_alert_title", name=titles[sid]),
                    "body": settle_history_body(what, legs)})
    return out


@router.get("/paper/alerts/records", response_model=HistoryOut)
async def paper_alerts_records(db: Annotated[Any, Depends(get_db)],
                               user_ref: Annotated[str, Depends(current_user_ref)]) -> HistoryOut:
    """D-22 / D-71 (owner decision): every fired stop (the alert rows, read or not) and every expiry settlement, newest
    first. No new table: the stop's alert and the settle orders are already stored with their text."""
    stops_ = (await _alerts_out(db, user_ref)).alerts
    records = [{"kind": "stop", "strategy_id": a.strategy_id, "strategy_name": a.strategy_name, "at": a.created_at,
                "title": a.title, "body": a.body} for a in stops_]
    records += await _settled_records(db, user_ref)
    records.sort(key=lambda r: r["at"], reverse=True)
    return HistoryOut.model_validate({"records": records})


@router.post("/paper/alerts/read", response_model=AlertsOut)
async def read_paper_alerts(db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> AlertsOut:
    await paper_trigger_store.mark_all_read(db, user_ref)
    await db.commit()
    return await _alerts_out(db, user_ref)


# GC-ADJ2 step 6: the book's own readers under public names for the adjustment-history route (one reader, no copy;
# no behaviour change)
identity = _identity
open_ids = _open_ids
connected = _connected
market_snapshot = _snapshot
open_prices = _prices
exact = _exact
engine_orders = _paper
signed = _signed
