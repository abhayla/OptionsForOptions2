"""Lane B1b (coordinator note, PC round 2 build 829ff65f, market closed, 28 Nov 21:25 IST): the worker log said "5
strategies monitored", each check skipped with the reason market_closed, while GET /api/monitoring-state answered an
empty list. Question: is the list empty by design, or is the worker's report lost when every check is skipped?

Answer pinned here (five running trades, market closed, the worker's own cycle): the worker's snapshot LISTS all five
with the reason market_closed (Lane FE3's fix, ``Worker._market_closed``), and the route names each ASKED id. The route
answers ``strategies: []`` only when the request carries no ``ids`` (the page always sends ``?ids=1,2,..``; the route
has no user and cannot know the trades): that is by design and it is not "all watched": any asked id the worker does not
name reads paused ``not_listed``."""
from __future__ import annotations

import datetime

from ofo_app import monitoring_state
from ofo_app.routes import monitoring_status as route
from test_background_cycle import FIRST_ID, Prov, _watched, scn  # noqa: F401
from test_market_closed_fe3_1128 import _worker_with
from test_monitoring_state import _Client, _fresh

FIVE = 5


async def test_core_five_running_trades_at_a_closed_market_are_all_listed_with_market_closed(scn):  # noqa: F811
    client = _Client()
    prov, now = Prov(scn), [scn.clock_at]
    prov.closed = True
    w = _worker_with(scn, client, prov, now, watched=_watched(scn, FIVE))
    await w.cycle()
    await monitoring_state.ExitsPublisher(client, "m").publish([], {}, now[0])  # a live monitor's (empty) report
    ids = [FIRST_ID + i for i in range(FIVE)]
    found = await monitoring_state.read_states(client, ids, now[0], heartbeat=_fresh)
    expected = dict.fromkeys(ids, (monitoring_state.PAUSED, "market_closed"))
    assert {i: (e.status, e.reason) for i, e in found.items()} == expected
    shown = route.compose(found, ids, now[0])
    assert [(s.strategy_id, s.watch_state, s.reason) for s in shown] == [(i, "paused", "market_closed") for i in ids]
    assert all(s.reason_text is not None for s in shown)


def test_a_request_with_no_ids_is_empty_by_design_and_an_asked_id_nobody_names_is_never_watched():
    now = datetime.datetime(2026, 11, 28, 4, 30, tzinfo=datetime.UTC)
    assert route.parse_ids("") == []
    [one] = route.compose({}, [7], now)
    assert (one.watch_state, one.reason) == ("paused", monitoring_state.NOT_LISTED)
