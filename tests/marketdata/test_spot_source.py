"""REQ-155 AC-5 / F-76: the one spot resolver, every answer state of every source, and scenarios ADJ-24a / ADJ-24b."""
from __future__ import annotations

import datetime
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from ofo.marketdata.health import HealthThresholds
from ofo.marketdata.kite_provider import SOURCE
from ofo.marketdata.quote import NormalizedQuote
from ofo.marketdata.spot_source import (
    REASON_FUTURE,
    REASON_NO_PRICE,
    REASON_NOT_FINITE,
    REASON_STALE,
    SOURCE_FEED,
    SOURCE_LAST_CLOSE,
    SOURCE_ORDER,
    SOURCE_REST,
    SPOT_NOT_AVAILABLE,
    SourceReading,
    SourceState,
    feed_reading,
    resolve_spot,
)
from ofo.rules.inputs import DataHealth
from ofo.settings import calc, defaults
from ofo.timeutil import IST

WINDOWS = calc.feed_windows(defaults())  # the registry's windows, passed explicitly (REQ-167 AC-4)
FEED_STALE = WINDOWS.stale

SCENARIOS = Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios"
NOW = datetime.datetime(2026, 10, 30, 11, 0, 0, tzinfo=IST)
CLOSE_AT = datetime.datetime(2026, 10, 29, 15, 30, tzinfo=IST)
S = SourceState


def fresh_feed(value: str = "23100", age: datetime.timedelta = datetime.timedelta(seconds=1)) -> SourceReading:
    return SourceReading(S.STATED, Decimal(value), NOW - age)


def rest(value: str | None = "23090") -> SourceReading:
    return SourceReading(S.STATED, None if value is None else Decimal(value), NOW)


def close(value: str = "23050") -> SourceReading:
    return SourceReading(S.STATED, Decimal(value), CLOSE_AT)


def test_fresh_feed_wins_and_is_labelled() -> None:
    a = resolve_spot(fresh_feed(), rest(), close(), now=NOW, windows=WINDOWS)
    assert (a.value, a.source, a.available) == (Decimal("23100"), SOURCE_FEED, True)
    assert a.at == NOW - datetime.timedelta(seconds=1) and a.reasons == ()


def test_feed_at_exactly_the_limit_is_fresh_and_one_second_past_uses_rest() -> None:
    assert resolve_spot(fresh_feed(age=FEED_STALE), rest(), close(), now=NOW, windows=WINDOWS).source == SOURCE_FEED
    late = fresh_feed(age=FEED_STALE + datetime.timedelta(seconds=1))
    a = resolve_spot(late, rest(), close(), now=NOW, windows=WINDOWS)
    assert (a.source, a.value) == (SOURCE_REST, Decimal("23090"))
    assert a.reasons == ((SOURCE_FEED, REASON_STALE),)  # the answer says why the feed was not used


@pytest.mark.parametrize("feed", [
    None, SourceReading(S.ABSENT), SourceReading(S.NOT_FOUND), SourceReading(S.FAILED), SourceReading(S.EMPTY),
    SourceReading(S.STATED, Decimal("0"), NOW), SourceReading(S.STATED, None, NOW),
    SourceReading(S.STATED, Decimal("23100"), None), SourceReading(S.STATED, Decimal("-1"), NOW),
    SourceReading(S.STATED, Decimal("23100"), NOW + datetime.timedelta(seconds=5)),  # a future tick is not fresh
])
def test_every_unusable_feed_state_falls_to_rest(feed: SourceReading | None) -> None:
    a = resolve_spot(feed, rest(), close(), now=NOW, windows=WINDOWS)
    assert (a.source, a.value) == (SOURCE_REST, Decimal("23090"))
    assert a.reasons[0][0] == SOURCE_FEED


