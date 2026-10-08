"""Round 9 (issue #30): typed slots for the execution safety gate's and the disconnect status's messages.

Every value is an exact engine/execution type or a closed pattern; none can carry free words. Types that live in
`ofo.execution` are imported on use, because `ofo.execution.safety` builds its messages with `render()` and so this
package must not import `ofo.execution` while it loads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ofo.engine.legs import Action as _Action
from ofo.engine.legs import Instrument as _EngineInstrument
from ofo.engine.legs import Leg as _Leg

from .slots import _IST, _MONTHS, MONEY_ABS_MAX, Count, Instrument, SlotType, Time, Underlying, _require_exact
from .slots import _validate_money


def _format_strike(strike: Decimal) -> str:
    return f"{strike:,}"


def _validate_strike(value: object, slot: str) -> None:
    _require_exact(value, Decimal, slot)
    assert isinstance(value, Decimal)
    if not value.is_finite() or value <= 0 or value > MONEY_ABS_MAX:
        raise ValueError(f"{slot} slot requires a finite positive strike within the cap, got {value!r}")


def _format_date(day: date) -> str:
    return f"{day.day:02d} {_MONTHS[day.month - 1]} {day.year:04d}"


@dataclass(frozen=True)
class LegValue:
    """One strategy leg as a message shows it: its 1-based number, the engine leg and its (supported) underlying."""

    number: int
    leg: _Leg
    underlying: str


def _validate_leg_value(value: object, slot: str) -> None:
    _require_exact(value, LegValue, slot)
    assert isinstance(value, LegValue)
    Count.validate(value.number)
    if value.number < 1:
        raise ValueError(f"{slot} slot requires a leg number >= 1, got {value.number}")
    _require_exact(value.leg, _Leg, f"{slot}.leg")
    Underlying.validate(value.underlying)
    leg = value.leg
    if type(leg.action) is not _Action or type(leg.instrument) is not _EngineInstrument:
        raise TypeError(f"{slot} slot requires an engine Action and Instrument")
    if leg.strike is not None:
        _validate_strike(leg.strike, f"{slot}.strike")
    _require_exact(leg.expiry, date, f"{slot}.expiry")


def _contract_text(value: LegValue) -> str:
    leg = value.leg
    what = "FUT" if leg.strike is None else f"{_format_strike(leg.strike)} {Instrument.format(leg.instrument)}"
    return f"{leg.action.value} {value.underlying} {what}"


class LegRef(SlotType):
    """A leg with its contract and expiry: "Leg 2 (SELL NIFTY 24,000 CE, expiry 30 Sep 2026)"."""

    @staticmethod
    def validate(value: object) -> None:
        _validate_leg_value(value, "LegRef")

    @staticmethod
    def format(value: LegValue) -> str:
        return f"Leg {value.number} ({_contract_text(value)}, expiry {_format_date(value.leg.expiry)})"


class LegContract(SlotType):
    """A leg's contract without its number or expiry: "SELL NIFTY 24,000 CE"."""

    @staticmethod
    def validate(value: object) -> None:
        _validate_leg_value(value, "LegContract")

    @staticmethod
    def format(value: LegValue) -> str:
        return _contract_text(value)


class Date(SlotType):
    """A calendar date, exactly `datetime.date` (not a datetime): "30 Sep 2026"."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, date, "Date")

    @staticmethod
    def format(value: date) -> str:
        return _format_date(value)


class Strikes(SlotType):
    """One or two listed strikes offered as alternatives (never applied): "23,950 or 24,050"."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, tuple, "Strikes")
        assert isinstance(value, tuple)
        if not 1 <= len(value) <= 2:
            raise ValueError(f"Strikes slot holds 1 or 2 strikes, got {len(value)}")
        for strike in value:
            _validate_strike(strike, "Strikes")

    @staticmethod
    def format(value: tuple[Decimal, ...]) -> str:
        return " or ".join(_format_strike(s) for s in value)


class Rupees(SlotType):
    """A rupee amount printed as given, paise included if present ("₹50,000.00"): the gate's margin figures."""

    @staticmethod
    def validate(value: object) -> None:
        _validate_money(value, "Rupees", signed=False)

    @staticmethod
    def format(value: Decimal) -> str:
        return f"₹{value:,}"


