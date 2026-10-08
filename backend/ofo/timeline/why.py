"""'Why did this trigger?' (REQ-040 AC-5; ADR-019 Q203; ADR-003 wording).

The answer is built ONLY from a ``RuleTriggerRecord`` and its recorded ``FollowUp``s: every value, threshold, time,
source, health and version in the text is a field of those records, printed exactly as stored (Decimals via
``str``, the timestamp via ``isoformat``). Nothing is recomputed, estimated or looked up elsewhere. A follow-up that
was not recorded is said to be "not recorded", never assumed.

Every line comes from the explanation catalogue (`ofo.errors.explanations`, W-024 round 9: not an error, so
REQ-065 AC-2's four parts do not apply). Wording is decision-support (ADR-003): it opens with "Your rule was triggered" and never advises what to do.
"""
from __future__ import annotations

from typing import Iterable

from ofo.rules.conditions import Op
from ofo.rules.inputs import InputName
from ofo.rules.model import RuleAction
from ofo.strategy.wording import find_banned_phrases
from ofo.timeline.catalogue import FollowUpKind
from ofo.timeline.records import FollowUp, RuleTriggerRecord
from ofo import wording as shared_wording
from ofo.errors.explanations import (
    ACTION_TEXT, FOLLOW_UP_TEXT, INPUT_LABEL_TEXT, OP_TEXT, render_explanation,
)

#: Plain-language names (re-exported from the explanation catalogue, keyed by enum member).
INPUT_LABELS: dict[InputName, str] = {name: INPUT_LABEL_TEXT[name.name] for name in InputName}
OP_WORDS: dict[Op, str] = {op: OP_TEXT[op.name] for op in Op}
ACTION_WORDS: dict[RuleAction, str] = {action: ACTION_TEXT[action.name] for action in RuleAction}
FOLLOW_UP_LABELS: dict[FollowUpKind, str] = {kind: FOLLOW_UP_TEXT[kind.name] for kind in FollowUpKind}


def advice_words_in(text: str) -> list[str]:
    """ADR-003 advice phrases found in ``text``: the phrase list this module used before (``find_banned_phrases``,
    kept so coverage is never narrower) plus the shared Q226/Q230 checker (``ofo.wording.find_advice_wording``: every
    word form of the five words, ADR-003 phrase families)."""
    found = find_banned_phrases(text)
    return found + [hit for hit in shared_wording.find_advice_wording(text) if hit not in found]


def why_did_this_trigger(record: RuleTriggerRecord, follow_ups: Iterable[FollowUp] = ()) -> str:
    """Plain-language answer from ``record`` and the follow-ups recorded for it; one line per fact."""
    if not isinstance(record, RuleTriggerRecord):
        raise ValueError(f"expected a RuleTriggerRecord, got {record!r}")
    recorded: dict[FollowUpKind, FollowUp] = {}
    for follow_up in follow_ups:
        if not isinstance(follow_up, FollowUp):
            raise ValueError(f"expected FollowUp items, got {follow_up!r}")
        if follow_up.kind in recorded:
            raise ValueError(f"{follow_up.kind.value} is given twice")
        recorded[follow_up.kind] = follow_up

    line = render_explanation
    lines = [line("why_triggered", rule_text=record.rule_text, kind=record.rule_kind.value, rule_id=record.rule_id)]
    if record.observations:
        for o in record.observations:
            lines.append(line("why_condition_met", input=o.input, value=o.value, op=o.op, threshold=o.threshold))
    else:
        lines.append(line("why_no_condition"))
    if record.missing:
        lines.append(line("why_not_available", inputs=tuple(record.missing)))
    lines.append(line("why_checked_at", time=record.timestamp.isoformat()))
    lines.append(line("why_market_data", source=record.source, health=record.data_health.value))
    if record.active_version is not None:
        lines.append(line("why_active_version", version=record.active_version))
    else:
        lines.append(line("why_planned_version", version=record.planned_version))
    lines.append(line("why_action", action=record.action))
    for kind in FollowUpKind:
        follow_up = recorded.get(kind)
        if follow_up is None:
            lines.append(line("why_follow_up_missing", follow_up=kind))
        elif kind.is_yes_no:
            lines.append(line("why_follow_up_yes_no", follow_up=kind, answer=bool(follow_up.answer)))
        else:
            lines.append(line("why_follow_up_answer", follow_up=kind, answer=str(follow_up.answer)))
    return "\n".join(lines)
