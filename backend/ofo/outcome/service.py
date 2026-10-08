"""The outcome of a draft strategy: one table, one set of scenario values, the payoff and the summary (W-063).

Spec: REQ-034 AC-1 (every part of the outcome view), AC-7 (plain language first), AC-8 (payoff graph and scenario table
from the same engine); REQ-033 AC-1/AC-3 (the leg formulas; expiry scenarios use the entry price, never the LTP);
ADR-008 (one engine, exact Decimal); ADR-061 (each expiry's forward; spot for CURRENT and the range); ADR-068 (planned
entry with its capture time; UX level per request, presentation only; the not-live labels).

AC-8 by construction: :func:`build_outcome` computes the scenario values ONCE (``scenario_values``) and both the table
(``build_table``) and the payoff points are taken from that one ``ScenarioValues``; nothing here prices a level.

Answer states (run-discipline B4 (d)), each with its label or refusal:

- no provider / no Zerodha session: ``NOT_CONNECTED``, "Draft - Live data not connected" (ADR-068, ADR-020 Q185).
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
from decimal import Decimal
from enum import Enum
from typing import Final

from ofo.engine.display import format_points, format_rupees
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.metrics import UNLIMITED, StrategyMetrics, strategy_metrics
from ofo.engine.model import (ModelInputs, SpotRefused, data_label, expiry_model, implied_vol, join_labels,
                              model_inputs)
from ofo.instruments.models import ZERODHA
from ofo.marketdata.disconnect import disconnect_message
from ofo.marketdata.forward import ForwardUnavailable, mid_price
from ofo.marketdata.quote import NormalizedQuote
from ofo.outcome.snapshot import MarketSnapshot
from ofo.rules.inputs import DataHealth
from ofo.scenario.config import ScenarioConfig, ScenarioSettings
from ofo.scenario.levels import LevelSet, build_level_set
from ofo.scenario.spot import spot_reading
from ofo.scenario.views import DEFAULT_VIEW, ScenarioValues, View, scenario_values
from ofo.table import ColumnSpec, Table, UXLevel, build_table, visible_columns

NOT_CONNECTED_LABEL: Final = "Draft - Live data not connected"
MARGIN_NOT_AVAILABLE_YET: Final = "NOT_AVAILABLE_YET"
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
    label: str | None


@dataclass(frozen=True)
class Summary:
    """REQ-034 AC-7: the three plain-language answers first, the detail after."""

    what_can_i_lose: str
    what_can_i_make: str
    where_do_i_start_losing: str
    max_profit: Decimal | None  # None = unlimited
    max_loss: Decimal | None  # None = unlimited
    max_profit_unlimited: bool
    max_loss_unlimited: bool
    breakevens: tuple[Decimal, ...]
    lower_be: Decimal | None
    upper_be: Decimal | None
    risk_boundaries: tuple[Decimal, ...]


@dataclass(frozen=True)
class Margin:
    state: str
    reason: str


@dataclass(frozen=True)
class Outcome:
    state: OutcomeState
    underlying: str
    ux_level: UXLevel
    status_label: str | None  # NOT_CONNECTED / REFUSED text, or REQ-049 AC-5's message when the feed dropped
    reason: str | None
    legs: tuple[OutcomeLeg, ...]
    margin: Margin
    valuation: datetime.datetime | None = None
    output_label: str | None = None  # data label + "estimated from spot", joined
    spot_level: Decimal | None = None
    spot_at: datetime.datetime | None = None
    level_set: LevelSet | None = None
    scenario: ScenarioValues | None = None
    table: Table | None = None
    visible_columns: tuple[ColumnSpec, ...] = ()
    payoff_points: tuple[tuple[Decimal, Decimal], ...] = ()
    summary: Summary | None = None


MARGIN: Final = Margin(MARGIN_NOT_AVAILABLE_YET, "margin from Zerodha comes with the margin item (needs the Kite login)")


def not_connected(definition: StrategyDefinition, ux_level: UXLevel = UXLevel.STANDARD) -> Outcome:
    """No provider or no Zerodha session (ADR-068 consequence, ADR-020 Q185): a state, never an error."""
    legs = tuple(OutcomeLeg(p.instrument_id, None, p.action, None, None, None, p.lots, None, None, p.planned_entry,
                            p.captured_at, None, None, None, NOT_CONNECTED_LABEL) for p in definition.legs)
    return Outcome(OutcomeState.NOT_CONNECTED, definition.underlying, ux_level, NOT_CONNECTED_LABEL,
                   "no live market data provider is connected", legs, MARGIN)


def _quote_label(q: NormalizedQuote) -> str | None:
    """The one stale/delayed wording (ofo.engine.model.data_label) applied to a leg quote's own time and health."""
    return data_label(SpotReading(Decimal(1), q.timestamp, q.health))


