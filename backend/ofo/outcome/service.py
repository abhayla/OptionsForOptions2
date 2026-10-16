"""The outcome of a draft strategy: one table, one set of scenario values, the payoff and the summary (W-063).

Spec: REQ-034 AC-1 (every part of the outcome view), AC-7 (plain language first), AC-8 (payoff graph and scenario table
from the same engine); REQ-033 AC-1/AC-3 (the leg formulas; expiry scenarios use the entry price, never the LTP);
ADR-008 (one engine, exact Decimal); ADR-061 (each expiry's forward; spot for CURRENT and the range); ADR-068 (planned
entry with its capture time; UX level per request, presentation only; the not-live labels).

AC-8 by construction: :func:`build_outcome` computes the scenario values ONCE (``scenario_values``) and both the table
(``build_table``) and the payoff points are taken from that one ``ScenarioValues``; nothing here prices a level.

Answer states (run-discipline B4 (d)), each with its label or refusal:

- no provider / no Zerodha session: ``NOT_CONNECTED``, "Draft — Live data not connected" (ADR-068, ADR-020 Q185).
- all inputs live: ``COMPUTED``, no data label.
- spot STALE/DELAYED: ``COMPUTED`` and every number carries "stale since HH:MM IST" (REQ-072 AC-2); when the feed has
  dropped, REQ-049 AC-5's message is added.
- spot missing / UNHEALTHY / UNAVAILABLE: ``REFUSED`` (SpotRefused reason).
- a forward fallback: ``COMPUTED``, labelled "estimated from spot" (ADR-061).
- a leg quote STALE/DELAYED: its LTP is used and the leg carries "stale since HH:MM IST"; the outcome label lists it.
- a leg with no quote, or an UNHEALTHY/UNAVAILABLE one: its LTP and IV are not used (live P&L and Greeks show "—" with
  a reason), the leg carries "no live quote" / "quote unhealthy"; expiry scenarios still use the planned entry.
- an expired or unknown leg, or a refused forward: ``REFUSED`` naming the leg / expiry.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Final

from ofo.charges import ChargeRates
from ofo.charges.round_trip import ChargesNotComputable, holds_bought_option, round_trip_charges
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.metrics import UNLIMITED, StrategyMetrics, strategy_metrics
from ofo.engine.model import (ModelInputs, SpotRefused, data_label, expiry_model, implied_vol, join_labels,
                              model_inputs)
from ofo.instruments.models import ZERODHA
from ofo.errors.explanations import ExplanationText, join_explanations, render_explanation
from ofo.marketdata.forward import ForwardUnavailable, mid_price
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.money import HUNDREDTH
from ofo.outcome.snapshot import MarketSnapshot
from ofo.rules.inputs import DataHealth
from ofo.scenario.config import ScenarioConfig, ScenarioSettings
from ofo.scenario.levels import LevelSet, build_level_set
from ofo.scenario.spot import spot_reading
from ofo.scenario.views import DEFAULT_VIEW, ScenarioValues, View, scenario_values
from ofo.table import ColumnSpec, Table, UXLevel, build_table, visible_columns

NOT_CONNECTED_LABEL: Final = render_explanation("outcome_not_connected")
MARGIN_NOT_AVAILABLE_YET: Final = "NOT_AVAILABLE_YET"
#: ADR-099 margin states: Zerodha's figures read for the planned orders / Zerodha could not be read / the planned orders
#: cannot be sent to Zerodha (a leg that is not a listed Zerodha contract). No session stays NOT_AVAILABLE_YET.
MARGIN_CHECKED: Final = "CHECKED"
MARGIN_UNREADABLE: Final = "UNREADABLE"
MARGIN_NO_BASKET: Final = "NO_BASKET"
_UNUSABLE: Final = (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE)


class OutcomeState(Enum):
    COMPUTED = "COMPUTED"
    NOT_CONNECTED = "NOT_CONNECTED"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class PlannedLeg:
    """A draft leg (ADR-068): the instrument, side, lots and the planned entry with the time it was captured."""

    instrument_id: str
    action: Action
    lots: int
    planned_entry: Decimal
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
    planned_entry: Decimal
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


@dataclass(frozen=True)
class Margin:
    """The margin block (ADR-099). ``needed`` / ``available`` / ``checked_at`` are set only in the CHECKED state: the
    amount needed is Zerodha's basket figure plus the ADR-094 top-up (a closing basket counts as 0), ``available`` is
    Zerodha's available funds, ``checked_at`` when Zerodha was read (ADR-088). Every other state carries no figure."""

    state: str
    reason: ExplanationText
    needed: Decimal | None = None
    available: Decimal | None = None
    checked_at: datetime.datetime | None = None


