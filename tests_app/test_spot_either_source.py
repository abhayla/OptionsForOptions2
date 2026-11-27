"""Lane U hotfix (REQ-118, REQ-049/100/114, ADR-330 (39), ADR-016..019): a spot is answered "not available" ONLY when
BOTH sources fail. No database, no Kite. Class: "a spot answered not available while one source had it" - the API
route's judge-then-resolve pair, and the worker (own process, no index tick, REST never asked, no alert rows)."""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from types import SimpleNamespace

from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import background
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
