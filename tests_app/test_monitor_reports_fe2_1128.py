"""Lane FE2 (28 Nov 2026), item 1: several API workers each run a paper monitor; the index-exit report is merged per
monitor, never overwritten by whichever monitor wrote last. Spec basis: ADR-016 to ADR-019; REQ-115; REQ-049
("Monitoring paused"); ADR-330 (44), (47), (58), (66).

Real case: the PC runs the API with more than one worker process. Monitor B has loaded only trade 1's index exit
(trade 2's exit was armed after B's last reload); monitor A loaded both and cannot judge either (no index reading).
A's report says "not run" for both; B's later write used to replace it, and trade 2 read watched although no monitor
was judging its exit.

Core: the real database, two monitors with their own feeds, ONE shared bus client (the Redis stand-in).
"""
from __future__ import annotations

import contextlib
import datetime
import json
from decimal import Decimal

from ofo_app import monitoring_state
from test_index_exit_watch_fe_1128 import _bus, _exit_above
from test_monitoring_state import _Client, _fresh
from test_paper_monitor import INDEX, Market, _monitor, _strategy, db  # noqa: F401 - fixture

D = Decimal
FAILED_LOADS = 2
BELOW = "23390.00"  # below the exit level 23,400.00: judged, not crossed


async def _worker_says_watched(client, ids, now) -> None:
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(i, monitoring_state.ACTIVE, "", "", now) for i in ids], now)


async def test_core_two_monitors_one_report_a_trade_nobody_judges_is_not_shown_as_watched(db, monkeypatch):  # noqa: F811
    market_b = Market()
    at = market_b.at
    s1, _ids1, _k1 = await _strategy(db)
    await _exit_above(db, s1.id)
    client = _Client()
    _bus(monkeypatch, client)
    market_b.tick(INDEX, BELOW)  # B's index is live
    monitor_b = _monitor(db, market_b)
    await monitor_b.step()  # B loads trade 1's exit only: writes watching [1]
    s2, _ids2, _k2 = await _strategy(db)
    await _exit_above(db, s2.id)  # armed after B's last reload
    market_a = Market()  # A's index tick is silent and no worker reading exists: it cannot judge any exit
    monitor_a = _monitor(db, market_a)
    await monitor_a.step()  # A loads both: not run for both
    later = at + datetime.timedelta(seconds=monitoring_state.REFRESH_S + 1)
    market_b.at = later
    market_b.tick(INDEX, BELOW)
    await monitor_b.step()  # B writes again (due): used to replace A's report
    await _worker_says_watched(client, [s1.id, s2.id], later)
    seen = await monitoring_state.read_states(client, [s1.id, s2.id], later, heartbeat=_fresh)
    print("STATES", seen)
    assert seen[s1.id].status == monitoring_state.ACTIVE, "trade 1's exit is judged by monitor B"
    assert (seen[s2.id].status, seen[s2.id].reason) == (monitoring_state.PAUSED, "stale"), \
        "trade 2's exit is judged by nobody: it must not read watched"


# ---- every answer state of the merged report (pure: no database) -----------------------------------------------------

NOW = datetime.datetime(2026, 10, 29, 4, 30, tzinfo=datetime.UTC)


def _slot(at, watching=(), not_run=None):
    return {"at": at.isoformat(), "watching": list(watching),
            "not_run": {str(k): v for k, v in (not_run or {}).items()}}


def _report(**owners):
    return json.dumps({"at": NOW.isoformat(), "owners": owners})


def test_one_monitor_judging_a_trade_covers_it_whatever_another_says():
    raw = _report(a=_slot(NOW, not_run={1: "index_not_live"}), b=_slot(NOW, watching=[1]))
    assert monitoring_state.decode_exits(raw, NOW) == {}


def test_a_trade_no_fresh_monitor_judges_carries_the_why_of_the_one_that_listed_it():
    raw = _report(a=_slot(NOW, not_run={1: "index_not_live"}), b=_slot(NOW, watching=[2]))
    assert monitoring_state.decode_exits(raw, NOW) == {1: "index_not_live"}


def test_a_stopped_monitors_old_slot_is_ignored_while_a_fresh_monitor_exists():
    old = NOW - datetime.timedelta(seconds=monitoring_state.SNAPSHOT_STALE_S + 1)
    raw = _report(dead=_slot(old, not_run={1: "index_not_live"}), live=_slot(NOW, watching=[2]))
    assert monitoring_state.decode_exits(raw, NOW) == {}


def test_every_monitor_stopped_every_listed_trade_reads_not_run():
    old = NOW - datetime.timedelta(seconds=monitoring_state.SNAPSHOT_STALE_S + 1)
    raw = _report(a=_slot(old, watching=[1]), b=_slot(old, not_run={2: "index_not_live"}))
    assert monitoring_state.decode_exits(raw, NOW) == {1: monitoring_state.INDEX_EXITS_NOT_RUN,
                                                        2: monitoring_state.INDEX_EXITS_NOT_RUN}


