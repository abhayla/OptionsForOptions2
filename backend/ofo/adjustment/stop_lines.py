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
from collections.abc import Mapping
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
#: The profit targets and the time exit are not loss stops but are plan exits too (``PLAN_EXIT_RULES``, ADR-330 (47)).
LOSS_STOP_RULES: Final = frozenset({*RULE_OF_LINE.values(), RUPEE_LOSS_RULE})


def is_stop_rule(rule_id_: object) -> bool:
    """A loss stop rule (``LOSS_STOP_RULES``): judged on the first check past its line, never at the candle close."""
    return isinstance(rule_id_, str) and rule_id_ in LOSS_STOP_RULES


#: ADR-330 (47): the % profit target. With the loss stops, the rupee profit target and the time exit it makes the ONE
#: set of the plan's own exits: each alerts on the first check past its level or time (no candle close, no quiet time,
#: no daily cap); only adjustment suggestions keep those. Case: A-G #207 (27 Nov 2026), A-E #202.
TRIGGER_PROFIT_PCT: Final = "T-07"
PLAN_EXIT_TRIGGERS: Final = frozenset({*STOP_TRIGGERS, TRIGGER_PROFIT_PCT, TRIGGER_TIME_EXIT})
PLAN_EXIT_RULES: Final = frozenset({*LOSS_STOP_RULES, TRIGGER_PROFIT_PCT, RUPEE_PROFIT_RULE, TRIGGER_TIME_EXIT})


def is_plan_exit_rule(rule_id_: object) -> bool:
    """A plan exit by its fixed rule id (``PLAN_EXIT_RULES``). Pure."""
    return isinstance(rule_id_, str) and rule_id_ in PLAN_EXIT_RULES


def _ids_naming(body: object, triggers: frozenset[str], fixed: frozenset[str]) -> frozenset[str]:
    """``fixed`` plus each body rule whose members name one of ``triggers``, whatever its own id
    (``playbook_store._check_rules`` allows any id). An unreadable body -> ``fixed`` (never fewer). Pure."""
    rules = body.get("rules") if isinstance(body, Mapping) else None
    out = set(fixed)
    for rule in rules if isinstance(rules, list) else ():
        members = (rule.get("any_of") or rule.get("all_of")) if isinstance(rule, Mapping) else None
        named = {m for m in members if isinstance(m, str)} if isinstance(members, list) else set()
        if isinstance(rule, Mapping) and isinstance(rule.get("id"), str) and triggers & named:
            out.add(rule["id"])
    return frozenset(out)


def loss_stop_rule_ids(body: object) -> frozenset[str]:
    """Every rule id that carries a LOSS stop in this plan, by trigger, not by id: ``LOSS_STOP_RULES`` plus each body
    rule whose members name T-06 / T-16 (a mixed any/all rule, or ``{"id": "MYSTOP", "any_of": ["T-16"]}``). Pure."""
    return _ids_naming(body, STOP_TRIGGERS, LOSS_STOP_RULES)


def plan_exit_rule_ids(body: object) -> frozenset[str]:
    """ADR-330 (47): EVERY rule id that is one of the plan's own exits in this plan: ``PLAN_EXIT_RULES`` plus each body
    rule whose members name a loss stop, the % profit target or the time exit. The ONE set the alert gate (via
    ``gate_readings``: fast path, quiet-time, paused-candle), the daily cap (``cap_scope.cap_exempt``), the
    store's restart count (``cap_scope.count_capped``) and the F-71 entry hold (``playbook_eval.never_held``) read.
    An unreadable body -> the fixed set (never fewer). Pure."""
    return _ids_naming(body, PLAN_EXIT_TRIGGERS, PLAN_EXIT_RULES)


def is_plan_exit(rule_id_: object, exits: frozenset[str] = frozenset()) -> bool:
    """A plan exit: in the fixed set, or in ``exits`` (``plan_exit_rule_ids`` of the plan). Pure."""
    return is_plan_exit_rule(rule_id_) or (isinstance(rule_id_, str) and rule_id_ in exits)


def is_loss_stop(rule_id_: object, stops: frozenset[str] = frozenset()) -> bool:
    """A loss stop: in the fixed set, or in ``stops`` (``loss_stop_rule_ids`` of the plan). Pure."""
    return is_stop_rule(rule_id_) or (isinstance(rule_id_, str) and rule_id_ in stops)


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
    "PLAN_EXIT_RULES",
    "PLAN_EXIT_TRIGGERS",
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
    "TRIGGER_PROFIT_PCT",
    "TRIGGER_TIME_EXIT",
    "StopInForce",
    "StopsInForce",
    "is_loss_stop",
    "is_plan_exit",
    "is_plan_exit_rule",
    "is_stop_rule",
    "loss_stop_rule_ids",
    "not_checked_code",
    "plan_exit_rule_ids",
    "rule_id",
    "rupee_loss_is_the_stop",
]
