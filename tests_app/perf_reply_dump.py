"""Lane H: write the full replies of plan-watch, adjustment-check, adjustment-plan and the batch route for the seeded,
armed ADJ-01 strategy to the file in OFO_REPLY_OUT (skipped unless OFO_PERF=1), so two builds can be compared byte for
byte (``cmp old new``): "same answers, faster". Run on a throwaway database, like perf_route_profile.py."""
from __future__ import annotations

import json
import os

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import db as app_db
from test_adjustment_check import _reset_engine, _seeded, app_db_url  # noqa: F401
from test_plan_watch import _arm

pytestmark = pytest.mark.skipif(os.environ.get("OFO_PERF") != "1", reason="measurement harness: set OFO_PERF=1")


async def test_dump(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _arm(app_db_url, sid)
    from ofo_app.main import create_app  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    out = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for name, url in (("plan-watch", f"/api/strategies/{sid}/plan-watch"),
                          ("adjustment-check", f"/api/strategies/{sid}/adjustment-check"),
                          ("adjustment-plan", f"/api/strategies/{sid}/adjustment-plan"),
                          ("batch", f"/api/plan-watch?strategy_ids={sid},987654")):
            r = await ac.get(url)
            out[name] = [r.status_code, r.json()]
    await app_db.close_db()
    with open(os.environ["OFO_REPLY_OUT"], "w", encoding="utf-8") as fh:  # noqa: ASYNC230
        json.dump(out, fh, indent=1, sort_keys=True)
