"""AC-3: a stale market-data input can never trigger a rule; the trigger record shows data health.

End to end with a real W-013 rule (ofo.rules.templates.entry_level_reached): the adapter turns quote health into
the Snapshot's input_health map, and the merged rule engine (backend/ofo/rules) refuses to trigger on it.
"""
import datetime
from decimal import Decimal as D

from ofo.marketdata.health import HealthThresholds, build_quote
from ofo.marketdata.quote import SourceMetadata
from ofo.marketdata.rule_adapter import input_health_from_quotes
from ofo.rules import (
    Direction,
    InputName,
    Outcome,
    RuleAction,
    Snapshot,
    entry_level_reached,
    evaluate,
)
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 9, 29, 10, 0, 0, tzinfo=IST)
THRESHOLDS = HealthThresholds(stale_after=datetime.timedelta(seconds=60), delayed_after=datetime.timedelta(seconds=0))

RULE = entry_level_reached("e-up", D("23500"), Direction.AT_OR_ABOVE, action=RuleAction.ALERT_AND_PREPARE_ORDERS)


def nifty_quote(*, age_seconds: int):
    ts = NOW - datetime.timedelta(seconds=age_seconds)
    return build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=D("23600.00"), bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=ts, source=SourceMetadata(provider="vendor-x", feed_id="NIFTY-INDEX"),
        now=NOW, feed_connected=True, thresholds=THRESHOLDS,
    )


def snapshot_for(quote) -> Snapshot:
    input_health = input_health_from_quotes({InputName.UNDERLYING_LEVEL: quote})
    return Snapshot(
        values={InputName.UNDERLYING_LEVEL: D("23600.00")},
        as_of=NOW,
        data_health=quote.health,
        source=quote.source.provider,
        input_health=input_health,
    )


def test_ac3_fresh_quote_lets_the_rule_trigger():
    quote = nifty_quote(age_seconds=1)
    assert quote.health is DataHealth.AVAILABLE
    result = evaluate(RULE, snapshot_for(quote))
    assert result.outcome is Outcome.TRIGGERED
    assert result.data_health is DataHealth.AVAILABLE


def test_ac3_stale_quote_can_never_trigger_the_rule_even_though_the_raw_value_satisfies_it():
    """CORE-adjacent AC-3: 23,600 >= 23,500 would trigger, but the quote behind it is stale, so the rule
    CANNOT_EVALUATE instead - the trigger record (Evaluation) shows the data health and the missing input."""
    quote = nifty_quote(age_seconds=120)
    assert quote.health is DataHealth.STALE
    result = evaluate(RULE, snapshot_for(quote))
    assert result.outcome is Outcome.CANNOT_EVALUATE
    assert result.outcome is not Outcome.TRIGGERED
    assert InputName.UNDERLYING_LEVEL in result.missing
    assert result.data_health is DataHealth.STALE


def test_ac3_unavailable_quote_also_blocks_the_trigger():
    quote = nifty_quote(age_seconds=1)
    input_health = input_health_from_quotes({InputName.UNDERLYING_LEVEL: quote})
    input_health[InputName.UNDERLYING_LEVEL] = DataHealth.UNAVAILABLE
    snapshot = Snapshot(
        values={InputName.UNDERLYING_LEVEL: D("23600.00")}, as_of=NOW,
        data_health=DataHealth.AVAILABLE, input_health=input_health,
    )
    result = evaluate(RULE, snapshot)
    assert result.outcome is Outcome.CANNOT_EVALUATE
