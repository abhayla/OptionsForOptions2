"""AC-5: disconnect BEHAVIOUR, not only text (ADR-015 Q182).

A disconnected feed makes every quote UNAVAILABLE, the affected strategy PAUSED, its disconnect status carries the
exact message and last-updated time, and a rule over those inputs is CANNOT_EVALUATE (never triggered). The message
is tied to exactly one cause (paused because the feed is disconnected) via disconnect_status_for_strategy.
"""
import datetime
from decimal import Decimal as D

import pytest

from ofo.marketdata.availability import MonitoringStatus, strategy_monitoring_status
from ofo.marketdata.disconnect import DisconnectStatus, disconnect_message, disconnect_status_for_strategy
from ofo.marketdata.health import HealthThresholds, build_quote
from ofo.marketdata.quote import SourceMetadata
from ofo.marketdata.rule_adapter import build_snapshot
from ofo.rules import Direction, InputName, Outcome, RuleAction, entry_level_reached, evaluate
from ofo.rules.inputs import DataHealth

UTC = datetime.timezone.utc
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 9, 29, 10, 0, 0, tzinfo=IST)
THRESHOLDS = HealthThresholds(stale_after=datetime.timedelta(seconds=60), delayed_after=datetime.timedelta(seconds=0))
SOURCE = SourceMetadata(provider="vendor-x", feed_id="NIFTY-INDEX")
RULE = entry_level_reached("e-up", D("23500"), Direction.AT_OR_ABOVE, action=RuleAction.ALERT_AND_PREPARE_ORDERS)


def nifty_quote(*, feed_connected: bool):
    return build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=D("23600.00"), bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=NOW, source=SOURCE, now=NOW, feed_connected=feed_connected, thresholds=THRESHOLDS,
    )


def test_ac5_exact_message_text_with_time_converted_to_ist():
    """ADR-015's own example format: 'Live market data disconnected. Last updated: 10:42:17 AM. Live strategy
    monitoring is paused.' UTC 05:12:17 -> IST (+5:30) 10:42:17."""
    last_updated_utc = datetime.datetime(2026, 9, 29, 5, 12, 17, tzinfo=UTC)
    msg = disconnect_message(last_updated_utc)
    assert msg == "Live market data disconnected. Last updated: 10:42:17 AM. Live strategy monitoring is paused."


def test_ac5_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        disconnect_message(datetime.datetime(2026, 9, 29, 9, 5, 0))


def test_ac5_disconnected_feed_makes_every_quote_unavailable_and_pauses_the_strategy():
    """AC-5 behaviour: when live data drops, every quote from that feed is UNAVAILABLE and the affected strategy's
    monitoring is PAUSED - not merely a status label typed by the caller."""
    quote = nifty_quote(feed_connected=False)
    assert quote.health is DataHealth.UNAVAILABLE
    status = strategy_monitoring_status({"NIFTY-INDEX": quote})
    assert status is MonitoringStatus.PAUSED


def test_ac5_disconnect_status_carries_the_exact_message_and_last_updated_time():
    quote = nifty_quote(feed_connected=False)
    status = strategy_monitoring_status({"NIFTY-INDEX": quote})
    disconnect = disconnect_status_for_strategy(feed_connected=False, monitoring_status=status, last_updated=NOW)
    assert disconnect is not None
    assert isinstance(disconnect, DisconnectStatus)
    assert disconnect.message == disconnect_message(NOW)
    assert disconnect.last_updated == NOW


def test_ac5_a_rule_over_disconnected_inputs_cannot_evaluate_and_is_never_triggered():
    """AC-5: no trigger is claimed without the data proving it (Q182) - a disconnected feed's rule CANNOT_EVALUATE."""
    quote = nifty_quote(feed_connected=False)
    snapshot = build_snapshot({InputName.UNDERLYING_LEVEL: quote}, {InputName.UNDERLYING_LEVEL: D("23600.00")}, NOW)
    result = evaluate(RULE, snapshot)
    assert result.outcome is Outcome.CANNOT_EVALUATE
    assert result.outcome is not Outcome.TRIGGERED


def test_ac5_no_disconnect_status_while_the_feed_is_connected_even_if_paused_for_another_reason():
    """The message is tied to exactly one cause: paused BECAUSE the feed is disconnected. A strategy paused for a
    different reason (e.g. a stale quote) while the feed stays connected gets no disconnect status."""
    assert disconnect_status_for_strategy(
        feed_connected=True, monitoring_status=MonitoringStatus.PAUSED, last_updated=NOW
    ) is None


def test_ac5_no_disconnect_status_when_the_strategy_is_still_active():
    assert disconnect_status_for_strategy(
        feed_connected=False, monitoring_status=MonitoringStatus.ACTIVE, last_updated=NOW
    ) is None
