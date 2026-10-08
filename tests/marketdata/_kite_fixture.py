"""Shared replay helper for the W-059 tests: the real 2026-10-08 recording, replayed into a KiteProvider."""
import datetime
import gzip
import pathlib

from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_frames import iter_recording
from ofo.marketdata.kite_provider import IST, KiteProvider

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "kite_ws"
FRAMES = FIXTURES / "frames-2026-10-08-092000-10s.bin.gz"
INSTRUMENTS = FIXTURES / "instruments-2026-10-08-subscribed.csv"
NIFTY_CE_ID = "NSE_FO:44614"
NIFTY_PE_ID = "NSE_FO:44615"
SENSEX_CE_ID = "BSE_FO:889331"


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now


def recorded_frames() -> list[tuple[datetime.datetime, bytes]]:
    with gzip.open(FRAMES) as f:
        return [(datetime.datetime.fromtimestamp(ns / 1e9, IST), frame) for ns, frame in iter_recording(f)]


def listed():
    return list(parse_instruments_csv(INSTRUMENTS))


def all_instrument_ids(provider_listed) -> list[str]:
    ids = [f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in provider_listed]
    return ids + ["INDEX:NIFTY 50", "INDEX:SENSEX", "INDEX:INDIA VIX"]


def replay(provider: KiteProvider, clock: Clock, frames=None) -> datetime.datetime:
    """Connect, feed every recorded frame at its recorded time; returns the time of the last frame."""
    frames = recorded_frames() if frames is None else frames
    provider.on_connected(frames[0][0])
    for at, frame in frames:
        clock.now = at
        provider.on_frame(frame, at)
    return frames[-1][0]


def new_provider():
    items = listed()
    clock = Clock(recorded_frames()[0][0])
    return KiteProvider(items, clock=clock), clock, items
