"""Lane RA2 item 8 (Lane Z2's fourth review T2; ADR-330 (64), REQ-115 AC-4, ADR-016 to ADR-019): one genuinely missing
strategy row must not blind the whole paper book.

Real case: an armed index exit at 22,850.00 on a trade whose strategy row is gone (``kinds_of`` says "unknown" for it,
the way the store answers an id it does not find). Before: when EVERY armed strategy read unknown after a first
good load, ``_paper_only`` raised ``BookUnreadError`` on every reload for ever (a failed read of the whole list was told
apart from a missing row by "all unknown", which is a guess; since Lane FD4 a failed read raises by itself). Now the
missing trade is left unwatched and unfired (told once as not applicable, the fire's own kind read still stops any fire
on it), every other trade keeps its watch, and a failed read of the whole list stays a failed read.
"""
from __future__ import annotations

from ofo_app import position_kind, strategy_store
from test_kinds_unread_fe3_1128 import CROSSED, _loaded, fail_next_read
from test_paper_monitor import INDEX, _exit_below, _stops, _strategy, _trigger_state, db  # noqa: F401


def _missing(*ids):
    """``kinds_of`` where these strategy ids have no row: "unknown" for them, the real answer for the others."""
    real = strategy_store.kinds_of

    async def answer(conn, asked):
        got = await real(conn, [i for i in asked if i not in ids])
        return {i: got.get(i, position_kind.UNKNOWN) for i in asked}
    return answer


async def test_core_the_only_armed_trade_has_no_row_the_reload_does_not_raise_and_nothing_fires(db, monkeypatch):  # noqa: F811
    market, stored, tid, monitor, _client, clock = await _loaded(db, monkeypatch)
    monkeypatch.setattr(strategy_store, "kinds_of", _missing(stored.id))
    monitor.notify()
    clock[0] = 10.0
    await monitor.step()
    assert monitor.read_failures == 0 and monitor.book_unread_since is None, "a missing row is not a failed read"
    assert monitor.not_applicable == {tid: position_kind.UNKNOWN}
    assert monitor._exits == [], "the trade whose row is missing is not watched"
    market.tick(INDEX, CROSSED)
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False) and await _stops(db, stored.id) == []


async def test_a_missing_row_leaves_every_other_trade_watched_and_still_fired(db, monkeypatch):  # noqa: F811
    market, first, first_tid, monitor, _client, clock = await _loaded(db, monkeypatch)
    second, _ids, keys = await _strategy(db)
    second_tid = await _exit_below(db, second.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    monkeypatch.setattr(strategy_store, "kinds_of", _missing(first.id))
    monitor.notify()
    clock[0] = 10.0
    await monitor.step()
    assert monitor.read_failures == 0
    assert [w.armed.trigger.id for w in monitor._exits] == [second_tid], "only the trade with a row is watched"
    market.tick(INDEX, CROSSED)
    assert await monitor.step() == 1
    assert await _trigger_state(db, second_tid) == (True, False)
    assert await _trigger_state(db, first_tid) == (False, False) and await _stops(db, first.id) == []


async def test_a_failed_read_of_the_whole_list_stays_a_failed_read_and_keeps_the_last_watch(db, monkeypatch):  # noqa: F811
    market, _stored, tid, monitor, _client, clock = await _loaded(db, monkeypatch)
    fail_next_read(monkeypatch)
    monitor.notify()
    clock[0] = 10.0
    await monitor.step()
    assert monitor.read_failures == 1 and len(monitor._exits) == 1
    market.tick(INDEX, CROSSED)
    assert await monitor.step() == 1 and await _trigger_state(db, tid) == (True, False), "the kept exit still fires"
