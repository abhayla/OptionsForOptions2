"""Lane FE3 (28 Nov 2026), W-34 (the PC's round 1, build 5fc6b102, market closed, paper only): "all 9 running trades
'Monitoring paused / Health unknown / Not being watched: the worker does not list this trade.' | expected: no paused
badge while the worker is running."

Cause: ``Worker._check_unpaused`` returned at ``MARKET_CLOSED`` BEFORE any status was set, so the snapshot of a closed
market named no trade, and the reader turned every id with no entry into paused ``not_listed``. Now the worker records
each listed trade's status with the reason ``market_closed`` ("The market is closed."), so the two cases read
differently: a closed market (the worker is running and lists the trade) versus a trade the worker really does not list
(``not_listed``). Spec basis: REQ-115 AC-4 (the pause names its true reason), REQ-165 AC-6 (a worker that is down or
late never reads current: unchanged, the heartbeat decides), ADR-016 to ADR-019 (a trade that owes a check keeps that
reason; a trade that is really not listed still reads paused ``not_listed``).
"""
from __future__ import annotations

import datetime

from ofo.rules.inputs import DataHealth
from ofo_app import background, monitoring_state
from ofo_app.monitoring_state import ACTIVE, PAUSED
from test_background_cycle import DEFAULTS, FIRST_ID, Calls, Prov, _settings, _watched, _worker, scn  # noqa: F401
from test_monitoring_state import _Client, _fresh

SEC = datetime.timedelta(seconds=1)


class _Listed(list):
    unread: frozenset = frozenset()


def _worker_with(scn, client, prov, now, **kw):  # noqa: F811
    watched, recorder = kw.pop("watched", None), kw.pop("recorder", None)
    w = _worker(prov, _watched(scn) if watched is None else watched, now, recorder or Calls(),
                settings=kw.pop("settings", None), want_client=client)

    async def no_wants(*_a, **_k):  # the test provider has no token table; the want write is not what is tested here
        return None
    w._write_wants = no_wants
    return w


async def _read(client, now):
    await monitoring_state.ExitsPublisher(client, "m").publish([], {}, now)  # a live monitor's (empty) report exists
    return (await monitoring_state.read_states(client, [FIRST_ID], now, heartbeat=_fresh))[FIRST_ID]


async def test_w34_a_listed_running_trade_reads_market_closed_not_not_listed_while_the_market_is_closed(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    prov.closed = True
    w = _worker_with(scn, client, prov, now)
    await w.cycle()
    got = await _read(client, now[0])
    print("CLOSED MARKET READS", got)
    assert (got.status, got.reason) == (PAUSED, "market_closed"), got
    assert got.reason != monitoring_state.NOT_LISTED


async def test_w34_a_trade_that_is_really_not_listed_still_reads_not_listed_when_the_market_is_closed(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    prov.closed = True
    watched = _Listed(_watched(scn))
    w = _worker_with(scn, client, prov, now, watched=watched)
    await w.cycle()
    watched.clear()  # dropped: exited, or no plan, or unreadable
    await w.rebuild()
    now[0] += SEC
    await w.cycle()
    got = await _read(client, now[0])
    assert (got.status, got.reason) == (PAUSED, monitoring_state.NOT_LISTED), got


async def test_w34_a_trade_owing_a_failed_check_keeps_that_reason_when_the_market_closes(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]

    async def recorder(_w, _s, _p=None):
        raise RuntimeError("db down")
    w = _worker_with(scn, client, prov, now, recorder=recorder, settings=_settings(dict(DEFAULTS)))
    await w.cycle()
    assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED
    prov.closed = True
    now[0] += SEC
    await w.cycle()
    got = await _read(client, now[0])
    assert (got.status, got.reason) == (PAUSED, "check_failed"), got


async def test_w34_a_trade_paused_for_a_stale_feed_reads_market_closed_once_the_market_has_closed(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    prov.health = DataHealth.STALE
    w = _worker_with(scn, client, prov, now)
    await w.cycle()
    assert w.paused_reason[FIRST_ID] is background.PriceState.STALE
    prov.closed = True
    now[0] += SEC
    await w.cycle()
    got = await _read(client, now[0])
    assert (got.status, got.reason) == (PAUSED, "market_closed"), got  # the true reason now: stale quotes are expected


async def test_w34_the_market_opening_makes_the_trade_watched_again(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    prov.closed = True
    w = _worker_with(scn, client, prov, now)
    await w.cycle()
    assert (await _read(client, now[0])).reason == "market_closed"
    prov.closed = False
    now[0] += SEC
    await w.cycle()
    got = await _read(client, now[0])
    assert (got.status, got.reason) == (ACTIVE, ""), got


async def test_w34_a_leg_with_no_token_keeps_its_own_reason_at_a_closed_market(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    prov.closed = True
    w = _worker_with(scn, client, prov, now)
    await w.cycle()
    w._no_token.add(FIRST_ID)  # what the want writer records for a leg with no token
    w.paused_reason[FIRST_ID] = background.PriceState.LEG_MISSING
    now[0] += SEC
    await w.cycle()
    assert w.paused_reason[FIRST_ID] is background.PriceState.LEG_MISSING


async def test_w34_review_f2_a_one_off_missing_quote_before_the_close_reads_market_closed_afterwards(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    w = _worker_with(scn, client, prov, now)
    await w.cycle()
    w.status[FIRST_ID] = background.MonitoringStatus.PAUSED  # a read-side leg_missing at 15:29:50, tokens fine
    w.paused_reason[FIRST_ID] = background.PriceState.LEG_MISSING
    prov.closed = True
    now[0] += SEC
    await w.cycle()
    assert w.paused_reason[FIRST_ID] is background.PriceState.MARKET_CLOSED


async def test_w34_review_f3_a_worker_running_through_the_close_checks_on_the_first_cycle_after_the_open(scn):  # noqa: F811
    client = _Client()
    calls = Calls()
    prov, now = Prov(scn), [scn.clock_at]
    w = _worker_with(scn, client, prov, now, recorder=calls)
    await w.cycle()
    before = len(calls.states)
    assert before == 1 and w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE
    prov.closed = True
    now[0] += 60 * SEC
    await w.cycle()
    assert w.paused_reason[FIRST_ID] is background.PriceState.MARKET_CLOSED and len(calls.states) == before
    prov.closed = False
    now[0] += 60 * SEC
    prov.move_spot(prov.spot.ltp + 1, now[0])
    await w.cycle()
    assert len(calls.states) == before + 1, "the first open cycle ran a check (no stale signature held it)"
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE


async def test_w34_review_f3_a_trade_owing_the_kind_check_keeps_that_reason_at_the_close(scn, monkeypatch):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    w = _worker_with(scn, client, prov, now)
    await w.cycle()
    w.status[FIRST_ID] = background.MonitoringStatus.PAUSED
    w.paused_reason[FIRST_ID] = background.PriceState.EXPIRY_KIND_UNKNOWN
    w._owed[FIRST_ID] = background.PriceState.EXPIRY_KIND_UNKNOWN
    prov.closed = True
    now[0] += SEC
    await w.cycle()
    assert w.paused_reason[FIRST_ID] is background.PriceState.EXPIRY_KIND_UNKNOWN
