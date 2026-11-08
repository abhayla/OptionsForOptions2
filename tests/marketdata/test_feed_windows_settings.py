"""REQ-167 AC-4 / AC-5 "Detection (feed stale and reconnect windows)": the two windows are read from the settings when
the feed's health is judged, so a changed setting changes the verdict with no restart. Defaults (3 s, 30 s) stay.

Pure: every time is passed in, the settings are plain mappings; no database, no clock.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.marketdata.feed_health import FEED_HEALTHY, FEED_WAITING, FeedState
from ofo.marketdata.spot_source import REASON_STALE, SOURCE_FEED, SourceReading, SourceState, resolve_spot
from ofo.rules.inputs import DataHealth
from ofo.settings import calc, defaults

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
T0 = datetime.datetime(2026, 10, 8, 10, 0, 0, tzinfo=IST)  # a Thursday, market open
SEC = datetime.timedelta(seconds=1)


def _values(**changed: str) -> dict[str, Decimal]:
    v = dict(defaults())
    v.update({k.replace("__", "."): Decimal(x) for k, x in changed.items()})
    return v


def _feed(values) -> FeedState:
    feed = FeedState(windows=calc.feed_windows(values), market_open=lambda _t: True)
    feed.on_connected(T0)
    feed.on_data(T0)
    return feed


def test_defaults_are_three_and_thirty_seconds():
    w = calc.feed_windows(defaults())
    assert (w.stale, w.reconnect) == (3 * SEC, 30 * SEC)


def test_feed_stale_window_changes_the_verdict_for_the_same_feed_state():
    """Core proof: last tick 4 s ago is stale at 3 s and fresh at 5 s."""
    now = T0 + 4 * SEC
    at_3 = _feed(_values(detection__feed_stale_seconds="3"))
    at_5 = _feed(_values(detection__feed_stale_seconds="5"))
    assert at_3.health(now) is DataHealth.STALE and at_3.phase(now) == FEED_WAITING
    assert at_5.health(now) is DataHealth.AVAILABLE and at_5.phase(now) == FEED_HEALTHY


def test_a_changed_setting_applied_to_a_running_feed_changes_the_next_verdict():
    """No restart: the same FeedState object, new windows applied, the next judgement differs."""
    now = T0 + 4 * SEC
    feed = _feed(defaults())
    assert feed.health(now) is DataHealth.STALE
    feed.apply_windows(calc.feed_windows(_values(detection__feed_stale_seconds="5")))
    assert feed.health(now) is DataHealth.AVAILABLE


def test_feed_reconnect_window_changes_the_verdict_for_the_same_outage():
    drop = T0 + SEC
    now = drop + 40 * SEC
    short = _feed(_values(detection__feed_reconnect_window_seconds="30"))
    long = _feed(_values(detection__feed_reconnect_window_seconds="60"))
    for f in (short, long):
        f.on_disconnected(drop)
    assert short.health(now) is DataHealth.UNAVAILABLE
    assert long.health(now) is DataHealth.STALE


def test_spot_from_the_feed_uses_the_stale_window_passed_in():
    reading = SourceReading(SourceState.STATED, Decimal("22500"), T0)
    now = T0 + 4 * SEC
    short = resolve_spot(reading, None, None, now=now,
                         windows=calc.feed_windows(_values(detection__feed_stale_seconds="3")))
    long = resolve_spot(reading, None, None, now=now,
                        windows=calc.feed_windows(_values(detection__feed_stale_seconds="5")))
    assert not short.available and (SOURCE_FEED, REASON_STALE) in short.reasons
    assert long.available and long.source == SOURCE_FEED
