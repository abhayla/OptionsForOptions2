"""Lane FE3 (28 Nov 2026), the round 2 review's R6 and R7 (worker half), ADR-330 (64), REQ-115 AC-4.

R6: an old armed stop on a REAL position is skipped (right), but it is said: once in the log per stop, and in the
monitoring report as "not applicable: real position", so no screen shows that stop as live.
R7: a trade whose exits are not being checked never reads watched: no list known (the first read of the book failed)
reads "not checked yet"; a failed read after a list was known keeps judging it for 120 s, then reads "could not read
the book" (``test_kinds_unread_fe3_1128`` has the longer cases).
"""
from __future__ import annotations

import logging

from ofo_app import held_entry_store, monitoring_state, paper_monitor, strategy_store
from test_kinds_unread_fe3_1128 import _raises
from test_monitoring_state import _Client, _fresh
from test_paper_monitor import INDEX, OPEN_AT, Market, _exit_below, _monitor, _strategy, db  # noqa: F401 - fixture


async def _worker_says_watched(client, sid, at):
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(sid, monitoring_state.ACTIVE, "", "", at)], at)
    return (await monitoring_state.read_states(client, [sid], at, heartbeat=_fresh))[sid]


async def test_r6_a_stop_on_a_real_position_is_judged_not_told_not_applicable(db, monkeypatch, caplog):  # noqa: F811
    """Lane R1 (ADR-330 (73)) rewrites FE3 R6: the stop of a real position is watched like a paper one's; nothing is
    told as "not applicable" (only an unreadable kind is) and the report never names it so."""
    market = Market()
    stored, _ids, keys = await _strategy(db)
    await held_entry_store.record(db, stored.id, OPEN_AT, None)  # ADR-292: held at the broker = a real position
    tid = await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22800.00")
    client = _Client()
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: client)
    monitor = _monitor(db, market)
    with caplog.at_level(logging.INFO, logger=paper_monitor.log.name):
        await monitor.step()
        monitor.notify()
        await monitor.step()
    assert monitor.not_applicable == {}
    told = [r for r in caplog.records if "not applicable" in r.getMessage() and f"trigger {tid} " in r.getMessage()]
    assert told == []
    got = await _worker_says_watched(client, stored.id, market.at)
    assert got.why != monitoring_state.EXIT_NOT_APPLICABLE, got


async def test_r7_no_list_known_and_the_book_unreadable_never_reads_watched(db, monkeypatch):  # noqa: F811
    market = Market()
    stored, _ids, keys = await _strategy(db)
    await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22900.00")
    client = _Client()
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: client)
    monkeypatch.setattr(strategy_store, "kinds_of", _raises)
    monitor = _monitor(db, market)
    await monitor.step()  # the first read of the book fails: no list is known, so no claim is made
    got = await _worker_says_watched(client, stored.id, market.at)
    print("READ", got)
    assert got.status == monitoring_state.PAUSED, got
