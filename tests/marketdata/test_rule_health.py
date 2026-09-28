"""AC-3: a stale market-data input can never trigger a rule; the trigger record shows data health.

End to end with real W-013 rules (ofo.rules.templates.entry_level_reached / a hand-built multi-input AllOf rule):
the adapter (build_snapshot) derives the Snapshot's health from the quotes backing the rule's own inputs - never
typed by the caller - and the merged rule engine (backend/ofo/rules) refuses to trigger on it.
"""
import datetime
from decimal import Decimal as D

from ofo.engine.legs import Instrument
from ofo.marketdata.health import HealthThresholds, build_quote
from ofo.marketdata.quote import SourceMetadata
from ofo.marketdata.rule_adapter import build_snapshot, worst_health
from ofo.rules import (
    AllOf,
    Compare,
    Direction,
    InputName,
    Op,
    Outcome,
    Rule,
    RuleAction,
    RuleKind,
    entry_level_reached,
    evaluate,
)
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 9, 29, 10, 0, 0, tzinfo=IST)
THRESHOLDS = HealthThresholds(stale_after=datetime.timedelta(seconds=60), delayed_after=datetime.timedelta(seconds=0))

LEVEL_RULE = entry_level_reached("e-up", D("23500"), Direction.AT_OR_ABOVE, action=RuleAction.ALERT_AND_PREPARE_ORDERS)
MULTI_RULE = Rule(
    "e-multi", RuleKind.ENTRY,
    AllOf((
        Compare(InputName.UNDERLYING_LEVEL, Op.GTE, D("23500")),
        Compare(InputName.DELTA, Op.GTE, D("0.3")),
    )),
    RuleAction.ALERT_AND_PREPARE_ORDERS,
)


def nifty_quote(*, age_seconds: int, feed_connected: bool = True):
    ts = NOW - datetime.timedelta(seconds=age_seconds)
    return build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=D("23600.00"), bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=ts, source=SourceMetadata(provider="vendor-x", feed_id="NIFTY-INDEX"),
        now=NOW, feed_connected=feed_connected, thresholds=THRESHOLDS,
    )


def option_quote(*, age_seconds: int):
    ts = NOW - datetime.timedelta(seconds=age_seconds)
    return build_quote(
        instrument_id="NIFTY26O2823500CE", underlying="NIFTY", exchange="NFO", segment="NFO-OPT",
        instrument_type=Instrument.CE, expiry=datetime.date(2026, 10, 28), strike=D("23500"),
        ltp=D("120.50"), bid=D("120"), ask=D("121"), volume=1000, oi=1000, oi_change=10,
        iv=D("14"), delta=D("0.45"), gamma=D("0.002"), theta=D("-8"), vega=D("6"),
        timestamp=ts, source=SourceMetadata(provider="vendor-x", feed_id="NIFTY-OPT"),
        now=NOW, feed_connected=True, thresholds=THRESHOLDS,
    )


def test_ac3_fresh_quote_lets_the_rule_trigger():
    quote = nifty_quote(age_seconds=1)
    assert quote.health is DataHealth.AVAILABLE
    snapshot = build_snapshot({InputName.UNDERLYING_LEVEL: quote}, {InputName.UNDERLYING_LEVEL: D("23600.00")}, NOW)
    assert snapshot.data_health is DataHealth.AVAILABLE  # derived by the adapter, not typed by the test
    result = evaluate(LEVEL_RULE, snapshot)
    assert result.outcome is Outcome.TRIGGERED
    assert result.data_health is DataHealth.AVAILABLE


def test_ac3_stale_quote_can_never_trigger_the_rule_even_though_the_raw_value_satisfies_it():
    """CORE-adjacent AC-3: 23,600 >= 23,500 would trigger, but the quote behind it is stale, so the rule
    CANNOT_EVALUATE instead - the trigger record (Evaluation) shows the data health and the missing input."""
    quote = nifty_quote(age_seconds=120)
    assert quote.health is DataHealth.STALE
    snapshot = build_snapshot({InputName.UNDERLYING_LEVEL: quote}, {InputName.UNDERLYING_LEVEL: D("23600.00")}, NOW)
    assert snapshot.data_health is DataHealth.STALE
    result = evaluate(LEVEL_RULE, snapshot)
    assert result.outcome is Outcome.CANNOT_EVALUATE
    assert result.outcome is not Outcome.TRIGGERED
    assert InputName.UNDERLYING_LEVEL in result.missing
    assert result.data_health is DataHealth.STALE


def test_ac3_unavailable_quote_also_blocks_the_trigger():
    quote = nifty_quote(age_seconds=1, feed_connected=False)
    assert quote.health is DataHealth.UNAVAILABLE
    snapshot = build_snapshot({InputName.UNDERLYING_LEVEL: quote}, {InputName.UNDERLYING_LEVEL: D("23600.00")}, NOW)
    assert snapshot.data_health is DataHealth.UNAVAILABLE
    result = evaluate(LEVEL_RULE, snapshot)
    assert result.outcome is Outcome.CANNOT_EVALUATE


def test_ac3_multi_input_rule_the_deciding_input_is_stale_and_the_record_shows_stale():
    """AC-3 fix: a multi-input rule (AND of UNDERLYING_LEVEL and DELTA, two different quotes). The underlying is
    fresh and satisfies its branch; DELTA's quote is stale, so that branch is UNKNOWN, the AND cannot decide (not
    all TRUE, none FALSE) -> CANNOT_EVALUATE. The snapshot's derived data_health is the worst of the two quotes'
    healths (STALE beats AVAILABLE), and the trigger record shows exactly that."""
    fresh_underlying = nifty_quote(age_seconds=1)
    stale_option = option_quote(age_seconds=120)
    assert fresh_underlying.health is DataHealth.AVAILABLE
    assert stale_option.health is DataHealth.STALE

    quote_by_input = {InputName.UNDERLYING_LEVEL: fresh_underlying, InputName.DELTA: stale_option}
    assert worst_health(quote_by_input) is DataHealth.STALE  # derived, worst-of the two backing quotes

    snapshot = build_snapshot(
        quote_by_input,
        {InputName.UNDERLYING_LEVEL: D("23600.00"), InputName.DELTA: D("0.45")},
        NOW,
    )
    assert snapshot.data_health is DataHealth.STALE

    result = evaluate(MULTI_RULE, snapshot)
    assert result.outcome is Outcome.CANNOT_EVALUATE
    assert result.outcome is not Outcome.TRIGGERED
    assert InputName.DELTA in result.missing
    assert result.data_health is DataHealth.STALE  # the trigger record shows the derived health
