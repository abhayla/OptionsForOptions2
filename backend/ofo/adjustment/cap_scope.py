"""Which alert records the strategy's daily alert cap counts (ADR-267 and its amendment, #702; #200 2026-11-27).

A user's own index level watch, a day rule and the plan's own exits are never held by the daily cap and are not
counted against it. The plan's own exits are its loss stop lines (T-06 % of max loss, T-16 % of margin, the 2x-credit
line), its rupee loss stop and rupee profit target and its time exit T-10b (the % profit target T-07 stays counted:
a playbook level, not a stop or a level typed in rupees or clock time). Case: paper trade A-D #200 (weekly style,
cap 4) opened T-03, T-14, T-01 and T-10b, and its Rs 100 loss stop, flagged from about 11:00 at a loss of 162.5, was
held as "daily limit" until the exit at 11:23.
Any other rule id, an empty one or a non-string is counted (fail closed). This is the ONE home of that rule: the gate
(deciding a crossing) and the store (restoring the count on a worker start) both read it, so they cannot disagree.
A leaf module on purpose: it is not a gate module, so the store may import it without reaching the gate.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from ofo.adjustment import level_watch
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.playbook_eval import DAY_RULE_PREFIX, LEGACY_DAY_RULE_PREFIX

_EXEMPT_PREFIXES = (level_watch.RULE_PREFIX, DAY_RULE_PREFIX, LEGACY_DAY_RULE_PREFIX)
#: the plan's own exits by exact rule id (the alert kinds plan_loss_stop, plan_rupee_loss, plan_rupee_profit and
#: plan_time_exit of ``ofo.alerts``)
PLAN_EXIT_RULES: Final = frozenset({sl.TRIGGER_MAX_LOSS, sl.TRIGGER_MARGIN, sl.CREDIT_RULE, *sl.RUPEE_RULES,
                                    sl.TRIGGER_TIME_EXIT})


def cap_exempt(rule_id: object, *, loss_stop: bool = False) -> bool:
    """``loss_stop`` = the rule carries a loss-stop trigger under its own id (``stop_lines.is_loss_stop``, gap 3)."""
    if loss_stop:
        return True
    return isinstance(rule_id, str) and (rule_id in PLAN_EXIT_RULES or rule_id.startswith(_EXEMPT_PREFIXES))


def count_capped(rule_ids: Iterable[object], *, stops: frozenset[str]) -> int:
    """How many of these stored rule ids count toward the daily cap. ``stops`` = ``stop_lines.loss_stop_rule_ids`` of
    the plan, the same function the gate's readings read."""
    return sum(1 for r in rule_ids if not cap_exempt(r, loss_stop=sl.is_loss_stop(r, stops)))
