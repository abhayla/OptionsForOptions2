"""Typed slots for `MessageTemplate`: every value that fills a template placeholder is validated and
formatted by exactly one of these types, never a raw string interpolated by hand.

Spec basis: ADR-003 and owner decision Q226 ("every platform message comes from a fixed, reviewed
template catalogue with typed slots ... Zerodha's or the user's own text is only quoted, word for
word, in a labelled field and is never part of a template"); ADR-008 (money is exact decimal).

Round 5 (issue #30) closes every way a slot value could carry words:
- every slot needs the EXACT type (`type(v) is T`), never a subclass: a `str`/`int`/`Decimal`/
  `datetime` subclass can override `__format__`/`__str__`/`strftime` and print anything while
  comparing equal to an allowed value;
- `Code`, `Underlying`, `Instrument` and `ExternalSource` are closed sets, never free words;
- `Time` is printed from digits and a fixed month table in IST: a tz-aware datetime's zone NAME
  (`%Z`) is free text chosen by whoever built the tzinfo, so it is never printed;
- money is finite, capped, at most 2 decimal places, and signed only in a P&L slot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum, unique

from ofo.engine.legs import Instrument as _EngineInstrument
from ofo.execution.safety import CheckCode
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

#: Input-domain cap (builder brief checklist "absurd sizes"): no rupee amount shown in an error
#: exceeds ₹1 lakh crore (10^12). Anything larger is a bug upstream, refused rather than printed.
MONEY_ABS_MAX = Decimal("1000000000000")
#: Input-domain cap for plain integers shown in a message (lots, legs, minutes).
INT_ABS_MAX = 1_000_000_000

_PAISE = Decimal("0.01")
_IST = timezone(timedelta(hours=5, minutes=30))
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _require_exact(value: object, expected: type, slot: str) -> None:
    if type(value) is not expected:
        raise TypeError(f"{slot} slot requires exactly {expected.__name__}, got {type(value).__name__}")


class SlotType:
    """Base marker for a template slot type: validates a raw value, formats it for display."""

    @staticmethod
    def validate(value: object) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def format(value: object) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


def _validate_money(value: object, slot: str, *, signed: bool) -> None:
    _require_exact(value, Decimal, slot)
    assert isinstance(value, Decimal)
    if not value.is_finite():
        raise ValueError(f"{slot} slot requires a finite value, got {value!r} (NaN/Infinity refused)")
    if not signed and value < 0:
        raise ValueError(f"{slot} slot requires a non-negative amount, got {value!r}")
    if abs(value) > MONEY_ABS_MAX:
        raise ValueError(f"{slot} slot value {value!r} exceeds the cap {MONEY_ABS_MAX}")
    if value != value.quantize(_PAISE):
        raise ValueError(f"{slot} slot allows at most 2 decimal places (paise), got {value!r}")


def _format_rupees(magnitude: Decimal) -> str:
    """₹ + thousands separators; whole rupees without decimals, otherwise exactly 2 decimals."""
    magnitude = magnitude.copy_abs()
    if magnitude == magnitude.to_integral_value():
        return f"₹{magnitude.quantize(Decimal('1')):,}"
    return f"₹{magnitude.quantize(_PAISE):,}"


class Money(SlotType):
    """A rupee AMOUNT (available/required margin): exact `Decimal`, finite, >= 0, capped, paise at
    most. A slot that is genuinely a signed profit/loss uses `PnLMoney` instead."""

    @staticmethod
    def validate(value: object) -> None:
        _validate_money(value, "Money", signed=False)

    @staticmethod
    def format(value: Decimal) -> str:
        # copy_abs in _format_rupees: Decimal("-0") is zero and prints as ₹0, never "₹-0".
        return _format_rupees(value)


class PnLMoney(SlotType):
    """A profit/loss rupee figure: may be negative (a loss), otherwise the same rules as `Money`."""

    @staticmethod
    def validate(value: object) -> None:
        _validate_money(value, "PnLMoney", signed=True)

    @staticmethod
    def format(value: Decimal) -> str:
        sign = "-" if value < 0 else ""
        return f"{sign}{_format_rupees(value)}"


class Int(SlotType):
    """A whole number as the user entered it (may be zero or negative: that can be the error).
    Exactly `int` (not `bool`, not a subclass), |value| capped."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, int, "Int")
        assert isinstance(value, int)
        if abs(value) > INT_ABS_MAX:
            raise ValueError(f"Int slot value {value} exceeds the cap {INT_ABS_MAX}")

    @staticmethod
    def format(value: int) -> str:
        return str(int(value))


