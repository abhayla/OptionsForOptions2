"""D-30 (ADR-320; REQ-112 AC-2): an opportunity whose contracts have expired reads Lapsed, with the time it lapsed.
Real case 23 Nov: 16 Nov PATH opportunities on expired contracts were still Open on 23 Nov. The one place a
record lapses is the worker (ADR-237 (6)): the rebuild asks its gate store, per strategy,
with the IST day of the worker's clock."""
from __future__ import annotations

import datetime as dt

import pytest
from ofo.timeutil import IST
from ofo_app import playbook_store
from test_background_cycle import FakeGate, _rig

EXPIRY = dt.date(2026, 11, 16)
LATER = dt.date(2026, 11, 23)


class _Rec:
    def __init__(self, i: int) -> None:
        self.id = i


async def _lapse(monkeypatch, expiry, today):
    lapsed: list = []

    async def open_suggestions(_db, _user, _sid):
        return [_Rec(1), _Rec(2)]

    async def lapse(_db, _user, sid, reason="x"):
        lapsed.append((sid, reason))
    monkeypatch.setattr(playbook_store, "open_suggestions", open_suggestions)
    monkeypatch.setattr(playbook_store, "lapse", lapse)
    await playbook_store.lapse_expired(None, "owner", 161, expiry, today)
    return lapsed


async def test_open_records_of_an_expired_position_lapse_as_contract_expired(monkeypatch):
    assert await _lapse(monkeypatch, EXPIRY, LATER) == [(1, "contract_expired"), (2, "contract_expired")]


@pytest.mark.parametrize(("expiry", "today"), [(EXPIRY, EXPIRY), (LATER, EXPIRY), (None, LATER)])
async def test_the_expiry_day_itself_and_an_unknown_expiry_lapse_nothing(monkeypatch, expiry, today):
    assert await _lapse(monkeypatch, expiry, today) == []


class ExpiryGate(FakeGate):
    def __init__(self) -> None:
        super().__init__()
        self.asked: list = []

    async def lapse_changed(self, _w):
        return False

    async def lapse_expired(self, w, today):
        self.asked.append((w.strategy_id, today, max(x.expiry for x in w.tracked.position.legs)))
        return False


async def test_the_rebuild_asks_for_the_expiry_lapse_of_every_strategy_with_the_workers_day():
    gate, listed = ExpiryGate(), []
    w = _rig(gate, listed)
    await w.rebuild()
    sid, today, expiry = gate.asked[0]
    assert sid == listed[0][0].strategy_id and today == w._clock().astimezone(IST).date()
    assert isinstance(expiry, dt.date)
