# ruff: noqa: E501, PLC0415
"""Explanation templates: platform wording that is NOT an error (W-024 round 9 part 2).

Decision (orchestrator as product owner, recorded in work/W-024.md): the timeline "why did this trigger?" text is not
an error, so REQ-065 AC-2's four parts do not apply; it is still platform wording, so it comes from this fixed,
reviewed catalogue (ADR-003 Q226: "every platform message comes from a fixed, reviewed template catalogue with typed
slots"), passes the same wording check, and is pinned in the same pin file as the error templates.

Each template is one line of an explanation and names which of the three explanation fields it belongs to:
`what_triggered`, `values_seen` or `rule`. Recorded data (the user's rule text, a source name, what the broker
reported) is printed exactly as stored, quoted, and never scanned as our wording.
"""
from __future__ import annotations

import datetime
import functools
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from ofo import wording as _wording

from ofo.errors.gate_slots import PlaybookField, PlaybookTypeName
from ofo.errors.slots import Count, SlotType, _require_exact
from ofo.errors.templates import MARGIN_SHORTFALL_NEXT_ACTION, ZERODHA_BUSY_TEXT

EXPLANATION_FIELDS: tuple[str, ...] = ("what_triggered", "values_seen", "rule")


def check_explanation_wording(text: str, where: str) -> None:
    """The platform's own words of an explanation: the old timeline phrase list AND the shared Q226/Q230 checker."""
    from ofo.strategy.wording import find_banned_phrases

    if not any(ch.isalpha() for ch in text):
        return  # a template of slots and punctuation only ("{a}: {b}") holds no platform words to check
    found = find_banned_phrases(text)
    found += [hit for hit in _wording.find_advice_wording(text) if hit not in found]
    if found:
        raise ValueError(f"the platform's own answer wording contains advice phrases {found}: {text!r}")
    _wording.check_platform_text(text, where)


# --- typed slots --------------------------------------------------------------------------------------------------

_EXPLANATION_MINT = object()


class ExplanationText(str):
    """A finished explanation line: made ONLY by `render_explanation()` (fix round, review MAJOR-1/MAJOR-2). A typed
    API field (ofo_app.api_models.CatalogueText) and the `Explained` slot accept this type and refuse a plain str, so
    text built anywhere else cannot pass as an explanation. Joining or slicing one gives a plain `str` again."""

    __slots__ = ()

    def __new__(cls, text: str, _mint: object = None) -> "ExplanationText":
        if _mint is not _EXPLANATION_MINT:
            raise TypeError("ExplanationText is made only by render_explanation()")
        return super().__new__(cls, text)


#: A recorded single value: no whitespace, at most 64 characters, so it can never carry a sentence.
_TOKEN_MAX = 64


class Recorded(SlotType):
    """A recorded VALUE printed exactly as stored (fix round, review MAJOR-1: no free text). Accepted: `int` (not
    bool), `Decimal`, a date/time, an `Enum` member's value, an `ExplanationText`, or a `str` that is one token (no
    whitespace, at most 64 characters: an id, a symbol, a code, a number). A sentence is refused: the user's own
    words go in a `UserText` slot (quoted), a nested explanation in an `Explained` slot."""

    @staticmethod
    def validate(value: object) -> None:
        if isinstance(value, BaseException):
            raise TypeError("an exception is never a slot value")
        if type(value) in (int, Decimal, datetime.date, datetime.time, datetime.datetime, ExplanationText):
            return
        if isinstance(value, Enum) and type(value.value) in (str, int):
            Recorded.validate(value.value)
            return
        if type(value) is str and value and len(value) <= _TOKEN_MAX and not any(ch.isspace() for ch in value):
            return
        raise TypeError(f"Recorded slot takes a typed value or one token, got {type(value).__name__} {value!r:.40}")

    @staticmethod
    def format(value: object) -> str:
        if isinstance(value, Enum):
            return str(value.value)
        return str.__str__(value) if isinstance(value, str) else str(value)


class Explained(SlotType):
    """A nested explanation line: exactly an `ExplanationText` from `render_explanation()`."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is not ExplanationText:
            raise TypeError(f"Explained slot takes a render_explanation() result, got {type(value).__name__}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


class Quoted(SlotType):
    """Recorded text (the user's rule text, a source name, a broker answer), printed quoted: never our wording. A
    platform line stored as that text (an `ExplanationText`) is accepted and quoted the same way."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is ExplanationText:
            return
        _require_exact(value, str, "Quoted")

    @staticmethod
    def format(value: str) -> str:
        return f'"{str.__str__(value)}"'


#: REQ-134 AC-1: the name a strategy holds until the user types one (the prefill, and every row saved before
#: migration 0025). Kept in the wording door; ofo.strategy.definition re-exports it for the strategy code.
DEFAULT_STRATEGY_NAME = "New Strategy"

_USER_WORDS_MINT = object()

#: The request-parsing layer (W-024 round 10 item 3): the modules where a value the user typed first enters the
#: domain. Only code IN these modules can mint `UserWords`; each entry names the request field it parses.
REQUEST_LAYER: Mapping[str, str] = MappingProxyType({
    "ofo.admin.client_id": "the Client ID an admin types (normalise_client_id)",
    "ofo.adjustment.playbook_text": "a playbook's name the user typed (name_shown)",
    "ofo.rules.model": "a rule's name and description the user typed (Rule.shown_name)",
    "ofo.strategy.definition": "the strategy settings the user changed (rules_ref, risk_limits, preferences)",
    "ofo.strategy.stored_form": "a strategy's name the user typed (check_strategy_name)",
})


class UserWords(str):
    """The user's own words, as parsed from a request field. Made ONLY by `user_words()` called from a module of
    `REQUEST_LAYER`; a direct call raises, so text from an exception (`str(e)`) built anywhere else cannot become
    user text."""

    __slots__ = ()

    def __new__(cls, text: str, _mint: object = None) -> "UserWords":
        if _mint is not _USER_WORDS_MINT:
            raise TypeError("UserWords is made only by user_words() in the request-parsing layer")
        return super().__new__(cls, text)


def user_words(value: object) -> UserWords:
    """Mint `UserWords` from a request field's value. Callable only from a `REQUEST_LAYER` module (fail closed: an
    unknown caller is refused); an exception, a non-`str` or a blank value is refused."""
    import sys

    caller = sys._getframe(1).f_globals.get("__name__")  # noqa: SLF001 - the caller's module is the door
    if caller not in REQUEST_LAYER:
        raise TypeError(f"user_words() is callable only from the request-parsing layer, not {caller!r}")
    if isinstance(value, BaseException):
        raise TypeError("an exception is never user text")
    _require_exact(value, str, "UserText")
    if not str.__str__(value).strip():
        raise ValueError("UserText must not be blank")
    return UserWords(value, _USER_WORDS_MINT)


class UserText(Quoted):
    """The user's own words (a rule name they typed, a value they entered), quoted word for word in the labelled place
    the template gives it (ADR-003 Q226: "Zerodha's or the user's own text is only quoted, word for word, in a
    labelled field"). Round 10 item 3: the slot takes only `UserWords` (minted by the request-parsing layer) or an
    `ExplanationText` (a platform line, e.g. a default rule description); a plain `str` - e.g. `str(e)` - is refused,
    and `UserText(...)` itself raises."""

    def __new__(cls, *args: object, **kwargs: object) -> "UserText":
        raise TypeError("UserText is a slot type; user text is minted only by user_words() in the request layer")

    @staticmethod
    def validate(value: object) -> None:
        if isinstance(value, BaseException):
            raise TypeError("an exception is never a slot value")
        if type(value) is ExplanationText or type(value) is UserWords:
            return
        raise TypeError(f"UserText slot takes UserWords from the request layer, got {type(value).__name__}")


#: Plain-language names of every rule input (units as REQ-041 AC-4 / ofo.rules.inputs define them), by enum name.
INPUT_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "UNDERLYING_LEVEL": "underlying level",
    "UNDERLYING_MOVE_POINTS": "underlying move (points)",
    "UNDERLYING_MOVE_PCT": "underlying move (%)",
    "DISTANCE_TO_SHORT_STRIKE": "distance to the nearest short strike (points)",
    "DISTANCE_TO_BREAKEVEN": "distance to the nearest breakeven (points)",
    "NET_PREMIUM": "net premium (Rs)",
    "LIVE_PNL": "live P&L (Rs)",
    "PNL_PCT_OF_MAX_PROFIT": "P&L as % of max profit",
    "PNL_PCT_OF_MAX_LOSS": "loss as % of max loss",
    "DTE": "days to expiry",
    "TIME_OF_DAY": "time of day (minutes after midnight IST)",
    "IV": "implied volatility",
    "IV_PERCENTILE": "IV percentile",
    "DELTA": "delta",
    "GAMMA": "gamma",
    "THETA": "theta",
    "VEGA": "vega",
})
OP_TEXT: Mapping[str, str] = MappingProxyType({"GTE": "at or above", "GT": "above", "LTE": "at or below", "LT": "below"})
ACTION_TEXT: Mapping[str, str] = MappingProxyType({
    "ALERT_ONLY": "alert only",
    "ALERT_AND_PREPARE_ORDERS": "alert and prepare orders for your review",
})
#: The words for a rule template's direction (ofo.rules.templates.Direction) and volatility measure (InputName).
DIRECTION_TEXT: Mapping[str, str] = MappingProxyType({"AT_OR_ABOVE": "at or above", "AT_OR_BELOW": "at or below"})
MEASURE_TEXT: Mapping[str, str] = MappingProxyType({"IV": "implied volatility", "IV_PERCENTILE": "IV percentile"})
#: The four partial-execution choices a user picks (REQ-058 AC-2; the first two spelled as the requirement fixes them).
CHOICE_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "COMPLETE_STRATEGY": "Complete Strategy",
    "RETRY_FAILED_LEG": "Retry Failed Leg",
    "REVIEW_MANUALLY": "Review Manually",
    "CLOSE_PARTIAL_STRATEGY": "Close Partial Strategy",
})
#: The order-sequence step names (ofo.execution.sequence.StepKind).
STEP_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "PROTECTION": "Establish protection",
    "SHORT_POSITIONS": "Establish short positions",
    "OTHER": "Legs with no protection relation",
})
#: The labels of the Builder's change history (W-016 / REQ-070 AC-2 to AC-4) and of the scenario and health tables.
BUILDER_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "ORIGINAL": "Original suggested setup",
    "STRIKE": "User modified strike",
    "QUANTITY": "User changed quantity",
    "ADD_LEG": "User added leg",
    "REMOVE_LEG": "User removed leg",
    "EXPIRY": "User changed expiry",
    "ALTERNATIVE": "Setup changed to alternative",
    "RESTORE": "User restored an earlier configuration",
    "UNDO": "User undid the last change",
})
#: W-196 (REQ-155, ADR-214): the names of the iron condor adjustment approaches, by catalogue A-id (decision support).
ADJUSTMENT_APPROACH_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "A-36": "No change",
    "A-01": "Roll the untested spread toward spot",
    "A-05": "Roll the tested spread out (same width)",
    "A-29": "Reduce the tested side",
    "A-28": "Close the tested spread",
    "A-11": "Re-centre both shorts at the money",
    "A-31": "Exit the whole strategy",
})
#: GC-ADJ2 step 3 (REQ-159 AC-5, REQ-160 AC-1): the playbook editor's names of the approaches NOT in ADJUSTMENT_APPROACH_LABEL_TEXT (that table stays the one home of its ids; a test holds the two disjoint). Source: tests/fixtures/adjust_scenarios/_playbooks.json approaches.
PLAYBOOK_APPROACH_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "A-02": "Roll the tested short away",
    "A-03": "Roll out in time (same strikes, next expiry)",
    "A-04": "Roll up/down and out (diagonal roll)",
    "A-06": "Shift a leg by +/- N strikes",
    "A-07": "Re-centre / reset around spot",
    "A-08": "Straddle-ise (move the untested short to the tested strike)",
    "A-09": "Add wings (cap the loss)",
    "A-10": "Inverted strangle",
    "A-12": "Convert to a (broken-wing) butterfly",
    "A-13": "Add a jade lizard",  # the fixture says "no risk on one side": a promise word (Q226), not shown
    "A-14": "Calendar / diagonal on the tested side",
    "A-15": "Ratio fix (buy back the extra short or add a far long)",
    "A-16": "Long option to debit spread",
    "A-17": "Roll a winning long up and take capital out",
    "A-18": "Gamma scalp with futures",
    "A-19": "Add a second calendar at the new spot",
    "A-20": "Delta hedge with futures",
    "A-21": "Delta hedge with a synthetic future",
    "A-22": "Debit spread in the direction of the breach",
    "A-23": "Delta-neutral helper (calculator)",
    "A-24": "Take profit, whole strategy",
    "A-25": "Take partial profit (close X%)",
    "A-26": "Close the untested side for profit",
    "A-27": "Buy back cheap shorts",
    "A-35": "Time exit",
    "A-32": "Stop-loss per leg",
    "A-33": "Move stop to cost after one stop",
    "A-34": "Re-enter after a stop",
    "A-30": "Add lots to the tested side",
    "A-37": "Alert only / watch a level",
    "A-38": "Pause monitoring until a time",
})
#: GC-ADJ2 step 3 (REQ-159 AC-4): each day-and-date rule kind in words.
PLAYBOOK_DAY_RULE_KIND_TEXT: Mapping[str, str] = MappingProxyType({
    "weekday": "Every week on",
    "beforeWeekend": "The last session before a weekend",
    "beforeHoliday": "The day before a market holiday",
    "afterBreak": "The first session after a weekend or holiday",
    "expiry": "Expiry day",
    "beforeExpiry": "The day before expiry",
    "monthlyWeek": "Monthly-expiry week",
    "dom": "Day of the month",
    "date": "A specific date",
    "event": "A known event day (needs the admin event list)",
    "away": "My unavailable days (fires the session before the first day)",
})
#: GC-ADJ2 step 3 (REQ-159 AC-4): each day rule action (body ``action`` index) in words.
PLAYBOOK_DAY_RULE_ACTION_TEXT: Mapping[str, str] = MappingProxyType({
    "0": "Run the carry check (overnight margin, gap loss)",
    "1": "Show reduce / partial profit / exit",
    "2": "Show add-hedge where it applies",
    "3": "Pause suggestions",
    "4": "Tighten every trigger by this %",
    "5": "Prepare an exit for review",
    "6": "Do not suggest rolls",
})
#: GC-ADJ2 step 3 (REQ-160 AC-1): the plain-words summary's sentences. A doubled brace is a slot the editor fills from the body ({name} after rendering); the words are the catalogue's.
PLAYBOOK_SUMMARY_TEXT: Mapping[str, str] = MappingProxyType({
    "type_line": "{{type}}, {{kind}} expiry. Stages: {{stages}}.",
    "kind_weekly": "weekly",
    "kind_monthly": "monthly",
    "stage_open": "{{name}} ({{from}}+ days left)",
    "stage_span": "{{name}} ({{from}}-{{to}} days left)",
    "stage_single": "{{name}} ({{from}} days left)",
    "looks_head": "Looks at an adjustment when (numbers per stage):",
    "trigger": "{{label}}: {{values}}",
    "trigger_unit": "{{label}}: {{values}} {{unit}}",
    "rules_head": "Combined rules:",
    "rule_all": "{{id}}: only when {{members}} all hold",
    "joiner_and": " and ",
    "shows": "Shows {{count}} approaches.",
    "days_head": "Day rules:",
    "day_rule": "{{when}} at {{at}}: {{action}}",
    "days_none": "none",
    "plan": "Plan: target {{target}}% of max profit, stop at {{stop}}% of max loss, at most {{max}} adjustments.",
})
#: GC-ADJ1 step 3 (REQ-046 AC-3, REQ-045 AC-5): one plain line per approach, shown in the Review adjustment drawer before
#: any pick. No figure, no ranking word (ADR-003).
ADJUSTMENT_APPROACH_ABOUT_TEXT: Mapping[str, str] = MappingProxyType({
    "A-36": "Keep every leg as it is. This is the baseline the others are compared with.",
    "A-01": "Move the side spot is moving away from closer to spot, keeping its width.",
    "A-05": "Move the side spot is pressing on further out, keeping its width.",
    "A-29": "Close part of the side spot is pressing on and keep the rest.",
    "A-28": "Close the whole side spot is pressing on and keep the other side.",
    "A-11": "Move both short strikes to the strike nearest spot, keeping each wing's distance.",
    "A-31": "Close every open leg.",
})
#: REQ-156 AC-2 (ADR-214 (2a)): each compare criterion row's shown name, in the AC-2 group order
ADJUSTMENT_CRITERION_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "credit": "Credit (+) or debit (-)",
    "cost": "Charges plus bid-ask cost",
    "margin_change": "Margin change (negative = margin freed)",
    "max_loss": "Max loss",
    "move_m2": "P&L if spot falls 2%",
    "move_m1": "P&L if spot falls 1%",
    "move_p1": "P&L if spot rises 1%",
    "move_p2": "P&L if spot rises 2%",
    "breakevens": "Breakevens",
    "max_profit": "Max profit",
    "premium_left": "Premium still left to earn",
    "pop": "POP",
    "delta": "Net delta",
    "gamma": "Gamma",
    "theta": "Theta",
    "vega": "Vega",
    "adjustments": "Adjustments used",
    "liquidity": "Strike liquidity (widest bid-ask spread)",
    "fresh": "Would you open this fresh",
})
#: REQ-156 AC-3: each row's leader in plain words (decision-support words only, ADR-003: no ranking word)
ADJUSTMENT_LEADER_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "credit": "Most credit",
    "cost": "Lowest cost",
    "margin_change": "Lowest margin change",  # the lowest value = frees the most margin, not "smallest"
    "max_loss": "Smallest max loss",
    "move_m2": "Highest P&L at -2%",
    "move_m1": "Highest P&L at -1%",
    "move_p1": "Highest P&L at +1%",
    "move_p2": "Highest P&L at +2%",
    "breakevens": "Widest profit range",
    "max_profit": "Highest max profit",
    "premium_left": "Most premium left",
    "pop": "Highest POP",
    "delta": "Closest to delta-neutral",
    "gamma": "Lowest gamma",
    "theta": "Most theta",
    "vega": "Lowest vega",
    "adjustments": "Fewest adjustments",
    "liquidity": "Tightest spreads",
    "fresh": "Smallest fresh max loss",
})
SCENARIO_VIEW_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "AT_EXPIRY": "At Expiry",
    "ESTIMATED_NOW": "Estimated Now (estimate)",
})
HEALTH_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "HEALTHY": "Healthy",
    "WATCH": "Watch",
    "ADJUSTMENT_OPPORTUNITY": "Adjustment opportunity",
    "EXIT_CONDITION_REACHED": "Exit condition reached",
})
FOLLOW_UP_TEXT: Mapping[str, str] = MappingProxyType({
    "ALERT_GENERATED": "Alert generated",
    "ORDER_PREPARED": "Order prepared",
    "CONFIRMATION_REQUIRED": "Confirmation required",
    "EXECUTED": "Executed",
    "BROKER_REPORTED": "Broker reported",
    "RECONCILIATION_SUCCEEDED": "Reconciliation succeeded",
})


