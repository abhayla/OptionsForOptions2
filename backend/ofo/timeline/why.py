"""'Why did this trigger?' (REQ-040 AC-5; ADR-019 Q203; ADR-003 wording).

The answer is built ONLY from a ``RuleTriggerRecord`` and its recorded ``FollowUp``s: every value, threshold, time,
source, health and version in the text is a field of those records, printed exactly as stored (Decimals via
``str``, the timestamp via ``isoformat``). Nothing is recomputed, estimated or looked up elsewhere. A follow-up that
was not recorded is said to be "not recorded", never assumed.

Wording is decision-support (ADR-003): it opens with "Your rule was triggered" and never advises what to do.
"""
from __future__ import annotations

from typing import Iterable

from ofo.rules.conditions import Op
from ofo.rules.inputs import InputName
from ofo.rules.model import RuleAction
from ofo.timeline.catalogue import FollowUpKind
from ofo.timeline.records import FollowUp, RuleTriggerRecord

#: Plain-language names of every rule input (units as REQ-041 AC-4 / ofo.rules.inputs define them).
INPUT_LABELS: dict[InputName, str] = {
    InputName.UNDERLYING_LEVEL: "underlying level",
    InputName.UNDERLYING_MOVE_POINTS: "underlying move (points)",
    InputName.UNDERLYING_MOVE_PCT: "underlying move (%)",
    InputName.DISTANCE_TO_SHORT_STRIKE: "distance to the nearest short strike (points)",
    InputName.DISTANCE_TO_BREAKEVEN: "distance to the nearest breakeven (points)",
    InputName.NET_PREMIUM: "net premium (Rs)",
    InputName.LIVE_PNL: "live P&L (Rs)",
    InputName.PNL_PCT_OF_MAX_PROFIT: "P&L as % of max profit",
    InputName.PNL_PCT_OF_MAX_LOSS: "loss as % of max loss",
    InputName.DTE: "days to expiry",
    InputName.TIME_OF_DAY: "time of day (minutes after midnight IST)",
    InputName.IV: "implied volatility",
    InputName.IV_PERCENTILE: "IV percentile",
    InputName.DELTA: "delta",
    InputName.GAMMA: "gamma",
    InputName.THETA: "theta",
    InputName.VEGA: "vega",
}

OP_WORDS: dict[Op, str] = {
    Op.GTE: "at or above",
    Op.GT: "above",
    Op.LTE: "at or below",
    Op.LT: "below",
}

ACTION_WORDS: dict[RuleAction, str] = {
    RuleAction.ALERT_ONLY: "alert only",
    RuleAction.ALERT_AND_PREPARE_ORDERS: "alert and prepare orders for your review",
}

FOLLOW_UP_LABELS: dict[FollowUpKind, str] = {
    FollowUpKind.ALERT_GENERATED: "Alert generated",
    FollowUpKind.ORDER_PREPARED: "Order prepared",
    FollowUpKind.CONFIRMATION_REQUIRED: "Confirmation required",
    FollowUpKind.EXECUTED: "Executed",
    FollowUpKind.BROKER_REPORTED: "Broker reported",
    FollowUpKind.RECONCILIATION_SUCCEEDED: "Reconciliation succeeded",
}


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

    lines = [f'Your rule was triggered: "{record.rule_text}" ({record.rule_kind.value} rule {record.rule_id}).']
    if record.observations:
        for o in record.observations:
            lines.append(f"Condition met: {INPUT_LABELS[o.input]} was {o.value}, "
                         f"{OP_WORDS[o.op]} the threshold {o.threshold}.")
    else:
        lines.append("Condition met: this rule has no market condition; it applies as soon as it is checked.")
    if record.missing:
        lines.append("Not available when checked: " + ", ".join(INPUT_LABELS[n] for n in record.missing) + ".")
    lines.append(f"Checked at: {record.timestamp.isoformat()}.")
    lines.append(f"Market data: source {record.source}, health {record.data_health.value}.")
    if record.active_version is None:
        lines.append("Active strategy version: none (nothing had executed yet).")
    else:
        lines.append(f"Active strategy version: {record.active_version}.")
    lines.append(f"The rule's chosen action: {ACTION_WORDS[record.action]}.")
    for kind in FollowUpKind:
        follow_up = recorded.get(kind)
        if follow_up is None:
            text = "not recorded"
        elif kind.is_yes_no:
            text = "yes" if follow_up.answer else "no"
        else:
            text = f'"{follow_up.answer}"'
        lines.append(f"{FOLLOW_UP_LABELS[kind]}: {text}.")
    return "\n".join(lines)
