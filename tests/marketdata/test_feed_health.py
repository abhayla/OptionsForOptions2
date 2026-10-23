"""REQ-114 AC-7: outside market hours (ADR-119 calendar) silence is expected: "Market closed. Prices are from
<time>." (ADR-177) and at most one reconnect per 5 minutes. A weekend and the 2026-10-20 Dussehra holiday (the
legacy list had it open, F-54)."""
# ruff: noqa: S311, PLR2004  (a seeded test random source, never a secret; REQ-114 numbers are the point of the asserts)
from __future__ import annotations

import datetime
import pathlib
import random
import re

import pytest
from ofo.market_calendar import is_market_open
from ofo.marketdata.disconnect import market_closed_message
from ofo.marketdata.feed_health import FEED_HEALTHY, FEED_MARKET_CLOSED, FEED_WAITING, FeedState
from ofo.marketdata.reconnect_policy import CLOSED_RETRY_EVERY, reconnect_wait

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
OPEN_THURSDAY = datetime.datetime(2026, 10, 8, 10, 0, tzinfo=IST)
SATURDAY = datetime.datetime(2026, 10, 10, 11, 0, tzinfo=IST)
DUSSEHRA = datetime.datetime(2026, 10, 20, 11, 0, tzinfo=IST)  # a Tuesday, NSE F&O holiday
AFTER_CLOSE = datetime.datetime(2026, 10, 8, 15, 30, tzinfo=IST)


@pytest.mark.parametrize(("when", "expected"), [(OPEN_THURSDAY, True), (SATURDAY, False), (DUSSEHRA, False),
                                                (AFTER_CLOSE, False)])
def test_the_calendar_answers_for_a_weekday_a_weekend_a_holiday_and_the_close(when, expected):
    assert is_market_open(when) is expected


@pytest.mark.parametrize("when", [SATURDAY, DUSSEHRA, AFTER_CLOSE])
def test_a_closed_market_waits_at_least_5_minutes_between_connects(when):
    rng = random.Random(3)
    waits = [reconnect_wait(nominal, rng, market_open=is_market_open(when)) for nominal in (1, 2, 4, 8, 16, 30)]
    assert min(waits) >= CLOSED_RETRY_EVERY == 300


def test_an_open_market_keeps_the_short_backoff():
    rng = random.Random(3)
    assert reconnect_wait(1, rng, market_open=is_market_open(OPEN_THURSDAY)) <= 1


def _feed_with_a_price_at(when: datetime.datetime) -> FeedState:
    feed = FeedState()
    feed.on_connected(when)
    feed.on_data(when)
    return feed


def test_the_feed_reads_market_closed_on_a_weekend_and_on_the_holiday_not_waiting_or_reconnecting():
    for when in (SATURDAY, DUSSEHRA):
        feed = _feed_with_a_price_at(AFTER_CLOSE)
        assert feed.phase(when, is_market_open(when)) == FEED_MARKET_CLOSED
        feed.on_disconnected(when)  # even a dropped connection is "market closed", not "reconnecting"
        assert feed.phase(when, is_market_open(when)) == FEED_MARKET_CLOSED


def test_an_open_market_keeps_its_phases_and_the_default_is_open():
    feed = _feed_with_a_price_at(OPEN_THURSDAY)
    assert feed.phase(OPEN_THURSDAY) == FEED_HEALTHY == feed.phase(OPEN_THURSDAY, True)
    assert feed.phase(OPEN_THURSDAY + datetime.timedelta(seconds=30), True) == FEED_WAITING


def test_a_session_ended_by_zerodha_still_says_so_when_the_market_is_closed():
    feed = _feed_with_a_price_at(OPEN_THURSDAY)
    feed.on_session_ended(OPEN_THURSDAY)
    assert feed.phase(SATURDAY, False) != FEED_MARKET_CLOSED


def test_the_last_price_time_is_the_last_price_frame_not_a_heartbeat():
    feed = _feed_with_a_price_at(AFTER_CLOSE)
    feed.on_activity(SATURDAY)
    assert feed.last_price_at == AFTER_CLOSE


def test_the_closed_text_is_the_catalogue_template_with_the_last_price_time():
    assert market_closed_message(AFTER_CLOSE) == "Market closed. Prices are from 03:30:00 PM."


def test_adr_177_one_wording_in_backend_and_frontend_and_the_old_wording_nowhere_a_user_sees_it():
    """AC-7 / ADR-177: the backend message and the frontend's marketClosedText are the same characters; the old
    "Market closed - last price" wording is in no backend, frontend source, or test tree."""
    root = pathlib.Path(__file__).resolve().parents[2]
    front = (root / "frontend" / "src" / "lib" / "sharedStateText.js").read_text(encoding="utf-8")
    prefix = re.search(r"MARKET_CLOSED_PREFIX = '([^']+)'", front)
    assert prefix is not None and prefix.group(1) == "Market closed. Prices are from "
    assert market_closed_message(AFTER_CLOSE) == f"{prefix.group(1)}03:30:00 PM."
    needle = "Market closed - last price"
    trees = [root / "backend", root / "frontend" / "src", root / "frontend" / "e2e", root / "frontend" / "tests",
             root / "tests_app", root / "tests"]
    me = pathlib.Path(__file__).resolve()
    hits = [str(f) for t in trees for f in t.rglob("*") if f.is_file() and f.suffix in {".py", ".js", ".ts", ".vue"}
            and f != me and needle in f.read_text(encoding="utf-8", errors="replace")]
    assert hits == []
