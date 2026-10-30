"""The outcome of a draft strategy: one table, one set of scenario values, the payoff and the summary (W-063).

Spec: REQ-034 AC-1 (every part of the outcome view), AC-7 (plain language first), AC-8 (payoff graph and scenario table
from the same engine); REQ-033 AC-1/AC-3 (the leg formulas; expiry scenarios use the entry price, never the LTP);
ADR-008 (one engine, exact Decimal); ADR-061 (each expiry's forward; spot for CURRENT and the range); ADR-068 (planned
entry with its capture time; the not-live labels).

AC-8 by construction: :func:`build_outcome` computes the scenario values ONCE (``scenario_values``) and both the table
(``build_table``) and the payoff points are taken from that one ``ScenarioValues``; nothing here prices a level. The one
computation runs over the GRAPH's levels (the table's columns plus every strike in range, GC-BM F-8); the table takes
its own columns from it (``on_levels``), so the strikes are graph points and never scenario-table columns (Q33D = C).

Answer states (run-discipline B4 (d)), each with its label or refusal:

- no provider / no Zerodha session: ``NOT_CONNECTED``, "Draft — Live data not connected" (ADR-068, ADR-020 Q185).
- all inputs live: ``COMPUTED``, no data label.
- spot STALE/DELAYED: ``COMPUTED`` and every number carries "stale since HH:MM IST" (REQ-072 AC-2); when the feed has
  dropped, REQ-049 AC-5's message is added.
- market closed (ADR-119 calendar, ``MarketSnapshot.market_closed``) with the last close held: ``COMPUTED`` from it
  exactly as in hours (ADR-200 (1)); no "stale since" and no "disconnected" text: the answer's ``market_closed`` and
  ``last_price_at`` carry the one market-closed banner (ADR-200 (2), ADR-177). A held quote that is not sound
  (``quote.planning_price_usable``) is unusable; a contract with no held price stays unpriced (ADR-200 (4)).
- spot missing / UNHEALTHY / UNAVAILABLE: ``REFUSED`` (SpotRefused reason).
- a forward fallback: ``COMPUTED``, labelled "estimated from spot" (ADR-061).
- a leg quote STALE/DELAYED: its LTP is used and the leg carries "stale since HH:MM IST"; the outcome label lists it.
- a leg with no quote, or an UNHEALTHY/UNAVAILABLE one: its LTP and IV are not used (live P&L and Greeks show "—" with
  a reason), the leg carries "no live quote" / "quote unhealthy"; expiry scenarios still use the planned entry.
- an expired or unknown leg, or a refused forward: ``REFUSED`` naming the leg / expiry.
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Final

from ofo.charges import ChargeRates
from ofo.charges.round_trip import ChargesBreakdown, ChargesNotComputable, holds_bought_option, round_trip_breakdown
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.metrics import UNLIMITED, MultiExpiryError, StrategyMetrics, strategy_metrics
from ofo.engine.model import (
    ModelInputs,
    SpotRefused,
    data_label,
    expiry_model,
    implied_vol,
    iv_price,
    join_labels,
    leg_greeks_unrounded,
    market_closed_model,
    model_inputs,
)
from ofo.errors.explanations import ExplanationText, join_explanations, render_explanation
from ofo.instruments.models import ZERODHA
from ofo.marketdata.forward import ForwardUnavailable, spot_fallback_forward
from ofo.marketdata.quote import NormalizedQuote, is_live_price, planning_price_usable
from ofo.marketdata.shared_compute import FeedScope
from ofo.money import HUNDREDTH
from ofo.outcome import money
from ofo.outcome.snapshot import MarketSnapshot
from ofo.rules.inputs import DataHealth
from ofo.scenario.config import ScenarioConfig, ScenarioSettings
from ofo.scenario.levels import (
    ColumnKind,
    ExpectedMove,
    LevelColumn,
    LevelSet,
    RangeOverride,
    build_level_set,
    first_multiple_at_or_above,
    graph_level_set,
)
from ofo.scenario.spot import spot_reading
from ofo.outcome.target import Target, TargetAsk, TargetOffer, entries_target, live_target, target_offer
from ofo.scenario.views import DEFAULT_VIEW, LABELS, ScenarioValues, View, on_levels, scenario_values
from ofo.table import ColumnSpec, Table, build_table, visible_columns
from ofo.timeutil import IST

NOT_CONNECTED_LABEL: Final = render_explanation("outcome_not_connected")
#: REQ-077 AC-9: the label of an At Expiry answer built from the user's own prices when there is no live data
FROM_ENTRIES_LABEL: Final = render_explanation("outcome_from_entries")
#: REQ-133 AC-3: a just (re)connected feed with no price frame yet, inside the staleness limit
WAITING_FIRST_PRICE_LABEL: Final = render_explanation("outcome_waiting_first_price")
MARGIN_NOT_AVAILABLE_YET: Final = "NOT_AVAILABLE_YET"
#: ADR-099 margin states: Zerodha's figures read for the planned orders / Zerodha could not be read / the planned orders
#: cannot be sent to Zerodha (a leg that is not a listed Zerodha contract). No session stays NOT_AVAILABLE_YET.
MARGIN_CHECKED: Final = "CHECKED"
MARGIN_UNREADABLE: Final = "UNREADABLE"
MARGIN_NO_BASKET: Final = "NO_BASKET"
_UNUSABLE: Final = (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE)
#: REQ-137 AC-1 / D-B24: the payoff table's intervals a user may pick, in index points
PAYOFF_TABLE_STEPS: Final = (Decimal(10), Decimal(25), Decimal(50), Decimal(100))
#: REQ-137 AC-1: with no interval picked, "default the underlying's strike step: NIFTY 50, SENSEX 100". This is NOT
#: the scenario grid's Admin step (ADR-042: NIFTY 100, SENSEX 300), which the per-leg table keeps.
PAYOFF_TABLE_DEFAULT_STEPS: Final = {"NIFTY": Decimal(50), "SENSEX": Decimal(100)}
MAX_PAYOFF_TABLE_ROWS: Final = 1000
#: D-B20 (Fixed SD): the SD block's horizon in calendar days; the days to the nearest expiry when fewer
SD_HORIZON_DAYS: Final = 7
_TENTH: Final = Decimal("0.1")


class OutcomeState(Enum):
    COMPUTED = "COMPUTED"
    FROM_ENTRIES = "FROM_ENTRIES"  # REQ-077 AC-9: no live data; At Expiry numbers from the user's prices, never live
    NOT_CONNECTED = "NOT_CONNECTED"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class PlannedLeg:
    """A draft leg (ADR-068): the instrument, side, lots and the planned entry with the time it was captured."""

    instrument_id: str
    action: Action
    lots: int
    planned_entry: Decimal | None  # None = saved without a price (ADR-085): the leg needs a reprice
    captured_at: datetime.datetime

    def __post_init__(self) -> None:
        if not isinstance(self.action, Action):
            raise ValueError(f"action must be an Action, got {self.action!r}")
        if isinstance(self.lots, bool) or not isinstance(self.lots, int) or self.lots <= 0:
            raise ValueError(f"lots must be a positive integer, got {self.lots!r}")
        if not isinstance(self.captured_at, datetime.datetime) or self.captured_at.tzinfo is None:
            raise ValueError(f"captured_at must be a timezone-aware datetime, got {self.captured_at!r}")


@dataclass(frozen=True)
class StrategyDefinition:
    underlying: str
    legs: tuple[PlannedLeg, ...]

    def __post_init__(self) -> None:
        if not self.legs:
            raise ValueError("a strategy needs at least one leg")


@dataclass(frozen=True)
class OutcomeLeg:
    instrument_id: str
    symbol: str | None
    action: Action
    instrument: Instrument | None
    strike: Decimal | None
    expiry: datetime.date | None
    lots: int
    lot_size: int | None
    quantity: int | None
    planned_entry: Decimal | None
    captured_at: datetime.datetime
    ltp: Decimal | None
    iv: Decimal | None
    health: DataHealth | None
    label: ExplanationText | None


@dataclass(frozen=True)
class Summary:
    """REQ-034 AC-7: the three plain-language answers first, the detail after."""

    what_can_i_lose: ExplanationText
    what_can_i_make: ExplanationText
    where_do_i_start_losing: ExplanationText
    max_profit: Decimal | None  # None = unlimited
    max_loss: Decimal | None  # None = unlimited
    max_profit_unlimited: bool
    max_loss_unlimited: bool
    breakevens: tuple[Decimal, ...]
    lower_be: Decimal | None
    upper_be: Decimal | None
    risk_boundaries: tuple[Decimal, ...]
    # W-075 / ADR-082 (2): the round-trip charges inside max_profit / max_loss (None = not included: no rate set or
    # a leg the rate table cannot price - the sentences then keep ADR-071's "before charges and taxes" wording)
    charges: Decimal | None = None
    charges_unavailable: bool = False
    # REQ-135 AC-4 (W-155): a strategy of one futures leg. A side with no fixed maximum has no Reward/Risk, and the
    # reason says so; a futures leg holds no time value and no intrinsic value (both 0.00). Every other strategy keeps
    # these None: the money-summary requirement (W-154) owns its Reward/Risk, Time value and Intrinsic value.
    reward_risk: Decimal | None = None
    reward_risk_reason: ExplanationText | None = None
    time_value: Decimal | None = None
    intrinsic_value: Decimal | None = None
    # REQ-081 (W-154): the money figures, all from ofo.outcome.money. ``value_label`` / ``value_reason``: the label of
    # the time and intrinsic values, or why they are absent; ``funds_share`` is set after the margin read
    # (CHECKED only).
    risk_reward: Decimal | None = None
    net_premium: money.NetPremium | None = None
    value_label: ExplanationText | None = None
    value_reason: ExplanationText | None = None
    funds_share: money.FundsShare | None = None


@dataclass(frozen=True)
class Margin:
    """The margin block (ADR-099). ``needed`` / ``available`` / ``checked_at`` are set only in the CHECKED state: the
    amount needed is Zerodha's basket figure plus the ADR-094 top-up (a closing basket counts as 0), ``available`` is
    Zerodha's available funds, ``checked_at`` when Zerodha was read (ADR-088). Every other state carries no figure."""

    state: str
    reason: ExplanationText
    needed: Decimal | None = None
    broker_needed: Decimal | None = None  # CHECKED only: Zerodha's own final.total (a closing basket: 0), never ours
    available: Decimal | None = None
    checked_at: datetime.datetime | None = None
    shortfall: bool = False  # CHECKED only: Zerodha's available funds are below the amount needed (Decimal compare)
    shortfall_reason: ExplanationText | None = None  # REQ-055 AC-4: set only with ``shortfall`` (the one comparison)