@pytest.mark.parametrize("answer", [
    None, SourceReading(S.ABSENT), SourceReading(S.NOT_FOUND), SourceReading(S.FAILED), SourceReading(S.EMPTY),
    SourceReading(S.STATED, None, NOW),                # 200 with no last_price: empty, not 0
    SourceReading(S.STATED, Decimal("0"), NOW),        # an exchange 0 is "no trade", not a price
])
def test_every_unusable_rest_state_falls_to_last_close_labelled_with_its_date(answer: SourceReading | None) -> None:
    a = resolve_spot(None, answer, close(), now=NOW, windows=WINDOWS)
    assert (a.source, a.value, a.at) == (SOURCE_LAST_CLOSE, Decimal("23050"), CLOSE_AT)
    assert [n for n, _ in a.reasons] == [SOURCE_FEED, SOURCE_REST]  # both better sources are named as skipped


def test_rest_200_without_last_price_is_never_zero() -> None:
    a = resolve_spot(None, rest(None), None, now=NOW, windows=WINDOWS)
    assert a.value is None and dict(a.reasons)[SOURCE_REST] == REASON_NO_PRICE


@pytest.mark.parametrize("last", [None, SourceReading(S.ABSENT), SourceReading(S.NOT_FOUND), SourceReading(S.FAILED),
                                  SourceReading(S.EMPTY), SourceReading(S.STATED, Decimal("0"), CLOSE_AT)])
def test_nothing_usable_gives_no_value_and_three_reasons(last: SourceReading | None) -> None:
    a = resolve_spot(None, SourceReading(S.FAILED), last, now=NOW, windows=WINDOWS)
    assert (a.value, a.source, a.at, a.available) == (None, None, None, False)
    assert [n for n, _ in a.reasons] == [SOURCE_FEED, SOURCE_REST, SOURCE_LAST_CLOSE]
    assert dict(a.reasons)[SOURCE_REST] == "failed"


def test_naive_now_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_spot(None, None, None, now=datetime.datetime(2026, 10, 30, 11, 0),  # noqa: DTZ001 - the naive input is the test
                     windows=WINDOWS)


def _scenario(name: str) -> tuple[dict, SourceReading, SourceReading, SourceReading, datetime.datetime]:
    d = json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))
    now = datetime.datetime.fromisoformat(d["clock"]["ist"])
    st, spot = d["data_state"], Decimal(d["market"]["spot"])
    feed = fresh_feed(str(spot)) if st["feed"] == "ok" else SourceReading(S.ABSENT)  # "missing" = no tick held
    rest_r = {"ok": SourceReading(S.STATED, spot, now), "failed": SourceReading(S.FAILED)}[st["rest"]]
    return d, feed, rest_r, SourceReading(S.ABSENT), now


def test_adj_24a_feed_missing_rest_used() -> None:
    d, feed, rest_r, last, now = _scenario("ADJ-24a")
    a = resolve_spot(feed, rest_r, last, now=now, windows=WINDOWS)
    assert d["data_state"]["spot_source"] == "rest" and a.source == SOURCE_REST
    assert a.value == Decimal(d["market"]["spot"]) and a.at == now
    assert d["expected"]["suggest"] is True and a.available


def test_adj_24b_every_source_failed_spot_not_available() -> None:
    d, feed, rest_r, last, now = _scenario("ADJ-24b")
    a = resolve_spot(feed, rest_r, last, now=now, windows=WINDOWS)
    assert d["data_state"]["spot_source"] == "none" and a.value is None and SPOT_NOT_AVAILABLE == "spot_not_available"
    assert len(a.reasons) == len(SOURCE_ORDER)
    assert d["expected"]["suggest"] is False
    assert d["expected"]["approaches"]["withheld"].lower() == "no adjustment opportunity checked: spot not available"


