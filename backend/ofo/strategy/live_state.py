"""Live market state: what the market is doing now. Separate from, and never part of, the strategy definition.

Spec: REQ-038 AC-1; ADR-019 Q189; spec/data/domain-model.md §2 (live side) and §5 (market data health values).
A ``LiveState`` holds no reference to a ``StrategyDefinition`` and has no method that produces or changes one:
per-leg quotes are keyed by the leg's position in the definition. Money and prices are exact ``Decimal``.
Greeks, P&L and distances are signed; prices, IV, margin and charges are not.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal

from ofo.engine.legs import require_decimal, require_price
from ofo.rules.inputs import DataHealth
from ofo.strategy.definition import MAX_LEGS

MAX_NAMED = 50
MAX_COUNT = 10**12
_NAME = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,59}$")

__all__ = [
    "DataHealth",
    "Greeks",
    "LegQuote",
    "LiveState",
    "LiveStateError",
]


class LiveStateError(ValueError):
    """A live market state value is invalid."""

    def __init__(self, *args: object, detail: str | None = None) -> None:
        """``detail`` marks developer-only input-validation text: it is never shown to a user."""
        super().__init__(*args) if detail is None else super().__init__(detail)


def _signed(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise LiveStateError(detail=f"{label} must be a finite decimal.Decimal, got {value!r}")
    return value


def _check(fn, value: object, label: str, **kw) -> None:
    try:
        fn(value, label, **kw)
    except ValueError as exc:
        raise LiveStateError(str(exc)) from exc


def _count(value: object, label: str, *, signed: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > MAX_COUNT or (not signed and value < 0):
        raise LiveStateError(detail=f"{label} must be an int{'' if signed else ' >= 0'} within {MAX_COUNT}, got {value!r}")


def _pairs(values: object, label: str, check) -> tuple:
    if not isinstance(values, tuple) or len(values) > MAX_NAMED:
        raise LiveStateError(detail=f"{label} must be a tuple of at most {MAX_NAMED} (name, value) pairs")
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str) or not _NAME.match(item[0]):
            raise LiveStateError(detail=f"{label}: each entry must be (name, value) with a name matching {_NAME.pattern}")
        if item[0] in seen:
            raise LiveStateError(detail=f"{label}: duplicate name {item[0]!r}")
        seen.add(item[0])
        check(item[1], f"{label} {item[0]!r}")
    return values


def _is_bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise LiveStateError(detail=f"{label} must be True or False, got {value!r}")


@dataclass(frozen=True)
class Greeks:
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal

    def __post_init__(self) -> None:
        for label in ("delta", "gamma", "theta", "vega"):
            _signed(getattr(self, label), label)


@dataclass(frozen=True)
class LegQuote:
    """Market data for the definition leg at ``leg_index`` (its position in ``StrategyDefinition.legs``)."""

    leg_index: int
    ltp: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: int = 0
    oi: int = 0
    oi_change: int = 0
    iv: Decimal | None = None
    greeks: Greeks | None = None

    def __post_init__(self) -> None:
        if isinstance(self.leg_index, bool) or not isinstance(self.leg_index, int) or not 0 <= self.leg_index < MAX_LEGS:
            raise LiveStateError(f"leg_index must be an int in 0..{MAX_LEGS - 1}, got {self.leg_index!r}")
        for label in ("ltp", "bid", "ask"):
            if getattr(self, label) is not None:
                _check(require_price, getattr(self, label), label)
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise LiveStateError(f"bid {self.bid} is above ask {self.ask}")
        _count(self.volume, "volume")
        _count(self.oi, "oi")
        _count(self.oi_change, "oi_change", signed=True)
        if self.iv is not None:
            _check(require_decimal, self.iv, "iv")
        if self.greeks is not None and not isinstance(self.greeks, Greeks):
            raise LiveStateError(f"greeks must be Greeks or None, got {self.greeks!r}")


@dataclass(frozen=True)
class LiveState:
    """One snapshot of the constantly changing market side of a strategy (Q189). Immutable; a tick is a new one."""

    as_of: datetime.datetime
    data_health: DataHealth
    spot: Decimal | None = None
    futures: Decimal | None = None
    leg_quotes: tuple[LegQuote, ...] = ()
    pnl: Decimal | None = None
    margin: Decimal | None = None
    charges: Decimal | None = None
    distances: tuple[tuple[str, Decimal], ...] = ()
    trigger_state: tuple[tuple[str, bool], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, datetime.datetime) or self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise LiveStateError(f"as_of must be a timezone-aware datetime, got {self.as_of!r}")
        if not isinstance(self.data_health, DataHealth):
            raise LiveStateError(f"data_health must be a DataHealth, got {self.data_health!r}")
        for label in ("spot", "futures"):
            if getattr(self, label) is not None:
                _check(require_price, getattr(self, label), label, allow_zero=False)
        for label in ("margin", "charges"):
            if getattr(self, label) is not None:
                _check(require_decimal, getattr(self, label), label)
        if self.pnl is not None:
            _signed(self.pnl, "pnl")
        if not isinstance(self.leg_quotes, tuple) or len(self.leg_quotes) > MAX_LEGS:
            raise LiveStateError(f"leg_quotes must be a tuple of at most {MAX_LEGS} LegQuote")
        indexes = [q.leg_index for q in self.leg_quotes if isinstance(q, LegQuote)]
        if len(indexes) != len(self.leg_quotes):
            raise LiveStateError("every leg quote must be a LegQuote")
        if len(set(indexes)) != len(indexes):
            raise LiveStateError("two quotes for the same leg_index")
        _pairs(self.distances, "distances", _signed)
        _pairs(self.trigger_state, "trigger_state", _is_bool)
