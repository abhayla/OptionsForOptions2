"""Lane U hotfix (REQ-118, REQ-049/100/114, ADR-330 (39), ADR-016..019): a spot is answered "not available" ONLY when
BOTH sources fail. No database, no Kite. Class: "a spot answered not available while one source had it" - the API
route's judge-then-resolve pair, and the worker (own process, no index tick, REST never asked, no alert rows)."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
from decimal import Decimal
from types import SimpleNamespace

from ofo.marketdata.shared_reading import SharedReading
from ofo.marketdata.spot_source import REASON_NO_TIME, REASON_REST_STALE, SourceReading, SourceState, rest_problem
from ofo.rules.inputs import DataHealth
from ofo.settings import calc as settings_calc
from ofo.settings import defaults as settings_defaults
from ofo_app import background, live_market
from ofo_app.routes import outcome
from test_background_cycle import Calls, Prov, _watched, _worker, scn  # noqa: F401 - the fixture is used by name

SPOT = Decimal("23001")


def _fresh():
    return SourceReading(SourceState.STATED, Decimal("23000"), outcome.server_now())


class _Reader:
    def __init__(self, reading=None, boom=None):
        self.calls, self._reading, self._boom = 0, reading, boom

    async def __call__(self, _underlying):
        self.calls += 1
        if self._boom is not None:
            raise self._boom
        return self._reading if self._reading is not None else SourceReading(SourceState.STATED, SPOT,
                                                                             outcome.server_now())


def _market(*feeds):
    """feed_at answers the given readings in turn (the last one repeats): a judge that sees a feed, then none."""
    seq = list(feeds)

    def feed_at(_judged):
        return seq.pop(0) if len(seq) > 1 else seq[0]
    return SimpleNamespace(feed_at=feed_at, last_close=None)


async def test_fresh_tick_makes_zero_rest_calls_and_answers_the_feed():
    reader = _Reader()
    answer = await outcome.index_spot_of(_market(_fresh()), reader, "NIFTY", None)
    assert answer.available and answer.source == "feed" and reader.calls == 0


async def test_judge_says_feed_but_the_resolve_finds_none_rest_is_used_and_the_spot_returned():
    """The old pair: ``rest_spot_if_needed`` predicted the feed (REST skipped), ``judge_spot`` then found no usable
    feed value -> "not available". One answer now: the first judgment is the answer, or REST is asked."""
    reader = _Reader()
    answer = await outcome.index_spot_of(_market(_fresh(), None), reader, "NIFTY", None)
    assert answer.available


async def test_no_feed_rest_gives_the_spot():
    reader = _Reader()
    answer = await outcome.index_spot_of(_market(None), reader, "NIFTY", None)
    assert answer.value == SPOT and answer.source == "rest_quote" and reader.calls == 1


async def test_both_fail_not_available_with_one_log_line_naming_both_reasons(caplog):
    reader = _Reader(SourceReading(SourceState.FAILED))
    with caplog.at_level(logging.WARNING):
        answer = await outcome.index_spot_of(_market(None), reader, "NIFTY", None)
    assert not answer.available
    lines = [r.getMessage() for r in caplog.records if "index spot not available" in r.getMessage()]
    assert len(lines) == 1 and "feed" in lines[0] and "REST failed" in lines[0], lines


async def test_a_raising_rest_reader_is_a_failed_rest_never_an_error(caplog):
    reader = _Reader(boom=RuntimeError("boom"))
    with caplog.at_level(logging.WARNING):
        answer = await outcome.index_spot_of(_market(None), reader, "NIFTY", None)
    assert not answer.available and reader.calls == 1
    assert any("REST" in r.getMessage() and "index spot not available" in r.getMessage() for r in caplog.records)


# ---- the worker: its own process, no index tick in its book ------------------------------------------------------

async def test_worker_without_an_index_tick_reads_the_shared_rest_spot_and_computes(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.spot = None  # the worker's book holds no tick of the index (LEG_MISSING before)
    reader = _Reader(SourceReading(SourceState.STATED, Decimal("23420"), scn.clock_at))
    w = _worker(prov, _watched(scn), now, calls, rest_spot=reader)
    await w.cycle()
    assert [s for s, _ in calls.states] == [100], w.paused_reason
    assert calls.states[0][1].spot == Decimal("23420") and reader.calls == 1


async def test_worker_with_a_fresh_index_tick_makes_zero_rest_calls(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    reader = _Reader()
    w = _worker(prov, _watched(scn), now, calls, rest_spot=reader)
    await w.cycle()
    assert [s for s, _ in calls.states] == [100] and reader.calls == 0


async def test_worker_rest_failure_pauses_with_the_named_state_and_logs_both_reasons(scn, caplog):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.spot = None
    reader = _Reader(SourceReading(SourceState.FAILED))
    w = _worker(prov, _watched(scn), now, calls, rest_spot=reader)
    with caplog.at_level(logging.WARNING):
        await w.cycle()
    assert calls.states == [] and w.paused_reason[100] is background.PriceState.LEG_MISSING
    assert any("index spot not available" in r.getMessage() for r in caplog.records)


def test_the_spot_door_is_one_function_in_every_process():
    """No second copy: the worker's REST read and the routes' share ``outcome``'s one resolver."""
    assert hasattr(outcome, "index_spot_of") and not hasattr(outcome, "rest_spot_if_needed")
    assert datetime  # keep the import used by the module docstring contract


