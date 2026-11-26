"""GC-ICLIVE D-39: the live-data status message comes from the same freshness as the prices shown (one source).

Real case 23 Nov 2026 (C1, first read): "Live market data disconnected ... monitoring paused" beside spot 25523.85
and live leg prices; seconds later all live. The message read the feed's status while the prices on the same page
read each quote's own health. Now: when every price held is available (live), no disconnected message is raised; a
stale or lost price still says so. Real function: ofo.outcome.service._feed_message.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

from ofo.outcome.service import _feed_message
from ofo.rules.inputs import DataHealth

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


def test_a_leg_with_no_quote_is_not_live_so_the_message_stays():
    """Review: a leg whose quote is missing has no price; the message must not be hidden because spot is available."""
    snap = _snapshot(DataHealth.UNAVAILABLE, DataHealth.AVAILABLE, DataHealth.AVAILABLE)
    snap.legs["NSE_FO:9"] = SimpleNamespace(quote=None)
    assert _feed_message(snap) is not None


def test_the_not_live_state_asks_the_one_decision(monkeypatch):
    from ofo.outcome import service  # noqa: PLC0415
    asked = []
    real = service._feed_message
    monkeypatch.setattr(service, "_unpriced_legs", lambda definition, snapshot, label: ())
    monkeypatch.setattr(service, "_feed_message", lambda snap, **kw: asked.append(kw) or real(snap, **kw))
    snap = _snapshot(DataHealth.UNAVAILABLE, DataHealth.AVAILABLE, DataHealth.AVAILABLE)
    out = service.not_live(SimpleNamespace(underlying="NIFTY"), snap)
    assert asked == [{"shown_live": False}]  # a reply that shows no live price always carries the message
    assert "disconnected" in str(out.status_label)


def test_the_label_builder_is_called_from_one_function_only():
    import pathlib  # noqa: PLC0415
    import re  # noqa: PLC0415
    path = pathlib.Path(__file__).resolve().parents[2] / "backend/ofo/outcome/service.py"
    source = path.read_text(encoding="utf-8")
    calls = [m.start() for m in re.finditer(r"_not_live_label\(", source) if source[m.start() - 4:m.start()] != "def "]
    assert len(calls) == 1, "only _feed_message may call _not_live_label"
    assert source.rfind("def _feed_message", 0, calls[0]) > source.rfind("\ndef ", 0, calls[0]) - 1