def _feed_message(snapshot: MarketSnapshot) -> str | None:
    """REQ-049 AC-5's message when the feed is not live; the last update is the newest input time we hold."""
    if snapshot.status.health is DataHealth.AVAILABLE:
        return None
    times = [q.timestamp for q in [snapshot.spot, *(lm.quote for lm in snapshot.legs.values())] if q is not None]
    return disconnect_message(max(times) if times else snapshot.valuation)


def _summary(metrics: StrategyMetrics, level_set: LevelSet, inputs: ModelInputs) -> Summary:
    idx = inputs.underlying
    profit_unl, loss_unl = metrics.max_profit is UNLIMITED, metrics.max_loss is UNLIMITED
    if loss_unl:
        lose = f"Your loss has no fixed limit if {idx} rises far enough by expiry."
    elif metrics.max_loss == 0:
        lose = "You cannot lose money at expiry."
    else:
        lose = f"At most {format_rupees(metrics.max_loss)} at expiry."
    if profit_unl:
        make = f"Your profit has no fixed limit if {idx} rises far enough by expiry."
    elif metrics.max_profit <= 0:
        make = "This strategy cannot make money at expiry."
    else:
        make = f"At most {format_rupees(metrics.max_profit)} at expiry."
    lo, up = level_set.lower_be, level_set.upper_be
    if lo is not None and up is not None:
        inside_profit = inputs.strategy.expiry_pnl_at((lo + up) / 2) > 0
        start = (f"If {idx} ends below {format_points(lo)} or above {format_points(up)} at expiry."
                 if inside_profit else
                 f"If {idx} ends between {format_points(lo)} and {format_points(up)} at expiry.")
    elif lo is not None:
        start = f"If {idx} ends below {format_points(lo)} at expiry."
    elif up is not None:
        start = f"If {idx} ends above {format_points(up)} at expiry."
    elif metrics.max_loss == 0:
        start = "At no level at expiry."
    else:
        start = "At every level at expiry: there is no breakeven."
    return Summary(lose, make, start, None if profit_unl else metrics.max_profit,
                   None if loss_unl else metrics.max_loss, profit_unl, loss_unl, level_set.breakevens,
                   lo, up, level_set.risk_boundaries)


def _refused(definition, ux_level, reason, legs, message=None) -> Outcome:
    return Outcome(OutcomeState.REFUSED, definition.underlying, ux_level, join_labels(message, "Outcome refused"),
                   reason, tuple(legs), MARGIN)


