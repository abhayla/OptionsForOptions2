"""Calculators for the reference-video values whose feasibility is ``pass`` (REQ-071 AC-1; W-049).

Spec: spec/technical-design/adjustment-data-contract.md, rows 4-11, 14, 16-18, 26-29 (each row's "Calculation"
cell) and "Owner readings of the unclear values (Q246)" + the Q248 note (rows 4 and 26: Black-Scholes per
scenario-calculations section 4, rate recorded with every calculation). REQ-047 AC-5: every calculated value
records its inputs, so each calculator returns a :class:`MetricValue` carrying them.

ADR-008: every P&L, payoff and model number comes from the one engine. This module only CALLS it (legs P&L
convention, strategy live/expiry P&L, net premium, strategy metrics, booked P&L, Black-Scholes); the engine modules
are called through their module attribute so a test can prove no calculator carries its own formula.

Registered here: rows 4, 5, 6, 7, 8, 9, 10, 11, 14, 16, 17, 18, 26, 27, 28, 29. Not registered: rows 12 and 13
(feasibility ``unclear``), 19-25 and 30 (``unknown``/``fail``/out of V1); rows 1, 2, 3 and 15 are raw feed/broker
values (``pass``) outside this item's list and need no calculator.

Data this layer does not own is an explicit input, never fetched or defaulted: the margin (row 27/28, Zerodha's
margin API; ``StrategyInput.margin``), the available margin (row 27), the exchange holiday list (row 17 trading
days), the risk-free rate (``StrategyInput.rate``; the admin setting with its 6.5 % default does not exist yet).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from typing import Any, Callable, Final, Mapping, Sequence

from ofo.adjustment.registry import MetricRegistry
from ofo.engine import black_scholes as _bs
from ofo.engine import booked as _booked
from ofo.engine import strategy as _strategy
from ofo.engine.black_scholes import IST
from ofo.engine.booked import ClosedLeg
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Instrument, require_price
from ofo.engine.metrics import UNLIMITED
from ofo.instruments.catalogue import Catalogue, ContractKind
from ofo.strategy.versions import OutcomeKind, StrategyRecord

PERCENT_STEP: Final = Decimal("0.01")
MAX_HOLIDAYS: Final = 400


@dataclass(frozen=True)
class MetricValue:
    """One computed value, the registry row it answers, when it was computed for, and every input it used."""

    metric_id: int
    value: Any
    as_of: datetime.datetime
    inputs: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, datetime.datetime) or self.as_of.tzinfo is None:
            raise ValueError(f"as_of must be a timezone-aware datetime, got {self.as_of!r}")
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


def _require_inputs(inputs: object) -> StrategyInput:
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    return inputs


def _leg(inputs: StrategyInput, index: object) -> LegInput:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(inputs.legs):
        raise ValueError(f"leg index must be an int in 0..{len(inputs.legs) - 1}, got {index!r}")
    return inputs.legs[index]


def _option_leg(inputs: StrategyInput, index: object) -> LegInput:
    leg = _leg(inputs, index)
    if leg.instrument is Instrument.FUT:
        raise ValueError(f"leg {leg.contract} is a future; this value needs an option leg (a strike)")
    return leg


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator * 100 / denominator).quantize(PERCENT_STEP, rounding=ROUND_HALF_EVEN)


def _market(inputs: StrategyInput) -> dict[str, Any]:
    return {"spot": inputs.underlying_level, "rate": inputs.rate, "days_in_year": inputs.days_in_year,
            "valuation_time": inputs.valuation_time}


def _ltp_leg(inputs: StrategyInput, index: object) -> tuple[LegInput, Decimal]:
    leg = _option_leg(inputs, index)
    if leg.ltp is None:
        raise ValueError(f"leg {leg.contract} has no LTP; the pricing model needs one")
    years = _bs.year_fraction(inputs.valuation_time, leg.expiry, days_in_year=inputs.days_in_year)
    return leg, years


# Row 26 -------------------------------------------------------------------------------------------------------
def implied_volatility(inputs: StrategyInput, leg_index: int) -> MetricValue:
    """Row 26 (Q246/Q248): the option's IV implied from its LTP by the engine's Black-Scholes model."""
    inputs = _require_inputs(inputs)
    leg, years = _ltp_leg(inputs, leg_index)
    iv = _bs.implied_volatility(leg.instrument, leg.ltp, inputs.underlying_level, leg.strike, years, inputs.rate)
    return MetricValue(26, iv, inputs.valuation_time, {
        **_market(inputs), "contract": leg.contract, "strike": leg.strike, "ltp": leg.ltp, "years": years})


# Row 4 --------------------------------------------------------------------------------------------------------
def option_delta(inputs: StrategyInput, leg_index: int) -> MetricValue:
    """Row 4 (Q248): per-unit delta of one option (the option's own, not signed by BUY/SELL), 4 dp, at the IV
    implied from its LTP (row 26)."""
    inputs = _require_inputs(inputs)
    leg, years = _ltp_leg(inputs, leg_index)
    iv = _bs.implied_volatility(leg.instrument, leg.ltp, inputs.underlying_level, leg.strike, years, inputs.rate)
    greeks = _bs.bs_greeks(leg.instrument, inputs.underlying_level, leg.strike, years, inputs.rate, iv,
                           days_in_year=inputs.days_in_year)
    return MetricValue(4, greeks.delta, inputs.valuation_time, {
        **_market(inputs), "contract": leg.contract, "strike": leg.strike, "ltp": leg.ltp, "iv": iv,
        "years": years})


# Rows 5, 6, 7 -------------------------------------------------------------------------------------------------
def strike_distance_points(inputs: StrategyInput, leg_index: int) -> MetricValue:
    """Row 5: strike - spot, in index points (negative below spot)."""
    inputs = _require_inputs(inputs)
    leg = _option_leg(inputs, leg_index)
    return MetricValue(5, leg.strike - inputs.underlying_level, inputs.valuation_time,
                       {"spot": inputs.underlying_level, "contract": leg.contract, "strike": leg.strike})


def strike_distance_percent(inputs: StrategyInput, leg_index: int) -> MetricValue:
    """Row 6: (strike - spot) / spot, as a percent rounded half-even to 0.01."""
    inputs = _require_inputs(inputs)
    leg = _option_leg(inputs, leg_index)
    value = _percent(leg.strike - inputs.underlying_level, inputs.underlying_level)
    return MetricValue(6, value, inputs.valuation_time,
                       {"spot": inputs.underlying_level, "contract": leg.contract, "strike": leg.strike})


def strike_gap(inputs: StrategyInput, leg_a: int, leg_b: int) -> MetricValue:
    """Row 7: abs(strike A - strike B) of two different option legs of one strategy."""
    inputs = _require_inputs(inputs)
    first, second = _option_leg(inputs, leg_a), _option_leg(inputs, leg_b)
    if leg_a == leg_b:
        raise ValueError("a strike gap needs two different legs")
    return MetricValue(7, abs(first.strike - second.strike), inputs.valuation_time, {
        "contract_a": first.contract, "strike_a": first.strike,
        "contract_b": second.contract, "strike_b": second.strike})


# Rows 8, 9, 10, 11, 14 (engine P&L) --------------------------------------------------------------------------
def _ltps(inputs: StrategyInput) -> dict[str, Decimal | None]:
    return {leg.contract: leg.ltp for leg in inputs.legs}


def unrealised_pnl(inputs: StrategyInput) -> MetricValue:
    """Row 8: strategy live P&L, sum of leg (LTP - entry) x qty with the engine's sign convention."""
    inputs = _require_inputs(inputs)
    return MetricValue(8, inputs.strategy.live_pnl(), inputs.valuation_time,
                       {"ltps": _ltps(inputs), "entries": {leg.contract: leg.premium for leg in inputs.legs}})


def booked_pnl(closed: Sequence[ClosedLeg], as_of: datetime.datetime) -> MetricValue:
    """Row 9: booked P&L of each closed leg and the running total (engine :func:`ofo.engine.booked.booked_pnl`)."""
    items = tuple(closed)
    result = _booked.booked_pnl(items)
    return MetricValue(9, result, as_of, {"exits": tuple((c.reference, c.exit_price) for c in items)})


def remaining_profit(inputs: StrategyInput, closed: Sequence[ClosedLeg]) -> MetricValue:
    """Row 10 (Q246): max profit at expiry of the open legs (``inputs``) minus the losses already booked."""
    inputs = _require_inputs(inputs)
    items = tuple(closed)
    value = _booked.remaining_profit(inputs.strategy, items)
    return MetricValue(10, value, inputs.valuation_time, {
        "open_contracts": tuple(leg.contract for leg in inputs.legs),
        "exits": tuple((c.reference, c.exit_price) for c in items)})


def pnl_at_level(inputs: StrategyInput, level: Decimal) -> MetricValue:
    """Row 11: strategy P&L at expiry if the underlying settles at ``level`` (entry prices, never LTP)."""
    inputs = _require_inputs(inputs)
    require_price(level, "level")
    return MetricValue(11, inputs.strategy.expiry_pnl_at(level), inputs.valuation_time, {"level": level})


def net_premium_now(inputs: StrategyInput) -> MetricValue:
    """Row 14: sold premiums minus bought premiums at the current LTPs, in rupees (credit positive)."""
    inputs = _require_inputs(inputs)
    value = _strategy.net_premium(inputs.strategy, _strategy.PriceBasis.LTP)
    return MetricValue(14, value, inputs.valuation_time, {"ltps": _ltps(inputs)})


# Rows 16, 17 (instrument catalogue) ---------------------------------------------------------------------------
def _catalogue_kind(leg: LegInput) -> ContractKind:
    return ContractKind.FUTURE if leg.instrument is Instrument.FUT else ContractKind.OPTION


def lots(inputs: StrategyInput, leg_index: int, catalogue: Catalogue) -> MetricValue:
    """Row 16: the leg's units, the lot size from the instrument catalogue, and units / lot size (whole lots only)."""
    inputs = _require_inputs(inputs)
    leg = _leg(inputs, leg_index)
    if not isinstance(catalogue, Catalogue):
        raise ValueError(f"catalogue must be a Catalogue, got {catalogue!r}")
    lot_size = catalogue.lot_size(inputs.underlying, leg.expiry, _catalogue_kind(leg))
    if leg.quantity % lot_size:
        raise ValueError(f"{leg.quantity} units of {leg.contract} is not a whole number of lots of {lot_size}")
    return MetricValue(16, {"units": leg.quantity, "lot_size": lot_size, "lots": leg.quantity // lot_size},
                       inputs.valuation_time, {"contract": leg.contract, "expiry": leg.expiry})


def days_to_expiry(inputs: StrategyInput, leg_index: int, catalogue: Catalogue,
                   holidays: frozenset[datetime.date]) -> MetricValue:
    """Row 17: calendar days and trading days from the valuation date (IST) to the leg's expiry.

    Trading days count the weekdays after the valuation date up to and including the expiry day, less
    ``holidays`` (the exchange holiday list, an explicit input: this layer has no calendar source). The expiry must
    be one the instrument catalogue lists for the underlying.
    """
    inputs = _require_inputs(inputs)
    leg = _leg(inputs, leg_index)
    if not isinstance(catalogue, Catalogue):
        raise ValueError(f"catalogue must be a Catalogue, got {catalogue!r}")
    if not isinstance(holidays, frozenset) or len(holidays) > MAX_HOLIDAYS:
        raise ValueError(f"holidays must be a frozenset of at most {MAX_HOLIDAYS} dates")
    for day in holidays:
        if not isinstance(day, datetime.date) or isinstance(day, datetime.datetime):
            raise ValueError(f"every holiday must be a datetime.date, got {day!r}")
    if not catalogue.contracts_for(inputs.underlying, leg.expiry):
        raise ValueError(f"the instrument catalogue lists no {inputs.underlying} contract expiring {leg.expiry}")
    today = inputs.valuation_time.astimezone(IST).date()
    calendar = (leg.expiry - today).days
    if calendar < 0:
        raise ValueError(f"valuation date {today} is after the {leg.expiry} expiry")
    trading = sum(
        1 for n in range(1, calendar + 1)
        if (day := today + datetime.timedelta(days=n)).weekday() < 5 and day not in holidays)
    return MetricValue(17, {"calendar_days": calendar, "trading_days": trading}, inputs.valuation_time,
                       {"valuation_date": today, "expiry": leg.expiry, "holidays": tuple(sorted(holidays))})


# Row 18 -------------------------------------------------------------------------------------------------------
def market_clock(now: datetime.datetime) -> MetricValue:
    """Row 18: the platform clock read as exchange (IST) time of day."""
    if not isinstance(now, datetime.datetime) or now.tzinfo is None:
        raise ValueError(f"now must be a timezone-aware datetime, got {now!r}")
    ist = now.astimezone(IST)
    return MetricValue(18, ist.timetz(), now, {"clock": now})


# Rows 27, 28 (margin: Zerodha is the authority, an explicit input here) ---------------------------------------
def _stated_margin(inputs: StrategyInput) -> Decimal:
    if inputs.margin is None:
        raise ValueError("no margin stated for this strategy; it comes from Zerodha's margin API (row 27)")
    return inputs.margin.total


def margin(inputs: StrategyInput, available: Decimal) -> MetricValue:
    """Row 27: the margin the strategy needs (as the broker stated it) and the margin available (broker-stated)."""
    inputs = _require_inputs(inputs)
    required = _stated_margin(inputs)
    require_price(available, "available margin")
    return MetricValue(27, {"required": required, "available": available}, inputs.valuation_time,
                       {"source": inputs.margin.source})


def loss_percent_of_margin(inputs: StrategyInput) -> MetricValue:
    """Row 28 (Q246): unrealised loss / margin blocked x 100, half-even to 0.01 %; 0 when the strategy is not at a
    loss. The unrealised P&L is row 8 (engine live P&L)."""
    inputs = _require_inputs(inputs)
    blocked = _stated_margin(inputs)
    if blocked == 0:
        raise ValueError("the stated margin is 0; a loss percent of 0 capital has no value")
    pnl = inputs.strategy.live_pnl()
    loss = -pnl if pnl < 0 else Decimal(0)
    return MetricValue(28, _percent(loss, blocked), inputs.valuation_time,
                       {"unrealised_pnl": pnl, "margin": blocked, "margin_source": inputs.margin.source,
                        "ltps": _ltps(inputs)})


# Row 29 -------------------------------------------------------------------------------------------------------
def adjustments_made(record: StrategyRecord, as_of: datetime.datetime) -> MetricValue:
    """Row 29: versions activated after the strategy's first activated version, read from the record itself.

    Each meaningful modification after execution is a new version (ADR-019 Q190); one becomes active only after
    confirmation, execution and reconciliation. The first activation is the entry, not an adjustment.
    """
    if not isinstance(record, StrategyRecord):
        raise ValueError(f"record must be a StrategyRecord, got {record!r}")
    activated = [o for o in record.outcomes if o.kind is OutcomeKind.ACTIVATED]
    count = max(len(activated) - 1, 0)
    return MetricValue(29, count, as_of, {"activated_versions": tuple(o.version_number for o in activated)})


CALCULATORS: Final[dict[int, Callable[..., MetricValue]]] = {
    4: option_delta,
    5: strike_distance_points,
    6: strike_distance_percent,
    7: strike_gap,
    8: unrealised_pnl,
    9: booked_pnl,
    10: remaining_profit,
    11: pnl_at_level,
    14: net_premium_now,
    16: lots,
    17: days_to_expiry,
    18: market_clock,
    26: implied_volatility,
    27: margin,
    28: loss_percent_of_margin,
    29: adjustments_made,
}


def build_registry() -> MetricRegistry:
    """The metric registry with every calculator above registered; the registry refuses any non-``pass`` row."""
    registry = MetricRegistry()
    for metric_id, calculator in CALCULATORS.items():
        registry.register_calculator(metric_id, calculator)
    return registry


__all__ = ["CALCULATORS", "ClosedLeg", "MetricValue", "UNLIMITED", "build_registry"]