@dataclass(frozen=True)
class Outcome:
    state: OutcomeState
    underlying: str
    status_label: ExplanationText | None  # NOT_CONNECTED / REFUSED text, or REQ-049 AC-5's message when the feed dropped
    reason: ExplanationText | None
    legs: tuple[OutcomeLeg, ...]
    margin: Margin
    valuation: datetime.datetime | None = None
    output_label: ExplanationText | None = None  # data label + "estimated from spot", joined
    spot_level: Decimal | None = None
    spot_at: datetime.datetime | None = None
    level_set: LevelSet | None = None
    scenario: ScenarioValues | None = None
    table: Table | None = None
    visible_columns: tuple[ColumnSpec, ...] = ()
    payoff_points: tuple[tuple[Decimal, Decimal], ...] = ()
    summary: Summary | None = None
    centre_label: ExplanationText | None = None  # FROM_ENTRIES only: where the level grid is centred, and why
    # ADR-167 (2): the round trip by component; None = no rate set / not priced
    charges_breakdown: ChargesBreakdown | None = None
    # GC-UI step 4 (REQ-083 AC-1/AC-2, D-B06/D-B14), only when both views were asked for: each view's values over the
    # SAME graph levels (At Expiry first), and the other view's values on the table's columns (``on_levels``)
    curves: tuple[ScenarioValues, ...] = ()
    other_view: ScenarioValues | None = None
    payoff_table: PayoffTable | None = None  # REQ-137 AC-1: only when asked for (a step or both views)
    standard_deviation: StandardDeviation | None = None  # REQ-083 AC-4 / REQ-137 AC-3: only when asked for
    target: Target | TargetOffer | None = None  # REQ-084 AC-4: the limits alone unless a target was sent (AC-6)


@dataclass(frozen=True)
class PayoffTable:
    """REQ-137 AC-1: index levels at the picked interval with both views' values from the one engine. A view the
    engine cannot give (a leg without IV, ADR-143 mixed expiries, no live prices) is unavailable with its reason."""

    step: Decimal
    levels: tuple[Decimal, ...]
    nearest_spot: Decimal | None  # the row highlighted; None when the answer has no live index price
    views: tuple[ScenarioValues, ...] = ()  # Estimated Now first, then At Expiry (the screen's column order)
    unavailable_reason: ExplanationText | None = None
    spot: Decimal | None = None  # D-B26: the same spot ``nearest_spot`` is picked from; each row's move % uses it


@dataclass(frozen=True)
class SdRow:
    """One SD row: the move, its percent of spot and the two levels, each half-up to 0.1 from the exact figure."""

    sd: int
    move: Decimal
    percent: Decimal
    lower: Decimal
    upper: Decimal


