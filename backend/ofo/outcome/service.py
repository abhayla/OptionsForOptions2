"""The outcome of a draft strategy: one table, one set of scenario values, the payoff and the summary (W-063).

Spec: REQ-034 AC-1 (every part of the outcome view), AC-7 (plain language first), AC-8 (payoff graph and scenario table
from the same engine); REQ-033 AC-1/AC-3 (the leg formulas; expiry scenarios use the entry price, never the LTP);
ADR-008 (one engine, exact Decimal); ADR-061 (each expiry's forward; spot for CURRENT and the range); ADR-068 (planned
entry with its capture time; the not-live labels).

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

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from collections.abc import Mapping
from enum import Enum
from typing import Final

from ofo.charges import ChargeRates
from ofo.charges.round_trip import ChargesNotComputable, holds_bought_option, round_trip_charges
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.metrics import UNLIMITED, MultiExpiryError, StrategyMetrics, strategy_metrics
from ofo.engine.model import (ModelInputs, SpotRefused, data_label, expiry_model, implied_vol, join_labels,
                             leg_greeks_unrounded, model_inputs)
from ofo.errors.explanations import ExplanationText, join_explanations, render_explanation
from ofo.instruments.models import ZERODHA
from ofo.marketdata.forward import ForwardUnavailable, mid_price, spot_fallback_forward
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.marketdata.shared_compute import FeedScope
from ofo.money import HUNDREDTH
from ofo.outcome.snapshot import MarketSnapshot
from ofo.rules.inputs import DataHealth
from ofo.scenario.config import ScenarioConfig, ScenarioSettings
from ofo.scenario.levels import ColumnKind, ExpectedMove, LevelColumn, LevelSet, RangeOverride, build_level_set
from ofo.scenario.spot import spot_reading
from ofo.scenario.views import DEFAULT_VIEW, LABELS, ScenarioValues, View, scenario_values
from ofo.table import ColumnSpec, Table, build_table, visible_columns
from ofo.timeutil import IST

NOT_CONNECTED_LABEL: Final = render_explanation("outcome_not_connected")
#: REQ-077 AC-9: the label of an At Expiry answer built from the user's own prices when there is no live data
FROM_ENTRIES_LABEL: Final = render_explanation("outcome_from_entries")
MARGIN_NOT_AVAILABLE_YET: Final = "NOT_AVAILABLE_YET"
#: ADR-099 margin states: Zerodha's figures read for the planned orders / Zerodha could not be read / the planned orders
#: cannot be sent to Zerodha (a leg that is not a listed Zerodha contract). No session stays NOT_AVAILABLE_YET.
MARGIN_CHECKED: Final = "CHECKED"
MARGIN_UNREADABLE: Final = "UNREADABLE"
MARGIN_NO_BASKET: Final = "NO_BASKET"
_UNUSABLE: Final = (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE)


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
    shortfall: bool = False  # CHECKED only: Zerodha's available funds are below the amount needed (Decimal compare)


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


MARGIN: Final = Margin(MARGIN_NOT_AVAILABLE_YET, render_explanation("outcome_margin_pending"))


def margin_checked(needed: Decimal, available: Decimal, checked_at: datetime.datetime) -> Margin:
    """ADR-099: Zerodha's two figures and the time they were read. Both arrive already rounded half-up to the paisa
    where they were parsed (ADR-101: Kite's float noise 68498.85000000001 reads 68498.85); any rounding left here is on
    the safe side (needed UP, funds DOWN) for figures not from Kite, and ``shortfall``
    compares exactly the two amounts shown, so the screen never shows equal figures with a shortfall mark, nor hides a
    shortfall the gate would block. Display only: the gate (REQ-055) is the check before the basket."""
    for value in (needed, available):
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("a margin figure must be a finite Decimal")
    if not isinstance(checked_at, datetime.datetime) or checked_at.tzinfo is None:
        raise ValueError("checked_at must be a timezone-aware datetime")
    need = needed.quantize(HUNDREDTH, rounding=ROUND_CEILING)
    have = available.quantize(HUNDREDTH, rounding=ROUND_FLOOR)
    return Margin(MARGIN_CHECKED, render_explanation("outcome_margin_checked", needed=need, available=have,
                                                     time=checked_at), need, have, checked_at, have < need)


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


def _iv_price(q: NormalizedQuote) -> Decimal | None:
    """The price an IV is solved from, for a leg and for the ATM pair alike: the bid-ask mid when both sides are there
    and not crossed, else the LTP."""
    return mid_price(q.bid, q.ask) if q.bid and q.ask and q.ask >= q.bid else q.ltp


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
        iv = (known or {}).get(q.instrument_id) or _leg_iv(em, (kind, _iv_price(q), strike, fwd), shared, where)
        if iv is None:
            return None
        ivs.append(iv)
    return (ivs[0] + ivs[1]) / 2


def _expected_move(legs, snapshot: MarketSnapshot, valuation: datetime.datetime,
                   shared: FeedScope | None = None, known: Mapping[str, Decimal] | None = None) -> ExpectedMove | None:
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
    try:
        return ExpectedMove(iv, days)
    except ValueError:
        return None


def _centre_of(strikes) -> Decimal:
    """The middle strike (the lower one of two) of the legs: with no live index price the grid has to centre
    somewhere, and this is the one place the answer says where (REQ-077 AC-9). No arithmetic: a strike of the legs."""
    ordered = sorted(set(strikes))
    return ordered[(len(ordered) - 1) // 2]


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
                 rates: ChargeRates | None = None, override: RangeOverride | None = None) -> Outcome | None:
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
    charges = None
    if rates is not None:
        try:
            charges = round_trip_charges(model.strategy.legs, definition.underlying, rates)
        except ChargesNotComputable:
            charges = None
    # the ONE computation: always the At Expiry view; Estimated Now needs live prices and is never computed here
    values = scenario_values(level_set, model, View.AT_EXPIRY, rates=None if charges is None else rates)
    shown = values
    if view is View.ESTIMATED_NOW:
        shown = ScenarioValues(view, LABELS[view], "estimate", values.levels, False,
                               render_explanation("outcome_from_entries_no_estimate"), None, None,
                               spot_level=values.spot_level, spot_at=values.spot_at)
    table = dataclasses.replace(build_table(model, level_set=level_set, scenario=shown), spot_level=None, spot_at=None,
                                output_label=FROM_ENTRIES_LABEL)
    points = tuple(zip(shown.levels, shown.totals)) if shown.available and shown.totals is not None else ()
    dropped = None if snapshot is None else _not_live_label(snapshot)
    if dropped is NOT_CONNECTED_LABEL:  # no quote was ever held: nothing dropped, no last update to name
        dropped = None
    return Outcome(
        state=OutcomeState.FROM_ENTRIES, underlying=definition.underlying, status_label=dropped or FROM_ENTRIES_LABEL,
        reason=None, legs=tuple(legs), margin=MARGIN, valuation=valuation, output_label=FROM_ENTRIES_LABEL,
        spot_level=None, spot_at=None, level_set=level_set, scenario=shown, table=table,
        visible_columns=visible_columns(table), payoff_points=points,
        summary=_summary(strategy_metrics(model.strategy), level_set, model, charges, charges is None),
        centre_label=render_explanation("outcome_from_entries_centre", level=centre))


def build_outcome(definition: StrategyDefinition, snapshot: MarketSnapshot | None,
                  valuation: datetime.datetime | None = None, *,
                  view: View = DEFAULT_VIEW, config: ScenarioConfig | None = None,
                  rates: ChargeRates | None = None,
                  override: RangeOverride | None = None, shared: FeedScope | None = None) -> Outcome:
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
                             override=override)
                or not_connected(definition, snapshot))
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
        elif q.health in _UNUSABLE or q.ltp is None:
            label = (render_explanation("leg_label_quote_unusable", health=q.health) if q.ltp is not None
                     else render_explanation("leg_label_quote_no_price"))
        else:
            ltp, label = q.ltp, _quote_label(q)
            fwd = snapshot.forwards.get(c.expiry)
            if kind is not Instrument.FUT and fwd is not None and snapshot.spot is not None:
                price = _iv_price(q)
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
        return _refused(definition, reason, legs, message)
    except ForwardUnavailable:
        return _refused(definition, render_explanation("outcome_forward_refused"), legs, message)

    config = config or ScenarioSettings().for_index(definition.underlying)
    solved = {x.instrument_id: x.iv for x in legs if x.iv is not None}
    move = _expected_move(inputs, snapshot, valuation, shared, solved)
    level_set = build_level_set(model, config, expected_move=move, override=override)
    charges = None
    if rates is not None:
        try:
            charges = round_trip_charges(model.strategy.legs, definition.underlying, rates)
        except ChargesNotComputable:
            charges = None
    # the ONE computation (AC-8)
    values = scenario_values(level_set, model, view, rates=None if charges is None else rates)
    table = build_table(model, level_set=level_set, scenario=values,
                        leg_greeks=_shared_leg_greeks(model, snapshot, shared))
    points = tuple(zip(values.levels, values.totals)) if values.available and values.totals is not None else ()
    # Issue 297: a leg's own notice stays on `legs[].label`; the page prints it once under the leg's contract name.
    # The answer-level label carries only the data/model label (never a raw trading symbol, never a notice twice).
    return Outcome(
        state=OutcomeState.COMPUTED, underlying=definition.underlying, status_label=message,
        reason=None, legs=tuple(legs), margin=MARGIN, valuation=valuation,
        output_label=model.label, spot_level=model.spot_level, spot_at=model.spot_at,
        level_set=level_set, scenario=values, table=table, visible_columns=visible_columns(table),
        payoff_points=points,
        summary=_summary(strategy_metrics(model.strategy), level_set, model, charges, charges is None))
