"""Named rule inputs, market-data health and the Snapshot a rule is evaluated against.

Spec: REQ-041 AC-4 (inputs a rule can read), ADR-011 "WHEN" list, ADR-015 / REQ-049 (data health: never use
stale data as live), domain-model §7 (a trigger records its exact inputs, timestamp and data health).

Every value is an exact ``Decimal`` (money, points, percent, Greeks, minutes, days). A value that is not in the
snapshot is MISSING, never zero: a rule that reads it cannot be evaluated (fail closed).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from ofo.engine import UNLIMITED, Action, MultiExpiryError, PriceBasis, Strategy, net_premium, strategy_metrics

# India has no daylight saving; market hours and time windows are in IST.
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")


class InputName(Enum):
    """Every input a V1 rule condition can compare (REQ-041 AC-4)."""

    UNDERLYING_LEVEL = "underlying_level"
    UNDERLYING_MOVE_POINTS = "underlying_move_points"  # signed move since the reference (e.g. entry) level
    UNDERLYING_MOVE_PCT = "underlying_move_pct"
    DISTANCE_TO_SHORT_STRIKE = "distance_to_short_strike"  # points to the nearest short option strike
    DISTANCE_TO_BREAKEVEN = "distance_to_breakeven"  # points to the nearest at-expiry breakeven
    NET_PREMIUM = "net_premium"  # rupees total at LTP, credit positive, from engine.net_premium only (ADR-008)
    LIVE_PNL = "live_pnl"  # rupees, from the engine only (ADR-008)
    PNL_PCT_OF_MAX_PROFIT = "pnl_pct_of_max_profit"  # strategy-level threshold
    PNL_PCT_OF_MAX_LOSS = "pnl_pct_of_max_loss"  # strategy-level threshold (loss as a positive percent)
    DTE = "dte"  # calendar days to expiry
    TIME_OF_DAY = "time_of_day"  # minutes since 00:00 IST, taken from the snapshot timestamp
    IV = "iv"
    IV_PERCENTILE = "iv_percentile"
    DELTA = "delta"
    GAMMA = "gamma"
    THETA = "theta"
    VEGA = "vega"


class DataHealth(Enum):
    """Health of the market data behind a snapshot (domain-model §5, ADR-015)."""

    AVAILABLE = "available"
    STALE = "stale"
    DELAYED = "delayed"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"


def require_finite(value: object, name: str) -> Decimal:
    """Return ``value`` if it is a finite Decimal (any sign); raise ``ValueError`` otherwise."""
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a decimal.Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite, got {value}")
    return value


def minutes_of_day(moment: datetime.time) -> Decimal:
    """Minutes since midnight of a wall-clock time, as the TIME_OF_DAY input expresses it."""
    if not isinstance(moment, datetime.time):
        raise ValueError(f"expected a datetime.time, got {moment!r}")
    return Decimal(moment.hour * 60 + moment.minute) + Decimal(moment.second) / Decimal(60)


@dataclass(frozen=True)
class Snapshot:
    """Market and strategy values at one moment. TIME_OF_DAY is derived from ``as_of``, never supplied.

    Health: ``data_health`` applies to every supplied input; ``input_health`` can mark single inputs differently
    (e.g. IV stale while LTPs are live). An input whose health is not ``available`` is unusable, exactly like a
    missing one (ADR-015: never use stale data as live). TIME_OF_DAY comes from the timestamp, not from market
    data, so it is always usable.
    """

    values: Mapping[InputName, Decimal]
    as_of: datetime.datetime
    data_health: DataHealth
    source: str = "unspecified"
    input_health: Mapping[InputName, DataHealth] = field(default_factory=dict)
    _all: Mapping[InputName, Decimal] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, datetime.datetime) or self.as_of.tzinfo is None:
            raise ValueError(f"as_of must be a timezone-aware datetime, got {self.as_of!r}")
        if not isinstance(self.data_health, DataHealth):
            raise ValueError(f"data_health must be a DataHealth, got {self.data_health!r}")
        health = dict(self.input_health)
        for name, state in health.items():
            if not isinstance(name, InputName) or name is InputName.TIME_OF_DAY:
                raise ValueError(f"input_health keys must be market-data InputNames, got {name!r}")
            if not isinstance(state, DataHealth):
                raise ValueError(f"input_health values must be DataHealth, got {state!r}")
        object.__setattr__(self, "input_health", MappingProxyType(health))
        checked: dict[InputName, Decimal] = {}
        for name, value in dict(self.values).items():
            if not isinstance(name, InputName):
                raise ValueError(f"snapshot input names must be InputName, got {name!r}")
            if name is InputName.TIME_OF_DAY:
                raise ValueError("TIME_OF_DAY is derived from as_of and cannot be supplied")
            checked[name] = require_finite(value, name.value)
        object.__setattr__(self, "values", MappingProxyType(dict(checked)))
        full = dict(checked)
        full[InputName.TIME_OF_DAY] = minutes_of_day(self.as_of.astimezone(IST).time())
        object.__setattr__(self, "_all", MappingProxyType(full))

    def get(self, name: InputName) -> Decimal | None:
        """The input's value, or ``None`` when the snapshot does not carry it (missing, never zero)."""
        return self._all.get(name)

    def health_of(self, name: InputName) -> DataHealth:
        """The health of one input: its own override, else the snapshot's (TIME_OF_DAY is always available)."""
        if name is InputName.TIME_OF_DAY:
            return DataHealth.AVAILABLE
        return self.input_health.get(name, self.data_health)

    def usable(self, name: InputName) -> Decimal | None:
        """The value a rule may use: ``None`` when the input is missing or its data is not ``available``."""
        if self.health_of(name) is not DataHealth.AVAILABLE:
            return None
        return self.get(name)