@dataclass(frozen=True)
class StandardDeviation:
    available: bool
    reason: ExplanationText | None
    horizon_days: int | None = None
    iv: Decimal | None = None
    spot: Decimal | None = None
    rows: tuple[SdRow, ...] = ()


MARGIN: Final = Margin(MARGIN_NOT_AVAILABLE_YET, render_explanation("outcome_margin_pending"))


def margin_checked(needed: Decimal, available: Decimal, checked_at: datetime.datetime,
                   broker_needed: Decimal, top_up: Decimal) -> Margin:
    """ADR-099: the amount needed (ours: Zerodha's figure plus the ADR-094 top-up), Zerodha's own figure, Zerodha's
    available funds and the time they were read. Both arrive already rounded half-up to the paisa
    where they were parsed (ADR-101: Kite's float noise 68498.85000000001 reads 68498.85); any rounding left here is on
    the safe side (needed UP, funds DOWN) for figures not from Kite, and ``shortfall``
    compares exactly the two amounts shown, so the screen never shows equal figures with a shortfall mark, nor hides a
    shortfall the gate would block. Display only: the gate (REQ-055) is the check before the basket.
    ``top_up`` is the ADR-094 top-up exactly as ``margin_gate.basket_requirement`` computed it (never recomputed
    here); it alone picks the wording (GC-UI D-A47): 0 says Zerodha's figure already includes the bought legs'
    premium, more than 0 names the amount added."""
    for value in (needed, available, broker_needed, top_up):
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("a margin figure must be a finite Decimal")
    if top_up < 0:
        raise ValueError("the ADR-094 top-up is never below 0")
    if not isinstance(checked_at, datetime.datetime) or checked_at.tzinfo is None:
        raise ValueError("checked_at must be a timezone-aware datetime")
    need = needed.quantize(HUNDREDTH, rounding=ROUND_CEILING)
    have = available.quantize(HUNDREDTH, rounding=ROUND_FLOOR)
    theirs = max(broker_needed, Decimal(0)).quantize(HUNDREDTH, rounding=ROUND_CEILING)  # a closing basket: 0
    short = have < need
    added = top_up.quantize(HUNDREDTH, rounding=ROUND_CEILING)
    if added > 0:  # REQ-055 AC-3: each named for itself
        figures = {"broker_needed": theirs, "top_up": added, "needed": need, "available": have}
        checked_id, short_id = "outcome_margin_checked_top_up", "outcome_margin_short_top_up"
    else:  # nothing was added: never name an addition (GC-UI D-A47)
        figures = {"broker_needed": theirs, "available": have}
        checked_id, short_id = "outcome_margin_checked", "outcome_margin_short"
    reason = render_explanation(short_id, **figures) if short else None
    return Margin(MARGIN_CHECKED, render_explanation(checked_id, **figures), need,
                  theirs, have, checked_at, short, reason)


def margin_unreadable() -> Margin:
    """ADR-099: Zerodha could not be read; no figure is made up."""
    return Margin(MARGIN_UNREADABLE, render_explanation("outcome_margin_unreadable"))


def margin_busy() -> Margin:
    """REQ-118 AC-3: Zerodha's rate limiter refused the margin read; no figure, and the user is told why."""
    return Margin(MARGIN_UNREADABLE, render_explanation("outcome_margin_busy"))


def margin_no_basket() -> Margin:
    """A leg is not a listed Zerodha contract, so no basket can be sent: no figure, and no Kite call."""
    return Margin(MARGIN_NO_BASKET, render_explanation("outcome_margin_no_basket"))


def _contract_fields(snapshot: MarketSnapshot | None, instrument_id: str, stored=None):
    """The one lookup of a leg's contract: the snapshot's catalogue entry (symbol, instrument, strike, expiry), the same
    one the COMPUTED path reads. With no snapshot (no provider, #249) ``stored`` maps instrument id to the stored
    catalogue entry. A contract neither knows gives all None."""
    lm = None if snapshot is None else snapshot.legs.get(instrument_id)
    listed = lm.contract if lm is not None else (stored or {}).get(instrument_id)
    if listed is None:
        return None, None, None, None
    c = listed.contract
    kind = Instrument(c.instrument_type)
    symbol = listed.ref(ZERODHA).broker_symbol if listed.broker_refs else None
    return symbol, kind, (None if kind is Instrument.FUT else c.strike), c.expiry


def _unpriced_legs(definition: StrategyDefinition, snapshot: MarketSnapshot | None, label, stored=None) -> tuple:
    out = []
    for p in definition.legs:
        symbol, kind, strike, expiry = _contract_fields(snapshot, p.instrument_id, stored)
        out.append(OutcomeLeg(p.instrument_id, symbol, p.action, kind, strike, expiry, p.lots, None, None, p.planned_entry,
                              p.captured_at, None, None, None, label))
    return tuple(out)


def not_connected(definition: StrategyDefinition,
                  snapshot: MarketSnapshot | None = None, stored=None) -> Outcome:
    """No provider or no Zerodha session (ADR-068 consequence, ADR-020 Q185): a state, never an error. With a
    ``snapshot`` (a session that ended) the legs name their contract; with none, ``stored`` (instrument id -> the stored
    catalogue entry, #249) names them, and a contract it lacks stays unnamed."""
    legs = _unpriced_legs(definition, snapshot, NOT_CONNECTED_LABEL, stored)
    return Outcome(OutcomeState.NOT_CONNECTED, definition.underlying, NOT_CONNECTED_LABEL,
                   render_explanation("outcome_reason_no_provider"), legs, MARGIN)


def waiting_first_price(definition: StrategyDefinition, snapshot: MarketSnapshot) -> Outcome:
    """REQ-133 AC-3: the feed has just connected or reconnected and no price frame has arrived yet, still inside the
    feed's staleness limit (``FeedState.awaiting_first_price``). The answer is the not-connected state with the
    waiting words on the answer and on every leg, and no number at all (no LTP, no table): the quotes held from before
    the drop are not current, and the alarm (the stale labels) comes only once the limit passes with no frame."""
    legs = _unpriced_legs(definition, snapshot, WAITING_FIRST_PRICE_LABEL)
    return Outcome(OutcomeState.NOT_CONNECTED, definition.underlying, WAITING_FIRST_PRICE_LABEL, None, legs, MARGIN)


def not_live(definition: StrategyDefinition, snapshot: MarketSnapshot) -> Outcome:
    """The live market is connected but this strategy's inputs are not streaming (no subscriber on the shared feed, e.g.
    the REST fallback while the socket is down; ADR-068 (2) "labelled as not live"). No number is shown as live
    (REQ-049 AC-4): the state carries REQ-049 AC-5's message with the newest input time held, per leg too. Each leg
    names its contract (ADR-086), from the same snapshot lookup the computed answer uses."""
    label = _not_live_label(snapshot)
    legs = _unpriced_legs(definition, snapshot, label)
    return Outcome(OutcomeState.NOT_CONNECTED, definition.underlying, label, None, legs, MARGIN)


