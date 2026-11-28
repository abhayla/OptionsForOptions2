"""FD4 item 7 (UX-A08): where the time of GET /api/strategies/{id}/adjustment-plan goes, and one cost pinned.

Measured on a real database (scenario ADJ-01, warm; request log line and cProfile over 5 requests): the read is about
83 ms, db 16 ms in 19 statements, the other 67 ms compute. By share of the profiled compute: the STORED CATALOGUE loaded
in full for the expiry kind (``adjustment_readers.stored_kind`` -> ``catalogue_store.load_catalogue``: about 4,700
contract rows built per request) is about a quarter; ``read_market`` about 13 %; building the reply (the door
walk of the model) about 9 %; the chain model's implied volatilities about 9 %. The catalogue load is the one cost
that is not the page's own work: a read of only the underlying's expiries and futures would do (the change is outside
the plan route's files: RESULTS "For the owner lane"). This file pins that the route does not load it a SECOND time
(``_known_kind`` falls back to its own read only when the market gave no kind)."""
from __future__ import annotations

from ofo_app import adjustment_readers
from test_route_latency_budget import (  # noqa: F401 - the warm rig of the latency guard (real database)
    _warm,
    app_db_url,
    rig,
)


async def test_the_plan_read_loads_the_stored_catalogue_for_the_kind_once(rig, monkeypatch):  # noqa: F811
    sid = rig.ids[0]
    await _warm(rig, sid)
    real = adjustment_readers.stored_kind
    calls: list[str] = []

    async def counted(*a, **k):
        calls.append("stored_kind")
        return await real(*a, **k)
    monkeypatch.setattr(adjustment_readers, "stored_kind", counted)
    await rig.get(rig.urls(sid)["adjustment-plan"])
    assert len(calls) <= 1, calls


async def test_fd5_the_kind_read_asks_the_store_for_one_underlying_only(rig, monkeypatch):  # noqa: F811
    """FD5 item 4: ``stored_kind`` loaded the whole catalogue (about 4,700 rows per request) to read one underlying's
    expiries and futures. It now asks ``load_catalogue(db, <underlying>)``: the same rule on fewer rows."""
    sid = rig.ids[0]
    await _warm(rig, sid)
    real = adjustment_readers.load_catalogue
    asked: list[object] = []

    async def spy(db, name=None):
        asked.append(name)
        return await real(db, name)
    monkeypatch.setattr(adjustment_readers, "load_catalogue", spy)
    await rig.get(rig.urls(sid)["adjustment-plan"])
    assert asked and all(name == "NIFTY" for name in asked), asked
