"""REQ-041 AC-2: V1 entry conditions - immediate, level/range reached, premium target, volatility, time window."""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.rules import (
    DataHealth,
    Direction,
    InputName,
    Outcome,
    RuleAction,
    RuleKind,
    Snapshot,
    entry_immediate,
    entry_level_reached,
    entry_premium_target,
    entry_range,
    entry_time_window,
    entry_volatility,
    evaluate,
    snapshot_from_strategy,
)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
ACT = RuleAction.ALERT_AND_PREPARE_ORDERS


def snap(at: datetime.time = datetime.time(10, 0), health: DataHealth = DataHealth.AVAILABLE, **values: str):
    moment = datetime.datetime.combine(datetime.date(2026, 10, 20), at, tzinfo=IST)
    return Snapshot({InputName[k.upper()]: D(v) for k, v in values.items()}, moment, health)


def outcome(rule, **kw) -> Outcome:
    return evaluate(rule, snap(**kw)).outcome


def test_immediate_entry_always_triggers_even_without_market_data():
    """AC-2: 'Enter now' reads no input, so it triggers with no values and even while data is unavailable."""
    rule = entry_immediate("e-now", action=ACT)
    assert rule.kind is RuleKind.ENTRY and rule.inputs == ()
    result = evaluate(rule, snap(health=DataHealth.UNAVAILABLE))
    assert result.outcome is Outcome.TRIGGERED
    assert result.observations == ()


def test_level_reached_both_directions_at_the_boundary():
    """AC-2: 'at or above 23,500' triggers at 23,500.00, not at 23,499.95; 'at or below' mirrors it."""
    above = entry_level_reached("e-up", D("23500"), Direction.AT_OR_ABOVE, action=ACT)
    below = entry_level_reached("e-dn", D("23000"), Direction.AT_OR_BELOW, action=ACT)
    assert outcome(above, underlying_level="23500.00") is Outcome.TRIGGERED
    assert outcome(above, underlying_level="23499.95") is Outcome.NOT_TRIGGERED
    assert outcome(below, underlying_level="23000") is Outcome.TRIGGERED
    assert outcome(below, underlying_level="23000.05") is Outcome.NOT_TRIGGERED
    with pytest.raises(ValueError, match="> 0"):
        entry_level_reached("e", D("0"), Direction.AT_OR_ABOVE, action=ACT)


def test_range_includes_both_ends():
    """AC-2: range 23,100-23,300 triggers at both ends and not just outside them."""
    rule = entry_range("e-range", D("23100"), D("23300"), action=ACT)
    got = [outcome(rule, underlying_level=v) for v in ("23099.95", "23100", "23200", "23300", "23300.05")]
    assert got == [Outcome.NOT_TRIGGERED, Outcome.TRIGGERED, Outcome.TRIGGERED, Outcome.TRIGGERED,
                   Outcome.NOT_TRIGGERED]
    with pytest.raises(ValueError, match="above high"):
        entry_range("e", D("23300"), D("23100"), action=ACT)


def test_premium_target_credit_and_debit():
    """AC-2: rupee totals - credit 6,750 triggers at +6,750 not +6,746.25; debit 3,750 at -3,750, not -3,753.75."""
    credit = entry_premium_target("e-cr", D("6750"), receive=True, action=ACT)
    debit = entry_premium_target("e-db", D("3750"), receive=False, action=ACT)
    assert outcome(credit, net_premium="6750") is Outcome.TRIGGERED
    assert outcome(credit, net_premium="6746.25") is Outcome.NOT_TRIGGERED
    assert outcome(debit, net_premium="-3750") is Outcome.TRIGGERED
    assert outcome(debit, net_premium="-3746.25") is Outcome.TRIGGERED  # paying less than 3,750
    assert outcome(debit, net_premium="-3753.75") is Outcome.NOT_TRIGGERED  # paying more than 3,750