def _not_live_label(snapshot: MarketSnapshot) -> ExplanationText:
    """REQ-049 AC-5's message ("When live data drops ... Last updated: <time>") ONLY when a quote was held and then
    lost, stamped with the newest quote time held. When no quote was ever held for any input, nothing "dropped" and
    there is no last update to name: ADR-020 Q185's draft label ("Draft — Live data not connected", the catalogue's
    ``outcome_not_connected``), never the request time."""
    times = [q.timestamp for q in [snapshot.spot, *(lm.quote for lm in snapshot.legs.values())] if q is not None]
    times += list(snapshot.ended_times.values())  # ADR-077: times kept after the subscription ended
    if not times:
        return NOT_CONNECTED_LABEL
    return render_explanation("outcome_feed_disconnected", time=max(times))


def _quote_label(q: NormalizedQuote) -> ExplanationText | None:
    """The one stale/delayed wording (ofo.engine.model.data_label) applied to a leg quote's own time and health."""
    return data_label(SpotReading(Decimal(1), q.timestamp, q.health))


def _feed_message(snapshot: MarketSnapshot) -> ExplanationText | None:
    """REQ-049 AC-5's message when the feed is not live; the last update is the newest input time we hold."""
    if snapshot.status.health is DataHealth.AVAILABLE:
        return None
    return _not_live_label(snapshot)


def _start_losing(regions, idx, charges: Decimal | None = None) -> ExplanationText:
    """ADR-072: the sentence names every region where the engine's expiry P&L is below zero, nothing else. The levels
    are the pre-charges payoff's (spec sections 1 and 3); with the charges known, a sentence that names levels says
    they are before those charges (GC-UI D-A46)."""
    if not regions:
        return render_explanation("summary_start_never")
    if regions == ((None, None),):
        return render_explanation("summary_start_everywhere")
    if len(regions) == 1 and regions[0][:2] == (None, None):  # a loss everywhere but its single zero points (#172)
        if charges is None:
            return render_explanation("summary_start_touch", levels=regions[0][2])
        return render_explanation("summary_start_touch_with_charges", levels=regions[0][2], charges=charges)
    if charges is None:
        return render_explanation("summary_start_regions", index=idx, regions=regions)
    return render_explanation("summary_start_regions_with_charges", index=idx, regions=regions, charges=charges)


def exercise_stt_line(legs) -> ExplanationText | None:
    """Owner OQ-4 (a): the one line under the with-charges max-loss sentence when the strategy holds a bought option
    (exercise STT can then fall on it at expiry); None when nothing is bought. The text lives in one template."""
    return render_explanation("summary_lose_exercise_stt_note") if holds_bought_option(legs) else None


def _charges_breakdown(model: ModelInputs, underlying: str, rates: ChargeRates | None) -> ChargesBreakdown | None:
    """The one place the round trip is priced for an answer: None with no rate set or a leg the table cannot price."""
    if rates is None:
        return None
    try:
        return round_trip_breakdown(model.strategy.legs, underlying, rates)
    except ChargesNotComputable:
        return None


def _metrics_of(strategy) -> StrategyMetrics | None:
    """The engine's exact at-expiry metrics; None for legs on more than one expiry (futures legs included), which have
    no exact at-expiry payoff (G-065, ADR-143 (1)): no maximum, breakeven or loss region is made up for them."""
    return strategy_metrics(strategy) if strategy.is_single_expiry else None


def _mixed_expiry_summary(level_set: LevelSet, inputs: ModelInputs, charges: Decimal | None,
                          charges_unavailable: bool, spot: Decimal | None) -> Summary:
    """REQ-148 AC-4/AC-6: no single maximum, the ADR-143 worst-case line, the figures that do not need an exact
    at-expiry payoff (net premium, time and intrinsic value) kept; the ratio says why it is absent."""
    legs = inputs.strategy.legs
    ratio = money.reward_risk(None, None, single_expiry=False, charges_priced=charges is not None)
    split = money.time_and_intrinsic(legs, spot)
    return Summary(render_explanation("mixed_expiry_worst_case"), render_explanation("summary_make_mixed_expiry"),
                   render_explanation("summary_start_mixed_expiry"), None, None, False, False, (), None, None, (),
                   charges, charges_unavailable, reward_risk=ratio.reward_risk, reward_risk_reason=ratio.reason,
                   time_value=split.time, intrinsic_value=split.intrinsic, risk_reward=ratio.risk_reward,
                   net_premium=money.net_premium(legs), value_label=split.label, value_reason=split.reason)


def _summary(metrics: StrategyMetrics | None, level_set: LevelSet, inputs: ModelInputs,  # noqa: PLR0913
             charges: Decimal | None = None, charges_unavailable: bool = False, spot: Decimal | None = None) -> Summary:
    if metrics is None:
        return _mixed_expiry_summary(level_set, inputs, charges, charges_unavailable, spot)
    idx = inputs.underlying
    profit_unl, loss_unl = metrics.max_profit is UNLIMITED, metrics.max_loss is UNLIMITED
    max_loss = metrics.max_loss if loss_unl or charges is None else metrics.max_loss + charges  # ADR-082 (2)
    max_profit = metrics.max_profit if profit_unl or charges is None else metrics.max_profit - charges
    if loss_unl:
        lose = render_explanation("summary_lose_unlimited", index=idx)
    else:  # a zero maximum loss reads "At most ₹0.00 at expiry." - "cannot lose" is a banned phrase (ADR-003)
        lose = (render_explanation("summary_lose_at_most", amount=max_loss) if charges is None else
                join_explanations([
                    render_explanation("summary_lose_at_most_with_charges", amount=max_loss, charges=charges),
                    *filter(None, [exercise_stt_line(inputs.strategy.legs)])], " "))
    if profit_unl:
        make = render_explanation("summary_make_unlimited", index=idx)
    elif max_profit <= 0:
        make = render_explanation("summary_make_none")
    elif charges is None:
        make = render_explanation("summary_make_at_most", amount=max_profit)
    else:
        make = render_explanation("summary_make_at_most_with_charges", amount=max_profit, charges=charges)
    lo, up = level_set.lower_be, level_set.upper_be
    start = _start_losing(metrics.loss_regions, idx, charges)
    legs = inputs.strategy.legs
    shown_profit, shown_loss = None if profit_unl else max_profit, None if loss_unl else max_loss
    ratio = money.reward_risk(shown_profit, shown_loss, single_expiry=inputs.strategy.is_single_expiry,
                              charges_priced=charges is not None)
    future_only = len(legs) == 1 and legs[0].instrument is Instrument.FUT
    if future_only:  # REQ-135 AC-4 (row 27): a futures leg holds no time and no intrinsic value
        nothing = Decimal(0).quantize(HUNDREDTH)
        split = money.ValueSplit(nothing, nothing, None, None)
    else:
        split = money.time_and_intrinsic(legs, spot)
    return Summary(lose, make, start, shown_profit, shown_loss, profit_unl, loss_unl, level_set.breakevens,
                   lo, up, level_set.risk_boundaries, charges, charges_unavailable,
                   reward_risk=ratio.reward_risk, reward_risk_reason=ratio.reason, time_value=split.time,
                   intrinsic_value=split.intrinsic, risk_reward=ratio.risk_reward,
                   net_premium=money.net_premium(legs), value_label=split.label, value_reason=split.reason)


