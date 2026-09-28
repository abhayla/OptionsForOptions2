"""Typed slots for `MessageTemplate` (W-024 round 3): every value that fills a template placeholder
is validated and formatted by exactly one of these types — never a raw string interpolated by hand.

RCA (round 3): rounds 1-2 let `UserFacingError` accept four free-text strings at runtime, so any
caller could show any sentence; a denylist over that free text can never list every phrasing. Round
3's fix is structural: no free text reaches a user at all — only a fixed, reviewed template with
named, typed slots (`render(template_id, **slots)`), so the wording check runs once, over a finite
set, in CI (`tests/errors/test_error_catalogue.py`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ofo.engine.legs import Instrument as _EngineInstrument


class SlotType:
    """Base marker for a template slot type: validates a raw value, formats it for display."""

    @staticmethod
    def validate(value: object) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def format(value: object) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


class Money(SlotType):
    """A rupee amount. Must be `decimal.Decimal` (ADR-008: money is exact decimal, never float)."""

    @staticmethod
    def validate(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise TypeError(f"Money slot requires decimal.Decimal, got {type(value).__name__}")

    @staticmethod
    def format(value: Decimal) -> str:
        quantised = value.quantize(Decimal("1")) if value == value.to_integral_value() else value
        return f"₹{quantised:,}"


class Int(SlotType):
    """A plain count (e.g. lots, legs). Must be `int`, never `bool` or `float`."""

    @staticmethod
    def validate(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"Int slot requires int, got {type(value).__name__}")

    @staticmethod
    def format(value: int) -> str:
        return str(value)


class Time(SlotType):
    """A timezone-aware point in time. A naive `datetime` is refused (input-domain checklist)."""

    @staticmethod
    def validate(value: object) -> None:
        if not isinstance(value, datetime):
            raise TypeError(f"Time slot requires datetime.datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            raise ValueError("Time slot requires a timezone-aware datetime (naive datetime refused)")

    @staticmethod
    def format(value: datetime) -> str:
        return value.strftime("%d %b %Y, %H:%M %Z").strip()


class Instrument(SlotType):
    """A leg's option/future type. Must be `ofo.engine.legs.Instrument` (CE/PE/FUT), never a string."""

    @staticmethod
    def validate(value: object) -> None:
        if not isinstance(value, _EngineInstrument):
            raise TypeError(f"Instrument slot requires ofo.engine.legs.Instrument, got {type(value).__name__}")

    @staticmethod
    def format(value: _EngineInstrument) -> str:
        return value.name


_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+$")


class Code(SlotType):
    """A machine identifier (order id, error code fragment) — no spaces, no free-form sentences."""

    @staticmethod
    def validate(value: object) -> None:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("Code slot requires a non-empty str")
        if not _CODE_PATTERN.match(value):
            raise ValueError(f"Code slot must match {_CODE_PATTERN.pattern!r}, got {value!r}")

    @staticmethod
    def format(value: str) -> str:
        return value


@dataclass(frozen=True)
class ExternalText(SlotType):
    """A broker/vendor message, shown word for word in its own labelled field.

    Never merged into a sentence part, never scanned for our ADR-003 wording, never re-worded — it is
    someone else's text, clearly attributed. Round 3 replaces the paraphrased broker reason that used
    to live in the ORDER_REJECTION catalogue example with this: the real Zerodha message, quoted.
    """

    source: str
    text: str

    @staticmethod
    def validate(value: object) -> None:
        if not isinstance(value, ExternalText):
            raise TypeError(f"ExternalText slot requires an ExternalText instance, got {type(value).__name__}")
        if not value.source.strip() or not value.text.strip():
            raise ValueError("ExternalText requires non-blank source and text")

    @staticmethod
    def format(value: "ExternalText") -> str:
        return f"{value.source}'s message: «{value.text}»"
