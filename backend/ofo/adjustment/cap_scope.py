"""Which alert records the strategy's daily alert cap counts (ADR-267 and its amendment, #702).

A user's own index level watch and a day rule are never held by the daily cap and are not counted against it. Any
other rule id, an empty one or a non-string is counted (fail closed). This is the ONE home of that rule: the gate
(deciding a crossing) and the store (restoring the count on a worker start) both read it, so they cannot disagree.
A leaf module on purpose: it is not a gate module, so the store may import it without reaching the gate.
"""
from __future__ import annotations

from collections.abc import Iterable

from ofo.adjustment import level_watch
from ofo.adjustment.playbook_eval import DAY_RULE_PREFIX, LEGACY_DAY_RULE_PREFIX

_EXEMPT_PREFIXES = (level_watch.RULE_PREFIX, DAY_RULE_PREFIX, LEGACY_DAY_RULE_PREFIX)


def cap_exempt(rule_id: object) -> bool:
    return isinstance(rule_id, str) and rule_id.startswith(_EXEMPT_PREFIXES)


def count_capped(rule_ids: Iterable[object]) -> int:
    """How many of these stored rule ids count toward the daily cap."""
    return sum(1 for r in rule_ids if not cap_exempt(r))