def build_outcome(definition: StrategyDefinition, snapshot: MarketSnapshot | None,
                  ux_level: UXLevel = UXLevel.STANDARD, valuation: datetime.datetime | None = None, *,
                  view: View = DEFAULT_VIEW, config: ScenarioConfig | None = None) -> Outcome:
    """The outcome of ``definition`` on ``snapshot``; ``valuation`` defaults to the snapshot's valuation time."""
    if not isinstance(definition, StrategyDefinition):
        raise ValueError(f"definition must be a StrategyDefinition, got {definition!r}")
    if not isinstance(ux_level, UXLevel):
        raise ValueError(f"ux_level must be a UXLevel, got {ux_level!r}")
    if snapshot is None or snapshot.status.session_ended:
        return not_connected(definition, ux_level)
    if snapshot.underlying != definition.underlying:
        raise ValueError("the snapshot was read for another underlying")
    valuation = snapshot.valuation if valuation is None else valuation
    if valuation != snapshot.valuation:
        raise ValueError("the snapshot's forwards were read at another valuation time")
    message = _feed_message(snapshot)

    legs: list[OutcomeLeg] = []
    inputs: list[LegInput] = []
    problems: list[str] = []
    for p in definition.legs:
        lm = snapshot.legs.get(p.instrument_id)
        if lm is None or lm.contract is None or lm.problem is not None:
            why = "not in the snapshot" if lm is None else lm.problem
            problems.append(f"{p.instrument_id}: {why}")
            legs.append(OutcomeLeg(p.instrument_id, None, p.action, None, None, None, p.lots, None, None,
                                   p.planned_entry, p.captured_at, None, None, None, why))
            continue
        c = lm.contract.contract
        symbol = lm.contract.ref(ZERODHA).broker_symbol if lm.contract.broker_refs else None
        kind = Instrument(c.instrument_type)
        strike = None if kind is Instrument.FUT else c.strike
        q = lm.quote
        ltp = iv = None
        if q is None:
            label = "no live quote"
        elif q.health in _UNUSABLE or q.ltp is None:
            label = f"quote {q.health.value}; not used" if q.ltp is not None else "quote has no last price"
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
                    label = join_labels(label, "no implied volatility for this price")
        quantity = p.lots * c.lot_size
        legs.append(OutcomeLeg(p.instrument_id, symbol, p.action, kind, strike, c.expiry, p.lots, c.lot_size,
                               quantity, p.planned_entry, p.captured_at, ltp, iv, None if q is None else q.health,
                               label))
        try:
            inputs.append(LegInput(definition.underlying, symbol or p.instrument_id, p.action, kind, strike,
                                   c.expiry, quantity, p.planned_entry, ltp, iv))
        except ValueError as exc:
            problems.append(f"{p.instrument_id}: {exc}")
    for expiry, why in snapshot.forward_errors.items():
        if any(leg.expiry == expiry for leg in inputs):
            problems.append(f"forward for {expiry}: {why}")
    if problems:
        return _refused(definition, ux_level, "; ".join(problems), legs, message)

    try:
        spot = spot_reading(snapshot.spot)
        model = model_inputs(StrategyInput(definition.underlying, spot, valuation, snapshot.rate, tuple(inputs)),
                             snapshot.forwards)
    except (SpotRefused, ForwardUnavailable) as exc:
        return _refused(definition, ux_level, str(exc), legs, message)

    config = config or ScenarioSettings().for_index(definition.underlying)
    level_set = build_level_set(model, config)
    values = scenario_values(level_set, model, view)  # the ONE scenario computation (AC-8)
    table = build_table(model, level_set=level_set, scenario=values)
    points = tuple(zip(values.levels, values.totals)) if values.available and values.totals is not None else ()
    leg_labels = [f"{leg.symbol}: {leg.label}" for leg in legs if leg.label]
    return Outcome(
        state=OutcomeState.COMPUTED, underlying=definition.underlying, ux_level=ux_level, status_label=message,
        reason=None, legs=tuple(legs), margin=MARGIN, valuation=valuation,
        output_label=join_labels(model.label, *leg_labels), spot_level=model.spot_level, spot_at=model.spot_at,
        level_set=level_set, scenario=values, table=table, visible_columns=visible_columns(table, ux_level),
        payoff_points=points, summary=_summary(strategy_metrics(model.strategy), level_set, model))