def _enum_slot(name: str, enum_loader: Callable[[], type], table: Mapping[str, str]) -> type[SlotType]:
    def validate(value: object) -> None:
        if type(value) is not enum_loader() or value.name not in table:  # type: ignore[attr-defined]
            raise TypeError(f"{name} slot requires a known {enum_loader().__name__}, got {value!r}")

    def format(value: object) -> str:
        return table[value.name]  # type: ignore[attr-defined]

    return type(name, (SlotType,), {"validate": staticmethod(validate), "format": staticmethod(format)})


def _input_name() -> type:
    from ofo.rules.inputs import InputName
    return InputName


def _op() -> type:
    from ofo.rules.conditions import Op
    return Op


def _action() -> type:
    from ofo.rules.model import RuleAction
    return RuleAction


def _follow_up() -> type:
    from ofo.timeline.catalogue import FollowUpKind
    return FollowUpKind


def _direction() -> type:
    from ofo.rules.templates import Direction
    return Direction


InputLabel = _enum_slot("InputLabel", _input_name, INPUT_LABEL_TEXT)
OpWords = _enum_slot("OpWords", _op, OP_TEXT)
ActionWords = _enum_slot("ActionWords", _action, ACTION_TEXT)
FollowUpLabel = _enum_slot("FollowUpLabel", _follow_up, FOLLOW_UP_TEXT)
DirectionWords = _enum_slot("DirectionWords", _direction, DIRECTION_TEXT)
MeasureWords = _enum_slot("MeasureWords", _input_name, MEASURE_TEXT)


class Amount(SlotType):
    """A rule threshold the user typed (a level, a rupee amount, a bound): exactly `Decimal` or `int`, finite."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) not in (Decimal, int):
            raise TypeError(f"Amount slot requires Decimal or int, got {type(value).__name__}")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("Amount slot requires a finite number")

    @staticmethod
    def format(value: object) -> str:
        if isinstance(value, Decimal):  # plain notation, never 1E+3; a negative zero prints without its sign
            return f"{abs(value):f}" if value.is_zero() else f"{value:f}"
        return str(value)


class Days(SlotType):
    """A whole number of days to expiry: exactly `int`, 0 or more."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, int, "Days")
        if value < 0:  # type: ignore[operator]
            raise ValueError("Days slot requires a value >= 0")

    @staticmethod
    def format(value: int) -> str:
        return str(value)


class ClockHm(SlotType):
    """A time of day in IST, hours and minutes: exactly `datetime.time`."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, datetime.time, "ClockHm")

    @staticmethod
    def format(value: datetime.time) -> str:
        return value.isoformat("minutes")


class InputLabels(SlotType):
    """A non-empty tuple of rule inputs, shown by their plain-language names joined with ", "."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, tuple, "InputLabels")
        assert isinstance(value, tuple)
        if not value:
            raise ValueError("InputLabels slot requires at least one input")
        for item in value:
            InputLabel.validate(item)

    @staticmethod
    def format(value: tuple) -> str:
        return ", ".join(InputLabel.format(item) for item in value)


class YesNo(SlotType):
    """A recorded yes/no follow-up: exactly `bool`."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, bool, "YesNo")

    @staticmethod
    def format(value: bool) -> str:
        return "yes" if value else "no"



# --- W-066: the outcome's typed number slots and its closed label tables -----------------------------------------------

class Rupees(SlotType):
    """Exact money, a finite `Decimal`, printed to the paisa with Indian grouping and the rupee sign (display rules)."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, Decimal, "Rupees")
        if not value.is_finite():  # type: ignore[attr-defined]
            raise ValueError("Rupees slot requires a finite number")

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_rupees  # late: display imports this module
        return format_rupees(value)


class WholeRupees(SlotType):
    """REQ-152: a summary money figure in whole rupees, Indian grouping, no sign (net premium, margin figures)."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_whole_rupees  # late: display imports this module
        return format_whole_rupees(value, signed=False)


class SignedWholeRupees(SlotType):
    """REQ-152: a summary money figure in whole rupees, Indian grouping, "+" on profit, U+2212 on loss, "0" for zero."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_whole_rupees  # late: display imports this module
        return format_whole_rupees(value, signed=True)


class SignedRupeesPaisa(SlotType):
    """GC-TP fix1 (ADR-209): a signed paper P&L with the unit word, to the paisa: ``+Rs 962.00`` (REQ-089 AC-3 shape)."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_signed_paisa  # late: display imports this module
        shown = format_signed_paisa(value)
        sign = shown[0] if shown[0] in "+\u2212" else ""
        return f"{sign}Rs {shown[len(sign):]}"  # +Rs 962.00, (minus sign)Rs 1,100.45, Rs 0.00


class SignedPaisa(SlotType):
    """GC-UI D-B48: a paper P&L figure to the paisa, Indian grouping, "+" on profit, U+2212 on loss, "0.00" for zero."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_signed_paisa  # late: display imports this module
        return format_signed_paisa(value)


class WholePoints(SlotType):
    """REQ-152 / D-A04: an index level in whole points with Indian grouping and no currency sign."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_whole_points  # late: display imports this module
        return format_whole_points(value)


class OiCount(SlotType):
    """GC-UI D-B16: an open interest, a whole contract count of 0 or more (never a bool), in the drawer's compact Indian
    form ("62,075", "74.9L", "1.23Cr"); a real 0 prints "0"."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, int, "OiCount")
        if value < 0:  # type: ignore[operator]
            raise ValueError("OiCount slot requires a count of 0 or more")

    @staticmethod
    def format(value: int) -> str:
        from ofo.engine.display import format_oi_compact  # late: display imports this module
        return format_oi_compact(value)


