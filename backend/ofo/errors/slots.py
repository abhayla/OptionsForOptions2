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
from ofo.execution.safety import CheckCode
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS


class SlotType:
    """Base marker for a template slot type: validates a raw value, formats it for display."""

    @staticmethod
    def validate(value: object) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def format(value: object) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


class Money(SlotType):
    """A non-negative rupee amount. Must be `decimal.Decimal` (ADR-008: money is exact decimal,
    never float), finite (NaN/Infinity refused: round-4 verifier finding — a template once rendered
    "₹NaN is below the ₹-5 this strategy needs"), and >= 0 — every current Money slot is an amount
    (available/required margin), never a P&L; a slot that legitimately needs a sign uses `PnLMoney`.
    """

    @staticmethod
    def validate(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise TypeError(f"Money slot requires decimal.Decimal, got {type(value).__name__}")
        if not value.is_finite():
            raise ValueError(f"Money slot requires a finite value, got {value!r} (NaN/Infinity refused)")
        if value < 0:
            raise ValueError(f"Money slot requires a non-negative amount, got {value!r}")

    @staticmethod
    def format(value: Decimal) -> str:
        quantised = value.quantize(Decimal("1")) if value == value.to_integral_value() else value
        return f"₹{quantised:,}"


class PnLMoney(SlotType):
    """A profit/loss rupee amount: may be negative (a loss), but still `decimal.Decimal` and finite
    (NaN/Infinity refused). Use only for a slot that is genuinely a signed P&L figure — every other
    money slot is `Money` (amounts are never negative)."""

    @staticmethod
    def validate(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise TypeError(f"PnLMoney slot requires decimal.Decimal, got {type(value).__name__}")
        if not value.is_finite():
            raise ValueError(f"PnLMoney slot requires a finite value, got {value!r} (NaN/Infinity refused)")

    @staticmethod
    def format(value: Decimal) -> str:
        quantised = value.quantize(Decimal("1")) if value == value.to_integral_value() else value
        sign = "-" if quantised < 0 else ""
        return f"{sign}₹{abs(quantised):,}"


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


#: Strict incident-reference format: "ERR-" + 8 hex digits, e.g. "ERR-1A2B3C4D". Chosen specifically
#: because hex digits cannot spell a word: this closes off the round-4 verifier's injection ("free
#: text with hyphens/underscores can spell an advice phrase") for any reference id, without relying
#: on the wording checker to catch it.
_REFERENCE_ID_PATTERN = re.compile(r"^ERR-[0-9A-Fa-f]{8}$")

#: The known check/error codes a Code slot may carry, alongside a strict reference id. Built from
#: `CheckCode` (the safety-gate check codes, W-014) rather than hand-duplicated, so a new check code
#: is automatically a valid Code value without a second list to keep in sync.
_KNOWN_CODES: frozenset[str] = frozenset(code.value for code in CheckCode)


class Code(SlotType):
    """A closed machine identifier: one of the known check/error codes (`CheckCode`), or a strict
    incident reference id (`ERR-` + 8 hex digits). Round-4 fix (REQ-065/W-024 second parked round):
    the old pattern accepted ANY hyphen/underscore-joined word ("risk-free", "GUARANTEED-PROFIT",
    "you_should_buy") because it never checked meaning, only character class — so advice wording
    reached a user through a slot the wording checker never looked at. A closed set has no room for
    that: neither "risk-free" nor "GUARANTEED-PROFIT" is a `CheckCode` value or matches the reference
    format, so both are refused at the slot boundary, before render() even reaches the wording check.
    """

    @staticmethod
    def validate(value: object) -> None:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("Code slot requires a non-empty str")
        if value in _KNOWN_CODES:
            return
        if _REFERENCE_ID_PATTERN.match(value):
            return
        raise ValueError(
            f"Code slot must be a known check code or match {_REFERENCE_ID_PATTERN.pattern!r}, got {value!r}"
        )

    @staticmethod
    def format(value: str) -> str:
        return value


class Underlying(SlotType):
    """A market symbol: closed to the underlyings this catalogue tracks (`SUPPORTED_UNDERLYINGS`,
    i.e. NIFTY/SENSEX) — never a free word, for the same reason `Code` is now closed: an unchecked
    string slot is a place advice wording (or anything else) can be smuggled into user-facing text."""

    @staticmethod
    def validate(value: object) -> None:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("Underlying slot requires a non-empty str")
        if value not in SUPPORTED_UNDERLYINGS:
            raise ValueError(
                f"Underlying slot must be one of {sorted(SUPPORTED_UNDERLYINGS)}, got {value!r}"
            )

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