# ---- review round 1 (Opus attacks A1-A9): the REST reading obeys the ONE index age rule ---------------------------

MIN = datetime.timedelta(minutes=1)


def _rest(scn_, age: datetime.timedelta | None):
    """A REST reading ``age`` older than the worker's clock (None: no time at all)."""
    return SourceReading(SourceState.STATED, Decimal("23430"), None if age is None else scn_.clock_at - age)


async def _one_cycle(scn, rest, spot="none", drop=False, n=1):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    if spot is None or spot == "none":
        prov.spot = None
    else:
        prov.spot = spot(prov.spot)
    if drop:
        prov.drop = {prov.leg_id("23500", "CE")}
    reader = _Reader(rest)
    w = _worker(prov, _watched(scn, n), now, calls, rest_spot=reader)
    await w.cycle()
    return w, calls, reader


async def test_a1_no_tick_and_a_10_minute_old_rest_is_not_evaluated_paused_stale_rest_stale(scn):  # noqa: F811
    w, calls, _ = await _one_cycle(scn, _rest(scn, 10 * MIN))
    assert calls.states == [] and w.paused_reason[100] is background.PriceState.STALE
    assert w.paused_why[100] == "rest_stale"


async def test_a2_a_rest_reading_with_no_time_is_not_usable(scn):  # noqa: F811
    w, calls, _ = await _one_cycle(scn, _rest(scn, None))
    assert calls.states == [] and w.paused_reason[100] is background.PriceState.LEG_MISSING


async def test_a3_a_stale_tick_is_never_replaced_by_an_older_rest_and_both_old_evaluates_nothing(scn):  # noqa: F811
    tick_at = scn.clock_at - datetime.timedelta(seconds=1)  # 11:39:59, health STALE (index age rule)
    stale = lambda q: dataclasses.replace(q, timestamp=tick_at, health=DataHealth.STALE)  # noqa: E731
    w, calls, _ = await _one_cycle(scn, _rest(scn, 5 * MIN + datetime.timedelta(seconds=1)), spot=stale)
    assert calls.states == [] and w.paused_reason[100] is background.PriceState.STALE
    w, calls, _ = await _one_cycle(scn, _rest(scn, 10 * MIN), spot=stale)
    assert calls.states == [] and w.paused_reason[100] is background.PriceState.STALE


async def test_a3b_a_newer_rest_within_the_age_limit_replaces_an_older_stale_tick(scn):  # noqa: F811
    old = lambda q: dataclasses.replace(q, timestamp=scn.clock_at - 5 * MIN, health=DataHealth.STALE)  # noqa: E731
    w, calls, _ = await _one_cycle(scn, _rest(scn, datetime.timedelta(seconds=5)), spot=old)
    assert [s for s, _ in calls.states] == [100] and calls.states[0][1].spot == Decimal("23430"), w.paused_reason


async def test_a5_an_option_leg_missing_with_the_index_fine_asks_rest_zero_times(scn):  # noqa: F811
    w, calls, reader = await _one_cycle(scn, _rest(scn, datetime.timedelta(seconds=5)),
                                        spot=lambda q: q, drop=True)
    assert reader.calls == 0 and calls.states == [] and w.paused_reason[100] is background.PriceState.LEG_MISSING


async def test_a_fresh_rest_5_seconds_old_with_no_tick_is_evaluated(scn):  # noqa: F811
    w, calls, reader = await _one_cycle(scn, _rest(scn, datetime.timedelta(seconds=5)))
    assert [s for s, _ in calls.states] == [100] and reader.calls == 1, w.paused_reason


