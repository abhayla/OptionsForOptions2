"""REQ-114 AC-1, AC-2, AC-3: the reconnect numbers and the jitter bounds, with a FIXED random seed."""
# ruff: noqa: S311, PLR2004  (a seeded test random source, never a secret; REQ-114 numbers are the point of the asserts)
from __future__ import annotations

import datetime
import random

from ofo.marketdata.reconnect_policy import (
    BACKOFF_MAX,
    BACKOFF_START,
    CHECK_EVERY,
    CLOSED_RETRY_EVERY,
    JITTER_FRACTION,
    SILENT_AFTER,
    is_silent,
    jittered,
    next_backoff,
    next_check,
    reconnect_wait,
)

T0 = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def test_the_req114_numbers():
    assert datetime.timedelta(seconds=15) == CHECK_EVERY
    assert datetime.timedelta(seconds=60) == SILENT_AFTER
    assert (BACKOFF_START, BACKOFF_MAX, JITTER_FRACTION, CLOSED_RETRY_EVERY) == (1, 30, 0.5, 300)


def test_the_nominal_backoff_doubles_and_is_capped_at_30():
    waits, w = [], BACKOFF_START
    for _ in range(8):
        waits.append(w)
        w = next_backoff(w)
    assert waits == [1, 2, 4, 8, 16, 30, 30, 30]


def test_seeded_jitter_stays_within_0_to_50_percent_of_each_wait_and_the_cap_holds():
    """AC-3: for 5,000 seeded draws on every nominal wait, wait is in [nominal/2, nominal], never above 30."""
    rng = random.Random(20261008)
    nominal = BACKOFF_START
    for _ in range(10):
        draws = [jittered(nominal, rng) for _ in range(5000)]
        assert min(draws) >= nominal * (1 - JITTER_FRACTION) and max(draws) <= nominal <= BACKOFF_MAX
        assert len({round(d, 6) for d in draws}) > 100  # it really is random, not a constant
        nominal = next_backoff(nominal)


def test_two_users_with_different_seeds_do_not_wait_the_same_time():
    a, b = random.Random(1), random.Random(2)
    assert [jittered(4, a) for _ in range(5)] != [jittered(4, b) for _ in range(5)]


def test_silence_is_exactly_60_seconds():
    assert not is_silent(T0 + datetime.timedelta(seconds=59.9), T0)
    assert is_silent(T0 + datetime.timedelta(seconds=60), T0)


def test_the_next_check_is_within_15_seconds_and_never_after_the_60_second_mark():
    assert next_check(T0, T0) == T0 + datetime.timedelta(seconds=15)
    now = T0 + datetime.timedelta(seconds=50)
    assert next_check(now, T0) == T0 + datetime.timedelta(seconds=60)  # the 60 s mark, not now + 15
    assert next_check(T0 + datetime.timedelta(seconds=60), T0) == T0 + datetime.timedelta(seconds=75)


def test_a_closed_market_never_reconnects_faster_than_every_5_minutes():
    rng = random.Random(7)
    assert all(reconnect_wait(nominal, rng, market_open=False) >= 300 for nominal in (1, 2, 4, 30) for _ in range(50))
    assert all(reconnect_wait(30, rng, market_open=True) <= 30 for _ in range(50))
