"""Feed-wide health logs each CHANGE with its reason (diagnostic for the 27 Nov stale option legs; REQ-133, ADR-015).
No behaviour change: ``FeedState.health`` returns what it did before; only a log line per change and a counter."""
from __future__ import annotations

import datetime
import logging

from ofo.marketdata.feed_health import FeedState
from ofo.rules.inputs import DataHealth
from ofo.settings import calc, defaults

WINDOWS = calc.feed_windows(defaults())
T0 = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("feed health")]


def _open_feed(open_: bool = True) -> FeedState:
    return FeedState(windows=WINDOWS, market_open=lambda _t: open_)


def test_stale_then_live_logs_exactly_two_changes(caplog) -> None:
    caplog.set_level(logging.INFO)
    feed = _open_feed()
    feed.on_connected(T0)
    feed.on_data(T0)
    assert feed.health(T0) is DataHealth.AVAILABLE
    late = T0 + datetime.timedelta(seconds=4)
    assert feed.health(late) is DataHealth.STALE
    feed.on_data(late)
    assert feed.health(late) is DataHealth.AVAILABLE
    lines = _lines(caplog)
    assert lines[-2:] == [
        "feed health AVAILABLE -> STALE: no feed activity for 4.0 s (limit 3.0 s)",
        "feed health STALE -> AVAILABLE: live",
    ]


def test_unchanged_health_logs_nothing_more(caplog) -> None:
    caplog.set_level(logging.INFO)
    feed = _open_feed()
    feed.on_connected(T0)
    feed.on_data(T0)
    feed.health(T0)
    before = len(_lines(caplog))
    for _ in range(5):
        feed.health(T0)
    assert len(_lines(caplog)) == before


def test_on_connected_logs_awaiting_data(caplog) -> None:
    caplog.set_level(logging.INFO)
    feed = _open_feed()
    feed.on_connected(T0)
    assert feed.health(T0) is DataHealth.STALE
    assert any(line.endswith("STALE: awaiting data after (re)connect") for line in _lines(caplog))


def test_market_closed_and_counter(caplog) -> None:
    caplog.set_level(logging.INFO)
    feed = _open_feed(open_=False)
    assert feed.health(T0) is DataHealth.STALE
    assert _lines(caplog)[-1].endswith(": market closed")
    assert feed.health_changes == {"market closed": 1}
