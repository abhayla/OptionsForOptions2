"""Lane FE2 (28 Nov 2026), item 6 (issue #867): ``Worker._checked_body`` keeps one entry per strategy ever checked; an
entry goes when its strategy leaves the list (exited, deleted, no plan), never when a read merely failed (the
strategy is still there). Spec basis: REQ-115 AC-3 (a re-read rebuilds the monitors); ADR-330 (44).
"""
from __future__ import annotations

from test_background_cycle import FIRST_ID, Calls, Prov, _watched, _worker, scn  # noqa: F401 - the module fixture


class _Listed(list):
    """What the owner lister returns: the monitors, and the strategies whose read failed this time."""
    unread: frozenset = frozenset()


async def test_a_strategy_that_left_the_list_loses_its_checked_body(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    watched = _Listed(_watched(scn))
    w = _worker(prov, watched, now, calls)
    await w.cycle()
    assert FIRST_ID in w._checked_body
    watched.clear()  # the strategy exited
    await w.rebuild()
    print("CHECKED BODIES", dict(w._checked_body))
    assert w._checked_body == {}


async def test_a_strategy_whose_read_failed_keeps_its_checked_body(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    watched = _Listed(_watched(scn))
    w = _worker(prov, watched, now, calls)
    await w.cycle()
    watched.clear()
    watched.unread = frozenset({FIRST_ID})  # not a strategy leaving
    await w.rebuild()
    assert FIRST_ID in w._checked_body

