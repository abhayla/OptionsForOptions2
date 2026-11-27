"""Lane J2 (27 Nov), the join of Lane J (loss stop, "skipped with a reason, a plan stop raised at once") and Lane U
(the index from the feed first, Zerodha's quote second). One worker, four cases of where the index comes from, each with
a crossed plan stop: it is raised when the worker can price the trade, and when it cannot the strategy is recorded as
skipped with a reason (a log line, the pause state), never silently. No database, no Kite.
Spec basis: ADR-330 (39), (44), (47); ADR-016 to ADR-019 (fail closed)."""
from __future__ import annotations

import dataclasses
import logging
from decimal import Decimal

from ofo.adjustment import alert_gate
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import background
from ofo_app import settings_in_force as sif
from test_background_cycle import (  # noqa: F401 - the fixture is used by name
    MIN_STOP_PCT, Calls, FakeGate, Prov, _followed, _system_body, _watched, _worker, scn)
from test_spot_either_source import MIN, _Reader, _rest  # noqa: F401

STOP = "T-06"


def _stop_watched(scn_):
    """The system iron condor with its max-loss stop at the smallest percent (any loss crosses it) and a stored entry
    base, so the stop reads real numbers (as test_background_cycle._both does)."""
    body = _system_body("ic")
    body = {**body, "triggers": {**body["triggers"], STOP: {**body["triggers"][STOP], "on": True,
                                                            "weekly": [MIN_STOP_PCT] * 3,
                                                            "monthly": [MIN_STOP_PCT] * 3}}}
    w = _watched(scn_)[0]
    entry = sif.StopBase(Decimal("3000"), Decimal("1000"), scn_.clock_at, "entry")
    return dataclasses.replace(w, body=body, resolved=_followed(body),
                               tracked=dataclasses.replace(w.tracked, stop_base=entry))


async def _run(scn_, rest, feed_spot: bool):
    prov, now, calls, gate = Prov(scn_), [scn_.clock_at], Calls(), FakeGate()
    if not feed_spot:
        prov.spot = None
    reader = _Reader(rest) if rest is not None else None
    w = _worker(prov, [_stop_watched(scn_)], now, calls, gate_store=gate, rest_spot=reader)
    await w.cycle()
    return w, calls, gate


def _opened(gate):
    return [e for _sid, e in gate.events if isinstance(e, alert_gate.Opened)]


async def test_index_only_from_the_feed_the_crossed_stop_is_raised(scn):  # noqa: F811
    w, calls, gate = await _run(scn, None, feed_spot=True)
    assert [s for s, _ in calls.states] == [100], w.paused_reason
    assert any(e.rule_id == STOP for e in _opened(gate)), gate.events


async def test_index_only_from_the_quote_the_crossed_stop_is_raised(scn):  # noqa: F811
    rest = SourceReading(SourceState.STATED, Decimal("23420"), scn.clock_at)
    w, calls, gate = await _run(scn, rest, feed_spot=False)
    assert [s for s, _ in calls.states] == [100], w.paused_reason
    assert any(e.rule_id == STOP for e in _opened(gate)), gate.events


async def test_neither_source_is_skipped_with_a_visible_reason_and_raises_nothing(scn, caplog):  # noqa: F811
    with caplog.at_level(logging.INFO):
        w, calls, gate = await _run(scn, SourceReading(SourceState.FAILED), feed_spot=False)
    assert calls.states == [] and _opened(gate) == []  # not priced: nothing guessed
    assert w.paused_reason[100] is background.PriceState.LEG_MISSING  # recorded, not dropped
    lines = [r.getMessage() for r in caplog.records if "check skipped" in r.getMessage()]
    assert lines == ["background: strategy 100 check skipped: prices_leg_missing"], lines


async def test_stale_quote_is_skipped_with_both_reasons_visible_and_raises_nothing(scn, caplog):  # noqa: F811
    with caplog.at_level(logging.INFO):
        w, calls, gate = await _run(scn, _rest(scn, 10 * MIN), feed_spot=False)
    assert calls.states == [] and _opened(gate) == []
    assert w.paused_reason[100] is background.PriceState.STALE and w.paused_why[100] == "rest_stale"
    assert any("check skipped: prices_stale" in r.getMessage() for r in caplog.records)


async def test_a_skipped_strategy_with_no_tick_is_logged_not_silent(scn, caplog):  # noqa: F811
    """The second cycle with nothing ticked is the NOT_TICKED path: it names its reason too (Lane J's line)."""
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, [_stop_watched(scn)], now, calls, rest_spot=_Reader())
    await w.cycle()
    with caplog.at_level(logging.INFO):
        await w.cycle()
    assert any("check skipped" in r.getMessage() for r in caplog.records)


async def test_a_stale_reason_does_not_survive_a_later_fresh_read(scn):  # noqa: F811
    """Review F4: ``paused_why`` is set by a stale REST pause and gone once a fresh read lets the check run."""
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.spot = None
    reader = _Reader(_rest(scn, 10 * MIN))
    w = _worker(prov, [_stop_watched(scn)], now, calls, rest_spot=reader)
    await w.cycle()
    assert w.paused_why[100] == "rest_stale"
    reader._reading = SourceReading(SourceState.STATED, Decimal("23420"), now[0])
    w._rest_cycle.clear()
    await w.cycle()
    assert 100 not in w.paused_why and w.status[100] is background.MonitoringStatus.ACTIVE
    assert [s for s, _ in calls.states] == [100]


async def test_a_raising_rest_reader_pauses_with_a_reason_and_is_asked_once_per_cycle(scn, caplog):  # noqa: F811
    """Review F5: at the worker, a reader that raises is "no REST spot" (one call, paused, skipped line), never a crash."""
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.spot = None
    reader = _Reader(boom=RuntimeError("boom"))
    w = _worker(prov, _watched(scn, 2), now, calls, rest_spot=reader)
    with caplog.at_level(logging.INFO):
        await w.cycle()
    assert reader.calls == 1 and calls.states == []
    assert w.paused_reason[100] is background.PriceState.LEG_MISSING
    assert any("check skipped: prices_leg_missing" in r.getMessage() for r in caplog.records)