def _refused(definition, reason: ExplanationText, legs, message=None) -> Outcome:
    return Outcome(OutcomeState.REFUSED, definition.underlying, join_labels(message, render_explanation("outcome_refused")),
                   reason, tuple(legs), MARGIN)


def _leg_iv(em, leg, shared, where):
    """One leg's implied volatility through the one engine; None when the engine has no answer for these inputs (a
    deterministic answer, so it is shared too: only a raised error is never cached). With ``shared`` the figure is
    computed once per (feed owner, underlying, expiry, quote instant, exact inputs). ``leg`` is
    (kind, price, strike, forward)."""
    kind, price, strike, fwd = leg

    def compute():
        try:
            return implied_vol(em, kind, price, strike).iv
        except (ValueError, ArithmeticError):
            return None

    if shared is None:
        return compute()
    inputs = (kind.value, strike, price, em.level, fwd.forward, fwd.implied_yield, fwd.years, fwd.rate,
              fwd.days_in_year)
    return shared.compute(where, inputs, compute)


def _shared_leg_greeks(model, snapshot, shared):
    """REQ-050 AC-1: each option leg's per-unit unrounded Greeks, computed once per (feed owner, underlying, expiry,
    snapshot instant, exact inputs) through the engine's one function; ``None`` for a futures leg or a leg with no IV
    (nothing is computed or cached for it), and for every leg when there is no ``shared`` scope."""
    if shared is None:
        return None
    out = []
    for leg in model.legs:
        if leg.instrument is Instrument.FUT or leg.iv is None:
            out.append(None)
            continue
        em = model.expiry_model(leg.expiry)
        f = em.forward
        where = (snapshot.underlying, leg.expiry, snapshot.valuation, "leg_greeks", leg.contract)
        inputs = (leg.instrument.value, leg.strike, leg.iv, em.level, f.forward, f.implied_yield, f.years, f.rate,
                  f.days_in_year, em.dividend_yield)
        out.append(shared.compute(where, inputs, lambda leg=leg: leg_greeks_unrounded(model, leg)))
    return out


def _usable(q: NormalizedQuote | None) -> bool:
    """A quote an IV may be solved from: present, a live last price (never 0) and a health that is not unusable - the
    same refusals a leg's quote gets in build_outcome."""
    return q is not None and q.ltp is not None and is_live_price(q.ltp) and q.health not in _UNUSABLE


def atm_iv(snapshot: MarketSnapshot, expiry: datetime.date, shared: FeedScope | None = None,
           known: Mapping[str, Decimal] | None = None) -> Decimal | None:
    """REQ-106 AC-1: the mean of the CE and PE implied volatilities at the strike of ``expiry``'s chain nearest that
    expiry's parity forward (ties: the lower strike), each solved like a leg's IV (same engine call, same price basis,
    same quote refusals). None when there is no forward or chain for the expiry, either quote is missing or unusable,
    or either IV is not solved. ``known``: IVs this answer already solved per instrument id (its legs), read back
    instead of solved twice - the same engine call on the same inputs."""
    fwd = snapshot.forwards.get(expiry)
    chain = [q for q in snapshot.chains.get(expiry, ()) if q.expiry == expiry and q.strike is not None
             and q.instrument_type in (Instrument.CE, Instrument.PE)]
    if fwd is None or not chain or snapshot.spot is None:
        return None
    strike = min({q.strike for q in chain}, key=lambda k: (abs(k - fwd.forward), k))
    try:
        em = expiry_model(spot_reading(snapshot.spot), fwd, underlying=snapshot.underlying)
    except (ValueError, ArithmeticError):
        return None
    ivs = []
    for kind in (Instrument.CE, Instrument.PE):
        q = next((x for x in chain if x.strike == strike and x.instrument_type is kind), None)
        if not _usable(q):
            return None
        where = (snapshot.underlying, expiry, snapshot.valuation, "leg_iv", q.instrument_id)
        iv = (known or {}).get(q.instrument_id) or _leg_iv(em, (kind, iv_price(q), strike, fwd), shared, where)
        if iv is None:
            return None
        ivs.append(iv)
    return (ivs[0] + ivs[1]) / 2


def _expected_move(legs, snapshot: MarketSnapshot, valuation: datetime.datetime,  # noqa: PLR0913
                   shared: FeedScope | None = None, known: Mapping[str, Decimal] | None = None, *,
                   horizon: int | None = None) -> ExpectedMove | None:
    """REQ-027 (Q254) / REQ-034 AC-4: the one expected move the product computes (the default range today; REQ-083's
    SD bands and REQ-027's suggestions call this too). IV = :func:`atm_iv` of the nearest leg expiry; days = calendar
    days from the valuation date in India time to that expiry, at least 1. None when there are no legs, the ATM IV is
    not solved, or the engine's ExpectedMove refuses the values: the range is then today's (spot, strikes, breakevens,
    risk boundaries)."""
    if not legs:
        return None
    expiry = min(leg.expiry for leg in legs)
    iv = atm_iv(snapshot, expiry, shared, known)
    if iv is None:
        return None
    days = max((expiry - valuation.astimezone(IST).date()).days, 1)
    if horizon is not None:  # D-B20 Fixed SD: at most ``horizon`` days
        days = min(days, horizon)
    try:
        return ExpectedMove(iv, days)
    except ValueError:
        return None


