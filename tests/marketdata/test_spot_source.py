"""REQ-155 AC-5 / F-76: the one spot resolver, every answer state of every source, and scenarios ADJ-24a / ADJ-24b."""
from __future__ import annotations

import datetime
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from ofo.marketdata.feed_health import FEED_STALE
from ofo.marketdata.spot_source import (
    REASON_NO_PRICE,
    REASON_STALE,
    SOURCE_FEED,
    SOURCE_LAST_CLOSE,
    SOURCE_ORDER,
    SOURCE_REST,
    SPOT_NOT_AVAILABLE,
    SourceReading,
    SourceState,
    resolve_spot,
)
from ofo.timeutil import IST

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
    a = resolve_spot(fresh_feed(), rest(), close(), now=NOW)
    assert (a.value, a.source, a.available) == (Decimal("23100"), SOURCE_FEED, True)
    assert a.at == NOW - datetime.timedelta(seconds=1) and a.reasons == ()


def test_feed_at_exactly_the_limit_is_fresh_and_one_second_past_uses_rest() -> None:
    assert resolve_spot(fresh_feed(age=FEED_STALE), rest(), close(), now=NOW).source == SOURCE_FEED
    a = resolve_spot(fresh_feed(age=FEED_STALE + datetime.timedelta(seconds=1)), rest(), close(), now=NOW)
    assert (a.source, a.value) == (SOURCE_REST, Decimal("23090"))
    assert a.reasons == ((SOURCE_FEED, REASON_STALE),)  # the answer says why the feed was not used


@pytest.mark.parametrize("feed", [
    None, SourceReading(S.ABSENT), SourceReading(S.NOT_FOUND), SourceReading(S.FAILED), SourceReading(S.EMPTY),
    SourceReading(S.STATED, Decimal("0"), NOW), SourceReading(S.STATED, None, NOW),
    SourceReading(S.STATED, Decimal("23100"), None), SourceReading(S.STATED, Decimal("-1"), NOW),
    SourceReading(S.STATED, Decimal("23100"), NOW + datetime.timedelta(seconds=5)),  # a future tick is not fresh
])
def test_every_unusable_feed_state_falls_to_rest(feed: SourceReading | None) -> None:
    a = resolve_spot(feed, rest(), close(), now=NOW)
    assert (a.source, a.value) == (SOURCE_REST, Decimal("23090"))
    assert a.reasons[0][0] == SOURCE_FEED


@pytest.mark.parametrize("answer", [
    None, SourceReading(S.ABSENT), SourceReading(S.NOT_FOUND), SourceReading(S.FAILED), SourceReading(S.EMPTY),
    SourceReading(S.STATED, None, NOW),                # 200 with no last_price: empty, not 0
    SourceReading(S.STATED, Decimal("0"), NOW),        # an exchange 0 is "no trade", not a price
])
def test_every_unusable_rest_state_falls_to_last_close_labelled_with_its_date(answer: SourceReading | None) -> None:
    a = resolve_spot(None, answer, close(), now=NOW)
    assert (a.source, a.value, a.at) == (SOURCE_LAST_CLOSE, Decimal("23050"), CLOSE_AT)
    assert [n for n, _ in a.reasons] == [SOURCE_FEED, SOURCE_REST]  # both better sources are named as skipped


def test_rest_200_without_last_price_is_never_zero() -> None:
    a = resolve_spot(None, rest(None), None, now=NOW)
    assert a.value is None and dict(a.reasons)[SOURCE_REST] == REASON_NO_PRICE


@pytest.mark.parametrize("last", [None, SourceReading(S.ABSENT), SourceReading(S.NOT_FOUND), SourceReading(S.FAILED),
                                  SourceReading(S.EMPTY), SourceReading(S.STATED, Decimal("0"), CLOSE_AT)])
def test_nothing_usable_gives_no_value_and_three_reasons(last: SourceReading | None) -> None:
    a = resolve_spot(None, SourceReading(S.FAILED), last, now=NOW)
    assert (a.value, a.source, a.at, a.available) == (None, None, None, False)
    assert [n for n, _ in a.reasons] == [SOURCE_FEED, SOURCE_REST, SOURCE_LAST_CLOSE]
    assert dict(a.reasons)[SOURCE_REST] == "failed"


def test_naive_now_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_spot(None, None, None, now=datetime.datetime(2026, 10, 30, 11, 0))  # noqa: DTZ001 - the naive input is the test


def _scenario(name: str) -> tuple[dict, SourceReading, SourceReading, SourceReading, datetime.datetime]:
    d = json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))
    now = datetime.datetime.fromisoformat(d["clock"]["ist"])
    st, spot = d["data_state"], Decimal(d["market"]["spot"])
    feed = fresh_feed(str(spot)) if st["feed"] == "ok" else SourceReading(S.ABSENT)  # "missing" = no tick held
    rest_r = {"ok": SourceReading(S.STATED, spot, now), "failed": SourceReading(S.FAILED)}[st["rest"]]
    return d, feed, rest_r, SourceReading(S.ABSENT), now


def test_adj_24a_feed_missing_rest_used() -> None:
    d, feed, rest_r, last, now = _scenario("ADJ-24a")
    a = resolve_spot(feed, rest_r, last, now=now)
    assert d["data_state"]["spot_source"] == "rest" and a.source == SOURCE_REST
    assert a.value == Decimal(d["market"]["spot"]) and a.at == now
    assert d["expected"]["suggest"] is True and a.available


def test_adj_24b_every_source_failed_spot_not_available() -> None:
    d, feed, rest_r, last, now = _scenario("ADJ-24b")
    a = resolve_spot(feed, rest_r, last, now=now)
    assert d["data_state"]["spot_source"] == "none" and a.value is None and SPOT_NOT_AVAILABLE == "spot_not_available"
    assert len(a.reasons) == len(SOURCE_ORDER)
    assert d["expected"]["suggest"] is False
    assert d["expected"]["approaches"]["withheld"].lower() == "no suggestion: spot not available"
