"""GC-ALERT1 step 5 finding: a record the background worker opens must render in the opportunities inbox.

``background.DbGateStore.apply`` stores the group as ``f"{strategy_id}:{at.isoformat()}"``; the inbox reply keys a
group as ``f"{strategy_id}-{group}"`` in an ``Identifier`` field (``^[A-Za-z0-9_\\-.]{1,64}$``), so ':' and '+' make
GET /api/adjustment-opportunities answer 500 for every user with one worker-opened record. Since ADR-237 (6) the worker
is the ONLY writer, so the inbox would be down for every user with a record. This test opens through the worker's own
store with the gate's own Opened event and reads the inbox through the real route.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import test_adjustment_check as check_test
from ofo.adjustment import alert_gate
from ofo_app.background import DbGateStore, Watched
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call

app_db_url = check_test.app_db_url
OK = 200
AT = datetime.datetime(2026, 11, 2, 4, 30, 1, 250000, tzinfo=datetime.UTC)


async def test_a_worker_opened_record_renders_in_the_inbox(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    w = Watched(user_ref="owner", strategy_id=sid, tracked=None, body={}, is_system=True, feed_owner="owner")
    opened = await DbGateStore().apply(
        w, [alert_gate.Opened("T-01", AT, 0, Decimal("0.5000"), Decimal("0.3416"))], None)
    assert list(opened) == ["T-01"]
    status, body = await _call("GET", "/api/adjustment-opportunities")
    assert status == OK, body
    mine = [g for g in body["groups"] if g["strategy_id"] == sid]
    assert [r["id"] for g in mine for r in g["records"]] == [opened["T-01"]]