async def test_a_stale_rest_is_logged_with_the_cause_and_the_reason(scn, caplog):  # noqa: F811
    with caplog.at_level(logging.WARNING):
        await _one_cycle(scn, _rest(scn, 10 * MIN))
    lines = [r.getMessage() for r in caplog.records if "index spot not available" in r.getMessage()]
    assert lines and "index quote missing" in lines[0] and "rest_stale" in lines[0], lines


async def test_a8_three_strategies_one_underlying_one_rest_call_per_cycle(scn):  # noqa: F811
    _, calls, reader = await _one_cycle(scn, _rest(scn, datetime.timedelta(seconds=5)), n=3)
    assert reader.calls == 1 and len(calls.states) == 3  # noqa: PLR2004


async def test_a_hung_rest_read_costs_one_short_deadline_per_cycle_not_nine_seconds(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.spot = None

    async def hang(_u):
        await asyncio.sleep(30)
    w = _worker(prov, _watched(scn, 3), now, calls, rest_spot=hang)
    assert w._rest_deadline == 2.0  # noqa: PLR2004
    w._rest_deadline = 0.05
    started = asyncio.get_running_loop().time()
    await w.cycle()
    assert asyncio.get_running_loop().time() - started < 1.0 and calls.states == []
    assert w.paused_reason[100] is background.PriceState.LEG_MISSING


async def test_a9_no_login_is_one_stored_login_read_per_10_seconds_not_per_strategy_per_cycle(scn, monkeypatch):  # noqa: F811
    t = [0.0]
    monkeypatch.setattr(live_market, "REST_SPOT", SharedReading(clock=lambda: t[0]))
    reads = []

    async def no_login(_owner):
        reads.append(1)

    login = background.StoredLogin(no_login, lambda: scn.clock_at)
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.spot = None
    w = _worker(prov, _watched(scn, 3), now, calls, rest_spot=background.worker_rest_spot(login))
    await w.cycle()
    await w.cycle()
    assert len(reads) == 1  # three strategies, two cycles inside 10 s
    t[0] += 10.1
    await w.cycle()
    assert len(reads) == 2  # noqa: PLR2004


# ---- the API: a stale REST is not available (A7); the pure rule -------------------------------------------------

def _ctx(at):
    return SimpleNamespace(clock=lambda: at, feed_windows=settings_calc.feed_windows(settings_defaults()))


async def test_a7_api_a_30_minute_old_rest_is_not_available_with_both_reasons_logged(scn, caplog):  # noqa: F811
    at = scn.clock_at
    reader = _Reader(SourceReading(SourceState.STATED, SPOT, at - 30 * MIN))
    with caplog.at_level(logging.WARNING):
        answer = await outcome.index_spot_of(_market(None), reader, "NIFTY", _ctx(at))
    assert not answer.available and dict(answer.reasons)["rest_quote"] == "rest_stale"
    lines = [r.getMessage() for r in caplog.records if "index spot not available" in r.getMessage()]
    assert len(lines) == 1 and "feed absent" in lines[0] and "REST rest_stale" in lines[0], lines


async def test_api_a_rest_within_the_age_limit_is_available_and_closed_market_is_not_age_checked(scn):  # noqa: F811
    at = scn.clock_at
    recent = _Reader(SourceReading(SourceState.STATED, SPOT, at - datetime.timedelta(seconds=30)))
    ok = await outcome.index_spot_of(_market(None), recent, "NIFTY", _ctx(at))
    assert ok.available and ok.source == "rest_quote"
    night = datetime.datetime(2026, 11, 6, 23, 0, tzinfo=at.tzinfo)  # market closed: last-trade time may be old
    old = _Reader(SourceReading(SourceState.STATED, SPOT, night - datetime.timedelta(hours=7)))
    closed = await outcome.index_spot_of(_market(None), old, "NIFTY", _ctx(night))
    assert closed.available and closed.source == "rest_quote"


def test_rest_problem_is_the_one_rule(scn):  # noqa: F811
    win = settings_calc.feed_windows(settings_defaults())
    at = scn.clock_at
    assert rest_problem(SourceReading(SourceState.STATED, SPOT, None), at, win) == REASON_NO_TIME
    assert rest_problem(SourceReading(SourceState.STATED, SPOT, at - 10 * MIN), at, win) == REASON_REST_STALE
    assert rest_problem(SourceReading(SourceState.STATED, SPOT, at - datetime.timedelta(seconds=59)), at, win) is None