def test_premium_target_on_ratio_spread_uses_engine_net_premium():
    """AC-2: BUY 75x23000CE@100 / SELL 150x23200CE@60 is a +1,500 credit (engine), so 'credit at least 1,500'
    triggers and 'at least 1,500.01' does not; before the fix the rules saw an unweighted -40 and never triggered."""
    legs = (
        Leg(Action.BUY, Instrument.CE, D("23000"), datetime.date(2026, 10, 27), 75, D("100"), D("100")),
        Leg(Action.SELL, Instrument.CE, D("23200"), datetime.date(2026, 10, 27), 150, D("60"), D("60")),
    )
    snapshot = snapshot_from_strategy(Strategy(legs), underlying_level=D("23100"),
                                      as_of=datetime.datetime(2026, 10, 20, 10, 0, tzinfo=IST),
                                      data_health=DataHealth.AVAILABLE)
    assert snapshot.get(InputName.NET_PREMIUM) == D("1500")
    at = entry_premium_target("e-cr", D("1500"), receive=True, action=ACT)
    above = entry_premium_target("e-cr2", D("1500.01"), receive=True, action=ACT)
    result = evaluate(at, snapshot)
    assert result.outcome is Outcome.TRIGGERED
    assert result.observations[0].value == D("1500")
    assert evaluate(above, snapshot).outcome is Outcome.NOT_TRIGGERED


def test_volatility_condition():
    """AC-2: IV percentile at or above 70 triggers at 70; IV between 12 and 18 includes both ends."""
    pct = entry_volatility("e-ivp", InputName.IV_PERCENTILE, D("70"), None, action=ACT)
    band = entry_volatility("e-iv", InputName.IV, D("12"), D("18"), action=ACT)
    assert outcome(pct, iv_percentile="70") is Outcome.TRIGGERED
    assert outcome(pct, iv_percentile="69.99") is Outcome.NOT_TRIGGERED
    assert [outcome(band, iv=v) for v in ("11.99", "12", "18", "18.01")] == [
        Outcome.NOT_TRIGGERED, Outcome.TRIGGERED, Outcome.TRIGGERED, Outcome.NOT_TRIGGERED]
    with pytest.raises(ValueError, match="IV or IV_PERCENTILE"):
        entry_volatility("e", InputName.DELTA, D("1"), None, action=ACT)
    with pytest.raises(ValueError, match="low and/or a high"):
        entry_volatility("e", InputName.IV, None, None, action=ACT)


def test_volatility_missing_iv_cannot_evaluate():
    """AC-2: with no IV in the snapshot the volatility entry is CANNOT_EVALUATE, not 'not triggered'."""
    rule = entry_volatility("e-iv", InputName.IV, D("12"), None, action=ACT)
    result = evaluate(rule, snap(underlying_level="23200"))
    assert result.outcome is Outcome.CANNOT_EVALUATE and result.missing == (InputName.IV,)


def test_time_window_in_ist_inclusive():
    """AC-2: window 09:30-11:00 IST triggers at 09:30 and 11:00, not at 09:29 or 11:01; UTC input is converted."""
    rule = entry_time_window("e-time", datetime.time(9, 30), datetime.time(11, 0), action=ACT)
    got = [evaluate(rule, snap(at=datetime.time(h, m))).outcome for h, m in ((9, 29), (9, 30), (11, 0), (11, 1))]
    assert got == [Outcome.NOT_TRIGGERED, Outcome.TRIGGERED, Outcome.TRIGGERED, Outcome.NOT_TRIGGERED]
    utc = Snapshot({}, datetime.datetime(2026, 10, 20, 4, 0, tzinfo=datetime.timezone.utc), DataHealth.AVAILABLE)
    result = evaluate(rule, utc)  # 04:00 UTC = 09:30 IST
    assert result.outcome is Outcome.TRIGGERED
    assert result.observations[0].value == D("570")