@dataclass(frozen=True)
class Outcome:
    state: OutcomeState
    underlying: str
    ux_level: UXLevel
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


MARGIN: Final = Margin(MARGIN_NOT_AVAILABLE_YET, render_explanation("outcome_margin_pending"))


def margin_checked(needed: Decimal, available: Decimal, checked_at: datetime.datetime) -> Margin:
    """ADR-099: Zerodha's two figures and the time they were read, each shown to the paisa as Zerodha shows them
    (half up: Kite's float noise 68498.85000000001 reads 68498.85). Display only: the gate (REQ-055) compares the
    unrounded figures."""
    for value in (needed, available):
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("a margin figure must be a finite Decimal")
    if not isinstance(checked_at, datetime.datetime) or checked_at.tzinfo is None:
        raise ValueError("checked_at must be a timezone-aware datetime")
    need = needed.quantize(HUNDREDTH, rounding=ROUND_HALF_UP)
    have = available.quantize(HUNDREDTH, rounding=ROUND_HALF_UP)
    return Margin(MARGIN_CHECKED, render_explanation("outcome_margin_checked", needed=need, available=have,
                                                     time=checked_at), need, have, checked_at)


def margin_unreadable() -> Margin:
    """ADR-099: Zerodha could not be read; no figure is made up."""
    return Margin(MARGIN_UNREADABLE, render_explanation("outcome_margin_unreadable"))


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


def not_connected(definition: StrategyDefinition, ux_level: UXLevel = UXLevel.STANDARD,
                  snapshot: MarketSnapshot | None = None, stored=None) -> Outcome:
    """No provider or no Zerodha session (ADR-068 consequence, ADR-020 Q185): a state, never an error. With a
    ``snapshot`` (a session that ended) the legs name their contract; with none, ``stored`` (instrument id -> the stored
    catalogue entry, #249) names them, and a contract it lacks stays unnamed."""
    legs = _unpriced_legs(definition, snapshot, NOT_CONNECTED_LABEL, stored)
    return Outcome(OutcomeState.NOT_CONNECTED, definition.underlying, ux_level, NOT_CONNECTED_LABEL,
                   render_explanation("outcome_reason_no_provider"), legs, MARGIN)


def not_live(definition: StrategyDefinition, snapshot: MarketSnapshot,
             ux_level: UXLevel = UXLevel.STANDARD) -> Outcome:
    """The live market is connected but this strategy's inputs are not streaming (no subscriber on the shared feed, e.g.
    the REST fallback while the socket is down; ADR-068 (2) "labelled as not live"). No number is shown as live
    (REQ-049 AC-4): the state carries REQ-049 AC-5's message with the newest input time held, per leg too. Each leg
    names its contract (ADR-086), from the same snapshot lookup the computed answer uses."""
    label = _not_live_label(snapshot)
    legs = _unpriced_legs(definition, snapshot, label)
    return Outcome(OutcomeState.NOT_CONNECTED, definition.underlying, ux_level, label, None, legs, MARGIN)


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


def _start_losing(regions, idx) -> ExplanationText:
    """ADR-072: the sentence names every region where the engine's expiry P&L is below zero, nothing else."""
    if not regions:
        return render_explanation("summary_start_never")
    if regions == ((None, None),):
        return render_explanation("summary_start_everywhere")
    if len(regions) == 1 and regions[0][:2] == (None, None):  # a loss everywhere but its single zero points (#172)
        return render_explanation("summary_start_touch", levels=regions[0][2])
    return render_explanation("summary_start_regions", index=idx, regions=regions)


def exercise_stt_line(legs) -> ExplanationText | None:
    """Owner OQ-4 (a): the one line under the with-charges max-loss sentence when the strategy holds a bought option
    (exercise STT can then fall on it at expiry); None when nothing is bought. The text lives in one template."""
    return render_explanation("summary_lose_exercise_stt_note") if holds_bought_option(legs) else None


def _summary(metrics: StrategyMetrics, level_set: LevelSet, inputs: ModelInputs,
             charges: Decimal | None = None, charges_unavailable: bool = False) -> Summary:
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
    start = _start_losing(metrics.loss_regions, idx)
    return Summary(lose, make, start, None if profit_unl else max_profit,
                   None if loss_unl else max_loss, profit_unl, loss_unl, level_set.breakevens,
                   lo, up, level_set.risk_boundaries, charges, charges_unavailable)


def _refused(definition, ux_level, reason: ExplanationText, legs, message=None) -> Outcome:
    return Outcome(OutcomeState.REFUSED, definition.underlying, ux_level, join_labels(message, render_explanation("outcome_refused")),
                   reason, tuple(legs), MARGIN)


