"""GC-6 ORDERS-SCREEN round 2, finding 2: the page-load read takes every strategy lock first, in ascending id, and only
then writes audit rows. Check / Execute take a strategy lock and then the audit append lock; a page load that took
strategy 1, wrote audit rows (audit lock), then waited for strategy 2 formed a cycle with a Check on strategy 2.

No database: the two collaborators are replaced by recorders, so the ORDER of the calls is asserted on the real
``_read_open_orders``. The two-connection database proof needs committed rows in six tables and a teardown; it is
named in the round report as not written here (see the PR body).
"""
from __future__ import annotations

import pytest
from ofo_app import order_audit
from ofo_app import strategy_store as store
from ofo_app.routes import orders as route

TAG1, TAG2, TAG3 = "OFS1V1L0", "OFS2V1L0", "OFS3V1L0"


class _Session:
    class reads:
        @staticmethod
        def fetch_orders():
            return [{"tag": t, "order_id": f"1{t}", "status": "OPEN", "filled_quantity": 0, "quantity": 65,
                     "pending_quantity": 65, "transaction_type": "BUY", "tradingsymbol": "X", "exchange": "NFO",
                     "order_type": "LIMIT", "product": "NRML", "price": 1, "average_price": 0}
                    for t in (TAG1, TAG2, TAG3)]


async def _run(monkeypatch, open_tags):
    events: list[tuple[str, object]] = []

    async def lock(_db, _user, sid):
        events.append(("lock", sid))

    async def record(_db, _orders, _trades, tags):
        events.append(("audit", tuple(sorted(tags))))

    monkeypatch.setattr(store, "lock_strategy", lock)
    monkeypatch.setattr(order_audit, "record_broker_book", record)
    result = await route._read_open_orders(object(), "u", _Session(), open_tags)
    return result, events


async def test_every_strategy_lock_comes_before_any_audit_write_in_ascending_id(monkeypatch):
    tags = {3: frozenset({TAG3}), 1: frozenset({TAG1}), 2: frozenset({TAG2})}
    (kind, fresh), events = await _run(monkeypatch, tags)
    assert kind == "read" and set(fresh) == {TAG1, TAG2, TAG3}
    assert [e for e in events if e[0] == "lock"] == [("lock", 1), ("lock", 2), ("lock", 3)]
    first_audit = next(i for i, e in enumerate(events) if e[0] == "audit")
    assert all(e[0] == "lock" for e in events[:first_audit]) and first_audit == len(tags)
    assert [e[1] for e in events[first_audit:]] == [(TAG1,), (TAG2,), (TAG3,)]  # one audit write per strategy


async def test_one_open_plan_still_locks_then_audits(monkeypatch):
    _, events = await _run(monkeypatch, {7: frozenset({TAG1})})
    assert events == [("lock", 7), ("audit", (TAG1,))]


@pytest.mark.parametrize("session", [None])
async def test_no_session_takes_no_lock_and_writes_nothing(monkeypatch, session):
    events: list[str] = []

    async def lock(*_a):
        events.append("lock")

    monkeypatch.setattr(store, "lock_strategy", lock)
    out = await route._read_open_orders(object(), "u", session, {1: frozenset({TAG1})})
    assert out == ("failed", None) and events == []