def _centre_of(strikes) -> Decimal:
    """The middle strike (the lower one of two) of the legs: with no live index price the grid has to centre
    somewhere, and this is the one place the answer says where (REQ-077 AC-9). No arithmetic: a strike of the legs."""
    ordered = sorted(set(strikes))
    return ordered[(len(ordered) - 1) // 2]


def _graph_points(graph: ScenarioValues) -> tuple[tuple[Decimal, Decimal], ...]:
    """The payoff graph's points: the engine's values at the graph levels (the table's columns plus every strike in
    range, GC-BM F-8), so the drawn line has its kinks at the strikes; none when the view is unavailable."""
    if not graph.available or graph.totals is None:
        return ()
    return tuple(zip(graph.levels, graph.totals, strict=True))


def standard_deviation(spot: Decimal | None, move: ExpectedMove | None) -> StandardDeviation:
    """REQ-083 AC-4 / REQ-137 AC-3: the ONE SD figure behind the chart's bands and the SD table, from
    :meth:`ExpectedMove.exact_points` (the one formula). No spot or no ATM IV: unavailable with the reason."""
    if spot is None:
        return StandardDeviation(False, render_explanation("sd_no_spot"))
    if move is None:
        return StandardDeviation(False, render_explanation("sd_no_iv"))
    one = move.exact_points(spot)
    rows = tuple(SdRow(n, (one * n).quantize(_TENTH, ROUND_HALF_UP),
                       (one * n / spot * 100).quantize(_TENTH, ROUND_HALF_UP),
                       (spot - one * n).quantize(_TENTH, ROUND_HALF_UP),
                       (spot + one * n).quantize(_TENTH, ROUND_HALF_UP)) for n in (1, 2))
    return StandardDeviation(True, None, move.days, move.iv, spot, rows)


def payoff_table_default_step(index: str) -> Decimal:
    """REQ-137 AC-1: the payoff table's interval when none is picked (the underlying's strike step). An index with no
    stated strike step is refused, never given another index's step."""
    try:
        return PAYOFF_TABLE_DEFAULT_STEPS[index]
    except KeyError:
        raise ValueError(f"no payoff table strike step is stated for {index!r} (REQ-137 AC-1)") from None


def payoff_table(level_set: LevelSet, model: ModelInputs, step: Decimal | None, *,  # noqa: PLR0913
                 config: ScenarioConfig, rates: ChargeRates | None, spot: Decimal | None,
                 no_estimate: ExplanationText | None = None) -> PayoffTable:
    """REQ-137 AC-1: rows from the first multiple of ``step`` at or above the range start to the range end; each view
    from :func:`scenario_values` on those levels (the one engine). ``step`` None: the underlying's strike step
    (REQ-137 AC-1, :func:`payoff_table_default_step`), never the grid's Admin step.
    ``no_estimate``: Estimated Now cannot be computed (no live prices) and carries this reason."""
    if step is None:
        step = payoff_table_default_step(config.index)
    elif step not in PAYOFF_TABLE_STEPS or not isinstance(step, Decimal):
        raise ValueError(f"payoff table step must be one of {PAYOFF_TABLE_STEPS}, got {step!r}")
    first = first_multiple_at_or_above(level_set.start, step)
    count = 0 if first > level_set.end else int((level_set.end - first) / step) + 1
    if count > MAX_PAYOFF_TABLE_ROWS:
        return PayoffTable(step, (), None, (), render_explanation("payoff_table_too_many_rows", step=step))
    levels = tuple(first + step * i for i in range(count))
    table_set = dataclasses.replace(level_set, columns=tuple(LevelColumn(lvl, frozenset({ColumnKind.GRID}))
                                                             for lvl in levels))
    views = []
    for v in (View.ESTIMATED_NOW, View.AT_EXPIRY):
        if v is View.ESTIMATED_NOW and no_estimate is not None:
            views.append(ScenarioValues(v, LABELS[v], "estimate", levels, False, no_estimate, None, None))
        else:
            views.append(scenario_values(table_set, model, v, rates=rates))
    nearest = None if spot is None or not levels else min(levels, key=lambda x: (abs(x - spot), x))
    return PayoffTable(step, levels, nearest, tuple(views), spot=spot)


def _other(view: View) -> View:
    return View.ESTIMATED_NOW if view is View.AT_EXPIRY else View.AT_EXPIRY


def _both(graph: ScenarioValues, other_graph: ScenarioValues,
          level_set: LevelSet) -> tuple[tuple[ScenarioValues, ...], ScenarioValues]:
    """REQ-083 AC-1: the two views over the one graph level set, At Expiry first, and the other view cut to the table's
    columns. Both come from :func:`scenario_values` on the same inputs and levels; nothing here prices a level."""
    if graph.levels != other_graph.levels:
        raise ValueError("the two curves were computed on different levels")
    pair = (graph, other_graph) if graph.view is View.AT_EXPIRY else (other_graph, graph)
    return pair, on_levels(other_graph, level_set)


def _no_current(level_set: LevelSet) -> LevelSet:
    """The centre is not a market price: no column of the grid is marked CURRENT."""
    cols = []
    for c in level_set.columns:
        kinds = c.kinds - {ColumnKind.CURRENT}
        if kinds:  # a column that existed only as CURRENT (an off-grid centre) is dropped
            cols.append(LevelColumn(c.level, kinds))
    return dataclasses.replace(level_set, columns=tuple(cols))


def from_entries(definition: StrategyDefinition, snapshot: MarketSnapshot | None, stored,  # noqa: PLR0913
                 valuation: datetime.datetime, *, view: View = DEFAULT_VIEW, config: ScenarioConfig | None = None,
                 rates: ChargeRates | None = None, override: RangeOverride | None = None,
                 both_views: bool = False, payoff_step: Decimal | None = None,
                 sd_bands: bool = False, target: TargetAsk | None = None) -> Outcome | None:
    """REQ-077 AC-9: with no live data, a strategy whose EVERY leg has a planned entry shows its At Expiry numbers
    from the one engine at those prices, labelled "From your prices - no live data". Returns None (the caller keeps
    today's not-connected / not-live answer, ADR-085) when any leg has no entry, a contract is unknown, the legs are
    not one expiry or there is no strike to centre on. No price here is live: no LTP, IV, Greek, bid/ask or index
    price is set; Estimated Now is unavailable with its reason. When live data DROPPED (a snapshot that held a quote),
    ``status_label`` is REQ-049 AC-5's message with its last-update time (REQ-049 AC-5 and REQ-077 AC-9 both hold);
    ``output_label`` always carries the from-your-prices label."""
    if any(p.planned_entry is None for p in definition.legs):
        return None
    legs: list[OutcomeLeg] = []
    inputs: list[LegInput] = []
    for p in definition.legs:
        lm = None if snapshot is None else snapshot.legs.get(p.instrument_id)
        listed = lm.contract if lm is not None and lm.contract is not None else (stored or {}).get(p.instrument_id)
        if listed is None:
            return None
        c = listed.contract
        symbol, kind, strike, _expiry = _contract_fields(snapshot, p.instrument_id, stored)
        quantity = p.lots * c.lot_size
        legs.append(OutcomeLeg(p.instrument_id, symbol, p.action, kind, strike, c.expiry, p.lots, c.lot_size, quantity,
                               p.planned_entry, p.captured_at, None, None, None, None))
        inputs.append(LegInput(definition.underlying, symbol or p.instrument_id, p.action, kind, strike, c.expiry,
                               quantity, p.planned_entry))
    config = config or ScenarioSettings().for_index(definition.underlying)
    strikes = [leg.strike for leg in inputs if leg.strike is not None]
    if not strikes:
        return None
    centre = _centre_of(strikes)
    rate = Decimal(0)  # At Expiry uses no rate or forward; the gate needs one consistent value
    try:
        reading = SpotReading(centre, valuation, DataHealth.AVAILABLE)
        forwards = {leg.expiry: spot_fallback_forward(leg.expiry, centre, valuation, valuation, rate)
                    for leg in inputs}
        model = model_inputs(StrategyInput(definition.underlying, reading, valuation, rate, tuple(inputs)), forwards)
        level_set = _no_current(build_level_set(model, config, override=override))
    except (MultiExpiryError, ForwardUnavailable):
        return None
    breakdown = _charges_breakdown(model, definition.underlying, rates)
    charges = None if breakdown is None else breakdown.total
    # the ONE computation: always the At Expiry view; Estimated Now needs live prices and is never computed here
    graph = scenario_values(graph_level_set(level_set, model), model, View.AT_EXPIRY,
                            rates=None if charges is None else rates)
    values = on_levels(graph, level_set)  # the table's columns (Q33D = C); the graph keeps the strikes (F-8)

    def no_estimate(levels):
        return ScenarioValues(View.ESTIMATED_NOW, LABELS[View.ESTIMATED_NOW], "estimate", levels, False,
                              render_explanation("outcome_from_entries_no_estimate"), None, None,
                              spot_level=values.spot_level, spot_at=values.spot_at)

    shown = no_estimate(values.levels) if view is View.ESTIMATED_NOW else values
    curves, other = ((), None)
    if both_views:  # Estimated Now needs live prices: its curve is unavailable with the same reason
        curves, other = _both(graph, no_estimate(graph.levels), level_set)
        other = values if view is View.ESTIMATED_NOW else other
    table_p = None
    if both_views or payoff_step is not None:
        table_p = payoff_table(level_set, model, payoff_step, config=config, rates=None if charges is None else rates,
                               spot=None, no_estimate=render_explanation("outcome_from_entries_no_estimate"))
    table = dataclasses.replace(build_table(model, level_set=level_set, scenario=shown), spot_level=None, spot_at=None,
                                output_label=FROM_ENTRIES_LABEL)
    points = _graph_points(graph) if shown.available else ()
    dropped = None if snapshot is None else _not_live_label(snapshot)
    if dropped is NOT_CONNECTED_LABEL:  # no quote was ever held: nothing dropped, no last update to name
        dropped = None
    return Outcome(
        state=OutcomeState.FROM_ENTRIES, underlying=definition.underlying, status_label=dropped or FROM_ENTRIES_LABEL,
        reason=None, legs=tuple(legs), margin=MARGIN, valuation=valuation, output_label=FROM_ENTRIES_LABEL,
        spot_level=None, spot_at=None, level_set=level_set, scenario=shown, table=table,
        visible_columns=visible_columns(table), payoff_points=points,
        summary=_summary(_metrics_of(model.strategy), level_set, model, charges, charges is None),
        charges_breakdown=breakdown, centre_label=render_explanation("outcome_from_entries_centre", level=centre),
        curves=curves, other_view=other, payoff_table=table_p,
        standard_deviation=standard_deviation(None, None) if sd_bands else None,
        target=(entries_target(target, model, payoff_table_default_step(definition.underlying))
                if target is not None and target.asked
                else target_offer(model, payoff_table_default_step(definition.underlying), live=False)))


def build_outcome(definition: StrategyDefinition, snapshot: MarketSnapshot | None,
                  valuation: datetime.datetime | None = None, *,
                  view: View = DEFAULT_VIEW, config: ScenarioConfig | None = None,
                  rates: ChargeRates | None = None,
                  override: RangeOverride | None = None, shared: FeedScope | None = None,
                  both_views: bool = False, payoff_step: Decimal | None = None,
                  sd_bands: bool = False, target: TargetAsk | None = None) -> Outcome:
    """The outcome of ``definition`` on ``snapshot``; ``valuation`` defaults to the snapshot's valuation time.

    ``shared`` (REQ-050 AC-1/AC-3, ADR-053): a :class:`FeedScope` (the cache plus the feed's owner). Each leg's
    market-wide IV and per-unit Greeks are then computed once per feed snapshot and read back by every other reader of
    the same feed; the owner is part of the key, so two users' feeds never share. Without ``shared`` every call
    computes itself.

    ``rates`` (ADR-082 (2)): the charge rates in force. Given, the maximum-loss / maximum-profit sentences and the At
    Expiry values include the round-trip charges at the planned prices; None, or a leg the rate table cannot price,
    keeps the values before charges, ADR-071's phrase, and ``Summary.charges_unavailable``. Breakevens, risk
    boundaries and the zero-P&L columns are the locked ADR-008 values and never move with charges."""
    if not isinstance(definition, StrategyDefinition):
        raise ValueError(f"definition must be a StrategyDefinition, got {definition!r}")
    if snapshot is None:
        return not_connected(definition, snapshot)
    if snapshot.status.session_ended:  # REQ-077 AC-9 "with no live data" includes an ended session
        return (from_entries(definition, snapshot, None, snapshot.valuation, view=view, rates=rates, config=config,
                             override=override, both_views=both_views, payoff_step=payoff_step,
                             sd_bands=sd_bands, target=target)
                or not_connected(definition, snapshot))
    if snapshot.underlying != definition.underlying:
        raise ValueError("the snapshot was read for another underlying")
    valuation = snapshot.valuation if valuation is None else valuation
    if valuation != snapshot.valuation:
        raise ValueError("the snapshot's forwards were read at another valuation time")
    closed = snapshot.market_closed  # ADR-200: a STALE quote is then the last close held from the session
    # REQ-049 AC-5's "disconnected" message names a drop; a closed market is expected silence (the banner says it)
    message = None if closed else _feed_message(snapshot)

    legs: list[OutcomeLeg] = []
    inputs: list[LegInput] = []
    problems: list[ExplanationText] = []
    for p in definition.legs:
        lm = snapshot.legs.get(p.instrument_id)
        if p.planned_entry is None:  # an unpriced leg (ADR-085) is never computed
            why = render_explanation("draft_leg_needs_reprice")
            problems.append(render_explanation("outcome_problem_leg", leg=p.instrument_id, why=why))
            legs.append(OutcomeLeg(p.instrument_id, None, p.action, None, None, None, p.lots, None, None,
                                   None, p.captured_at, None, None, None, why))
            continue
        if lm is None or lm.contract is None or lm.problem is not None:
            why = (lm.problem if lm is not None and lm.problem is not None
                   else render_explanation("outcome_why_not_in_snapshot"))
            problems.append(render_explanation("outcome_problem_leg", leg=p.instrument_id, why=why))
            legs.append(OutcomeLeg(p.instrument_id, None, p.action, None, None, None, p.lots, None, None,
                                   p.planned_entry, p.captured_at, None, None, None, why))
            continue
        c = lm.contract.contract
        symbol, kind, strike, _expiry = _contract_fields(snapshot, p.instrument_id)
        q = lm.quote
        ltp = iv = None
        if q is None or (q.ltp is not None and not is_live_price(q.ltp)):  # a last price of 0 is no live price
            label = render_explanation("leg_label_no_quote")
        elif q.health in _UNUSABLE or q.ltp is None or (closed and not planning_price_usable(q, market_closed=True)):
            label = (render_explanation("leg_label_quote_unusable", health=q.health) if q.ltp is not None
                     else render_explanation("leg_label_quote_no_price"))
        else:
            # ADR-200 (2): after hours the held last close sits under the one market-closed banner (the answer's
            # ``market_closed`` + ``last_price_at``), never under "stale since"; in hours the stale label as before
            ltp, label = q.ltp, (None if closed else _quote_label(q))
            fwd = snapshot.forwards.get(c.expiry)
            if kind is not Instrument.FUT and fwd is not None and snapshot.spot is not None:
                price = iv_price(q)
                try:
                    em = expiry_model(spot_reading(snapshot.spot), fwd, underlying=definition.underlying)
                    where = (snapshot.underlying, c.expiry, snapshot.valuation, "leg_iv", p.instrument_id)
                    iv = _leg_iv(em, (kind, price, strike, fwd), shared, where)
                except (ValueError, ArithmeticError):
                    iv = None
                if iv is None:
                    label = join_labels(label, render_explanation("leg_label_no_iv"))
        quantity = p.lots * c.lot_size
        legs.append(OutcomeLeg(p.instrument_id, symbol, p.action, kind, strike, c.expiry, p.lots, c.lot_size,
                               quantity, p.planned_entry, p.captured_at, ltp, iv, None if q is None else q.health,
                               label))
        try:
            inputs.append(LegInput(definition.underlying, symbol or p.instrument_id, p.action, kind, strike,
                                   c.expiry, quantity, p.planned_entry, ltp, iv))
        except ValueError:  # the cause goes to no user (W-066): a closed reason
            problems.append(render_explanation("outcome_problem_leg", leg=p.instrument_id,
                                               why=render_explanation("outcome_why_leg_input")))
    for expiry, why in snapshot.forward_errors.items():
        if any(leg.expiry == expiry for leg in inputs):
            problems.append(render_explanation("outcome_forward_error", expiry=expiry, why=why))
    if problems:
        return _refused(definition, join_explanations(problems, "; "), legs, message)

    try:
        if closed and snapshot.spot is not None and not planning_price_usable(snapshot.spot, market_closed=True):
            raise SpotRefused("a closed market's held index quote is not sound")  # ADR-200 (4): never a default
        spot = spot_reading(snapshot.spot)
        model = model_inputs(StrategyInput(definition.underlying, spot, valuation, snapshot.rate, tuple(inputs)),
                             snapshot.forwards)
        if closed:  # ADR-200 (2): one place drops "stale since" for every output built from the model
            model = market_closed_model(model)
    except SpotRefused:
        spot_q = snapshot.spot
        if spot_q is None or not is_live_price(spot_q.ltp):
            reason = render_explanation("outcome_spot_missing", underlying=definition.underlying)
        else:
            reason = render_explanation("outcome_spot_unusable", underlying=definition.underlying,
                                        health=spot_q.health)
        return _refused(definition, reason, legs, message)
    except ForwardUnavailable:
        return _refused(definition, render_explanation("outcome_forward_refused"), legs, message)

    config = config or ScenarioSettings().for_index(definition.underlying)
    solved = {x.instrument_id: x.iv for x in legs if x.iv is not None}
    move = _expected_move(inputs, snapshot, valuation, shared, solved)
    level_set = build_level_set(model, config, expected_move=move, override=override)
    breakdown = _charges_breakdown(model, definition.underlying, rates)
    charges = None if breakdown is None else breakdown.total
    # the ONE computation (AC-8)
    graph_levels = graph_level_set(level_set, model)
    graph = scenario_values(graph_levels, model, view, rates=None if charges is None else rates)
    values = on_levels(graph, level_set)  # the table's columns (Q33D = C); the graph keeps the strikes (F-8)
    curves, other = ((), None)
    if both_views:  # REQ-083 AC-1: the other view from the same engine, on the same graph levels and inputs
        curves, other = _both(graph, scenario_values(graph_levels, model, _other(view),
                                                     rates=None if charges is None else rates), level_set)
    table_p = None
    if both_views or payoff_step is not None:
        table_p = payoff_table(level_set, model, payoff_step, config=config, rates=None if charges is None else rates,
                               spot=model.spot_level)
    sd = None
    if sd_bands:  # the same expected move as the range, on the fixed horizon (D-B20)
        sd = standard_deviation(model.spot_level, _expected_move(inputs, snapshot, valuation, shared, solved,
                                                                 horizon=SD_HORIZON_DAYS))
    table = build_table(model, level_set=level_set, scenario=values,
                        leg_greeks=_shared_leg_greeks(model, snapshot, shared))
    points = _graph_points(graph)
    # Issue 297: a leg's own notice stays on `legs[].label`; the page prints it once under the leg's contract name.
    # The answer-level label carries only the data/model label (never a raw trading symbol, never a notice twice).
    return Outcome(
        state=OutcomeState.COMPUTED, underlying=definition.underlying, status_label=message,
        reason=None, legs=tuple(legs), margin=MARGIN, valuation=valuation,
        output_label=model.label, spot_level=model.spot_level,
        spot_at=model.spot_at,
        level_set=level_set, scenario=values, table=table, visible_columns=visible_columns(table),
        payoff_points=points,
        summary=_summary(_metrics_of(model.strategy), level_set, model, charges, charges is None,
                         spot=model.spot_level),
        charges_breakdown=breakdown, curves=curves, other_view=other, payoff_table=table_p,
        standard_deviation=sd,
        target=(live_target(target, model, graph_levels, payoff_table_default_step(definition.underlying))
                if target is not None and target.asked
                else target_offer(model, payoff_table_default_step(definition.underlying), live=True)))
