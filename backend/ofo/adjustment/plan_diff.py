"""What a strategy's plan changed against the playbook it was made from (ADR-330 (9); pure, no database).

A plan is a COPY of its playbook's body. Each condition (a trigger, a guard, a day rule, an approach, a rule, a
situation, a plan setting) can be changed or switched off for this trade, never added: ``subset_of`` is False when the
plan holds a condition the playbook lacks. ``diff`` lists what differs ("the plan marks the conditions the user changed
or switched off"); ``reset`` is the playbook's conditions again (a deep copy)
with the plan's own sheet levels and settings kept.

A condition's name is its path: ``triggers.T-01``, ``guards.max_adjustments``, ``day_rules.<id or position>``. Values
compare as stored (decimal strings, never floats).
"""
from __future__ import annotations

import copy
from typing import Any

from ofo.adjustment import stop_lines as sl
from ofo.settings import layers

#: top-level keys that are not conditions: identity and layout of the body, and the strategy layer's own values
#: (ADR-245: a plan's settings are the trade's values, never a playbook condition)
_NOT_CONDITIONS = frozenset({"schema", "strategy_type", "status", "stages", layers.PLAN_SETTINGS})
#: the plan sheet's own levels (ADR-330 (5)): a user may type one where the playbook holds none, so they are values
#: of the trade, not conditions. The three literals equal the plan route's TARGET_KEY, MAX_KEY, TIME_KEY (test-pinned)
SHEET_LEVELS = frozenset({"profit_target_pct_of_max_profit", sl.RUPEE_PROFIT_KEY, sl.RUPEE_LOSS_KEY,
                          "max_adjustments", "time_exit"})


def _item_key(item: Any, position: int) -> str:
    if isinstance(item, dict) and isinstance(item.get("id"), str):
        return item["id"]
    return item if isinstance(item, str) else str(position)


def conditions(body: dict) -> dict[str, Any]:
    """Every condition of a body as {path: stored value}."""
    found: dict[str, Any] = {}
    for key, value in body.items():
        if key in _NOT_CONDITIONS:
            continue
        if isinstance(value, dict):
            found.update({f"{key}.{name}": item for name, item in value.items()
                          if not (key == "guards" and name in SHEET_LEVELS)})
        elif isinstance(value, list):
            found.update({f"{key}.{_item_key(item, i)}": item for i, item in enumerate(value)})
        else:
            found[key] = value
    return found


def _is_off(value: Any) -> bool:
    return isinstance(value, dict) and value.get("on") is False


def added(plan_body: dict, playbook_body: dict) -> list[str]:
    """The conditions the plan holds and its playbook does not (sorted)."""
    return sorted(set(conditions(plan_body)) - set(conditions(playbook_body)))


def subset_of(plan_body: dict, playbook_body: dict) -> bool:
    """True when the plan holds no condition its playbook lacks (the user cannot add one)."""
    return not added(plan_body, playbook_body)


def diff(plan_body: dict, playbook_body: dict) -> dict[str, list[str]]:
    """{changed, switched_off}: conditions whose value differs; conditions switched off (``on`` true -> false, or
    removed from the plan). A condition the plan added is not listed (``added`` / ``subset_of`` refuse it)."""
    plan, book = conditions(plan_body), conditions(playbook_body)
    changed: list[str] = []
    off: list[str] = []
    for path in sorted(book):
        if path not in plan or (_is_off(plan[path]) and not _is_off(book[path])):
            off.append(path)
        elif plan[path] != book[path]:
            changed.append(path)
    return {"changed": changed, "switched_off": off}


def reset(plan_body: dict, playbook_body: dict) -> dict:
    """Every condition back to the playbook's (a deep copy). The plan's own sheet levels (``SHEET_LEVELS`` guards) and
    plan settings are values of the trade, not conditions: they are kept as stored (LP-5 (a))."""
    out = copy.deepcopy(playbook_body)
    plan_guards = plan_body.get("guards") if isinstance(plan_body.get("guards"), dict) else {}
    guards = {k: v for k, v in (out.get("guards") or {}).items() if k not in SHEET_LEVELS}
    guards.update({k: copy.deepcopy(v) for k, v in plan_guards.items() if k in SHEET_LEVELS})
    if guards or "guards" in out:
        out["guards"] = guards
    if layers.PLAN_SETTINGS in plan_body:
        out[layers.PLAN_SETTINGS] = copy.deepcopy(plan_body[layers.PLAN_SETTINGS])
    return out