class SignedPercent(SlotType):
    """REQ-153: a percent to one decimal, half-up, with "+" / U+2212; only a true zero is "0.0" with no sign (F-4)."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_signed_percent  # late: display imports this module
        return format_signed_percent(value)


class Points(SlotType):
    """An index level in points, a finite `Decimal`, Indian grouping and no currency sign (display rules)."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_points  # late: display imports this module
        return format_points(value)


class IndexLevel(SlotType):
    """An index or trigger level, a finite `Decimal`, Indian grouping, always two decimals, no currency sign."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        from ofo.engine.display import format_index_level  # late: display imports this module
        return format_index_level(value)


class TargetValue(SlotType):
    """A clamped what-if target (REQ-084 AC-2): a timezone-aware date-time in IST words, "3 Nov, 15:30 IST", or an
    index level as `IndexLevel` prints it, "23,000.00"."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is datetime.datetime:
            HourMinute.validate(value)
        else:
            IndexLevel.validate(value)

    @staticmethod
    def format(value: datetime.datetime | Decimal) -> str:
        if isinstance(value, datetime.datetime):
            ist = value.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
            return f"{ist.day} {ist.strftime('%b')}, {HourMinute.format(value)} IST"
        return IndexLevel.format(value)


#: The wording parts of a `LevelRegions` / `ExceptLevels` slot (ADR-072; issue #172), pinned as `labels:level_region`
#: so a changed word needs a new pin ("pending owner read").
LEVEL_REGION_TEXT: Mapping[str, str] = MappingProxyType({
    "at": "at {lo}", "below": "below {hi}", "above": "above {lo}", "between": "between {lo} and {hi}",
    "except": "{region} (except exactly {levels})", "and": "{rest} and {last}", "or": "{rest} or {last}",
})