@pytest.mark.parametrize("bad", ["NaN", "sNaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("slot", [0, 1, 2], ids=["feed", "rest", "last_close"])
def test_a_non_finite_value_is_a_reason_never_a_spot_never_an_exception(slot: int, bad: str) -> None:
    readings = [SourceReading(S.STATED, Decimal(bad), NOW - datetime.timedelta(seconds=1)), None, None]
    readings = [readings[0] if i == slot else SourceReading(S.ABSENT) for i in range(3)]
    a = resolve_spot(*readings, now=NOW, windows=WINDOWS)
    assert a.value is None and a.reasons[slot] == (SOURCE_ORDER[slot], REASON_NOT_FINITE)


@pytest.mark.parametrize("slot", [1, 2], ids=["rest", "last_close"])
def test_a_future_dated_rest_quote_or_last_close_is_refused_like_the_feed(slot: int) -> None:
    future = SourceReading(S.STATED, Decimal("23090"), NOW + datetime.timedelta(seconds=5))
    readings = [future if i == slot else SourceReading(S.ABSENT) for i in range(3)]
    a = resolve_spot(*readings, now=NOW, windows=WINDOWS)
    assert a.value is None and a.reasons[slot] == (SOURCE_ORDER[slot], REASON_FUTURE)


# GC-IC1 fix: one shared skew window (the health module's clock_skew_tolerance) for every stated source.
def _td(**kw: float) -> datetime.timedelta:
    return datetime.timedelta(**kw)


def _only(slot: int, reading: SourceReading) -> list[SourceReading]:
    return [reading if i == slot else SourceReading(S.ABSENT) for i in range(3)]


@pytest.mark.parametrize("slot", [0, 1, 2], ids=["feed", "rest", "last_close"])
def test_a_reading_1s_after_the_callers_clock_resolves(slot: int) -> None:
    r = SourceReading(S.STATED, Decimal("23658.75"), NOW + _td(seconds=1))
    a = resolve_spot(*_only(slot, r), now=NOW, windows=WINDOWS)
    assert a.value == Decimal("23658.75") and a.source == SOURCE_ORDER[slot]


@pytest.mark.parametrize("slot", [0, 1, 2], ids=["feed", "rest", "last_close"])
def test_a_reading_exactly_at_the_skew_limit_resolves_and_beyond_is_refused(slot: int) -> None:
    skew = HealthThresholds().clock_skew_tolerance
    assert skew == _td(seconds=2)  # one constant, shared with the Execute gate (PR #427)
    ok = SourceReading(S.STATED, Decimal("23100"), NOW + skew)
    assert resolve_spot(*_only(slot, ok), now=NOW, windows=WINDOWS).available
    for ahead in (_td(seconds=2.5), _td(seconds=2, microseconds=1)):
        bad = SourceReading(S.STATED, Decimal("23100"), NOW + ahead)
        a = resolve_spot(*_only(slot, bad), now=NOW, windows=WINDOWS)
        assert a.value is None and a.reasons[slot] == (SOURCE_ORDER[slot], REASON_FUTURE)


@pytest.mark.parametrize("slot", [0, 1, 2], ids=["feed", "rest", "last_close"])
def test_a_reading_5h30_ahead_the_time_zone_error_shape_is_refused(slot: int) -> None:
    bad = SourceReading(S.STATED, Decimal("23100"), NOW + _td(hours=5, minutes=30))
    a = resolve_spot(*_only(slot, bad), now=NOW, windows=WINDOWS)
    assert a.value is None and a.reasons[slot] == (SOURCE_ORDER[slot], REASON_FUTURE)


def test_the_stale_rule_still_applies_to_old_feed_readings_and_a_skewed_one_is_fresh() -> None:
    old = SourceReading(S.STATED, Decimal("23100"), NOW - FEED_STALE - _td(seconds=1))
    a = resolve_spot(old, None, None, now=NOW, windows=WINDOWS)
    assert a.reasons[0] == (SOURCE_FEED, REASON_STALE)
    ahead = SourceReading(S.STATED, Decimal("23100"), NOW + _td(seconds=1.5))
    assert resolve_spot(ahead, None, None, now=NOW, windows=WINDOWS).source == SOURCE_FEED


@pytest.mark.parametrize("slot", [0, 1, 2], ids=["feed", "rest", "last_close"])
def test_naive_time_and_no_time_still_refused_with_skew(slot: int) -> None:
    for at in (None, (NOW + _td(seconds=1)).replace(tzinfo=None)):
        a = resolve_spot(*_only(slot, SourceReading(S.STATED, Decimal("1"), at)), now=NOW, windows=WINDOWS)
        assert a.value is None and a.reasons[slot][1] == "no_time"


# ---- #639 item 1: ONE feed reading rule for the screen and the worker (connection-aware, never last-change age) ----
def _index_quote(at: datetime.datetime, health=None):
    return NormalizedQuote(
        instrument_id="NSE_INDEX:256265", underlying="NIFTY", exchange="NSE", segment="NSE_INDEX", instrument_type=None,
        expiry=None, strike=None, ltp=Decimal("23420.00"), bid=None, ask=None, volume=None, oi=None, oi_change=None,
        iv=None, delta=None, gamma=None, theta=None, vega=None, timestamp=at, source=SOURCE,
        health=health or DataHealth.AVAILABLE)


QUIET = datetime.timedelta(seconds=10)  # a quiet index: last tick 10 s ago, longer than the 3 s feed window


def test_feed_reading_quiet_index_on_a_live_feed_is_fresh():
    reading = feed_reading(_index_quote(NOW - QUIET), NOW, feed_live=True)
    assert reading == SourceReading(S.STATED, Decimal("23420.00"), NOW)
    answer = resolve_spot(reading, None, None, now=NOW, windows=WINDOWS)
    assert (answer.value, answer.source) == (Decimal("23420.00"), SOURCE_FEED)


@pytest.mark.parametrize("why", ["feed_stale_or_disconnected_or_closed", "quote_stale", "no_tick_today"])
def test_feed_reading_not_live_keeps_the_last_change_so_the_window_refuses_it(why):
    at = NOW - QUIET
    live, health = True, DataHealth.AVAILABLE
    if why == "feed_stale_or_disconnected_or_closed":
        live = False
    elif why == "quote_stale":
        health = DataHealth.STALE
    else:
        at = NOW - datetime.timedelta(days=1)  # yesterday's last tick, no tick yet today
    reading = feed_reading(_index_quote(at, health), NOW, feed_live=live)
    assert reading == SourceReading(S.STATED, Decimal("23420.00"), at)
    assert resolve_spot(reading, None, None, now=NOW, windows=WINDOWS).reasons == ((SOURCE_FEED, REASON_STALE),
                                                                                   (SOURCE_REST, "absent"),
                                                                                   (SOURCE_LAST_CLOSE, "absent"))


def test_feed_reading_rollover_day_is_ist_not_utc():
    """Attack 2: 00:01 IST is still the previous UTC day; a tick at 23:59 IST the night before is NOT today."""
    now = datetime.datetime(2026, 10, 30, 0, 1, tzinfo=IST)
    before_midnight = datetime.datetime(2026, 10, 29, 23, 59, tzinfo=IST)
    assert feed_reading(_index_quote(before_midnight), now, feed_live=True).at == before_midnight
    after_utc_midnight = datetime.datetime(2026, 10, 30, 5, 29, tzinfo=IST)
    later = datetime.datetime(2026, 10, 30, 5, 31, tzinfo=IST)
    assert feed_reading(_index_quote(after_utc_midnight), later, feed_live=True).at == later


def test_feed_reading_absent_and_future():
    assert feed_reading(None, NOW, feed_live=True) == SourceReading(S.ABSENT)
    ahead = NOW + datetime.timedelta(minutes=1)
    reading = feed_reading(_index_quote(ahead), NOW, feed_live=True)
    assert reading.at == ahead
    assert resolve_spot(reading, None, None, now=NOW, windows=WINDOWS).reasons[0] == (SOURCE_FEED, REASON_FUTURE)