class Count(SlotType):
    """A count of real things (legs, lots, minutes): exactly `int`, 0 <= value <= cap."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, int, "Count")
        assert isinstance(value, int)
        if value < 0:
            raise ValueError(f"Count slot requires a value >= 0, got {value}")
        if value > INT_ABS_MAX:
            raise ValueError(f"Count slot value {value} exceeds the cap {INT_ABS_MAX}")

    @staticmethod
    def format(value: int) -> str:
        return str(int(value))


class Time(SlotType):
    """A timezone-aware point in time, shown in IST as "29 Sep 2026, 10:00 IST". A naive datetime is
    refused. Only digits and a fixed month name are printed; the tzinfo's own name never is."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, datetime, "Time")
        assert isinstance(value, datetime)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Time slot requires a timezone-aware datetime (naive datetime refused)")

    @staticmethod
    def format(value: datetime) -> str:
        ist = value.astimezone(_IST)
        return f"{ist.day:02d} {_MONTHS[ist.month - 1]} {ist.year:04d}, {ist.hour:02d}:{ist.minute:02d} IST"


class Instrument(SlotType):
    """A leg's option/future type: exactly `ofo.engine.legs.Instrument` (CE/PE/FUT)."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is not _EngineInstrument:
            raise TypeError(f"Instrument slot requires ofo.engine.legs.Instrument, got {type(value).__name__}")

    @staticmethod
    def format(value: _EngineInstrument) -> str:
        return {_EngineInstrument.CE: "CE", _EngineInstrument.PE: "PE", _EngineInstrument.FUT: "FUT"}[value]


#: Strict incident-reference format: "ERR-" + 8 hex digits, e.g. "ERR-1A2B3C4D". Hex digits cannot
#: spell any ADR-003/Q226 word. `fullmatch` (not `match` with `$`, which also accepts a trailing
#: newline).
_REFERENCE_ID_PATTERN = re.compile(r"ERR-[0-9A-F]{8}")

#: The known check codes a Code slot may carry, built from `CheckCode` (W-014) so a new check code
#: is valid without a second list to keep in sync.
_KNOWN_CODES: frozenset[str] = frozenset(code.value for code in CheckCode)


class Code(SlotType):
    """A closed machine identifier: a known `CheckCode` value, or a strict reference id
    (`ERR-` + 8 upper-case hex digits). Never a free word, however it is joined."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "Code")
        assert isinstance(value, str)
        if value in _KNOWN_CODES or _REFERENCE_ID_PATTERN.fullmatch(value):
            return
        raise ValueError(
            f"Code slot must be a known check code or match {_REFERENCE_ID_PATTERN.pattern!r}, got {value!r}"
        )

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


class Underlying(SlotType):
    """A market symbol, closed to the catalogue's underlyings (`SUPPORTED_UNDERLYINGS`)."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "Underlying")
        if value not in SUPPORTED_UNDERLYINGS:
            raise ValueError(f"Underlying slot must be one of {sorted(SUPPORTED_UNDERLYINGS)}, got {value!r}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


@unique
class ExternalSource(Enum):
    """Whose words an `ExternalText` quotes (Q226: "Zerodha's or the user's own text"). The value is
    the label shown before the quote; a closed set, so the label itself can never carry words."""

    ZERODHA = "Zerodha's message"
    USER = "Your own text"


@dataclass(frozen=True)
class ExternalText(SlotType):
    """Zerodha's or the user's own text, shown word for word in its own labelled field.

    Never merged into a sentence part, never scanned for our wording, never re-worded (Q226).
    """

    source: ExternalSource
    text: str

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, ExternalText, "ExternalText")
        assert isinstance(value, ExternalText)
        if type(value.source) is not ExternalSource:
            raise TypeError(f"ExternalText.source must be an ExternalSource, got {type(value.source).__name__}")
        _require_exact(value.text, str, "ExternalText.text")
        if not value.text.strip():
            raise ValueError("ExternalText requires non-blank text")

    @staticmethod
    def format(value: "ExternalText") -> str:
        return f"{value.source.value}: «{value.text}»"