class WorstCase(SlotType):
    """A premium-free worst case at expiry: a Decimal P&L or the engine's UNLIMITED marker."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.engine import UNLIMITED

        if value is UNLIMITED:
            return
        _validate_money(value, "WorstCase", signed=True)

    @staticmethod
    def format(value: object) -> str:
        from ofo.engine import UNLIMITED

        if value is UNLIMITED:
            return "an unlimited loss"
        assert isinstance(value, Decimal)
        return f"a loss of ₹{-value:,}" if value < 0 else f"a gain of ₹{value:,}"


class VersionStateName(SlotType):
    """A strategy version's state (`ofo.execution.context.VersionState`) or None (shown as "unknown")."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.execution.context import VersionState

        if value is not None and type(value) is not VersionState:
            raise TypeError(f"VersionStateName slot requires a VersionState or None, got {type(value).__name__}")

    @staticmethod
    def format(value: object) -> str:
        return "unknown" if value is None else value.value.lower()  # type: ignore[attr-defined]


class VersionStates(SlotType):
    """A non-empty frozenset of VersionState, shown sorted and joined with "or"."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.execution.context import VersionState

        _require_exact(value, frozenset, "VersionStates")
        assert isinstance(value, frozenset)
        if not value or any(type(v) is not VersionState for v in value):
            raise TypeError("VersionStates slot requires a non-empty frozenset of VersionState")

    @staticmethod
    def format(value: frozenset) -> str:
        return " or ".join(sorted(v.value.lower() for v in value))


class DataInputName(SlotType):
    """A market-data input execution needs (`ofo.execution.context.DataInput`), e.g. "underlying price"."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.execution.context import DataInput

        if type(value) is not DataInput:
            raise TypeError(f"DataInputName slot requires a DataInput, got {type(value).__name__}")

    @staticmethod
    def format(value: object) -> str:
        return value.value.lower().replace("_", " ")  # type: ignore[attr-defined]


class DataHealthState(SlotType):
    """An unhealthy data input's health (`DataHealth.STALE`/`UNAVAILABLE`, or None for no status), as a verb phrase."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.execution.context import DataHealth

        if value is not None and type(value) is not DataHealth:
            raise TypeError(f"DataHealthState slot requires a DataHealth or None, got {type(value).__name__}")
        if value is DataHealth.HEALTHY:
            raise ValueError("DataHealthState slot describes an unhealthy input; HEALTHY is not an error")

    @staticmethod
    def format(value: object) -> str:
        from ofo.execution.context import DataHealth

        if value is None:
            return "has no status"
        return "is out of date" if value is DataHealth.STALE else "is unavailable"


#: The value of each `ofo.execution.partial.ExecutionStatus` member -> plain words. Keyed by value, so this package
#: never imports ofo.execution.partial (only the order-issuing flows may: W-026's import test).
_STATUS_WORDS = {"complete": "complete", "partial_exception": "partly executed", "in_progress": "in progress",
                 "not_executed": "not executed", "reconciliation_required": "waiting for reconciliation"}


class ExecutionStatusName(SlotType):
    """A partial-execution status, given as its `ExecutionStatus` value (a closed set), shown in plain words."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "ExecutionStatusName")
        if value not in _STATUS_WORDS:
            raise ValueError(f"ExecutionStatusName slot must be one of {sorted(_STATUS_WORDS)}, got {value!r}")

    @staticmethod
    def format(value: str) -> str:
        return _STATUS_WORDS[value]


#: An underlying symbol the platform does not support, as the context names it: capitals and digits only.
_SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9]{0,19}")


class Symbol(SlotType):
    """A market symbol outside the supported set (the unsupported-underlying message): capitals and digits only."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "Symbol")
        assert isinstance(value, str)
        if not _SYMBOL_PATTERN.fullmatch(value):
            raise ValueError(f"Symbol slot must match {_SYMBOL_PATTERN.pattern!r}, got {value!r}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


class Clock(SlotType):
    """A timezone-aware time shown as the IST clock time with seconds, "10:42:17 AM" (ADR-015's own example)."""

    @staticmethod
    def validate(value: object) -> None:
        Time.validate(value)

    @staticmethod
    def format(value: datetime) -> str:
        ist = value.astimezone(_IST)
        hour = ist.hour % 12 or 12
        half = "AM" if ist.hour < 12 else "PM"
        return f"{hour:02d}:{ist.minute:02d}:{ist.second:02d} {half}"