def snapshot_from_strategy(
    strategy: Strategy,
    *,
    underlying_level: Decimal,
    as_of: datetime.datetime,
    data_health: DataHealth,
    source: str = "unspecified",
    extra: Mapping[InputName, Decimal] | None = None,
    input_health: Mapping[InputName, DataHealth] | None = None,
) -> Snapshot:
    """Build a Snapshot whose P&L, premium, distances and DTE come from the engine (ADR-008), never re-derived.

    LIVE_PNL (and the percent-of-max inputs) are left MISSING when any leg has no LTP; DTE, breakeven and the
    percent-of-max inputs are left missing for a multi-expiry strategy (no exact at-expiry payoff). Market inputs
    the engine does not own (IV, Greeks, moves) come in ``extra``; ``extra`` may not override an engine value.
    """
    level = require_finite(underlying_level, "underlying_level")
    if level <= 0:
        raise ValueError(f"underlying_level must be > 0, got {level}")
    values: dict[InputName, Decimal] = {InputName.UNDERLYING_LEVEL: level}

    has_all_ltps = all(leg.ltp is not None for leg in strategy.legs)
    if has_all_ltps:
        values[InputName.LIVE_PNL] = strategy.live_pnl()
    if all(leg.ltp is not None for leg in strategy.legs if leg.is_option):
        # Futures carry no premium, so a futures-only strategy's net premium is 0 by the engine's definition.
        values[InputName.NET_PREMIUM] = net_premium(strategy, PriceBasis.LTP)

    shorts = [leg.strike for leg in strategy.legs if leg.is_option and leg.action is Action.SELL]
    if shorts:
        values[InputName.DISTANCE_TO_SHORT_STRIKE] = min(abs(level - strike) for strike in shorts)

    try:
        metrics = strategy_metrics(strategy)
    except MultiExpiryError:
        metrics = None
    if metrics is not None:
        values[InputName.DTE] = Decimal((strategy.legs[0].expiry - as_of.astimezone(IST).date()).days)
        if metrics.breakevens:
            values[InputName.DISTANCE_TO_BREAKEVEN] = min(abs(level - be) for be in metrics.breakevens)
        if has_all_ltps:
            pnl = values[InputName.LIVE_PNL]
            if metrics.max_profit is not UNLIMITED and metrics.max_profit > 0:
                values[InputName.PNL_PCT_OF_MAX_PROFIT] = pnl * 100 / metrics.max_profit
            if metrics.max_loss is not UNLIMITED and metrics.max_loss > 0:
                values[InputName.PNL_PCT_OF_MAX_LOSS] = -pnl * 100 / metrics.max_loss

    for name, value in dict(extra or {}).items():
        if name in values:
            raise ValueError(f"{name.value} is computed by the engine and cannot be supplied in extra")
        values[name] = value
    return Snapshot(values=values, as_of=as_of, data_health=data_health, source=source,
                    input_health=dict(input_health or {}))
