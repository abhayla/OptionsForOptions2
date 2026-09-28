"""REQ-041 AC-1, AC-4, AC-5, AC-8: one rule model, its inputs, optional plans, AND/OR with V1 limits."""
import dataclasses
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.rules import (
    NO_ADJUSTMENT_RULE,
    NO_EXIT_RULE,
    AllOf,
    Always,
    AnyOf,
    Compare,
    ComplexityLimits,
    DataHealth,
    InputName,
    Op,
    Outcome,
    Rule,
    RuleAction,
    RuleKind,
    RulePlan,
    Snapshot,
    evaluate,
    evaluate_plan,
    exit_max_loss,
    snapshot_from_strategy,
)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
AS_OF = datetime.datetime(2026, 10, 20, 11, 15, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
GOLDEN = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, 75, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, 75, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 75, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 75, D("44.00"), D("39.50")),
))


def snap(**values: str) -> Snapshot:
    return Snapshot({InputName[k.upper()]: D(v) for k, v in values.items()}, AS_OF, DataHealth.AVAILABLE)


def lt(name: str, value: str) -> Compare:
    return Compare(InputName[name.upper()], Op.LTE, D(value))


def gt(name: str, value: str) -> Compare:
    return Compare(InputName[name.upper()], Op.GTE, D(value))


# ---- AC-1 -----------------------------------------------------------------------------------------------------


def test_one_model_for_entry_adjustment_and_exit():
    """AC-1: entry, adjustment and exit rules are the same Rule type, evaluated by the same function."""
    condition = gt("underlying_level", "23400")
    rules = [Rule(f"r-{kind.value}", kind, condition, RuleAction.ALERT_ONLY) for kind in RuleKind]
    assert {type(r) for r in rules} == {Rule}
    assert [r.kind for r in rules] == [RuleKind.ENTRY, RuleKind.ADJUSTMENT, RuleKind.EXIT]
    results = [evaluate(r, snap(underlying_level="23400")) for r in rules]
    assert [r.outcome for r in results] == [Outcome.TRIGGERED] * 3
    assert [r.kind for r in results] == [RuleKind.ENTRY, RuleKind.ADJUSTMENT, RuleKind.EXIT]


def test_rule_rejects_invalid_parts():
    """AC-1: the action is required and must be a RuleAction; kind, id and condition are validated."""
    condition = gt("live_pnl", "1000")
    with pytest.raises(TypeError):
        Rule("r", RuleKind.EXIT, condition)  # no action: the rule must choose one
    with pytest.raises(ValueError, match="RuleAction"):
        Rule("r", RuleKind.EXIT, condition, "alert")
    with pytest.raises(ValueError, match="RuleKind"):
        Rule("r", "exit", condition, RuleAction.ALERT_ONLY)
    with pytest.raises(ValueError, match="rule_id"):
        Rule(" ", RuleKind.EXIT, condition, RuleAction.ALERT_ONLY)
    with pytest.raises(ValueError, match="condition"):
        Rule("r", RuleKind.EXIT, "live_pnl > 1000", RuleAction.ALERT_ONLY)
    with pytest.raises(ValueError, match="only an entry rule"):
        Rule("r", RuleKind.EXIT, Always(), RuleAction.ALERT_ONLY)


# ---- AC-4 -----------------------------------------------------------------------------------------------------


def test_every_named_input_can_drive_a_rule():
    """AC-4: each input (level, move, distances, premium, P&L, DTE, IV, IV percentile, Greeks, thresholds) is usable."""
    expected = {
        "UNDERLYING_LEVEL", "UNDERLYING_MOVE_POINTS", "UNDERLYING_MOVE_PCT", "DISTANCE_TO_SHORT_STRIKE",
        "DISTANCE_TO_BREAKEVEN", "PREMIUM", "LIVE_PNL", "PNL_PCT_OF_MAX_PROFIT", "PNL_PCT_OF_MAX_LOSS", "DTE",
        "TIME_OF_DAY", "IV", "IV_PERCENTILE", "DELTA", "GAMMA", "THETA", "VEGA",
    }
    assert {n.name for n in InputName} == expected
    supplied = {n: D("-1.5") for n in InputName if n is not InputName.TIME_OF_DAY}
    snapshot = Snapshot(supplied, AS_OF, DataHealth.AVAILABLE)
    for name in InputName:
        rule = Rule(f"r-{name.value}", RuleKind.ADJUSTMENT, Compare(name, Op.LTE, D("-1.5")), RuleAction.ALERT_ONLY)
        result = evaluate(rule, snapshot)
        if name is InputName.TIME_OF_DAY:
            assert result.outcome is Outcome.NOT_TRIGGERED  # 675 minutes (11:15 IST) is not <= -1.5
            assert result.observations[0].value == D("675")
        else:
            assert result.outcome is Outcome.TRIGGERED, name
            assert result.observations[0].value == D("-1.5"), name


