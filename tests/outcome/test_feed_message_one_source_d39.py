"""GC-ICLIVE D-39: the live-data status message comes from the same freshness as the prices shown (one source).

Real case 23 Nov 2026 (C1, first read): "Live market data disconnected ... monitoring paused" beside spot 25523.85 and live leg
prices; seconds later all live. The message read the feed's status while the prices on the same page read each quote's own
health. Now: when every price held is available (live), no disconnected message is raised; a stale or lost price still says so.
Real function: ofo.outcome.service._feed_message.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

from ofo.rules.inputs import DataHealth
from ofo.outcome.service import _feed_message

AT = datetime.datetime(2026, 11, 23, 5, 0, tzinfo=datetime.UTC)


def _snapshot(status_health, *healths, spot=True):
    quote = lambda h: SimpleNamespace(health=h, timestamp=AT)  # noqa: E731
    legs = {f"NSE_FO:{i}": SimpleNamespace(quote=quote(h)) for i, h in enumerate(healths)}
    return SimpleNamespace(status=SimpleNamespace(health=status_health), spot=quote(healths[0]) if spot else None,
                           legs=legs, ended_times={})


def test_core_status_says_disconnected_but_every_price_is_live_no_message():
    assert _feed_message(_snapshot(DataHealth.UNAVAILABLE, DataHealth.AVAILABLE, DataHealth.AVAILABLE)) is None


def test_a_stale_price_still_gets_the_message():
    assert _feed_message(_snapshot(DataHealth.UNAVAILABLE, DataHealth.AVAILABLE, DataHealth.STALE)) is not None


def test_status_available_is_no_message():
    assert _feed_message(_snapshot(DataHealth.AVAILABLE, DataHealth.AVAILABLE)) is None


def test_no_price_held_at_all_keeps_the_not_connected_label():
    snap = _snapshot(DataHealth.UNAVAILABLE, DataHealth.AVAILABLE, spot=False)
    snap.legs = {}
    assert _feed_message(snap) is not None