def test_a_report_of_another_shape_is_unreadable_never_clear():
    flat = '{"at": "2026-10-29T04:30:00+00:00", "not_run": {}, "watching": []}'
    assert monitoring_state.decode_exits(flat, NOW) is None
    assert monitoring_state.decode_exits(_report(a={"at": "x"}), NOW) is None
    assert monitoring_state.decode_exits("not json", NOW) is None


async def test_a_publisher_keeps_the_other_monitors_slot_and_drops_one_long_dead():
    client = _Client()
    a, b = monitoring_state.ExitsPublisher(client, "a"), monitoring_state.ExitsPublisher(client, "b")
    long_dead = NOW - datetime.timedelta(seconds=monitoring_state.OWNER_KEEP_S + 1)
    client.data[monitoring_state.exits_key()] = _report(old=_slot(long_dead, watching=[9]))
    assert await a.publish([1], {}, NOW) and await b.publish([2], {2: "index_not_live"}, NOW)
    owners = json.loads(client.data[monitoring_state.exits_key()])["owners"]
    assert sorted(owners) == ["a", "b"]
    assert owners["a"]["watching"] == [1] and owners["b"]["not_run"] == {"2": "index_not_live"}


async def test_a_store_that_cannot_answer_writes_nothing_blind():
    client = _Client()
    pub = monitoring_state.ExitsPublisher(client, "a")
    client.boom = True
    assert await pub.publish([1], {}, NOW) is False
    assert client.data == {}


# ---- Opus review F1, F3, F5 ------------------------------------------------------------------------------------------

def test_review_f1_a_monitor_that_stopped_writing_loses_its_claim_before_the_two_minutes_are_up():
    """The API restarts at 10:00:00: the dead monitor's slot (written 09:59:59) says watching; the new monitor says it
    cannot judge. 40 s later the trade must NOT read judged."""
    dead = NOW - datetime.timedelta(seconds=1)
    raw = _report(old=_slot(dead, watching=[100]),
                  new=_slot(NOW + datetime.timedelta(seconds=2), not_run={100: "index_not_live"}))
    later = NOW + datetime.timedelta(seconds=40)
    assert monitoring_state.decode_exits(raw, later) == {100: "index_not_live"}


def test_review_f1_a_claim_nobody_renews_reads_not_run_not_judged():
    raw = _report(old=_slot(NOW, watching=[100]), live=_slot(NOW + datetime.timedelta(seconds=58), watching=[7]))
    got = monitoring_state.decode_exits(raw, NOW + datetime.timedelta(seconds=60))
    assert got == {100: monitoring_state.INDEX_EXITS_NOT_RUN}


def test_review_f1_a_claim_renewed_every_ten_seconds_stays_a_claim():
    raw = _report(a=_slot(NOW - datetime.timedelta(seconds=monitoring_state.WATCH_FRESH_S), watching=[100]))
    assert monitoring_state.decode_exits(raw, NOW) == {}


def test_review_f5_a_report_with_any_bad_slot_is_unreadable_never_a_skipped_slot():
    """Lane RA2 (FE3's deferred issue): a slot that cannot be read may be a monitor that WAS evaluating; it is not
    dropped (it was skipped before): the whole report is unreadable, every trade reads ``state_unreadable``."""
    good = _slot(NOW, watching=[1])
    assert monitoring_state.decode_exits(_report(a=good, bad={"at": "x"}), NOW) is None
    assert monitoring_state.decode_exits(_report(a=good), NOW) == {}
    assert monitoring_state.decode_exits(_report(bad={"at": "x"}), NOW) is None
    assert monitoring_state.decode_exits(_report(), NOW) is None


async def test_review_f3_a_monitor_whose_first_load_failed_publishes_no_slot(db, monkeypatch):  # noqa: F811
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    market = Market()
    s1, _i, _k = await _strategy(db)
    await _exit_above(db, s1.id)
    market.tick(INDEX, BELOW)
    client = _Client()
    _bus(monkeypatch, client)
    real = triggers.armed
    calls = {"n": 0}

    async def failing(session):
        calls["n"] += 1
        if calls["n"] <= FAILED_LOADS:  # the first load and its immediate retry both fail
            raise OSError("database down")
        return await real(session)
    monkeypatch.setattr(triggers, "armed", failing)
    monitor = _monitor(db, market)
    for _ in range(FAILED_LOADS):
        with contextlib.suppress(OSError):
            await monitor.step()  # nothing is loaded: no claim is made
    assert monitoring_state.exits_key() not in client.data
