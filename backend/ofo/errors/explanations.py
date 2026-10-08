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

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType

from ofo import wording as _wording

from .slots import SlotType, _require_exact

EXPLANATION_FIELDS: tuple[str, ...] = ("what_triggered", "values_seen", "rule")


def check_explanation_wording(text: str, where: str) -> None:
    """The platform's own words of an explanation: the old timeline phrase list AND the shared Q226/Q230 checker."""
    from ofo.strategy.wording import find_banned_phrases

    found = find_banned_phrases(text)
    found += [hit for hit in _wording.find_advice_wording(text) if hit not in found]
    if found:
        raise ValueError(f"the platform's own answer wording contains advice phrases {found}: {text!r}")
    _wording.check_platform_text(text, where)


# --- typed slots --------------------------------------------------------------------------------------------------

class Recorded(SlotType):
    """A recorded value printed exactly as stored: exactly `str`, `int` or `Decimal` (str of it)."""

    @staticmethod
    def validate(value: object) -> None:
        if type(value) not in (str, int, Decimal):
            raise TypeError(f"Recorded slot requires str, int or Decimal, got {type(value).__name__}")

    @staticmethod
    def format(value: object) -> str:
        return str(value)


class Quoted(SlotType):
    """Recorded text (the user's rule text, a source name, a broker answer), printed quoted: never our wording."""

    @staticmethod
    def validate(value: object) -> None:
        _require_exact(value, str, "Quoted")

    @staticmethod
    def format(value: str) -> str:
        return f'"{str.__str__(value)}"'


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


InputLabel = _enum_slot("InputLabel", _input_name, INPUT_LABEL_TEXT)
OpWords = _enum_slot("OpWords", _op, OP_TEXT)
ActionWords = _enum_slot("ActionWords", _action, ACTION_TEXT)
FollowUpLabel = _enum_slot("FollowUpLabel", _follow_up, FOLLOW_UP_TEXT)


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
)

EXPLANATIONS: Mapping[str, ExplanationTemplate] = MappingProxyType({t.id: t for t in _EXPLANATIONS})

#: Every fixed label an explanation can print (checked by tests/errors/test_template_pins.py and pinned there).
LABEL_TABLES: Mapping[str, Mapping[str, str]] = MappingProxyType({
    "input": INPUT_LABEL_TEXT, "op": OP_TEXT, "action": ACTION_TEXT, "follow_up": FOLLOW_UP_TEXT,
})


def _make_render_explanation() -> Callable[..., str]:
    snapshot = {t.id: (t.text, tuple(t.slots.items())) for t in _EXPLANATIONS}
    check = check_explanation_wording

    def render_explanation(template_id: str, **slots: object) -> str:
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
        return text.format(**formatted)

    return render_explanation


render_explanation = _make_render_explanation()
del _make_render_explanation
