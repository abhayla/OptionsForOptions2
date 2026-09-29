"""Core proof (W-018): a quote older than the freshness limit is 'stale', and a strategy that needs it becomes
'monitoring paused' while another strategy on healthy quotes stays active.

AC-2: five-value health state (available, stale, delayed, unhealthy, unavailable) derived from explicit inputs.
AC-6: monitoring availability is tracked per strategy, not app-wide.
"""
import datetime
from decimal import Decimal as D

import pytest

from ofo.marketdata.availability import MonitoringStatus, strategy_monitoring_status
from ofo.marketdata.health import HealthThresholds, build_quote, evaluate_health
from ofo.marketdata.quote import SourceMetadata
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 9, 29, 10, 0, 0, tzinfo=IST)
THRESHOLDS = HealthThresholds(stale_after=datetime.timedelta(seconds=60), delayed_after=datetime.timedelta(seconds=0))
SOURCE = SourceMetadata(provider="vendor-x", feed_id="NIFTY-INDEX")


def index_quote(*, age_seconds: int, feed_connected: bool = True, declared_delay: D = D("0")):
    ts = NOW - datetime.timedelta(seconds=age_seconds)
    return build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=D("23500.00"), bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=ts, source=SourceMetadata(provider="vendor-x", feed_id="NIFTY-INDEX",
                                             declared_delay_seconds=declared_delay),
        now=NOW, feed_connected=feed_connected, thresholds=THRESHOLDS,
    )


def test_core_boundary_available_at_the_limit_stale_just_past_it():
    """CORE: age == stale_after is still 'available' (inclusive limit); age > stale_after is 'stale'."""
    at_limit = index_quote(age_seconds=60)
    assert at_limit.health is DataHealth.AVAILABLE
    just_stale = index_quote(age_seconds=61)
    assert just_stale.health is DataHealth.STALE


def test_core_nifty_active_sensex_paused_on_the_same_strategy_set():
    """CORE: NIFTY quote fresh -> its strategy stays ACTIVE; SENSEX quote stale -> its strategy is PAUSED."""
    nifty = index_quote(age_seconds=10)
    sensex = index_quote(age_seconds=120)  # older than the 60s stale limit
    assert strategy_monitoring_status({"NIFTY-INDEX": nifty}) is MonitoringStatus.ACTIVE
    assert strategy_monitoring_status({"SENSEX-INDEX": sensex}) is MonitoringStatus.PAUSED


def test_ac2_unavailable_when_feed_disconnected_even_if_quote_is_fresh():
    q = index_quote(age_seconds=1, feed_connected=False)
    assert q.health is DataHealth.UNAVAILABLE


def test_ac2_unhealthy_on_a_crossed_quote_even_if_fresh():
    q = build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=D("23500.00"), bid=D("23510"), ask=D("23490"),  # crossed
        volume=None, oi=None, oi_change=None, iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=NOW, source=SOURCE, now=NOW, feed_connected=True, thresholds=THRESHOLDS,
    )
    assert q.health is DataHealth.UNHEALTHY


def test_ac2_delayed_when_source_declares_a_delay_beyond_tolerance():
    q = index_quote(age_seconds=1, declared_delay=D("5"))
    assert q.health is DataHealth.DELAYED


def test_ac2_stale_outranks_a_declared_delay():
    """Staleness by age is more severe than an explicit source-declared delay."""
    q = index_quote(age_seconds=120, declared_delay=D("5"))
    assert q.health is DataHealth.STALE


def test_ac2_no_price_at_all_is_unhealthy_not_available_and_pauses_its_strategy():
    """AC-2 fix: a quote with no LTP, bid or ask is not AVAILABLE (UNHEALTHY, documented), and its strategy pauses."""
    q = build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=None, bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=NOW, source=SOURCE, now=NOW, feed_connected=True, thresholds=THRESHOLDS,
    )
    assert q.health is DataHealth.UNHEALTHY
    assert any("no_price_data" in e for e in q.validation_errors)
    assert strategy_monitoring_status({"NIFTY-INDEX": q}) is MonitoringStatus.PAUSED


def test_evaluate_health_rejects_naive_datetimes():
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_health(
            timestamp=datetime.datetime(2026, 9, 29, 10, 0, 0), now=NOW, feed_connected=True,
            declared_delay_seconds=D("0"), validation_failed=False, thresholds=THRESHOLDS,
        )


def test_ac2_future_timestamp_within_clock_skew_tolerance_is_treated_as_fresh():
    """AC-2 fix: default 2s clock-skew tolerance (orchestrator default); within it, age 0 (fresh, AVAILABLE);
    building the quote must never raise."""
    slightly_future = NOW + datetime.timedelta(seconds=1)
    q = build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=D("23500.00"), bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=slightly_future, source=SOURCE, now=NOW, feed_connected=True, thresholds=THRESHOLDS,
    )
    assert q.health is DataHealth.AVAILABLE
    assert q.validation_errors == ()


def test_ac2_future_timestamp_beyond_clock_skew_tolerance_is_unhealthy_with_a_reason():
    """AC-2 fix: beyond the tolerance -> UNHEALTHY with a reason recorded, never a raised exception."""
    far_future = NOW + datetime.timedelta(seconds=10)
    q = build_quote(
        instrument_id="NIFTY-INDEX", underlying="NIFTY", exchange="NSE", segment="INDEX",
        instrument_type=None, expiry=None, strike=None,
        ltp=D("23500.00"), bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=far_future, source=SOURCE, now=NOW, feed_connected=True, thresholds=THRESHOLDS,
    )
    assert q.health is DataHealth.UNHEALTHY
    assert any("clock-skew" in e for e in q.validation_errors)


def test_evaluate_health_result_carries_health_and_reason():
    result = evaluate_health(
        timestamp=NOW + datetime.timedelta(seconds=10), now=NOW, feed_connected=True,
        declared_delay_seconds=D("0"), validation_failed=False, thresholds=THRESHOLDS,
    )
    assert result.health is DataHealth.UNHEALTHY
    assert "clock-skew" in result.reason


def test_ac6_strategy_needing_multiple_quotes_pauses_if_any_one_is_unhealthy():
    fresh_leg = index_quote(age_seconds=1)
    stale_leg = index_quote(age_seconds=200)
    status = strategy_monitoring_status({"leg-1": fresh_leg, "leg-2": stale_leg})
    assert status is MonitoringStatus.PAUSED


def test_ac6_missing_quote_pauses_the_strategy():
    status = strategy_monitoring_status({"leg-1": index_quote(age_seconds=1), "leg-2": None})
    assert status is MonitoringStatus.PAUSED


def test_ac6_rejects_a_strategy_with_no_quotes_at_all():
    with pytest.raises(ValueError, match="at least one quote"):
        strategy_monitoring_status({})


def test_thresholds_reject_negative_timedeltas():
    with pytest.raises(ValueError, match="stale_after"):
        HealthThresholds(stale_after=datetime.timedelta(seconds=-1))
