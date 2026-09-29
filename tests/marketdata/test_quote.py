"""AC-1: the normalized quote carries every named field, exact Decimal/int types, tz-aware timestamp, source."""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.legs import Instrument
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 9, 29, 10, 0, 0, tzinfo=IST)
SOURCE = SourceMetadata(provider="vendor-x", feed_id="NFO-OPT-1")


def option_quote(**overrides) -> NormalizedQuote:
    fields = dict(
        instrument_id="NIFTY26O0623500CE",
        underlying="NIFTY",
        exchange="NFO",
        segment="NFO-OPT",
        instrument_type=Instrument.CE,
        expiry=datetime.date(2026, 10, 6),
        strike=D("23500"),
        ltp=D("120.50"),
        bid=D("120.00"),
        ask=D("121.00"),
        volume=125000,
        oi=980000,
        oi_change=1500,
        iv=D("14.25"),
        delta=D("0.45"),
        gamma=D("0.002"),
        theta=D("-8.10"),
        vega=D("6.30"),
        timestamp=NOW,
        source=SOURCE,
        health=DataHealth.AVAILABLE,
    )
    fields.update(overrides)
    return NormalizedQuote(**fields)


def test_ac1_every_named_field_is_present_with_exact_types():
    """AC-1: instrument id, underlying, exchange, segment, expiry, strike, CE/PE, LTP, bid, ask, volume, OI,
    OI change, IV, Greeks, timestamp, source metadata, data health."""
    q = option_quote()
    assert q.instrument_id == "NIFTY26O0623500CE"
    assert q.underlying == "NIFTY"
    assert q.exchange == "NFO"
    assert q.segment == "NFO-OPT"
    assert q.expiry == datetime.date(2026, 10, 6)
    assert q.strike == D("23500") and isinstance(q.strike, D)
    assert q.instrument_type is Instrument.CE
    for field_name in ("ltp", "bid", "ask", "iv", "delta", "gamma", "theta", "vega"):
        assert isinstance(getattr(q, field_name), D), field_name
    assert isinstance(q.volume, int) and not isinstance(q.volume, bool)
    assert isinstance(q.oi, int) and isinstance(q.oi_change, int)
    assert q.timestamp.tzinfo is not None
    assert q.source == SOURCE
    assert q.health is DataHealth.AVAILABLE


def test_ac1_underlying_index_quote_carries_no_expiry_or_strike():
    """An underlying (index) quote has instrument_type=None and no expiry/strike, per AC-1's optional fields."""
    q = option_quote(instrument_type=None, expiry=None, strike=None)
    assert q.instrument_type is None
    assert q.expiry is None and q.strike is None


def test_ac1_future_quote_has_expiry_but_no_strike():
    q = option_quote(instrument_type=Instrument.FUT, strike=None)
    assert q.instrument_type is Instrument.FUT
    assert q.strike is None
    assert q.expiry == datetime.date(2026, 10, 6)


def test_rejects_naive_timestamp():
    """Input-domain checklist: a timezone-naive timestamp is rejected, not silently treated as UTC/IST."""
    with pytest.raises(ValueError, match="timezone-aware"):
        option_quote(timestamp=datetime.datetime(2026, 9, 29, 10, 0, 0))


def test_future_timestamp_never_raises_but_is_unhealthy_beyond_clock_skew():
    """Input-domain checklist: a quote timestamped well after 'now' never raises when built (NormalizedQuote has
    no clock dependency; build_quote takes 'now' explicitly, never the wall clock) - it becomes UNHEALTHY with a
    reason instead (REQ-049 AC-2 fix)."""
    from ofo.marketdata.health import DataHealth as _DataHealth
    from ofo.marketdata.health import build_quote

    future = NOW + datetime.timedelta(hours=1)
    q = build_quote(
        instrument_id="NIFTY26O0623500CE", underlying="NIFTY", exchange="NFO", segment="NFO-OPT",
        instrument_type=Instrument.CE, expiry=datetime.date(2026, 10, 6), strike=D("23500"),
        ltp=D("120.50"), bid=D("120.00"), ask=D("121.00"), volume=1000, oi=1000, oi_change=10,
        iv=D("14"), delta=D("0.4"), gamma=D("0.001"), theta=D("-1"), vega=D("1"),
        timestamp=future, source=SOURCE, now=NOW,
    )
    assert q.health is _DataHealth.UNHEALTHY
    assert any("clock-skew" in e for e in q.validation_errors)


def test_rejects_negative_price_and_absurd_volume():
    with pytest.raises(ValueError):
        option_quote(ltp=D("-1"))
    with pytest.raises(ValueError):
        option_quote(volume=10**13)


def test_rejects_option_quote_with_no_strike():
    with pytest.raises(ValueError, match="strike"):
        option_quote(strike=None)


def test_futures_quote_rejects_a_strike():
    with pytest.raises(ValueError, match="no strike"):
        option_quote(instrument_type=Instrument.FUT, strike=D("23500"))


def test_crossed_quote_is_recorded_but_not_rejected():
    """A crossed market (bid > ask) is a soft anomaly: constructed, flagged, left for HealthPolicy to weigh."""
    q = option_quote(bid=D("121.00"), ask=D("120.00"))
    assert any("crossed_quote" in e for e in q.validation_errors)


def test_source_metadata_rejects_negative_delay():
    with pytest.raises(ValueError, match="declared_delay_seconds"):
        SourceMetadata(provider="v", feed_id="f", declared_delay_seconds=D("-1"))
