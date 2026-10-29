"""GC-TP 5a (REQ-109 AC-7): Kite's DAY candle -> an index's official close. Bodies are written by hand in Kite's
documented day-candle shape (status success, data.candles = [[date-time +0530, open, high, low, close, volume]])."""
import datetime
import pathlib
from decimal import Decimal

import pytest
from ofo.history.candles import CandleError
from ofo.instruments.parser import parse_instruments_csv
from ofo_app.kite_history import CandleFetchError, KiteHistory

ROOT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"
LISTED = list(parse_instruments_csv(ROOT / "kite_ws" / "instruments-2026-10-08-subscribed.csv"))
SECRET = "tok-SECRET-123"  # noqa: S105
SENSEX_TOKEN = "265"  # noqa: S105 - the catalogue's Kite instrument token for the BSE SENSEX index row (fixture CSV)
EXPIRY = datetime.date(2026, 10, 29)


def history(transport):
    return KiteHistory(LISTED, api_key="key", access_token=SECRET, transport=transport)


def day_body(*rows: str) -> str:
    return '{"status":"success","data":{"candles":[' + ",".join(rows) + "]}}"


def day_row(date_text: str = "2026-10-29", close: str = "83211.07") -> str:
    return f'["{date_text}T00:00:00+0530",83050.12,83390.5,82980.0,{close},0]'


def day_close_of(body: str, status: int = 200):
    seen = {}

    def transport(url, headers):
        seen["url"], seen["headers"] = url, headers
        return status, body
    return history(transport).day_close(SENSEX_TOKEN, EXPIRY), seen


def test_one_day_candle_gives_its_close_as_an_exact_decimal_and_the_right_request():
    close, seen = day_close_of(day_body(day_row()))
    assert close == Decimal("83211.07") and isinstance(close, Decimal)
    assert seen["url"].endswith("/instruments/historical/265/day?from=2026-10-29&to=2026-10-29")
    assert seen["headers"]["Authorization"] == f"token key:{SECRET}" and SECRET not in seen["url"]


def test_close_keeps_digits_a_float_would_lose():
    close, _ = day_close_of(day_body(day_row(close="83211.0700000000000000001")))
    assert close == Decimal("83211.0700000000000000001")  # float(...) would round this to 83211.07


def test_a_whole_number_close_is_a_decimal_and_a_seven_field_row_is_read():
    close, _ = day_close_of(day_body('["2026-10-29T00:00:00+0530",1,2,0,83000,0,0]'))
    assert close == Decimal(83000) and isinstance(close, Decimal)


def test_no_candle_is_none_not_an_error():
    assert day_close_of(day_body())[0] is None


@pytest.mark.parametrize("status", [401, 429, 500])
def test_a_non_200_status_is_a_fetch_error_without_the_token(status):
    with pytest.raises(CandleFetchError) as err:
        day_close_of("", status)
    assert SECRET not in str(err.value)


def test_a_transport_error_is_a_fetch_error():
    def broken(url, headers):
        raise CandleFetchError("transport error: TimeoutError")
    with pytest.raises(CandleFetchError):
        history(broken).day_close(SENSEX_TOKEN, EXPIRY)


@pytest.mark.parametrize("body", [
    "not json", "[]", '{"status":"error","data":null}', '{"status":"success","data":{}}',
    '{"status":"success","data":{"candles":"x"}}', day_body("[1,2,3]"), day_body('["bad-date",1,2,0,3,0]'),
    day_body(day_row(close='"83211.07"')), day_body(day_row(close="null")), day_body(day_row(close="NaN")),
    day_body(day_row(close="0")), day_body(day_row(close="true")),
    day_body(day_row(), day_row()),  # two candles for one day is ambiguous
])
def test_a_malformed_or_ambiguous_body_is_a_candle_error(body):
    with pytest.raises(CandleError):
        day_close_of(body)


def test_a_candle_for_another_date_is_a_candle_error():
    with pytest.raises(CandleError):
        day_close_of(day_body(day_row("2026-10-28")))


def test_a_token_that_is_not_digits_is_refused_before_any_request():
    def never(url, headers):
        raise AssertionError("must not be called")
    with pytest.raises(CandleFetchError):
        history(never).day_close("265/../orders", EXPIRY)