def test_engine_snapshot_inputs_on_golden_condor():
    """AC-4: distances, premium, P&L, strategy thresholds and DTE of the golden condor at 23,200, all exact."""
    s = snapshot_from_strategy(GOLDEN, underlying_level=D("23200"), as_of=AS_OF, data_health=DataHealth.AVAILABLE,
                               extra={InputName.IV: D("13.4"), InputName.DELTA: D("-0.12")})
    assert s.get(InputName.LIVE_PNL) == D("1365.00")
    assert s.get(InputName.PREMIUM) == D("72.80")  # 72.50 + 78.00 - 38.20 - 39.50 per unit
    assert s.get(InputName.DISTANCE_TO_SHORT_STRIKE) == D("200")
    assert s.get(InputName.DISTANCE_TO_BREAKEVEN) == D("291")  # breakevens 22,909 and 23,491
    assert s.get(InputName.PNL_PCT_OF_MAX_PROFIT) == D("20")  # 1,365 / 6,825
    assert s.get(InputName.PNL_PCT_OF_MAX_LOSS) == D("-136500") / D("8175")
    assert s.get(InputName.DTE) == D("7")
    assert s.get(InputName.TIME_OF_DAY) == D("675")
    assert s.get(InputName.IV) == D("13.4") and s.get(InputName.DELTA) == D("-0.12")
    assert s.get(InputName.IV_PERCENTILE) is None  # not supplied: missing, never zero


def test_snapshot_rejects_bad_values():
    """AC-4: float values, supplied TIME_OF_DAY, naive timestamps and engine-value overrides are refused."""
    with pytest.raises(ValueError, match="decimal"):
        Snapshot({InputName.LIVE_PNL: -5000.0}, AS_OF, DataHealth.AVAILABLE)
    with pytest.raises(ValueError, match="finite"):
        Snapshot({InputName.LIVE_PNL: D("NaN")}, AS_OF, DataHealth.AVAILABLE)
    with pytest.raises(ValueError, match="derived"):
        Snapshot({InputName.TIME_OF_DAY: D("600")}, AS_OF, DataHealth.AVAILABLE)
    with pytest.raises(ValueError, match="timezone-aware"):
        Snapshot({}, datetime.datetime(2026, 10, 20, 11, 15), DataHealth.AVAILABLE)
    with pytest.raises(ValueError, match="engine"):
        snapshot_from_strategy(GOLDEN, underlying_level=D("23200"), as_of=AS_OF, data_health=DataHealth.AVAILABLE,
                               extra={InputName.LIVE_PNL: D("0")})


# ---- AC-5 -----------------------------------------------------------------------------------------------------


def test_plan_without_exit_or_adjustment_is_valid_and_monitored():
    """AC-5: an empty plan is valid, monitored, explained (not blocked), and evaluates to nothing."""
    plan = RulePlan()
    assert plan.monitored is True
    assert plan.explanations() == (NO_EXIT_RULE, NO_ADJUSTMENT_RULE)
    assert "You may want to consider defining an exit condition." in NO_EXIT_RULE
    assert evaluate_plan(plan, snap(live_pnl="-9000")) == ()

    with_exit = RulePlan(exit=(exit_max_loss("x", D("5000"), action=RuleAction.ALERT_ONLY),))
    assert with_exit.explanations() == (NO_ADJUSTMENT_RULE,)
    (result,) = evaluate_plan(with_exit, snap(live_pnl="-9000"))
    assert result.outcome is Outcome.TRIGGERED


def test_plan_rejects_misfiled_or_duplicate_rules():
    """AC-5: a rule in the wrong bucket, or the same rule id twice, is refused."""
    exit_rule = exit_max_loss("x", D("5000"), action=RuleAction.ALERT_ONLY)
    with pytest.raises(ValueError, match="cannot be filed under adjustment"):
        RulePlan(adjustment=(exit_rule,))
    with pytest.raises(ValueError, match="twice"):
        RulePlan(exit=(exit_rule, exit_rule))


def test_no_advice_wording_in_explanations():
    """AC-5: explanations are decision-support wording (ADR-003), never 'you should'."""
    for text in (NO_EXIT_RULE, NO_ADJUSTMENT_RULE):
        assert "you should" not in text.lower() and "best" not in text.lower()


# ---- AC-8 -----------------------------------------------------------------------------------------------------


