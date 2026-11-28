"""Lane FE2 (28 Nov 2026), item 7 (issue #864): the worker's half of "pass the kind from the worker's own read". The
catalogue read of the expiry kind (``adjustment_readers._tracked_on``) ran once per strategy on every re-read (every
10 s since Lane J3). The worker now records the kind of each (underlying, nearest expiry) its checks read, hands that
record to the lister, and the lister passes it to the reader when the reader accepts it. The reader's half is Lane
R3's file (``adjustment_readers.py``): written under "For the owner lane" in RESULTS-lane-fe2.
Spec basis: ADR-330 (44), (58); REQ-115 AC-3.
"""
from __future__ import annotations

import dataclasses
import datetime

from ofo_app import background
from test_background_cycle import Calls, FakeGate, Prov, _watched, _worker, scn  # noqa: F401 - the module fixture
from test_worker_j3 import _state_without_kind

NEAR = datetime.date(2026, 11, 9)


async def test_a_check_records_the_kind_it_read_for_the_nearest_expiry(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls, gate_store=FakeGate())
    await w.cycle()
    print("KINDS", w.kinds)
    assert w.kinds == {("NIFTY", NEAR): "weekly"}


async def test_a_kind_that_is_not_known_is_never_recorded(scn, monkeypatch):  # noqa: F811
    real = background.market_inputs

    def unknown(*a, **k):
        return dataclasses.replace(real(*a, **k), expiry_kind="")
    monkeypatch.setattr(background, "market_inputs", unknown)
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    watched = [dataclasses.replace(x, tracked=dataclasses.replace(
        x.tracked, position=dataclasses.replace(x.tracked.position, expiry_kind=""))) for x in _watched(scn)]
    _state_without_kind(monkeypatch)  # the state step answers "not known" for the kind-free trade
    w = _worker(prov, watched, now, calls, gate_store=FakeGate())
    await w.cycle()
    assert w.kinds == {}


async def test_the_workers_record_is_the_one_the_lister_is_given(scn):  # noqa: F811
    shared: dict = {}
    w = _worker(Prov(scn), _watched(scn), [scn.clock_at], Calls(), gate_store=FakeGate(), kinds=shared)
    assert w.kinds is shared


async def test_a_record_of_a_past_expiry_goes_at_the_next_rebuild(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker(prov, _watched(scn), now, calls, gate_store=FakeGate())
    w.kinds[("NIFTY", datetime.date(2026, 1, 1))] = "weekly"
    await w.cycle()
    await w.rebuild()
    assert ("NIFTY", datetime.date(2026, 1, 1)) not in w.kinds
    assert ("NIFTY", NEAR) in w.kinds


def test_the_lister_passes_the_record_only_when_the_reader_takes_it():
    kinds = {("NIFTY", NEAR): "weekly"}
    assert background.READER_TAKES_KINDS is True  # the reader half landed (Lane FR item 2, #864)
    assert background.reader_kinds_kwargs(kinds) == {"kinds": kinds}
    assert background.reader_kinds_kwargs(kinds, takes=False) == {}
    assert background.reader_kinds_kwargs(kinds, takes=True) == {"kinds": kinds}
    assert background.reader_kinds_kwargs(None, takes=True) == {}
