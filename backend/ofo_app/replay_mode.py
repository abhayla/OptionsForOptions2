"""TEST-ONLY replay mode for the outcome route (W-064 step 1; REQ-035, ADR-008).

When ``OUTCOME_REPLAY`` is set AND ``APP_ENV`` is ``test``, the outcome route's provider dependency is wired to the W-059
``KiteProvider`` fed from the real recorded frames file (tests/fixtures/kite_ws), valued at the recording's last frame.
Any other ``APP_ENV`` refuses the setting at start-up (``ofo_app.config.Settings`` validator, and again here), so a
production process can never serve recorded data as if it were live.
"""
from __future__ import annotations

import datetime
import gzip
import os
import pathlib
from decimal import Decimal

from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_frames import iter_recording
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app.routes.outcome import MarketContext

REPLAY_RATE = Decimal("0.065")
_FIXTURES = pathlib.Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "kite_ws"
FRAMES = _FIXTURES / "frames-2026-10-08-092000-10s.bin.gz"
INSTRUMENTS = _FIXTURES / "instruments-2026-10-08-subscribed.csv"


class ReplayRefused(RuntimeError):
    """Replay mode was requested outside APP_ENV=test."""


def replay_requested() -> bool:
    return os.environ.get("OUTCOME_REPLAY", "").strip().lower() in {"1", "true", "yes", "on"}


def require_test_env(app_env: str) -> None:
    if app_env != "test":
        raise ReplayRefused("OUTCOME_REPLAY is a test-only setting: it needs APP_ENV=test")


def build_replay_context() -> MarketContext:
    """Replays the recorded frames into a KiteProvider; the valuation clock is fixed at the last frame."""
    items = list(parse_instruments_csv(INSTRUMENTS))
    with gzip.open(FRAMES) as f:
        frames = [(datetime.datetime.fromtimestamp(ns / 1e9, IST), fr) for ns, fr in iter_recording(f)]
    now = frames[0][0]
    provider = KiteProvider(items, clock=lambda: now)
    provider.subscribe([f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in items])
    provider.on_connected(frames[0][0])
    for at, frame in frames:
        now = at
        provider.on_frame(frame, at)
    valuation = frames[-1][0]
    return MarketContext(provider, lambda: valuation, REPLAY_RATE)
