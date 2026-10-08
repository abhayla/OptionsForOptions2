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

from ofo.errors.slots import _IST, _MONTHS, MONEY_ABS_MAX, Count, Instrument, SlotType, Time, Underlying, _require_exact
from ofo.errors.slots import _validate_money


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


# --- Round 9 part 4: Strategy Guard rows and exchange contract symbols ------------------------------------------------

_CONTRACT_PATTERN = re.compile(r"[A-Z][A-Z0-9&-]{0,39}")
RISK_METRICS = ("max profit", "max loss", "breakevens", "net premium", "margin", "position")


class ContractSymbol(SlotType):
    """An exchange trading symbol such as NIFTY2693024000CE: capitals, digits, `&` and `-` only, at most 40."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "ContractSymbol")
        assert isinstance(value, str)
        if not _CONTRACT_PATTERN.fullmatch(value):
            raise ValueError(f"ContractSymbol slot must match {_CONTRACT_PATTERN.pattern!r}, got {value!r}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


def _risk_cell(value: object) -> str:
    from ofo.engine import UNLIMITED

    if value is UNLIMITED:
        return "unlimited"
    if value is None:
        return "unknown"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if isinstance(value, tuple):
        return ", ".join(f"{v:,}" for v in value) if value else "none"
    assert isinstance(value, Decimal)
    return f"{value:,}"


def _validate_risk_cell(value: object) -> None:
    from ofo.engine import UNLIMITED

    if value is UNLIMITED or value is None or isinstance(value, bool):
        return
    if type(value) is Decimal:
        if not value.is_finite() or abs(value) > MONEY_ABS_MAX:
            raise ValueError("RiskRows cell must be a finite Decimal within the money cap")
        return
    if type(value) is tuple and len(value) <= 20 and all(type(v) is Decimal and v.is_finite() for v in value):
        return
    raise TypeError(f"RiskRows cell must be a Decimal, a tuple of Decimals, UNLIMITED, None or a bool, got {value!r}")


class RiskRows(SlotType):
    """The changed rows of a Strategy Guard comparison: a tuple of (metric, before, after) with a closed metric set."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, tuple, "RiskRows")
        assert isinstance(value, tuple)
        if not 1 <= len(value) <= len(RISK_METRICS):
            raise ValueError("RiskRows needs 1..6 rows")
        for row in value:
            if type(row) is not tuple or len(row) != 3 or row[0] not in RISK_METRICS:
                raise ValueError(f"RiskRows row must be (metric, before, after) with a known metric, got {row!r}")
            _validate_risk_cell(row[1])
            _validate_risk_cell(row[2])

    @staticmethod
    def format(value: tuple) -> str:
        return "; ".join(f"{metric}: {_risk_cell(before)} -> {_risk_cell(after)}" for metric, before, after in value)


_ORDER_REF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


class OrderRef(SlotType):
    """A broker order id or the platform's own order key: letters, digits and `_ . : -` only, at most 64."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "OrderRef")
        assert isinstance(value, str)
        if not _ORDER_REF_PATTERN.fullmatch(value):
            raise ValueError(f"OrderRef slot must match {_ORDER_REF_PATTERN.pattern!r}, got {value!r}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


class UnitsByContract(SlotType):
    """Net units per contract: a tuple of (ContractSymbol, int) pairs, at most 100, printed as `SYMBOL: units`."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, tuple, "UnitsByContract")
        assert isinstance(value, tuple)
        if len(value) > 100:
            raise ValueError("UnitsByContract holds at most 100 pairs")
        for pair in value:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError(f"UnitsByContract pair must be (contract, units), got {pair!r}")
            ContractSymbol.validate(pair[0])
            _require_exact(pair[1], int, "UnitsByContract units")
            if abs(pair[1]) > 1_000_000_000:
                raise ValueError("UnitsByContract units exceed the cap")

    @staticmethod
    def format(value: tuple) -> str:
        return ", ".join(f"{contract}: {units}" for contract, units in value) if value else "none"
