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
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from ofo import wording as _wording

from ofo.errors.slots import SlotType, _require_exact

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


_USER_WORDS_MINT = object()

#: The request-parsing layer (W-024 round 10 item 3): the modules where a value the user typed first enters the
#: domain. Only code IN these modules can mint `UserWords`; each entry names the request field it parses.
REQUEST_LAYER: Mapping[str, str] = MappingProxyType({
    "ofo.admin.client_id": "the Client ID an admin types (normalise_client_id)",
    "ofo.rules.model": "a rule's name and description the user typed (Rule.shown_name)",
    "ofo.strategy.definition": "the strategy settings the user changed (rules_ref, risk_limits, preferences)",
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
                                                   "estimate_assume_valued", "scenario_estimated_unavailable"})
JOIN_SEPARATORS: frozenset[str] = frozenset({", ", "; ", " | "})


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
                        "Estimated Now is unavailable: no implied volatility for {legs}", {"legs": LegacyRecorded}),
    # The caption is the PAIR "<underlying> at expiry | You make/lose" (Q227): two reviewed halves, joined by " | ".
    ExplanationTemplate("scenario_caption_left", "values_seen", "{underlying} at expiry", {"underlying": Recorded}),
    ExplanationTemplate("scenario_caption_right", "values_seen", "You make/lose"),
    ExplanationTemplate("strike_part", "values_seen", " {strike}", {"strike": Recorded}),
    ExplanationTemplate("strike_none", "values_seen", ""),
    ExplanationTemplate("contract_description", "values_seen", "{underlying}{strike} {instrument} {expiry}",
                        {"underlying": Recorded, "strike": Explained, "instrument": Recorded, "expiry": Recorded}),
    ExplanationTemplate("leg_description", "values_seen", "{action}{strike} {instrument} {expiry} x{quantity}",
                        {"action": Recorded, "strike": Explained, "instrument": Recorded, "expiry": Recorded,
                         "quantity": Recorded}),
    ExplanationTemplate("change_underlying", "values_seen", "underlying {old} -> {new}",
                        {"old": Recorded, "new": Recorded}),
    ExplanationTemplate("change_leg_removed", "values_seen", "removed leg {leg}", {"leg": Recorded}),
    ExplanationTemplate("change_leg_added", "values_seen", "added leg {leg}", {"leg": Recorded}),
    ExplanationTemplate("change_quantity", "values_seen", "quantity of {leg} was {before}",
                        {"leg": Recorded, "before": Recorded}),
    ExplanationTemplate("change_field", "values_seen", "{label} {old} -> {new}",
                        {"label": Recorded, "old": UserText, "new": UserText}),
    ExplanationTemplate("change_legs_reordered", "values_seen", "legs reordered"),
    ExplanationTemplate("change_replaced_unreadable", "values_seen", "definition replaced, the previous one could not be compared"),
    ExplanationTemplate("change_summary_unreadable", "values_seen", "this change could not be shown"),
    ExplanationTemplate("change_restored", "values_seen", "restored entry {seq}", {"seq": Recorded}),
    ExplanationTemplate("rule_label_days_to_expiry_from", "rule", "{days} days to expiry or fewer, from {time} IST",
                        {"days": Days, "time": ClockHm}),
)

EXPLANATIONS: Mapping[str, ExplanationTemplate] = MappingProxyType({t.id: t for t in _EXPLANATIONS})

#: Every fixed label an explanation can print (checked by tests/errors/test_template_pins.py and pinned there).
LABEL_TABLES: Mapping[str, Mapping[str, str]] = MappingProxyType({
    "input": INPUT_LABEL_TEXT, "op": OP_TEXT, "action": ACTION_TEXT, "follow_up": FOLLOW_UP_TEXT,
    "direction": DIRECTION_TEXT, "measure": MEASURE_TEXT, "choice": CHOICE_LABEL_TEXT, "step": STEP_LABEL_TEXT,
    "builder": BUILDER_LABEL_TEXT, "scenario_view": SCENARIO_VIEW_LABEL_TEXT, "health": HEALTH_LABEL_TEXT,
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