def test_and_or_composition_and_deciding_values():
    """AC-8: 'level >= 23,400 AND (delta >= 0.3 OR IV percentile >= 70)' with the values that decided it."""
    rule = Rule("adj", RuleKind.ADJUSTMENT,
                AllOf((gt("underlying_level", "23400"), AnyOf((gt("delta", "0.3"), gt("iv_percentile", "70"))))),
                RuleAction.ALERT_ONLY)

    hit = evaluate(rule, snap(underlying_level="23400", delta="0.1", iv_percentile="70"))
    assert hit.outcome is Outcome.TRIGGERED
    assert [(o.input, o.value) for o in hit.observations] == [
        (InputName.UNDERLYING_LEVEL, D("23400")), (InputName.IV_PERCENTILE, D("70"))]

    miss_and = evaluate(rule, snap(underlying_level="23399.95", delta="0.5", iv_percentile="90"))
    assert miss_and.outcome is Outcome.NOT_TRIGGERED
    assert [(o.input, o.held) for o in miss_and.observations] == [(InputName.UNDERLYING_LEVEL, False)]

    miss_or = evaluate(rule, snap(underlying_level="23500", delta="0.29", iv_percentile="69.9"))
    assert miss_or.outcome is Outcome.NOT_TRIGGERED
    assert [o.input for o in miss_or.observations] == [InputName.DELTA, InputName.IV_PERCENTILE]


def test_strict_and_inclusive_operators_at_the_threshold():
    """AC-8: at exactly the threshold GTE/LTE hold and GT/LT do not."""
    s = snap(delta="0.30")
    held = {op: evaluate(Rule("r", RuleKind.ADJUSTMENT, Compare(InputName.DELTA, op, D("0.3")),
                              RuleAction.ALERT_ONLY), s).outcome for op in Op}
    assert held == {Op.GTE: Outcome.TRIGGERED, Op.LTE: Outcome.TRIGGERED,
                    Op.GT: Outcome.NOT_TRIGGERED, Op.LT: Outcome.NOT_TRIGGERED}


def test_missing_input_is_cannot_evaluate_even_when_or_would_hold():
    """AC-8: an OR with one true branch and one missing input is CANNOT_EVALUATE, naming the missing input."""
    rule = Rule("r", RuleKind.EXIT, AnyOf((gt("underlying_level", "23400"), gt("iv", "20"))), RuleAction.ALERT_ONLY)
    result = evaluate(rule, snap(underlying_level="23500"))
    assert result.outcome is Outcome.CANNOT_EVALUATE
    assert result.missing == (InputName.IV,)
    assert result.reason == "missing input(s): iv"


def test_v1_complexity_limits():
    """AC-8: depth 2 and 5 comparisons are allowed; depth 3 or 6 comparisons are refused; limits configurable."""
    five = AllOf((gt("delta", "0.3"), AnyOf((lt("dte", "3"), gt("iv", "20"))), gt("underlying_level", "1"),
                  lt("live_pnl", "0")))
    assert Rule("ok", RuleKind.ADJUSTMENT, five, RuleAction.ALERT_ONLY).inputs == (
        InputName.DELTA, InputName.DTE, InputName.IV, InputName.UNDERLYING_LEVEL, InputName.LIVE_PNL)

    three_deep = AllOf((gt("delta", "0.3"), AnyOf((lt("dte", "3"), AllOf((gt("iv", "20"), gt("gamma", "1")))))))
    with pytest.raises(ValueError, match="nested 3 levels deep; the V1 limit is 2"):
        Rule("deep", RuleKind.ADJUSTMENT, three_deep, RuleAction.ALERT_ONLY)

    six = AllOf((*five.children, gt("theta", "-5")))
    with pytest.raises(ValueError, match="6 comparisons; the V1 limit is 5"):
        Rule("wide", RuleKind.ADJUSTMENT, six, RuleAction.ALERT_ONLY)

    assert Rule("wide", RuleKind.ADJUSTMENT, six, RuleAction.ALERT_ONLY, limits=ComplexityLimits(max_leaves=6))
    with pytest.raises(ValueError, match="V1 limit is 1"):
        Rule("r", RuleKind.ADJUSTMENT, AllOf((gt("delta", "0"), AnyOf((gt("iv", "1"), gt("dte", "1"))))),
             RuleAction.ALERT_ONLY, limits=ComplexityLimits(max_depth=1))
    with pytest.raises(ValueError, match="at least two"):
        AllOf((gt("delta", "0"),))
    assert dataclasses.asdict(ComplexityLimits()) == {"max_depth": 2, "max_leaves": 5}
