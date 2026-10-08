"""Shared replay helper for the W-062 tests: the real 2026-10-08 recordings and Kite's candles for the same minutes."""
import datetime
import gzip
import json
import pathlib
from decimal import Decimal

from ofo.history.bars import IST, MinuteBar
from ofo.history.candles import parse_candles
from ofo.instruments.models import ZERODHA
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.kite_frames import iter_recording
from ofo.marketdata.kite_provider import KiteProvider

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
HISTORY = FIXTURES / "kite_history"
INSTRUMENTS = FIXTURES / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
WINDOWS = {"0920-0924": HISTORY / "frames-2026-10-08-0920-0924-8tok.bin.gz",
           "1506-1512": HISTORY / "frames-2026-10-08-1506-1512-8tok.bin.gz"}
CANDLES = HISTORY / "candles-2026-10-08.json"
DAY = datetime.date(2026, 10, 8)


def at(h: int, m: int, s: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 10, 8, h, m, s, tzinfo=IST)


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now


def frames(window: str) -> list[tuple[datetime.datetime, bytes]]:
    with gzip.open(WINDOWS[window]) as f:
        return [(datetime.datetime.fromtimestamp(ns / 1e9, IST), frame) for ns, frame in iter_recording(f)]


def listed():
    return list(parse_instruments_csv(INSTRUMENTS))


def token_ids() -> dict[str, str]:
    """Kite instrument token (as the candles file keys it) -> catalogue instrument id."""
    return {str(lc.ref(ZERODHA).broker_token): f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"
            for lc in listed()}


def index_ids() -> set[str]:
    return {"NSE_INDEX:1001", "BSE_INDEX:1"}


def candle_bars() -> dict[str, dict[str, list[MinuteBar]]]:
    """instrument id -> window -> Kite's candles, parsed from the recorded body text as Decimal."""
    ids = token_ids()
    body = json.loads(CANDLES.read_text(encoding="utf-8"))["bodies"]
    out: dict[str, dict[str, list[MinuteBar]]] = {}
    for token, windows in body.items():
        iid = ids[token]
        out[iid] = {w: parse_candles(text, iid, index=iid in index_ids()) for w, text in windows.items()}
    return out


def replay_window(window: str, listener_factory):
    """Replay one recorded window through a KiteProvider; listener_factory(fanout) wires the consumers.

    Returns (provider, fanout, last_frame_time). Every id the recording carries is subscribed through the FanOut."""
    items = listed()
    fr = frames(window)
    clock = Clock(fr[0][0])
    provider = KiteProvider(items, clock=clock)
    fan = FanOut(provider)
    ids = list(candle_bars())
    listener_factory(fan, ids)
    provider.on_connected(fr[0][0])
    for when, frame in fr:
        clock.now = when
        provider.on_frame(frame, when)
        fan.pump()
    return provider, fan, fr[-1][0]


def dec(text: str) -> Decimal:
    return Decimal(text)
