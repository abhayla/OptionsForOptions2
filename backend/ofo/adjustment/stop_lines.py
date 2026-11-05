"""The stop lines in force for one strategy, as the live check reads them (contract "Your adjustment settings" step 3).

Spec basis: ADR-245 (every alert line names the value it used), ADR-247 (default: 50 % of max loss or 2x the credit
received, whichever comes first; % of margin off), ADR-250 (a plan saved before ADR-247 keeps its own stops and gains
no 2x line), ADR-251 (the credit is the net credit collected so far), ADR-008 (exact decimal money).

The ONE producer of these lines is ``ofo_app.settings_in_force.stops_of``; the evaluator (``playbook_eval``) owns no
stop value: it compares the loss to each ACTIVE line's ``amount`` (structural guarantee, run-discipline B8). The
trigger ids a stop used to live under (``STOP_TRIGGERS``) are named here once, so the evaluator can skip their body
rules without spelling the ids itself.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Final

STOP_MAX_LOSS: Final = "max_loss_pct"
STOP_CREDIT: Final = "credit_multiple"
STOP_MARGIN: Final = "margin_pct"
KINDS: Final = (STOP_MAX_LOSS, STOP_CREDIT, STOP_MARGIN)

#: the body triggers that held a stop before step 3 (loss as % of max loss; loss as % of margin). Their body rules are
#: NOT evaluated: each stop is a ``stop.<kind>`` rule built from the line in force.
TRIGGER_MAX_LOSS: Final = "T-06"
TRIGGER_MARGIN: Final = "T-16"
STOP_TRIGGERS: Final = frozenset({TRIGGER_MAX_LOSS, TRIGGER_MARGIN})

#: the rule id prefix of a stop result (``stop.max_loss_pct``)
RULE_PREFIX: Final = "stop."

# ---- why a line has no amount (the settings screen's codes; ``settings_in_force`` re-exports them) ----------------
GUARDS_UNREADABLE: Final = "stop_guards_unreadable"
STOP_VALUE_UNREADABLE: Final = "stop_value_unreadable"
MAX_LOSS_UNKNOWN: Final = "stop_max_loss_unknown"
MAX_LOSS_UNLIMITED: Final = "stop_max_loss_unlimited"
NO_CREDIT: Final = "stop_no_credit_received"
CREDIT_UNKNOWN: Final = "stop_credit_unknown"
MARGIN_NOT_READ: Final = "stop_margin_not_read"
#: ADR-250: a plan saved before ADR-247 holds a per-stage % (its T-06 / T-16 values); the stage is not known
STAGE_UNKNOWN: Final = "stop_stage_unknown"

#: the live check's "not checked" code (error catalogue, ``adjust_trigger_*``) for each reason a line has no amount;
#: a reason outside this map -> ``NOT_CHECKED_OTHER`` (fail closed: never a passed stop)
_T: Final = "adjust_trigger_"
STOPS_NOT_SUPPLIED: Final = f"{_T}stop_not_supplied"
NOT_CHECKED_OTHER: Final = f"{_T}stop_value_unreadable"
NOT_CHECKED: Final = {
    GUARDS_UNREADABLE: NOT_CHECKED_OTHER,
    STOP_VALUE_UNREADABLE: NOT_CHECKED_OTHER,
    MAX_LOSS_UNKNOWN: f"{_T}missing_max_loss",
    MAX_LOSS_UNLIMITED: f"{_T}max_loss_not_finite",
    NO_CREDIT: f"{_T}stop_no_credit",
    CREDIT_UNKNOWN: f"{_T}stop_credit_unknown",
    MARGIN_NOT_READ: f"{_T}missing_margin",
    STAGE_UNKNOWN: f"{_T}missing_days_left",
}


def not_checked_code(reason: str | None) -> str:
    return NOT_CHECKED.get(reason or "", NOT_CHECKED_OTHER)


@dataclasses.dataclass(frozen=True)
class StopInForce:
    kind: str  # STOP_MAX_LOSS / STOP_CREDIT / STOP_MARGIN
    active: bool
    figure: Decimal | None  # the % or the multiple in force
    amount: Decimal | None  # the loss in rupees at which it fires (engine)
    source: str | None
    reason: str | None


@dataclasses.dataclass(frozen=True)
class StopsInForce:
    lines: tuple[StopInForce, ...]
    first: str | None
    reason: str | None


def rule_id(kind: str) -> str:
    return f"{RULE_PREFIX}{kind}"


def is_stop_rule(rule_id_: object) -> bool:
    return isinstance(rule_id_, str) and rule_id_.startswith(RULE_PREFIX)


__all__ = ["CREDIT_UNKNOWN", "GUARDS_UNREADABLE", "KINDS", "MARGIN_NOT_READ", "MAX_LOSS_UNKNOWN", "MAX_LOSS_UNLIMITED",
           "NOT_CHECKED", "NOT_CHECKED_OTHER", "NO_CREDIT", "STAGE_UNKNOWN", "STOP_VALUE_UNREADABLE",
           "not_checked_code", "RULE_PREFIX", "STOPS_NOT_SUPPLIED", "STOP_CREDIT", "STOP_MARGIN", "STOP_MAX_LOSS",
           "STOP_TRIGGERS", "TRIGGER_MARGIN", "TRIGGER_MAX_LOSS", "StopInForce", "StopsInForce", "is_stop_rule",
           "rule_id"]
