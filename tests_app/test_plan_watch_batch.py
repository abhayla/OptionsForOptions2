"""Lane H (REQ-049 AC-4): GET /api/plan-watch?strategy_ids=... answers a whole Positions list in one request.
Per row: the single route's reply (same lines, wording), or that route's refusal; one bad row never fails the others."""
from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from ofo_app import db as app_db
from test_adjustment_check import (
    _reset_engine,
    _seeded,
    app_db_url,  # noqa: F401 - the fixture of the check tests
)
from test_plan_watch import _arm

UNKNOWN = 987654


async def _both(sids: list[int], batch_ids: str) -> tuple[dict, dict[int, tuple[int, dict]]]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    _reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/api/plan-watch?strategy_ids={batch_ids}")
        assert r.status_code == 200, r.text  # noqa: PLR2004
        single = {}
        for sid in sids:
            s = await ac.get(f"/api/strategies/{sid}/plan-watch")
            single[sid] = (s.status_code, s.json())
    await app_db.close_db()
    return r.json(), single


async def test_batch_rows_equal_the_single_route_and_a_bad_row_fails_alone(app_db_url, monkeypatch):  # noqa: F811
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _arm(app_db_url, a)
    out, single = await _both([a, UNKNOWN], f"{a},{UNKNOWN},{a}")  # a repeated id is answered once
    assert [i["strategy_id"] for i in out["items"]] == [a, UNKNOWN]
    ok_a, bad = out["items"]  # one seeded strategy per scenario, so one real row beside the bad one
    assert ok_a["state"] == "ok" and ok_a["refusal"] is None
    assert ok_a["watch"] == single[a][1]  # the full reply, field for field
    assert bad["state"] == "refused" and bad["watch"] is None
    assert bad["status"] == single[UNKNOWN][0] == 404  # noqa: PLR2004
    assert bad["refusal"] == single[UNKNOWN][1]  # the same four-part message the single route's 404 body carries
    assert out["as_of"] == ok_a["watch"]["as_of"]


async def test_bad_asks_are_422(app_db_url, monkeypatch):  # noqa: F811
    await _seeded(app_db_url, monkeypatch, "ADJ-01")
    from ofo_app.main import create_app  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for ids in ("", "x", "0", "-3", ",".join(str(i) for i in range(1, 22))):
            r = await ac.get(f"/api/plan-watch?strategy_ids={ids}")
            assert r.status_code == 422, (ids, r.status_code)  # noqa: PLR2004
        assert (await ac.get("/api/plan-watch")).status_code == 422  # noqa: PLR2004
    await app_db.close_db()