class ExceptLevels(SlotType):
    """A non-empty, strictly ascending tuple of `Points` levels in plain notation: printed "X", "X and Y", "X, Y and Z"
    (the exact zero points inside a loss; issue #172)."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is not tuple or not value:
            raise TypeError(f"ExceptLevels slot takes a non-empty tuple, got {type(value).__name__}")
        for level in value:
            Points.validate(level)
            if "E" in str(level).upper():
                raise ValueError(f"a level is written in plain notation, got {level!r:.40}")
        if any(not value[i - 1] < value[i] for i in range(1, len(value))):
            raise ValueError("except levels must be strictly ascending")

    @staticmethod
    def format(value: tuple) -> str:
        parts = [Points.format(level) for level in value]
        return parts[0] if len(parts) == 1 else LEVEL_REGION_TEXT["and"].format(rest=", ".join(parts[:-1]),
                                                                                  last=parts[-1])


class LevelRegions(SlotType):
    """A non-empty tuple of level intervals ``(lower, upper)`` or ``(lower, upper, excepts)``, each bound a `Points`
    value or None (an open end, never both None) and ``excepts`` an `ExceptLevels` value strictly inside the interval:
    printed "below X", "between X and Y", "above X", with " (except exactly Z)" after a region that has excepts, joined
    "a, b or c" (ADR-072; issue #172)."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is not tuple or not value:
            raise TypeError(f"LevelRegions slot takes a non-empty tuple, got {type(value).__name__}")
        for item in value:
            if type(item) is not tuple or len(item) not in (2, 3) or item[0] is None and item[1] is None:
                raise TypeError(f"a level region is (lower, upper[, excepts]) with at least one bound, got {item!r:.40}")
            for bound in item[:2]:
                if bound is not None:
                    Points.validate(bound)
            for bound in item[:2]:
                if bound is not None and "E" in str(bound).upper():
                    raise ValueError(f"a level bound is written in plain notation, got {bound!r:.40}")
            if item[0] is not None and item[1] is not None and item[0] > item[1]:
                raise ValueError(f"a level region needs lower <= upper, got {item!r:.40}")
            if len(item) == 3:
                ExceptLevels.validate(item[2])
                if any((item[0] is not None and z <= item[0]) or (item[1] is not None and z >= item[1])
                       for z in item[2]):
                    raise ValueError(f"an except level lies strictly inside its region, got {item!r:.60}")
        last = len(value) - 1
        for i, (lo, hi, *_) in enumerate(value):
            if lo is None and i != 0:
                raise ValueError("only the first level region may have an open lower end")
            if hi is None and i != last:
                raise ValueError("only the last level region may have an open upper end")
            if i and value[i - 1][1] is not None and lo is not None and not value[i - 1][1] < lo:
                raise ValueError("level regions must be in order, without overlap, duplicates or touching ends")

    @staticmethod
    def format(value: tuple) -> str:
        text = LEVEL_REGION_TEXT
        parts = []
        for lo, hi, *excepts in value:
            lo_t = None if lo is None else Points.format(lo)
            hi_t = None if hi is None else Points.format(hi)
            key = "at" if lo is not None and lo == hi else "below" if lo is None else "above" if hi is None else "between"
            part = text[key].format(lo=lo_t, hi=hi_t)
            if excepts:
                part = text["except"].format(region=part, levels=ExceptLevels.format(excepts[0]))
            parts.append(part)
        return parts[0] if len(parts) == 1 else text["or"].format(rest=", ".join(parts[:-1]), last=parts[-1])


class SignedAmount(SlotType):
    """A finite `Decimal` printed with an explicit sign (+16.7)."""

    @staticmethod
    def validate(value: object) -> None:
        Rupees.validate(value)

    @staticmethod
    def format(value: Decimal) -> str:
        return f"{abs(value):+f}" if value.is_zero() else f"{value:+f}"  # plain notation, never +1E+2 or -0


class HourMinute(SlotType):
    """A timezone-aware time as the IST hour and minute, "09:20" (the data-label wording)."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, datetime.datetime, "HourMinute")
        if value.tzinfo is None or value.utcoffset() is None:  # type: ignore[attr-defined]
            raise ValueError("HourMinute slot requires a timezone-aware datetime")

    @staticmethod
    def format(value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime("%H:%M")


class ClockSeconds(SlotType):
    """A timezone-aware time as the IST clock time with seconds, "10:42:17 AM" (ADR-015's example)."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.errors.gate_slots import Clock
        Clock.validate(value)

    @staticmethod
    def format(value: datetime.datetime) -> str:
        from ofo.errors.gate_slots import Clock
        return Clock.format(value)


class UnderlyingName(SlotType):
    """An index name, closed to the catalogue's underlyings (NIFTY, SENSEX): never a free token (W-066 round 2)."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
        _require_exact(value, str, "UnderlyingName")
        if value not in SUPPORTED_UNDERLYINGS:
            raise ValueError(f"UnderlyingName slot must be one of {sorted(SUPPORTED_UNDERLYINGS)}, got {value!r}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


_INSTRUMENT_REF = re.compile(r"[A-Z][A-Z_]{0,15}:[0-9]{1,12}")
#: A Kite trading symbol (NIFTY2610822800CE, SENSEX26OCTFUT; the instrument dump also holds ARE&M, BAJAJ-AUTO).
_TRADING_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9&-]{0,39}")


class InstrumentRef(SlotType):
    """An instrument identity in the platform's form `SEGMENT:token` (NSE_FO:44624): a pattern, no free token."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "InstrumentRef")
        if not _INSTRUMENT_REF.fullmatch(value):  # type: ignore[arg-type]
            raise ValueError(f"InstrumentRef slot requires SEGMENT:token, got {value!r:.40}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


class LegRef(SlotType):
    """A leg named by its trading symbol (upper case letters and digits) or by its `SEGMENT:token` identity."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "LegRef")
        if not (_INSTRUMENT_REF.fullmatch(value) or _TRADING_SYMBOL.fullmatch(value)):  # type: ignore[arg-type]
            raise ValueError(f"LegRef slot requires a trading symbol or SEGMENT:token, got {value!r:.40}")

    @staticmethod
    def format(value: str) -> str:
        return str.__str__(value)


class LegRefs(SlotType):
    """A non-empty tuple of `LegRef`, joined with ", " by the formatter."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is not tuple or not value:
            raise TypeError(f"LegRefs slot takes a non-empty tuple, got {type(value).__name__}")
        for item in value:
            LegRef.validate(item)

    @staticmethod
    def format(value: tuple) -> str:
        return ", ".join(LegRef.format(item) for item in value)


class HealthWord(SlotType):
    """A data-health state: exactly a `DataHealth` member (never a string)."""

    @staticmethod
    def validate(value: object) -> None:
        from ofo.rules.inputs import DataHealth
        if type(value) is not DataHealth:
            raise TypeError(f"HealthWord slot requires a DataHealth, got {type(value).__name__}")

    @staticmethod
    def format(value: Enum) -> str:
        return str(value.value)


class ExpiryDate(SlotType):
    """A contract expiry: exactly a `datetime.date`, printed ISO."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, datetime.date, "ExpiryDate")

    @staticmethod
    def format(value: datetime.date) -> str:
        return value.isoformat()


class DayMonth(SlotType):
    """A contract date as day and month, no year: exactly a `datetime.date`, printed "24 Nov" (REQ-146 AC-5)."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, datetime.date, "DayMonth")

    @staticmethod
    def format(value: datetime.date) -> str:
        return f"{value.day:02d} {value.strftime('%b')}"


def _cell_enums() -> tuple[type, ...]:
    from ofo.engine.legs import Action, Instrument
    from ofo.table.model import LegStatus
    return (Action, Instrument, LegStatus)


class CellText(SlotType):
    """A text table cell: a leg number (`int`), an expiry (`date`) or a member of a closed enum (Action, Instrument,
    LegStatus). Never a string: money, points and numbers have their own cell templates."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is int and value >= 0:
            return
        if type(value) is datetime.date:
            return
        if type(value) in _cell_enums():
            return
        raise TypeError(f"CellText slot takes a leg number, a date or a closed enum member, got {type(value).__name__}")

    @staticmethod
    def format(value: object) -> str:
        if isinstance(value, Enum):
            return str(value.value)
        return value.isoformat() if isinstance(value, datetime.date) else str(value)


#: The 21 fixed table column headings (REQ-035 AC-2), by `ofo.table.columns.ColumnId` name.
COLUMN_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "LEG": "Leg", "ACTION": "Action", "INSTRUMENT": "Instrument", "EXPIRY": "Expiry", "STRIKE": "Strike",
    "QUANTITY": "Quantity", "ENTRY_PRICE": "Entry Price", "LTP": "LTP", "ENTRY_VALUE": "Entry Value",
    "CURRENT_VALUE": "Current Value", "UNREALIZED_PNL": "Unrealized P&L", "PNL_PERCENT": "P&L %", "IV": "IV",
    "DELTA": "Delta", "GAMMA": "Gamma", "THETA": "Theta", "DECAY": "Decay", "VEGA": "Vega", "LOWER_BE": "Lower Breakeven",
    "UPPER_BE": "Upper Breakeven", "STATUS": "Status",
})

#: GC-ADJ2 1A (REQ-158 AC-1; docs/design/playbook-body-v1.md "Strategy types"): each playbook strategy type's shown
#: name, by key, in the design note's order. ofo.adjustment.playbook_types holds the keys and reads the names here.
_PLAYBOOK_TYPE_LABELS_FILE = Path(__file__).resolve().parent.parent / "adjustment" / "playbook_type_labels.json"
PLAYBOOK_TYPE_LABEL_TEXT: Mapping[str, str] = MappingProxyType(
    json.loads(_PLAYBOOK_TYPE_LABELS_FILE.read_text(encoding="utf-8")))  # data, not code: no strategy name typed here

#: GC-ADJ2 step 4 (REQ-161 AC-1, AC-2; mockup screen 4): the fixed words of the strategy plan sheet and the tracking
#: panel's Plan entry, by key. Each is one reviewed template `plan_sheet_<key>`; the browser prints what the server sends.
PLAN_SHEET_LABEL_TEXT: Mapping[str, str] = MappingProxyType({
    "title": "When tracking starts: this strategy's plan", "playbook": "Playbook", "target": "Target",
    "stop": "Stop", "max_adjustments": "Max adjustments", "time_exit": "Time exit",
    "customise": "Customise triggers", "use_as_is": "Use playbook as is", "save": "Save plan", "close": "Close",
    "plan_entry": "Plan", "edit": "Edit plan", "no_plan": "No plan saved yet", "hour": "Hour", "minute": "Minute",
})

#: Why a table cell has no value (the cell's `reason`), by key. Each is one reviewed template `table_reason_<key>`.
TABLE_REASON_TEXT: Mapping[str, str] = MappingProxyType({
    "not_applicable": "not applicable",
    "not_available": "not available",
    "no_ltp": "no LTP for this leg",
    "entry_zero": "entry value is zero",
    "no_iv": "no implied volatility for this leg",
    "fut_no_strike": "a futures leg has no strike",
    "fut_no_iv": "a futures leg has no implied volatility",
    "no_scenario": "no scenario view is available",
    "no_status": "no status was given for this leg",
    "not_all_ltp": "not every leg has an LTP",
    "max_loss_multi_expiry": "max loss is exact only for a single-expiry strategy",
    "max_loss_unlimited": "max loss is unlimited",
    "max_loss_zero": "max loss is zero",
    "not_all_iv": "not every leg has an implied volatility",
    "futures_notional": "a premium and a futures notional cannot be added",
    "no_lower_be": "no lower breakeven",
    "no_upper_be": "no upper breakeven",
    "no_health": "no strategy health was given",
    "not_same_quantity": "the legs have different quantities, so there is no single per-unit figure",
    "no_next_open": "the market calendar has no next open, so there is no decay to it",
})


def _column_id() -> type:
    from ofo.table.columns import ColumnId
    return ColumnId


def _strategy_health() -> type:
    from ofo.table.model import StrategyHealth
    return StrategyHealth


def _scenario_view() -> type:
    from ofo.scenario.views import View
    return View


ColumnLabel = _enum_slot("ColumnLabel", _column_id, COLUMN_LABEL_TEXT)
HealthLabel = _enum_slot("HealthLabel", _strategy_health, HEALTH_LABEL_TEXT)
ScenarioViewLabel = _enum_slot("ScenarioViewLabel", _scenario_view, SCENARIO_VIEW_LABEL_TEXT)


@functools.lru_cache(maxsize=1)
def _reviewed_template_texts() -> frozenset[str]:
    from ofo.strategy.loader import load_templates

    return frozenset(text for t in load_templates() for text in (t.name, t.description))


class TemplateText(SlotType):
    """A name or description of a strategy template that the reviewed catalogue (ofo.strategy.loader, wording-checked at
    load) holds, word for word (W-117). Any other string is refused, so a route cannot pass its own sentence."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is not str or value not in _reviewed_template_texts():
            raise TypeError("TemplateText slot takes a template name or description held by the strategy catalogue")

    @staticmethod
    def format(value: object) -> str:
        return str(value)


# --- the catalogue ------------------------------------------------------------------------------------------------

class Values(SlotType):
    """A list of recorded values or explanation lines, joined with ", " by the formatter (never by a caller): a
    non-empty tuple whose items each pass `Recorded`, or one `ExplanationText` (e.g. a "none" line)."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) is ExplanationText:
            return
        if type(value) is not tuple or not value:
            raise TypeError(f"Values slot takes a non-empty tuple, got {type(value).__name__}")
        for item in value:
            Recorded.validate(item)

    @staticmethod
    def format(value: object) -> str:
        if type(value) is ExplanationText:
            return str.__str__(value)
        return ", ".join(Recorded.format(item) for item in value)  # type: ignore[union-attr]


class LegacyRecorded(SlotType):
    """KNOWN GAP (fix round, review MAJOR-1): the old free `str` slot, kept ONLY for the templates in
    `LEGACY_SLOT_TEMPLATES`, whose callers are in backend/ofo/engine and backend/ofo/scenario (owned by W-060 while it
    is open). tests/errors/test_explanation_slots.py pins that set so it can only shrink."""

    @staticmethod
    def validate(value: object) -> None:
        if isinstance(value, BaseException):
            raise TypeError("an exception is never a slot value")
        if type(value) not in (str, int, Decimal, ExplanationText):
            raise TypeError(f"slot requires str, int or Decimal, got {type(value).__name__}")

    @staticmethod
    def format(value: object) -> str:
        return str(value)


LEGACY_SLOT_TEMPLATES: frozenset[str] = frozenset({"estimate_line", "estimate_assume_iv",
                                                   "estimate_assume_valued"})
JOIN_SEPARATORS: frozenset[str] = frozenset({", ", "; ", " | ", " "})


@dataclass(frozen=True)
class ExplanationTemplate:
    """One reviewed line of an explanation: its field, its text (`{slot}` placeholders) and typed slots."""

    id: str
    field: str
    text: str
    slots: Mapping[str, type[SlotType]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.field not in EXPLANATION_FIELDS:
            raise ValueError(f"explanation field must be one of {EXPLANATION_FIELDS}, got {self.field!r}")
        object.__setattr__(self, "slots", MappingProxyType(dict(self.slots)))


def approach_name_id(approach_id: str) -> str:
    """The template id of an adjustment approach's shown name (``A-36`` -> ``adjust_approach_name_a_36``)."""
    return "adjust_approach_name_" + approach_id.lower().replace("-", "_")


def approach_about_id(approach_id: str) -> str:
    """The template id of an approach's one-line text (``A-36`` -> ``adjust_approach_about_a_36``)."""
    return "adjust_approach_about_" + approach_id.lower().replace("-", "_")


_EXPLANATIONS: tuple[ExplanationTemplate, ...] = (
    ExplanationTemplate("why_triggered", "what_triggered", "Your rule was triggered: {rule_text} ({kind} rule {rule_id}).",
                        {"rule_text": Quoted, "kind": Recorded, "rule_id": Recorded}),
    ExplanationTemplate("why_condition_met", "values_seen",
                        "Condition met: {input} was {value}, {op} the threshold {threshold}.",
                        {"input": InputLabel, "value": Recorded, "op": OpWords, "threshold": Recorded}),
    ExplanationTemplate("why_no_condition", "values_seen",
                        "Condition met: this rule has no market condition; it applies as soon as it is checked."),
    ExplanationTemplate("why_not_available", "values_seen", "Not available when checked: {inputs}.",
                        {"inputs": InputLabels}),
    ExplanationTemplate("why_checked_at", "values_seen", "Checked at: {time}.", {"time": Recorded}),
    ExplanationTemplate("why_market_data", "values_seen", "Market data: source {source}, health {health}.",
                        {"source": Quoted, "health": Recorded}),
    ExplanationTemplate("why_active_version", "rule", "Active strategy version: {version}.", {"version": Recorded}),
    ExplanationTemplate("why_planned_version", "rule",
                        "Active strategy version: none (not yet executed); evaluated against planned version "
                        "{version}.", {"version": Recorded}),
    ExplanationTemplate("why_action", "rule", "The rule's chosen action: {action}.", {"action": ActionWords}),
    ExplanationTemplate("why_follow_up_missing", "rule", "{follow_up}: not recorded.", {"follow_up": FollowUpLabel}),
    ExplanationTemplate("why_follow_up_yes_no", "rule", "{follow_up}: {answer}.",
                        {"follow_up": FollowUpLabel, "answer": YesNo}),
    ExplanationTemplate("why_follow_up_answer", "rule", "{follow_up}: {answer}.",
                        {"follow_up": FollowUpLabel, "answer": Quoted}),
    # Rule labels (ofo.rules.templates, REQ-041 AC-2/AC-3): the description a rule shows in lists and in "why".
    ExplanationTemplate("rule_label_enter_now", "rule", "Enter now"),
    ExplanationTemplate("rule_label_underlying_level", "rule", "Underlying {direction} {level}",
                        {"direction": DirectionWords, "level": Amount}),
    ExplanationTemplate("rule_label_underlying_range", "rule", "Underlying between {low} and {high}",
                        {"low": Amount, "high": Amount}),
    ExplanationTemplate("rule_label_net_credit", "rule", "Net credit at least Rs {target}", {"target": Amount}),
    ExplanationTemplate("rule_label_net_debit", "rule", "Net debit at most Rs {target}", {"target": Amount}),
    ExplanationTemplate("rule_label_volatility_between", "rule", "{measure} between {low} and {high}",
                        {"measure": MeasureWords, "low": Amount, "high": Amount}),
    ExplanationTemplate("rule_label_volatility_at_or_above", "rule", "{measure} at or above {low}",
                        {"measure": MeasureWords, "low": Amount}),
    ExplanationTemplate("rule_label_volatility_at_or_below", "rule", "{measure} at or below {high}",
                        {"measure": MeasureWords, "high": Amount}),
    ExplanationTemplate("rule_label_time_window", "rule", "Between {start} and {end} IST",
                        {"start": ClockHm, "end": ClockHm}),
    ExplanationTemplate("rule_label_profit_target", "rule", "Profit target {amount}", {"amount": Amount}),
    ExplanationTemplate("rule_label_max_loss", "rule", "Max loss {amount}", {"amount": Amount}),
    ExplanationTemplate("rule_label_days_to_expiry", "rule", "{days} days to expiry or fewer", {"days": Days}),
    # Order-sequence margin notes (ofo.execution.sequence): shown with the prepared order sequence.
    ExplanationTemplate("margin_note_no_planner", "values_seen", "margin impact unknown — not used (no margin planner)"),
    ExplanationTemplate("margin_note_planner_failed", "values_seen",
                        "margin impact unknown — not used (the margin planner failed)"),
    ExplanationTemplate("margin_note_used", "values_seen",
                        "margin impact used as the tie-break within each step; unverified against real Zerodha "
                        "margin behaviour (ADR-017 Q26)"),
    ExplanationTemplate("margin_note_not_used", "values_seen", "margin impact unknown — not used"),
    ExplanationTemplate("margin_note_not_needed", "values_seen",
                        "margin impact not needed: no step has two legs to order"),
    # Pre-execution risk flags (ofo.execution.safety): warnings shown beside a passed gate, not errors.
    ExplanationTemplate("flag_unlimited_loss", "values_seen",
                        "This strategy's possible loss has no upper limit if the market moves far enough."),
    ExplanationTemplate("flag_multi_expiry", "values_seen",
                        "This strategy has legs on more than one expiry; its exact at-expiry maximum loss cannot "
                        "be computed."),
    ExplanationTemplate("flag_charges_unavailable", "values_seen",
                        "A charges estimate is not available for this strategy."),
    ExplanationTemplate("flag_stale_on_exit", "values_seen", "Prices shown may be stale — confirm to continue."),
    ExplanationTemplate("flag_price_band_unknown_on_exit", "values_seen",
                        "We could not check this exit's price against today's price band — confirm to continue."),
    ExplanationTemplate("flag_expiry_day_entry", "values_seen",
                        "{symbol} expires today. Bought on its expiry day it gives no margin offset against a "
                        "short leg that expires later.", {"symbol": LegRef}),
    ExplanationTemplate("flag_expiry_day_short", "values_seen",
                        "{symbol} is a short leg that expires today. Selling it on its expiry day carries extra "
                        "expiry-day margin (an extra 2% on short options) and no margin offset against a later-expiry "
                        "leg.", {"symbol": LegRef}),
    ExplanationTemplate("flag_expiry_day_future", "values_seen",
                        "{symbol} is a future that expires today. A position taken on its expiry day gets no margin "
                        "offset against a leg that expires later. Futures expiry is cash-settled.", {"symbol": LegRef}),
    ExplanationTemplate("confirm_expiry_day_short", "values_seen",
                        "{symbols}: short leg(s) that expire today. Selling on the expiry day carries extra "
                        "expiry-day margin (an extra 2% on short options) and no margin offset against a later-expiry "
                        "leg.", {"symbols": LegRefs}),
    ExplanationTemplate("flag_expiry_day_future_short", "values_seen",
                        "{symbol} is a short future that expires today. Selling it on its expiry day gets no margin "
                        "offset against a leg that expires later. Futures expiry is cash-settled.",
                        {"symbol": LegRef}),
    ExplanationTemplate("confirm_expiry_day_short_future", "values_seen",
                        "{symbols}: short future(s) that expire today, with no margin offset against a later-expiry "
                        "leg. Futures expiry is cash-settled.", {"symbols": LegRefs}),
    ExplanationTemplate("confirm_to_continue", "values_seen", "Confirm to continue."),
    # --- round 9 part 5: platform wording that was built inline (admin, estimate, review, rules, labels) -----------
    ExplanationTemplate("label_client_id", "values_seen", "Client ID"),
    ExplanationTemplate("client_id_not_valid", "values_seen",
                        "{value} is not a Client ID (expected 6 characters: 2 letters + 4 digits or 3 letters + 3 "
                        "digits, e.g. AB1234 or ABC123)", {"value": UserText}),
    ExplanationTemplate("import_row_ref", "values_seen", "row {number} ({category})",
                        {"number": Recorded, "category": Recorded}),
    ExplanationTemplate("import_refused", "values_seen", "import of {file} refused; unresolved: {rows}",
                        {"file": Recorded, "rows": Values}),
    ExplanationTemplate("import_row_duplicate", "values_seen", "{client_id} also appears on row {row}",
                        {"client_id": Recorded, "row": Recorded}),
    ExplanationTemplate("import_row_inactive", "values_seen",
                        "{client_id} is on the list but INACTIVE; reactivate or exclude this row",
                        {"client_id": Recorded}),
    ExplanationTemplate("import_row_already", "values_seen", "{client_id} is already on the list",
                        {"client_id": Recorded}),
    ExplanationTemplate("import_row_new", "values_seen", "{client_id} will be added", {"client_id": Recorded}),
    ExplanationTemplate("import_row_excluded", "values_seen", "excluded by admin"),
    ExplanationTemplate("import_row_reactivated", "values_seen", "{client_id} will be reactivated",
                        {"client_id": Recorded}),
    ExplanationTemplate("estimate_line", "values_seen", "Estimated {label}: {value} (estimate; assumes {assumptions})",
                        {"label": LegacyRecorded, "value": LegacyRecorded, "assumptions": LegacyRecorded}),
    ExplanationTemplate("estimate_label_pnl_now", "values_seen", "P&L now at {underlying} {level}",
                        {"underlying": Recorded, "level": Recorded}),
    ExplanationTemplate("estimate_ivs_none", "values_seen", "none (futures only)"),
    ExplanationTemplate("estimate_assume_model", "values_seen", "{model} model", {"model": Recorded}),
    ExplanationTemplate("estimate_assume_iv", "values_seen", "IV {ivs}", {"ivs": LegacyRecorded}),
    ExplanationTemplate("estimate_assume_rate", "values_seen", "rate {rate}", {"rate": Recorded}),
    ExplanationTemplate("estimate_assume_valued", "values_seen", "valued {time}", {"time": LegacyRecorded}),
    ExplanationTemplate("estimate_model_name", "values_seen",
                        "Black-Scholes-Merton (European, each expiry's implied dividend yield from put-call parity; "
                        "\"estimated from spot\" when the forward is unavailable)"),  # ADR-061, ADR-063
    ExplanationTemplate("alternative_choice_reason", "values_seen",
                        "User chose {chosen} {instrument} instead of unavailable {original} {instrument} ({code})",
                        {"chosen": Recorded, "instrument": Recorded, "original": Recorded, "code": Recorded}),
    ExplanationTemplate("review_note_undetermined", "values_seen", "{leg}: {reason}",
                        {"leg": Recorded, "reason": Recorded}),
    ExplanationTemplate("review_note_naked", "values_seen", "{legs}: {units} sold units have no protective leg (naked)",
                        {"legs": Values, "units": Recorded}),
    ExplanationTemplate("review_unknown_multi_expiry", "values_seen",
                        "legs expire on different dates; exact at-expiry values do not exist"),
    ExplanationTemplate("review_unknown_no_ltp", "values_seen", "no current price (LTP) for every leg"),
    ExplanationTemplate("review_unknown_margin", "values_seen", "the margin estimate is unavailable"),
    ExplanationTemplate("source_note_instrument_list", "values_seen",
                        "Kite Connect's public instrument dump (no login required); the source of every contract, "
                        "lot size, tick size and strike in the catalogue."),
    ExplanationTemplate("rule_alert", "what_triggered", "Your rule was triggered: {rule} ({detail}).",
                        {"rule": UserText, "detail": Explained}),
    ExplanationTemplate("rule_no_condition_detail", "values_seen", "no condition"),
    ExplanationTemplate("rule_cannot_decide", "values_seen", "cannot be decided without: {inputs}",
                        {"inputs": Values}),
    ExplanationTemplate("rule_input_state", "values_seen", "{input} ({state})", {"input": Recorded, "state": Recorded}),
    ExplanationTemplate("rule_observation", "values_seen", "{input} {value} {op} {threshold}",
                        {"input": Recorded, "value": Recorded, "op": Recorded, "threshold": Recorded}),
    ExplanationTemplate("plan_no_exit_rule", "rule",
                        "No exit rule is defined. This strategy is still monitored, but no exit alert of yours will "
                        "fire. You may want to consider defining an exit condition."),
    ExplanationTemplate("plan_no_adjustment_rule", "rule",
                        "No adjustment rule is defined. This strategy is still monitored; the platform may point out "
                        "an adjustment opportunity, but no rule of yours will trigger."),
    ExplanationTemplate("scenario_estimated_unavailable", "values_seen",
                        "Estimated Now is unavailable: no implied volatility for {legs}", {"legs": LegRefs}),
    # The caption is the PAIR "<underlying> at expiry | You make/lose" (Q227): two reviewed halves, joined by " | ".
    ExplanationTemplate("scenario_caption_left", "values_seen", "{underlying} at expiry", {"underlying": UnderlyingName}),
    ExplanationTemplate("scenario_caption_right", "values_seen", "You make/lose"),
    ExplanationTemplate("strike_part", "values_seen", " {strike}", {"strike": Recorded}),
    ExplanationTemplate("strike_none", "values_seen", ""),
    ExplanationTemplate("contract_description", "values_seen", "{underlying}{strike} {instrument} {expiry}",
                        {"underlying": Recorded, "strike": Explained, "instrument": Recorded, "expiry": Recorded}),
    # REQ-151 (U23): a contract as the screens print it, "NIFTY 3 Nov 22650 PE" (the strike and CE/PE only on an option)
    ExplanationTemplate("contract_display", "values_seen", "{underlying} {day} {month}{strike} {instrument}",
                        {"underlying": Recorded, "day": Recorded, "month": Recorded, "strike": Explained, "instrument": Recorded}),
    ExplanationTemplate("leg_description", "values_seen", "{action}{strike} {instrument} {expiry} x{quantity}",
                        {"action": Recorded, "strike": Explained, "instrument": Recorded, "expiry": Recorded,
                         "quantity": Recorded}),
    ExplanationTemplate("change_underlying", "values_seen", "underlying {old} -> {new}",
                        {"old": Recorded, "new": Recorded}),
    ExplanationTemplate("change_leg_removed", "values_seen", "removed leg {leg}", {"leg": Recorded}),
    ExplanationTemplate("change_leg_added", "values_seen", "added leg {leg}", {"leg": Recorded}),
    ExplanationTemplate("change_quantity", "values_seen", "quantity of {leg} was {before}",
                        {"leg": Recorded, "before": Recorded}),
    ExplanationTemplate("change_field", "values_seen", "{map} {name}: {old} -> {new}",
                        {"map": Recorded, "name": Recorded, "old": Recorded, "new": Recorded}),
    ExplanationTemplate("change_rules_ref", "values_seen", "rules reference: {old} -> {new}",
                        {"old": Recorded, "new": Recorded}),
    ExplanationTemplate("change_value_unset", "values_seen", "not set"),
    ExplanationTemplate("change_legs_reordered", "values_seen", "legs reordered"),
    ExplanationTemplate("change_entries_repriced", "values_seen", "planned entry prices repriced"),
    ExplanationTemplate("change_replaced_unreadable", "values_seen", "definition replaced, the previous one could not be compared"),
    ExplanationTemplate("change_summary_unreadable", "values_seen", "this change could not be shown"),
    ExplanationTemplate("change_restored", "values_seen", "restored entry {seq}", {"seq": Recorded}),
    # REQ-134 AC-1: a strategy's name as the API shows it - the user's own words, quoted word for word (ADR-003)
    ExplanationTemplate("strategy_name_shown", "values_seen", "{name}", {"name": UserText}),
    # GC-ADJ2 step 2 (REQ-158 AC-3): a playbook's name as the API shows it - the user's own words (ADR-003)
    ExplanationTemplate("playbook_name_shown", "values_seen", "{name}", {"name": UserText}),
    ExplanationTemplate("change_renamed", "values_seen", "Renamed from {old} to {new}",
                        {"old": UserText, "new": UserText}),
    ExplanationTemplate("rule_label_days_to_expiry_from", "rule", "{days} days to expiry or fewer, from {time} IST",
                        {"days": Days, "time": ClockHm}),
    # --- W-066 (issue #151, REQ-034 AC-7): every text of the outcome API, with typed slots --------------------------
    ExplanationTemplate("outcome_not_connected", "values_seen", "Draft — Live data not connected"),
    # REQ-077 AC-9: no live data, At Expiry numbers from the user's own prices (never a live price)
    ExplanationTemplate("outcome_from_entries", "values_seen", "From your prices - no live data"),
    # REQ-133 AC-3: the feed just (re)connected and no price frame arrived yet, inside the staleness limit: no number
    ExplanationTemplate("outcome_waiting_first_price", "values_seen", "Waiting for the first live price"),
    ExplanationTemplate("outcome_from_entries_centre", "values_seen",
                        "There is no live index price, so the levels are centred on your strike {level}.",
                        {"level": Points}),
    ExplanationTemplate("outcome_from_entries_no_estimate", "values_seen",
                        "Estimated Now needs live prices, which are not available. At Expiry is shown from your "
                        "prices."),
    # REQ-084 AC-2 / AC-5 (owner 2026-10-29, question tool "Approve all three"): the what-if target's three sentences
    ExplanationTemplate("target_estimate_label", "values_seen",
                        "Estimate from the pricing model at your target, not a forecast."),
    ExplanationTemplate("target_clamped", "values_seen", "Target moved to the nearest allowed value: {value}.",
                        {"value": TargetValue}),
    ExplanationTemplate("target_greeks_no_time_left", "values_seen",
                        "No Greeks at expiry: the options have no time left."),
    # GC-TP R-19a (REQ-144 AC-1..AC-4, Sensibull 020): the Projected badge and the Target block's two captions
    ExplanationTemplate("target_badge_profit", "values_seen", "Projected profit: Rs {amount}", {"amount": WholeRupees}),
    ExplanationTemplate("target_badge_loss", "values_seen", "Projected loss: Rs {amount}", {"amount": WholeRupees}),
    ExplanationTemplate("target_badge_zero", "values_seen", "Projected P/L: {amount}", {"amount": WholeRupees}),
    ExplanationTemplate("target_badge_unavailable", "values_seen", "Projected figure not available"),
    ExplanationTemplate("target_badge_no_target", "values_seen", "No target is set."),
    ExplanationTemplate("target_badge_percent_unavailable", "values_seen",
                        "% of margin needed not available: Zerodha margin could not be read"),
    ExplanationTemplate("target_days_to_expiry", "values_seen", "{days}D to expiry", {"days": Days}),
    ExplanationTemplate("target_move_no_spot", "values_seen",
                        "The move from spot is not available: there is no live index price."),
    # GC-TP R-18 (ADR-209): the line naming the booked P&L a paper strategy's target figures include
    ExplanationTemplate("target_includes_booked", "values_seen", "includes {amount} booked", {"amount": SignedRupeesPaisa}),
    ExplanationTemplate("target_booked_unreadable", "values_seen",
                        "Booked profit and loss could not be read, so these figures are for the open legs only."),
    # W-071 (owner-approved 2026-10-15): the reprice prompt of a reopened draft leg; frontend REPRICE_PROMPT.
    ExplanationTemplate("draft_leg_needs_reprice", "values_seen", "This leg was saved without a planned entry. Reprice it to see its numbers."),
    ExplanationTemplate("outcome_refused", "values_seen", "Outcome refused"),
    ExplanationTemplate("outcome_reason_no_provider", "values_seen", "no live market data provider is connected"),
    ExplanationTemplate("outcome_margin_pending", "values_seen",
                        "Margin from Zerodha is not shown yet; it needs your Kite login."),
    # ADR-099: Zerodha's margin for the planned orders on the outcome screen (information, not advice: ADR-003)
    # GC-UI D-A47: two wordings, chosen on the server by the ADR-094 top-up (margin_gate.basket_requirement). Top-up
    # 0: Zerodha's figure already includes the bought legs' premium and nothing was added, so no addition is named.
    ExplanationTemplate("outcome_margin_checked", "values_seen",
                        "Zerodha's own margin figure is {broker_needed}, which already includes the premium of the "
                        "legs you buy; {available} is available in your Zerodha account.",
                        {"broker_needed": Rupees, "available": Rupees}),
    ExplanationTemplate("outcome_margin_checked_top_up", "values_seen",
                        "Zerodha's own margin figure is {broker_needed}; your planned entry prices are above "
                        "Zerodha's, which adds about {top_up}, so about {needed} is needed (an estimate); "
                        "{available} is available in your Zerodha account.",
                        {"broker_needed": Rupees, "top_up": Rupees, "needed": Rupees, "available": Rupees}),
    # REQ-055 AC-4: the Builder's shortfall line, decided on the server (Margin.shortfall); text only, no action
    ExplanationTemplate("outcome_margin_short", "values_seen",
                        "Zerodha's own margin figure is {broker_needed}, which already includes the premium of the "
                        "legs you buy; {available} is available in your account. " + MARGIN_SHORTFALL_NEXT_ACTION,
                        {"broker_needed": Rupees, "available": Rupees}),
    ExplanationTemplate("outcome_margin_short_top_up", "values_seen",
                        "Zerodha's own margin figure is {broker_needed}; your planned entry prices are above "
                        "Zerodha's, which adds about {top_up}, so about {needed} is needed (an estimate); "
                        "{available} is available in your account. " + MARGIN_SHORTFALL_NEXT_ACTION,
                        {"broker_needed": Rupees, "top_up": Rupees, "needed": Rupees, "available": Rupees}),
    ExplanationTemplate("outcome_margin_unreadable", "values_seen",
                        "Margin from Zerodha could not be read just now, so no margin figure is shown."),
    ExplanationTemplate("outcome_margin_empty", "values_seen",  # an EMPTY answer: outcome page and adjustment route
                        "Zerodha returned no margin figure for this basket."),
    ExplanationTemplate("outcome_margin_empty_funds", "values_seen",  # the available-funds read stated no figure
                        "Zerodha returned no available-funds figure for this account."),
    ExplanationTemplate("outcome_margin_busy", "values_seen", ZERODHA_BUSY_TEXT),  # REQ-118 AC-3
    ExplanationTemplate("outcome_margin_no_basket", "values_seen",
                        "Margin from Zerodha is shown when every leg is a listed Zerodha contract."),
    # REQ-155 (ADR-214): the adjustment approaches answer; every outside source's state worded here, never in the route
    ExplanationTemplate("adjust_pop_held", "values_seen",
                        "POP not available: the probability figure is held until its legal review is answered."),
    ExplanationTemplate("adjust_pop_no_volatility", "values_seen",
                        "POP not available: no implied volatility or time to expiry for this expiry."),
    ExplanationTemplate("adjust_pop_no_forward", "values_seen", "POP not available: no forward price for this expiry."),
    ExplanationTemplate("adjust_pop_different_expiries", "values_seen",
                        "POP not available: the legs are on different expiries."),
    ExplanationTemplate("adjust_pop_spot_stale_or_missing", "values_seen",
                        "POP not available: the spot is stale or missing."),
    ExplanationTemplate("adjust_margin_not_available", "values_seen", "Margin not available: {reason}",
                        {"reason": Explained}),
    # GC-ADJ2 1C (REQ-045 AC-1, Q252): the adjustment check's two flag labels and the playbook type's shown name
    ExplanationTemplate("adjust_check_flag_system", "what_triggered", "Adjustment opportunity detected"),
    ExplanationTemplate("adjust_check_flag_user", "what_triggered", "Your rule was triggered"),
    ExplanationTemplate("adjust_check_type_name", "values_seen", "{name}", {"name": PlaybookTypeName}),
    # GC-ADJ2 step 5 (REQ-112 AC-2/AC-6, REQ-162): suggestion outcomes, dismiss reasons and the inbox's fixed words
    ExplanationTemplate("suggestion_outcome_open", "values_seen", "Open"),
    ExplanationTemplate("suggestion_outcome_dismissed", "values_seen", "You dismissed this"),
    ExplanationTemplate("suggestion_outcome_acted_on", "values_seen", "Acted on"),
    ExplanationTemplate("suggestion_outcome_acted_on_paper", "values_seen", "Acted on - Paper - not sent to Zerodha"),
    ExplanationTemplate("suggestion_outcome_completed", "values_seen", "Completed"),
    ExplanationTemplate("suggestion_outcome_partly_completed", "values_seen", "Partly completed"),
    ExplanationTemplate("suggestion_outcome_lapsed", "values_seen", "Lapsed"),
    ExplanationTemplate("suggestion_lapsed_condition_stopped", "values_seen", "The condition stopped holding"),
    ExplanationTemplate("suggestion_lapsed_strategy_closed", "values_seen", "The strategy closed"),
    ExplanationTemplate("suggestion_dismiss_expected_within_plan", "values_seen", "Expected and within my plan"),
    ExplanationTemplate("suggestion_dismiss_will_act_later", "values_seen", "I will act later"),
    ExplanationTemplate("suggestion_dismiss_not_relevant", "values_seen", "Not relevant"),
    ExplanationTemplate("suggestion_dismiss_other", "values_seen", "Other"),
    ExplanationTemplate("suggestion_group_count", "what_triggered", "{count} adjustment conditions triggered",
                        {"count": Count}),
    ExplanationTemplate("suggestion_inbox_empty", "values_seen", "No adjustment opportunities"),
    ExplanationTemplate("adjust_condition_line", "values_seen", "{trigger}: {value} {cmp} {threshold}",
                        {"trigger": PlaybookField, "value": PlaybookField, "cmp": Explained,
                         "threshold": PlaybookField}),
    ExplanationTemplate("adjust_cmp_le", "values_seen", "at or below"),
    ExplanationTemplate("adjust_cmp_ge", "values_seen", "at or above"),
    ExplanationTemplate("adjust_cmp_lt", "values_seen", "below"),
    ExplanationTemplate("adjust_spot_from_feed", "values_seen", "Spot from the live feed"),
    ExplanationTemplate("adjust_spot_from_rest_quote", "values_seen", "Spot from a REST quote"),
    ExplanationTemplate("adjust_spot_from_last_close", "values_seen", "Spot from the last close"),
    ExplanationTemplate("adjust_spot_not_available", "values_seen",
                        "Spot not available (live feed: {feed}; REST quote: {rest}; last close: {close}), so no "
                        "After is computed.", {"feed": Explained, "rest": Explained, "close": Explained}),
    ExplanationTemplate("adjust_spot_why_absent", "values_seen", "nothing is held"),
    ExplanationTemplate("adjust_spot_why_feed_absent", "values_seen", "the feed is not connected"),
    ExplanationTemplate("adjust_spot_why_rest_quote_absent", "values_seen", "no quote was requested"),
    ExplanationTemplate("adjust_spot_why_last_close_absent", "values_seen", "no close is stored"),
    ExplanationTemplate("adjust_spot_why_rest_quote_failed", "values_seen", "the quote request failed"),
    ExplanationTemplate("adjust_spot_why_rest_quote_empty", "values_seen", "the quote had no price"),
    ExplanationTemplate("adjust_spot_why_feed_not_finite", "values_seen", "the feed's last price was not a number"),
    ExplanationTemplate("adjust_spot_why_no_price", "values_seen", "it carried no price"),
    ExplanationTemplate("adjust_spot_why_no_time", "values_seen", "it carried no time"),
    ExplanationTemplate("adjust_spot_why_tick_in_future", "values_seen", "its time is in the future"),
    ExplanationTemplate("adjust_spot_why_stale", "values_seen", "its last price is too old"),
    ExplanationTemplate("adjust_spot_why_not_finite", "values_seen", "its last price was not a number"),
    ExplanationTemplate("adjust_spot_why_not_found", "values_seen", "it does not know this contract"),
    ExplanationTemplate("adjust_spot_why_failed", "values_seen", "the read failed"),
    ExplanationTemplate("adjust_spot_why_empty", "values_seen", "the quote had no price"),
    ExplanationTemplate("adjust_booked_unknown", "values_seen",
                        "The booked P&L of this strategy could not be read, so no whole-trade figure is shown."),
    ExplanationTemplate("adjust_charges_unknown", "values_seen",
                        "Charges not available, so the figures after charges are not shown."),
    ExplanationTemplate("adjust_unknown_approach", "values_seen", "{approach} is not an approach this screen builds.",
                        {"approach": Recorded}),
    ExplanationTemplate("adjust_available_spot_missing", "values_seen",
                        "Not checked now: the spot is not available, so no approach can be built."),
    ExplanationTemplate("adjust_needs_one_expiry", "values_seen",
                        "The whole-trade After needs every open leg on one expiry."),
    ExplanationTemplate("outcome_feed_disconnected", "values_seen",
                        "Live market data disconnected. Last updated: {time}. Live strategy monitoring is paused.",
                        {"time": ClockSeconds}),
    ExplanationTemplate("data_label_stale", "values_seen", "stale since {time} IST", {"time": HourMinute}),
    ExplanationTemplate("data_label_delayed", "values_seen", "delayed, as of {time} IST", {"time": HourMinute}),
    ExplanationTemplate("label_estimated_from_spot", "values_seen", "estimated from spot"),
    ExplanationTemplate("leg_label_symbol", "values_seen", "{symbol}: {label}",
                        {"symbol": LegRef, "label": Explained}),
    ExplanationTemplate("leg_label_no_quote", "values_seen", "no live quote"),
    ExplanationTemplate("leg_label_quote_unusable", "values_seen", "quote {health}; not used", {"health": HealthWord}),
    ExplanationTemplate("leg_label_quote_no_price", "values_seen", "quote has no last price"),
    ExplanationTemplate("leg_label_no_iv", "values_seen", "no implied volatility for this price"),
    # W-125 (REQ-079 AC-4, ADR-150 (2) verbatim): on every leg placed by the fixed rule, until its strike is edited.
    ExplanationTemplate("ready_made_fixed_rule_label", "rule", "Strikes placed by a fixed rule - change them"),
    ExplanationTemplate("outcome_problem_leg", "values_seen", "Instrument {leg} cannot be used: {why}", {"leg": InstrumentRef, "why": Explained}),
    ExplanationTemplate("outcome_why_not_in_snapshot", "values_seen", "not in the snapshot"),
    ExplanationTemplate("outcome_why_unknown_instrument", "values_seen", "unknown instrument"),
    ExplanationTemplate("outcome_why_expired", "values_seen", "expired"),
    ExplanationTemplate("outcome_why_other_underlying", "values_seen",
                        "the contract is on {contract_on}, the strategy is on {underlying}",
                        {"contract_on": UnderlyingName, "underlying": UnderlyingName}),
    ExplanationTemplate("outcome_why_leg_input", "values_seen", "this leg cannot be valued from the data received"),
    ExplanationTemplate("outcome_why_forward", "values_seen",
                        "the forward price could not be derived from the option chain"),
    ExplanationTemplate("outcome_forward_error", "values_seen", "forward for {expiry}: {why}",
                        {"expiry": ExpiryDate, "why": Explained}),
    ExplanationTemplate("outcome_spot_missing", "values_seen",
                        "the {underlying} index value is missing; the outcome is refused", {"underlying": UnderlyingName}),
    ExplanationTemplate("outcome_spot_unusable", "values_seen",
                        "the {underlying} spot is {health}; the calculation is refused",
                        {"underlying": UnderlyingName, "health": HealthWord}),
    ExplanationTemplate("outcome_forward_refused", "values_seen",
                        "a forward price is missing or was read on other inputs; the outcome is refused"),
    ExplanationTemplate("summary_lose_unlimited", "values_seen",
                        "Your loss has no fixed limit if {index} rises far enough by expiry.", {"index": UnderlyingName}),
    ExplanationTemplate("summary_lose_at_most", "values_seen", "At most {amount} at expiry, before charges and taxes.", {"amount": Rupees}),
    ExplanationTemplate("summary_lose_at_most_with_charges", "values_seen",
                        "At most {amount} at expiry, including about {charges} of charges and taxes.",
                        {"amount": Rupees, "charges": Rupees}),
    ExplanationTemplate("summary_lose_exercise_stt_note", "values_seen",
                        "Holding a bought option to expiry in the money adds STT on its value; "
                        "squaring off before expiry avoids it."),
    ExplanationTemplate("summary_make_unlimited", "values_seen",
                        "Your profit has no fixed limit if {index} rises far enough by expiry.", {"index": UnderlyingName}),
    ExplanationTemplate("summary_make_none", "values_seen", "This strategy cannot make money at expiry."),
    # G-065 (REQ-148 AC-4/AC-6, ADR-143 (1), REQ-083 AC-3): legs on more than one expiry have no exact at-expiry payoff;
    # the worst-case line is ADR-143's own words, also the At Expiry chart's reason
    ExplanationTemplate("mixed_expiry_worst_case", "values_seen",
                        "Worst case: the loss for this strategy can't be estimated."),
    ExplanationTemplate("summary_make_mixed_expiry", "values_seen",
                        "The most this strategy can make can't be estimated: its legs are on more than one expiry."),
    ExplanationTemplate("summary_start_mixed_expiry", "values_seen",
                        "Where losses start can't be estimated: the legs are on more than one expiry."),
    ExplanationTemplate("summary_reward_risk_none", "values_seen", "No fixed maximum"),
    # REQ-081 (W-154): the money summary. No return, gain, expected or promise wording (ADR-003, ADR-164).
    ExplanationTemplate("money_premium_get", "values_seen", "Get {amount}", {"amount": Rupees}),
    ExplanationTemplate("money_premium_pay", "values_seen", "Pay {amount}", {"amount": Rupees}),
    ExplanationTemplate("money_premium_futures", "values_seen", "premium and futures value cannot be added"),
    ExplanationTemplate("money_price_missing", "values_seen", "a planned price is missing for at least one leg"),
    ExplanationTemplate("money_value_price_missing", "values_seen",
                        "a live price is missing for at least one leg or for the index"),
    ExplanationTemplate("money_value_label", "values_seen", "value of the options, not P&L"),
    ExplanationTemplate("money_charges_label", "values_seen", "estimate"),
    ExplanationTemplate("money_reward_risk_zero_loss", "values_seen", "max loss is 0"),
    ExplanationTemplate("money_reward_risk_no_charges", "values_seen",
                        "the charges could not be priced, so the ratio is not shown"),
    ExplanationTemplate("money_charges_exercise_stt", "values_seen",
                        "STT on exercise: {pct}% of the value of a bought option that finishes in the money. "
                        "It depends on where the index settles, so it is not in this total.", {"pct": Amount}),
    ExplanationTemplate("money_reward_risk_multi_expiry", "values_seen",
                        "no worst case for legs on different expiries"),
    # REQ-081 AC-9/AC-11 (ADR-207 (8)): the percent basis is the margin needed; the label is only "% of margin needed"
    ExplanationTemplate("money_margin_percent", "values_seen", "{pct}% of margin needed", {"pct": Amount}),
    ExplanationTemplate("money_margin_percent_small", "values_seen", "less than 0.1% of margin needed"),
    ExplanationTemplate("summary_make_at_most", "values_seen", "At most {amount} at expiry, before charges and taxes.", {"amount": Rupees}),
    ExplanationTemplate("summary_make_at_most_with_charges", "values_seen",
                        "At most {amount} at expiry, including about {charges} of charges and taxes.",
                        {"amount": Rupees, "charges": Rupees}),
    ExplanationTemplate("summary_start_regions", "values_seen", "If {index} ends {regions} at expiry.",
                        {"index": UnderlyingName, "regions": LevelRegions}),
    ExplanationTemplate("summary_start_touch", "values_seen", "At every level except exactly {levels} at expiry.",
                        {"levels": ExceptLevels}),
    # GC-UI D-A46: charges known; the levels are the pre-charges payoff's breakevens (spec sections 1 and 3)
    ExplanationTemplate("summary_start_regions_with_charges", "values_seen",
                        "If {index} ends {regions} at expiry, before about {charges} of charges and taxes.",
                        {"index": UnderlyingName, "regions": LevelRegions, "charges": Rupees}),
    ExplanationTemplate("summary_start_touch_with_charges", "values_seen",
                        "At every level except exactly {levels} at expiry, before about {charges} of charges and "
                        "taxes.", {"levels": ExceptLevels, "charges": Rupees}),
    ExplanationTemplate("summary_start_never", "values_seen", "At no level at expiry."),
    ExplanationTemplate("summary_start_everywhere", "values_seen",
                        "At every level at expiry."),
    ExplanationTemplate("scenario_view_label", "values_seen", "{view}", {"view": ScenarioViewLabel}),
    ExplanationTemplate("table_column_label", "values_seen", "{column}", {"column": ColumnLabel}),
    ExplanationTemplate("scenario_header_plain", "values_seen", "{level}", {"level": Points}),
    ExplanationTemplate("scenario_header_current", "values_seen", "CURRENT {level}", {"level": Points}),
    ExplanationTemplate("scenario_header_zero_pnl", "values_seen", "0-P&L {level}", {"level": Points}),
    ExplanationTemplate("scenario_header_current_zero_pnl", "values_seen", "CURRENT 0-P&L {level}",
                        {"level": Points}),
    ExplanationTemplate("summary_whole_rupees", "values_seen", "{amount}", {"amount": WholeRupees}),
    ExplanationTemplate("summary_whole_rupees_signed", "values_seen", "{amount}", {"amount": SignedWholeRupees}),
    ExplanationTemplate("summary_paisa_signed", "values_seen", "{amount}", {"amount": SignedPaisa}),
    # GC-TP step 8a (REQ-109 AC-10): a paper strategy's Charges, to the paisa, beside its P&L
    ExplanationTemplate("paper_charges", "values_seen", "{amount}", {"amount": Rupees}),
    # GC-TP step 7a (ADR-207 (5), REQ-109 AC-8): the paper stop-loss texts - the stop order's reason and the alert
    ExplanationTemplate("paper_stop_reason_index", "what_triggered",
                        "Conditional exit: {underlying} crossed {direction} {level}",
                        {"underlying": UnderlyingName, "direction": Recorded, "level": IndexLevel}),
    ExplanationTemplate("paper_stop_reason_leg", "what_triggered", "Stop-loss: {contract} crossed {direction} {level}",
                        {"contract": Explained, "direction": Recorded, "level": IndexLevel}),
    ExplanationTemplate("paper_trigger_level", "values_seen", "{level}", {"level": IndexLevel}),
    ExplanationTemplate("paper_alert_title", "what_triggered", "Paper strategy - {name}", {"name": Explained}),
    ExplanationTemplate("paper_alert_leg", "values_seen", "{contract} at {price}",
                        {"contract": Explained, "price": Explained}),
    ExplanationTemplate("paper_alert_legs", "values_seen", "{rest}, {leg}", {"rest": Explained, "leg": Explained}),
    ExplanationTemplate("paper_alert_body", "what_triggered",
                        "{what}; exited {count} legs at {prices}. A paper exit only: no order "
                        "was sent to Zerodha.",
                        {"what": Explained, "count": Recorded, "prices": Explained}),
    ExplanationTemplate("summary_breakeven_level", "values_seen", "{level}", {"level": WholePoints}),
    ExplanationTemplate("summary_breakeven_percent", "values_seen", "{level} ({percent}%)",
                        {"level": WholePoints, "percent": SignedPercent}),
    ExplanationTemplate("cell_dash", "values_seen", "\u2014"),
    # GC-UI step 4 (REQ-083 AC-4, REQ-137 AC-1/AC-3): the SD table and bands, and the payoff table's limits
    ExplanationTemplate("sd_move", "values_seen", "{points} ({percent}%)", {"points": Amount, "percent": Amount}),
    ExplanationTemplate("sd_label", "values_seen", "{n}SD", {"n": Recorded}),
    ExplanationTemplate("sd_no_iv", "values_seen",
                        "The standard deviation needs the at-the-money implied volatility, which is not available."),
    ExplanationTemplate("sd_no_spot", "values_seen",
                        "The standard deviation needs a live index price, which is not available."),
    ExplanationTemplate("payoff_table_too_many_rows", "values_seen",
                        "This range has too many rows at a {step}-point interval. Pick a wider interval.",
                        {"step": Amount}),
    # GC-UI D-B16 / D-B17 (REQ-083 AC-5, AC-6): the payoff chart's OI bars; the AC-6 line always opens with the
    # requirement's own words, then the reason. Today's OI change (D-B18) is Later: no template for it.
    ExplanationTemplate("outcome_oi_count", "values_seen", "{count}", {"count": OiCount}),
    ExplanationTemplate("outcome_oi_read_at", "values_seen", "OI data at {time} IST", {"time": HourMinute}),
    ExplanationTemplate("outcome_oi_nearest_expiry", "values_seen",
                        "OI is shown for the nearest expiry, {expiry}.", {"expiry": ExpiryDate}),
    ExplanationTemplate("outcome_oi_not_connected", "values_seen",
                        "OI not available for this expiry: live data is not connected."),
    ExplanationTemplate("outcome_oi_not_streaming", "values_seen",
                        "OI not available for this expiry: its strikes are not streaming."),
    ExplanationTemplate("outcome_oi_stale", "values_seen",
                        "OI not available for this expiry: the feed is stale."),
    ExplanationTemplate("outcome_oi_no_strikes", "values_seen",
                        "OI not available for this expiry: no listed strike is inside the chart's range."),
    ExplanationTemplate("cell_rupees", "values_seen", "{amount}", {"amount": Rupees}),
    ExplanationTemplate("cell_rupees_cr", "values_seen", "{amount} Cr", {"amount": Rupees}),
    ExplanationTemplate("cell_rupees_dr", "values_seen", "{amount} Dr", {"amount": Rupees}),
    ExplanationTemplate("cell_points", "values_seen", "{value}", {"value": Points}),
    ExplanationTemplate("cell_percent", "values_seen", "{value}%", {"value": Amount}),
    ExplanationTemplate("cell_percent_signed", "values_seen", "{value}%", {"value": SignedAmount}),
    ExplanationTemplate("cell_number", "values_seen", "{value}", {"value": Amount}),
    ExplanationTemplate("cell_text", "values_seen", "{value}", {"value": CellText}),
    ExplanationTemplate("cell_health", "values_seen", "{health}", {"health": HealthLabel}),
    # GC-UI step 5 (REQ-091 AC-2..AC-5, ADR-203, F-64): the Strategy Chart's source, future label, notes and reasons
    ExplanationTemplate("price_history_source", "values_seen", "Kite historical 1-minute candles"),
    ExplanationTemplate("price_history_future_label", "values_seen", "{underlying} {expiry} FUT",
                        {"underlying": UnderlyingName, "expiry": DayMonth}),
    ExplanationTemplate("price_history_leg_listed_from", "values_seen", "{leg} listed from {date}; showing {days} days",
                        {"leg": LegRef, "date": ExpiryDate, "days": Days}),
    ExplanationTemplate("price_history_leg_ended_on", "values_seen",
                        "{leg} has no prices after {date}; the chart ends there", {"leg": LegRef, "date": ExpiryDate}),
    ExplanationTemplate("price_history_leg_not_listed", "values_seen", "{leg} has no prices in this window.",
                        {"leg": LegRef}),
    ExplanationTemplate("price_history_no_future_candles", "values_seen",
                        "The index future has no prices in this window."),
    ExplanationTemplate("price_history_all_gaps", "values_seen",
                        "No minute in this window has a price for every leg."),
    ExplanationTemplate("price_history_no_session", "values_seen", "Connect Zerodha to see the strategy chart."),
    ExplanationTemplate("price_history_kite_refused", "values_seen",
                        "Zerodha did not return the price history. Try again later."),
    ExplanationTemplate("price_history_future_not_in_catalogue", "values_seen",
                        "No index future is listed in the stored instrument list."),
    # GC-UI step 9 F4: a saved leg's quantity is not a whole number of lots at today's lot size (lot size changed)
    ExplanationTemplate("price_history_quantity_not_whole_lots", "values_seen",
                        "{leg}: the saved quantity is not a whole number of lots at today's lot size.",
                        {"leg": LegRef}),
    # W-102: the Execute reply's cost when no charge rate set could be read (charges null, never a default)
    ExplanationTemplate("execute_cost_charges_not_included", "values_seen",
                        "Charges and taxes are not included: the charge rates could not be read."),
    # GC-TP R-20 / R-15 (ADR-210, owner-approved 2026-10-29): why a paper or what-if figure is a dash; one per reason code
    ExplanationTemplate("paper_reason_not_priced", "values_seen",
                        "Charges not shown: an order's value could not be worked out."),
    ExplanationTemplate("paper_reason_model_refused", "values_seen",
                        "Decay not shown: the pricing model could not value a leg."),
    ExplanationTemplate("paper_reason_contract_retired", "values_seen",
                        "This contract has expired and is no longer traded."),
    ExplanationTemplate("paper_reason_contract_delisted", "values_seen", "The exchange has removed this contract."),
    ExplanationTemplate("paper_reason_token_reassigned", "values_seen",
                        "The exchange now uses this contract's code for a different contract, so its price is not "
                        "shown."),
    ExplanationTemplate("paper_reason_contract_missing", "values_seen",
                        "This contract is not in today's contract list, so its price is not shown."),
    ExplanationTemplate("paper_reason_whatif_stale", "values_seen",
                        "Stale: this target figure uses prices older than expected and may be out of date."),
    # words that were already in the product (moved from the browser, unchanged): the paused book and the extremes
    ExplanationTemplate("paper_reason_prices_not_live", "values_seen", "Paper P&L paused - prices not live"),
    ExplanationTemplate("paper_reason_multi_expiry", "values_seen",
                        "Profit left and Loss left are not worked out: the open contracts have different expiries."),
    ExplanationTemplate("paper_extremes_prices_not_live", "values_seen",
                        "Profit left and Loss left are not worked out: prices are not live."),
    # REQ-156 (ADR-214 (2a)): the approach compare's cell texts and the reason beside every "-"
    ExplanationTemplate("adjust_cmp_rupees", "values_seen", "{amount}", {"amount": Rupees}),
    ExplanationTemplate("adjust_cmp_value", "values_seen", "{value}", {"value": Recorded}),
    ExplanationTemplate("adjust_cmp_percent", "values_seen", "{value}%", {"value": Recorded}),
    ExplanationTemplate("adjust_cmp_unlimited", "values_seen", "Unlimited"),
    ExplanationTemplate("adjust_cmp_dash", "values_seen", "-"),
    ExplanationTemplate("adjust_cmp_breakevens", "values_seen", "{levels} (profit range {width} points)",
                        {"levels": Recorded, "width": Points}),
    ExplanationTemplate("adjust_cmp_no_breakeven_loss", "values_seen", "No breakeven: a loss at every level"),
    ExplanationTemplate("adjust_cmp_no_breakeven_profit", "values_seen", "No breakeven: a profit at every level"),
    ExplanationTemplate("adjust_cmp_adjustments", "values_seen", "{used} used; no plan maximum set",
                        {"used": Recorded}),
    ExplanationTemplate("adjust_cmp_fresh", "values_seen", "Max profit {profit}, max loss {loss}",
                        {"profit": Explained, "loss": Explained}),
    ExplanationTemplate("adjust_cmp_no_price", "values_seen", "Not available: {leg} has no current price.",
                        {"leg": Recorded}),
    ExplanationTemplate("adjust_cmp_no_bid_ask", "values_seen", "Not available: {leg} has no bid or no ask.",
                        {"leg": Recorded}),
    ExplanationTemplate("adjust_cmp_no_greeks", "values_seen", "Not available: no Greeks for {leg}.",
                        {"leg": Recorded}),
    ExplanationTemplate("adjust_cmp_no_new_leg", "values_seen", "Not available: this approach opens no new leg."),
    ExplanationTemplate("adjust_cmp_nothing_open", "values_seen", "Not available: no leg stays open."),
    # ADR-215: the Greeks-after rows of an approach that leaves no open leg (exit); shown, and it cannot lead them
    ExplanationTemplate("adjust_cmp_no_position_left", "values_seen", "No position left after exit"),
    ExplanationTemplate("adjust_cmp_low_oi", "values_seen",
                        "{value}% (Zerodha may refuse fresh orders in {legs}: low open interest state not known)",
                        {"value": Recorded, "legs": Recorded}),
    ExplanationTemplate("adjust_cmp_adjustments_unknown", "values_seen",
                        "Not available: the paper book does not record adjustments yet."),
    ExplanationTemplate("adjust_cmp_margin_before_unknown", "values_seen",
                        "Not available: the margin of the current legs is not available."),
    # GC-TP fix1 (ADR-211 (5)): the breakeven dash of a card on legs with different expiries; "Exited" moved unchanged
    # from the browser (EXITED_TEXT), the reason beside every figure of a fully exited strategy
    ExplanationTemplate("paper_breakeven_multi_expiry", "values_seen",
                        "Breakeven is exact only for a single-expiry strategy"),
    ExplanationTemplate("paper_reason_exited", "values_seen", "Exited"),
    ExplanationTemplate("paper_extremes_unknown", "values_seen", "Profit left and Loss left are not worked out."),
    # GC-ADJ2 step 1A (REQ-158 AC-4): deleting the active playbook says the system one is active again
    ExplanationTemplate("playbook_system_active_again", "values_seen", "{type}: the system playbook is active again",
                        {"type": PlaybookTypeName}),
    # GC-ADJ2 step 3 (REQ-160 AC-3, AC-4): the playbook Test step's two fixed sentences
    ExplanationTemplate("playbook_test_no_strategy", "values_seen", "No current {type} strategy to test against",
                        {"type": PlaybookTypeName}),
    ExplanationTemplate("playbook_test_past_out_of_v1", "values_seen",
                        "Testing against past expiries is not in this version: it needs licensed historical option "
                        "data."),
    ExplanationTemplate("catalogue_template_name", "values_seen", "{text}", {"text": TemplateText}),
    ExplanationTemplate("catalogue_template_description", "values_seen", "{text}", {"text": TemplateText}),
    *(ExplanationTemplate(f"plan_sheet_{key}", "values_seen", text)  # REQ-161: the plan sheet's fixed words
      for key, text in PLAN_SHEET_LABEL_TEXT.items()),
    *(ExplanationTemplate(f"table_reason_{key}", "values_seen", text) for key, text in TABLE_REASON_TEXT.items()),
    *(ExplanationTemplate(approach_name_id(key), "values_seen", text)  # REQ-155: each approach's shown name
      for key, text in ADJUSTMENT_APPROACH_LABEL_TEXT.items()),
    *(ExplanationTemplate(approach_about_id(key), "values_seen", text)  # REQ-046 AC-3: each approach's one-line text
      for key, text in ADJUSTMENT_APPROACH_ABOUT_TEXT.items()),
    *(ExplanationTemplate(f"playbook_approach_{key.lower().replace('-', '_')}", "values_seen", text)
      for key, text in PLAYBOOK_APPROACH_LABEL_TEXT.items()),  # GC-ADJ2 step 3: the editor's labels
    *(ExplanationTemplate(f"playbook_day_kind_{key}", "values_seen", text) for key, text in PLAYBOOK_DAY_RULE_KIND_TEXT.items()),
    *(ExplanationTemplate(f"playbook_day_action_{key}", "values_seen", text)
      for key, text in PLAYBOOK_DAY_RULE_ACTION_TEXT.items()),
    *(ExplanationTemplate(f"playbook_summary_{key}", "values_seen", text) for key, text in PLAYBOOK_SUMMARY_TEXT.items()),
    *(ExplanationTemplate(f"adjust_cmp_row_{key}", "values_seen", text)  # REQ-156: each criterion row's name
      for key, text in ADJUSTMENT_CRITERION_LABEL_TEXT.items()),
    *(ExplanationTemplate(f"adjust_cmp_lead_{key}", "values_seen", text)  # REQ-156 AC-3: each row's leader words
      for key, text in ADJUSTMENT_LEADER_LABEL_TEXT.items()),
)

EXPLANATIONS: Mapping[str, ExplanationTemplate] = MappingProxyType({t.id: t for t in _EXPLANATIONS})

#: Every fixed label an explanation can print (checked by tests/errors/test_template_pins.py and pinned there).
LABEL_TABLES: Mapping[str, Mapping[str, str]] = MappingProxyType({
    "input": INPUT_LABEL_TEXT, "op": OP_TEXT, "action": ACTION_TEXT, "follow_up": FOLLOW_UP_TEXT,
    "direction": DIRECTION_TEXT, "measure": MEASURE_TEXT, "choice": CHOICE_LABEL_TEXT, "step": STEP_LABEL_TEXT,
    "builder": BUILDER_LABEL_TEXT, "scenario_view": SCENARIO_VIEW_LABEL_TEXT, "health": HEALTH_LABEL_TEXT,
    "column": COLUMN_LABEL_TEXT, "table_reason": TABLE_REASON_TEXT, "level_region": LEVEL_REGION_TEXT,
    "adjustment_approach": ADJUSTMENT_APPROACH_LABEL_TEXT, "adjustment_approach_about": ADJUSTMENT_APPROACH_ABOUT_TEXT,
    "adjustment_criterion": ADJUSTMENT_CRITERION_LABEL_TEXT, "adjustment_leader": ADJUSTMENT_LEADER_LABEL_TEXT,
    "playbook_type": PLAYBOOK_TYPE_LABEL_TEXT, "playbook_approach": PLAYBOOK_APPROACH_LABEL_TEXT,
    "playbook_day_kind": PLAYBOOK_DAY_RULE_KIND_TEXT, "playbook_day_action": PLAYBOOK_DAY_RULE_ACTION_TEXT,
    "playbook_summary": PLAYBOOK_SUMMARY_TEXT, "plan_sheet": PLAN_SHEET_LABEL_TEXT,
})


def _make_render_explanation() -> Callable[..., ExplanationText]:
    snapshot = {t.id: (t.text, tuple(t.slots.items())) for t in _EXPLANATIONS}
    check = check_explanation_wording
    mint = _EXPLANATION_MINT

    def render_explanation(template_id: str, **slots: object) -> ExplanationText:
        """The only way to build an explanation line: fill `template_id`'s typed slots. Fails closed on an unknown
        id, a missing/extra slot or a wrong slot type; re-checks the fixed words on every call."""
        if template_id not in snapshot:
            raise ValueError(f"unknown explanation template id {template_id!r}")
        text, slot_types = snapshot[template_id]
        expected = {name for name, _ in slot_types}
        if set(slots) != expected:
            raise ValueError(f"explanation {template_id!r} needs slots {sorted(expected)}, got {sorted(slots)}")
        check(text.format(**{name: "" for name in expected}), f"explanation {template_id}")
        formatted = {}
        for name, slot_type in slot_types:
            slot_type.validate(slots[name])
            formatted[name] = slot_type.format(slots[name])
        return ExplanationText(text.format(**formatted), mint)

    return render_explanation


render_explanation = _make_render_explanation()
del _make_render_explanation


def restore_explanation(template_id: str, stored: str) -> ExplanationText:
    """A line a `render_explanation()` call made earlier and a store kept (GC-TP 7a: a paper alert's title and body) read
    back as an explanation. Only a string that fits the template's fixed words, in order, is restored; anything else
    (a hand-written or edited row) is refused, so a store cannot smuggle its own sentence through a response."""
    found = next((t for t in _EXPLANATIONS if t.id == template_id), None)
    if found is None:
        raise ValueError(f"unknown explanation template id {template_id!r}")
    pieces = re.split(r"\{[a-z_]+\}", found.text)
    shape = ".+?".join(re.escape(piece) for piece in pieces)
    if type(stored) is not str or re.fullmatch(shape, stored, re.DOTALL) is None:
        raise ValueError(f"stored text does not fit explanation template {template_id!r}")
    return ExplanationText(stored, _EXPLANATION_MINT)


def join_explanations(parts: tuple[ExplanationText, ...] | list[ExplanationText], sep: str = ", ") -> ExplanationText:
    """Explanation lines joined into one: every part must be a `render_explanation()` result, the separator one of
    `JOIN_SEPARATORS`. So a joined line is still an `ExplanationText` and still holds only catalogue words."""
    if sep not in JOIN_SEPARATORS:
        raise ValueError(f"separator must be one of {sorted(JOIN_SEPARATORS)}, got {sep!r}")
    parts = tuple(parts)
    for part in parts:
        if type(part) is not ExplanationText:
            raise TypeError(f"join_explanations takes render_explanation() results, got {type(part).__name__}")
    return ExplanationText(sep.join(parts), _EXPLANATION_MINT)


def strike_text(strike: Decimal | None) -> ExplanationText:
    """The optional strike part of a contract or leg description: " 23600", or nothing for a future."""
    if strike is None:
        return render_explanation("strike_none")
    return render_explanation("strike_part", strike=format(strike.normalize(), "f"))
