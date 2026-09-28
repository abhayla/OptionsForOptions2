"""REQ-041 AC-7: adjustment rules have global defaults with per-strategy overrides (ADR-011 Q57 = C)."""
from decimal import Decimal as D

import pytest

from ofo.rules import (
    DISABLED,
    Compare,
    InputName,
    Op,
    Origin,
    Rule,
    RuleAction,
    RuleKind,
    exit_max_loss,
    resolve_adjustment_rules,
)


def adj(rule_id: str, name: InputName, op: Op, value: str) -> Rule:
    return Rule(rule_id, RuleKind.ADJUSTMENT, Compare(name, op, D(value)), RuleAction.ALERT_ONLY)


GLOBAL = {
    "short-strike-threatened": adj("g-short", InputName.DISTANCE_TO_SHORT_STRIKE, Op.LTE, "100"),
    "dte-threshold": adj("g-dte", InputName.DTE, Op.LTE, "2"),
    "pnl-threshold": adj("g-pnl", InputName.PNL_PCT_OF_MAX_LOSS, Op.GTE, "50"),
}


def summary(resolved):
    return [(r.slot, r.rule.rule_id, r.origin) for r in resolved]


def test_no_overrides_uses_global_defaults_in_order():
    """AC-7: with no strategy overrides the strategy gets every global default, in global order."""
    assert summary(resolve_adjustment_rules(GLOBAL, {})) == [
        ("short-strike-threatened", "g-short", Origin.GLOBAL_DEFAULT),
        ("dte-threshold", "g-dte", Origin.GLOBAL_DEFAULT),
        ("pnl-threshold", "g-pnl", Origin.GLOBAL_DEFAULT),
    ]


def test_override_replaces_disables_and_adds():
    """AC-7: an override replaces its slot in place, DISABLED removes it, a new slot is appended."""
    overrides = {
        "added-iv": adj("s-iv", InputName.IV_PERCENTILE, Op.GTE, "80"),
        "short-strike-threatened": adj("s-short", InputName.DISTANCE_TO_SHORT_STRIKE, Op.LTE, "150"),
        "dte-threshold": DISABLED,
    }
    resolved = resolve_adjustment_rules(GLOBAL, overrides)
    assert summary(resolved) == [
        ("short-strike-threatened", "s-short", Origin.STRATEGY_OVERRIDE),
        ("pnl-threshold", "g-pnl", Origin.GLOBAL_DEFAULT),
        ("added-iv", "s-iv", Origin.STRATEGY_OVERRIDE),
    ]
    assert resolved[0].rule.condition.threshold == D("150")  # the override's number, not the global 100
    assert GLOBAL["short-strike-threatened"].condition.threshold == D("100")  # the global default is untouched


def test_one_strategys_override_does_not_leak_to_another():
    """AC-7: resolving strategy A with an override leaves strategy B on the global default."""
    a = resolve_adjustment_rules(GLOBAL, {"dte-threshold": adj("a-dte", InputName.DTE, Op.LTE, "5")})
    b = resolve_adjustment_rules(GLOBAL, {})
    assert a[1].rule.rule_id == "a-dte" and b[1].rule.rule_id == "g-dte"


def test_invalid_defaults_and_overrides_are_refused():
    """AC-7: non-adjustment rules, disabling an unknown slot, blank slots and repeated rule ids raise."""
    exit_rule = exit_max_loss("x", D("5000"), action=RuleAction.ALERT_ONLY)
    with pytest.raises(ValueError, match="adjustment rules only"):
        resolve_adjustment_rules({"m": exit_rule}, {})
    with pytest.raises(ValueError, match="adjustment rules only"):
        resolve_adjustment_rules(GLOBAL, {"dte-threshold": exit_rule})
    with pytest.raises(ValueError, match="no global default"):
        resolve_adjustment_rules(GLOBAL, {"unknown": DISABLED})
    with pytest.raises(ValueError, match="non-empty"):
        resolve_adjustment_rules(GLOBAL, {"": adj("s", InputName.DTE, Op.LTE, "1")})
    with pytest.raises(ValueError, match="repeat a rule id"):
        resolve_adjustment_rules(GLOBAL, {"extra": adj("g-dte", InputName.DTE, Op.LTE, "1")})
