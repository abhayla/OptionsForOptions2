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

from ofo.checks import pnl_amount as rupee

STOP_MAX_LOSS: Final = "max_loss_pct"
STOP_CREDIT: Final = "credit_multiple"
STOP_MARGIN: Final = "margin_pct"
KINDS: Final = (STOP_MAX_LOSS, STOP_CREDIT, STOP_MARGIN)

#: the body triggers that held a stop before step 3 (loss as % of max loss; loss as % of margin). Their body rules are
#: NOT evaluated: each stop is a ``stop.<kind>`` rule built from the line in force.
TRIGGER_MAX_LOSS: Final = "T-06"
TRIGGER_MARGIN: Final = "T-16"
STOP_TRIGGERS: Final = frozenset({TRIGGER_MAX_LOSS, TRIGGER_MARGIN})
#: the plan's time exit ("Clock time reached", ADR-330 (7)): its alert kind is plan_time_exit, not a stop line
TRIGGER_TIME_EXIT: Final = "T-10b"

#: ADR-330 (5): the plan's rupee levels (whole trade, before charges). Rule ids like the 2x-credit line; the guards
#: hold the typed level as decimal text. A hit raises an alert and nothing more.
RUPEE_LOSS_RULE: Final = "plan.rupee_loss"
RUPEE_PROFIT_RULE: Final = "plan.rupee_profit"
RUPEE_LOSS_KEY: Final = "loss_stop_rupees"
RUPEE_RULES: Final = frozenset({RUPEE_LOSS_RULE, RUPEE_PROFIT_RULE})  # one amount each, no per-stage value
RUPEE_PROFIT_KEY: Final = "profit_target_rupees"

#: rule ids: the max-loss and margin lines answer under their old trigger ids (same wording, same rule memory, so
#: "already true" and the alert gate carry over); only the 2x-credit line (ADR-247) has a new id
CREDIT_RULE: Final = "stop.credit_x"
LINE_OF_TRIGGER: Final = {TRIGGER_MAX_LOSS: STOP_MAX_LOSS, TRIGGER_MARGIN: STOP_MARGIN}
RULE_OF_LINE: Final = {STOP_MAX_LOSS: TRIGGER_MAX_LOSS, STOP_MARGIN: TRIGGER_MARGIN, STOP_CREDIT: CREDIT_RULE}

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


def rupee_loss_is_the_stop(body: object) -> bool:
    """ADR-330 (5)(a): a plan has ONE loss stop. When it is typed in rupees (a readable level in the guards), that level
    IS the stop and the T-06 percent line is not a second one. A level that cannot be read does not replace it (fail
    closed: the percent line keeps checking). Pure."""
    guards = body.get("guards") if isinstance(body, dict) else None
    raw = guards.get(RUPEE_LOSS_KEY) if isinstance(guards, dict) else None
    try:
        return isinstance(raw, str) and rupee.level_of(raw) is not None
    except ValueError:
        return False


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
    #: the figures at the stages after this one (a pre-ADR-247 plan's per-stage %; () for a flat line)
    later: tuple[Decimal, ...] = ()


@dataclasses.dataclass(frozen=True)
class StopsInForce:
    lines: tuple[StopInForce, ...]
    first: str | None
    reason: str | None


def rule_id(kind: str) -> str:
    return RULE_OF_LINE[kind]


#: REQ-170 AC-5 ("a stop-loss ... acts on the live price at once"): EVERY loss stop a plan can hold, the ONE set the
#: alert gate's fast path reads: the % of max loss (T-06), % of margin (T-16) and 2x-credit lines, and the typed rupee
#: level (``plan.rupee_loss``, ADR-330 (5)(a): when typed it IS the plan's one loss stop). Case: paper trade A-E #202
#: (2026-11-27, Stop Rs 50, loss Rs 85.75 at 12:13:44) opened no alert while the rupee stop waited for candle closes.
#: The profit targets (T-07, ``plan.rupee_profit``) and the time exit (T-10b) are not loss stops: they keep the
#: candle-close confirmation.
LOSS_STOP_RULES: Final = frozenset({*RULE_OF_LINE.values(), RUPEE_LOSS_RULE})


def is_stop_rule(rule_id_: object) -> bool:
    """A loss stop rule (``LOSS_STOP_RULES``): judged on the first check past its line, never at the candle close."""
    return isinstance(rule_id_, str) and rule_id_ in LOSS_STOP_RULES


__all__ = [
    "CREDIT_RULE",
    "CREDIT_UNKNOWN",
    "GUARDS_UNREADABLE",
    "KINDS",
    "LINE_OF_TRIGGER",
    "LOSS_STOP_RULES",
    "MARGIN_NOT_READ",
    "MAX_LOSS_UNKNOWN",
    "MAX_LOSS_UNLIMITED",
    "NOT_CHECKED",
    "NOT_CHECKED_OTHER",
    "NO_CREDIT",
    "RULE_OF_LINE",
    "RUPEE_LOSS_KEY",
    "RUPEE_LOSS_RULE",
    "RUPEE_PROFIT_KEY",
    "RUPEE_PROFIT_RULE",
    "RUPEE_RULES",
    "STAGE_UNKNOWN",
    "STOPS_NOT_SUPPLIED",
    "STOP_CREDIT",
    "STOP_MARGIN",
    "STOP_MAX_LOSS",
    "STOP_TRIGGERS",
    "STOP_VALUE_UNREADABLE",
    "TRIGGER_MARGIN",
    "TRIGGER_MAX_LOSS",
    "TRIGGER_TIME_EXIT",
    "StopInForce",
    "StopsInForce",
    "is_stop_rule",
    "not_checked_code",
    "rule_id",
    "rupee_loss_is_the_stop",
]
