"""W-062: the app adapter for Kite's minute candles, tested with the recorded bodies through a fake transport."""
import datetime
import json
import logging
import pathlib
from decimal import Decimal

import pytest

from ofo.history.bars import IST, BarSource
from ofo.history.candles import CandleError
from ofo.instruments.parser import parse_instruments_csv
from ofo_app.kite_history import CandleFetchError, KiteHistory

ROOT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"
LISTED = list(parse_instruments_csv(ROOT / "kite_ws" / "instruments-2026-10-08-subscribed.csv"))
BODIES = json.loads((ROOT / "kite_history" / "candles-2026-10-08.json").read_text(encoding="utf-8"))["bodies"]
NIFTY_CE = "NSE_FO:44614"  # Kite token 11421186
SECRET = "tok-SECRET-123"
START = datetime.datetime(2026, 10, 8, 15, 5, tzinfo=IST)
END = datetime.datetime(2026, 10, 8, 15, 12, tzinfo=IST)


def history(transport):
    return KiteHistory(LISTED, api_key="key", access_token=SECRET, transport=transport)


def test_recorded_body_through_a_fake_transport_gives_decimal_kite_bars_and_the_right_request():
    seen = {}

    def transport(url, headers):
        seen["url"], seen["headers"] = url, headers
        return 200, BODIES["11421186"]["1506-1512"]

    bars = history(transport).minute_candles(NIFTY_CE, START, END)
    assert "/instruments/historical/11421186/minute?from=2026-10-08+15:05:00&to=2026-10-08+15:12:00&oi=1" in seen["url"]
    assert seen["headers"]["Authorization"] == f"token key:{SECRET}" and SECRET not in seen["url"]
    by = {b.minute.strftime("%H:%M"): b for b in bars}
    assert (by["15:09"].close, by["15:09"].volume, by["15:09"].oi) == (Decimal("38.3"), 132925, 5721170)
    assert all(b.source is BarSource.KITE and isinstance(b.close, Decimal) for b in bars)


def test_index_candles_carry_no_volume_or_oi():
    bars = history(lambda u, h: (200, BODIES["256265"]["1506-1512"])).minute_candles("NSE_INDEX:1001", START, END)
    assert bars and all(b.volume is None and b.oi is None for b in bars)


def test_http_error_and_transport_error_raise_a_fetch_error_without_the_token(caplog):
    def http_error(url, headers):
        return 429, ""

    def broken(url, headers):
        raise CandleFetchError("transport error: TimeoutError")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(CandleFetchError) as e1:
            history(http_error).minute_candles(NIFTY_CE, START, END)
        with pytest.raises(CandleFetchError) as e2:
            history(broken).minute_candles(NIFTY_CE, START, END)
    assert SECRET not in str(e1.value) and SECRET not in str(e2.value)
    assert SECRET not in " ".join(r.getMessage() for r in caplog.records)


def test_malformed_body_is_refused_and_an_unknown_instrument_is_an_error():
    with pytest.raises(CandleError):
        history(lambda u, h: (200, "<html>")).minute_candles(NIFTY_CE, START, END)
    with pytest.raises(CandleFetchError):
        history(lambda u, h: (200, "{}")).minute_candles("NSE_FO:1", START, END)