def build_outcome(definition: StrategyDefinition, snapshot: MarketSnapshot | None,
                  ux_level: UXLevel = UXLevel.STANDARD, valuation: datetime.datetime | None = None, *,
                  view: View = DEFAULT_VIEW, config: ScenarioConfig | None = None,
                  rates: ChargeRates | None = None) -> Outcome:
    """The outcome of ``definition`` on ``snapshot``; ``valuation`` defaults to the snapshot's valuation time.

    ``rates`` (ADR-082 (2)): the charge rates in force. Given, the maximum-loss / maximum-profit sentences and the At
    Expiry values include the round-trip charges at the planned prices; None, or a leg the rate table cannot price,
    keeps the values before charges, ADR-071's phrase, and ``Summary.charges_unavailable``. Breakevens, risk
    boundaries and the zero-P&L columns are the locked ADR-008 values and never move with charges."""
    if not isinstance(definition, StrategyDefinition):
        raise ValueError(f"definition must be a StrategyDefinition, got {definition!r}")
    if not isinstance(ux_level, UXLevel):
        raise ValueError(f"ux_level must be a UXLevel, got {ux_level!r}")
    if snapshot is None or snapshot.status.session_ended:
        return not_connected(definition, ux_level, snapshot)
    if snapshot.underlying != definition.underlying:
        raise ValueError("the snapshot was read for another underlying")
    valuation = snapshot.valuation if valuation is None else valuation
    if valuation != snapshot.valuation:
        raise ValueError("the snapshot's forwards were read at another valuation time")
    message = _feed_message(snapshot)

    legs: list[OutcomeLeg] = []
    inputs: list[LegInput] = []
    problems: list[ExplanationText] = []
    for p in definition.legs:
        lm = snapshot.legs.get(p.instrument_id)
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
        elif q.health in _UNUSABLE or q.ltp is None:
            label = (render_explanation("leg_label_quote_unusable", health=q.health) if q.ltp is not None
                     else render_explanation("leg_label_quote_no_price"))
        else:
            ltp, label = q.ltp, _quote_label(q)
            fwd = snapshot.forwards.get(c.expiry)
            if kind is not Instrument.FUT and fwd is not None and snapshot.spot is not None:
                price = mid_price(q.bid, q.ask) if q.bid and q.ask and q.ask >= q.bid else q.ltp
                try:
                    em = expiry_model(spot_reading(snapshot.spot), fwd, underlying=definition.underlying)
                    iv = implied_vol(em, kind, price, strike).iv
                except (ValueError, ArithmeticError):
                    iv = None
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
        return _refused(definition, ux_level, join_explanations(problems, "; "), legs, message)

    try:
        spot = spot_reading(snapshot.spot)
        model = model_inputs(StrategyInput(definition.underlying, spot, valuation, snapshot.rate, tuple(inputs)),
                             snapshot.forwards)
    except SpotRefused:
        spot_q = snapshot.spot
        if spot_q is None or not is_live_price(spot_q.ltp):
            reason = render_explanation("outcome_spot_missing", underlying=definition.underlying)
        else:
            reason = render_explanation("outcome_spot_unusable", underlying=definition.underlying,
                                        health=spot_q.health)
        return _refused(definition, ux_level, reason, legs, message)
    except ForwardUnavailable:
        return _refused(definition, ux_level, render_explanation("outcome_forward_refused"), legs, message)

    config = config or ScenarioSettings().for_index(definition.underlying)
    level_set = build_level_set(model, config)
    charges = None
    if rates is not None:
        try:
            charges = round_trip_charges(model.strategy.legs, definition.underlying, rates)
        except ChargesNotComputable:
            charges = None
    # the ONE computation (AC-8)
    values = scenario_values(level_set, model, view, rates=None if charges is None else rates)
    table = build_table(model, level_set=level_set, scenario=values)
    points = tuple(zip(values.levels, values.totals)) if values.available and values.totals is not None else ()
    # Issue 297: a leg's own notice stays on `legs[].label`; the page prints it once under the leg's contract name.
    # The answer-level label carries only the data/model label (never a raw trading symbol, never a notice twice).
    return Outcome(
        state=OutcomeState.COMPUTED, underlying=definition.underlying, ux_level=ux_level, status_label=message,
        reason=None, legs=tuple(legs), margin=MARGIN, valuation=valuation,
        output_label=model.label, spot_level=model.spot_level, spot_at=model.spot_at,
        level_set=level_set, scenario=values, table=table, visible_columns=visible_columns(table, ux_level),
        payoff_points=points,
        summary=_summary(strategy_metrics(model.strategy), level_set, model, charges, charges is None))
