# ruff: noqa: PLC0414, PLC0415, RUF007
"""GC-SET lots (REQ-167 AC-5, "Limits"): the most lots one leg may hold is the ``limits.max_lots`` setting, checked by the
ONE shared check (``check_lots``) every lots-accepting route passes, read at each request with no restart.

Spec basis: REQ-167 AC-5 Limits (lot caps); ADR-222 (9). Default 10000 (the number the schema used to type).
Same pattern as ``test_settings_calc_wiring.py``: one app, asked repeatedly; the row is inserted in the SAME
rolled-back transaction between the asks, so nothing is committed.
"""

from __future__ import annotations

from http import HTTPStatus

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_settings_rate_wiring import _app, _body, _live
from test_settings_rate_wiring import replayed as replayed

KEY = "limits.max_lots"


def _with_lots(body: dict, lots: int) -> dict:
    return {**body, "legs": [{**body["legs"][0], "lots": lots}, *body["legs"][1:]]}


async def test_core_the_max_lots_setting_is_the_outcome_routes_lot_cap(app_engine: AsyncEngine, replayed, monkeypatch):
    """Core: no row -> the default 10000 accepts a 10000-lot leg and refuses 10001 (422, reason). A 500 row effective
    now -> the next ask on the SAME app refuses 600 lots with the reason (422) and still accepts 500."""
    from ofo_app import settings_store

    _live(replayed, monkeypatch)
    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        app = _app(session)
        body = _body(replayed)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            top = await ac.post("/api/strategies/outcome", json=_with_lots(body, 10000))
            over = await ac.post("/api/strategies/outcome", json=_with_lots(body, 10001))
            await settings_store.add_setting(session, KEY, "500", set_by="admin-test", correlation_id="gcset-lots-1")
            refused = await ac.post("/api/strategies/outcome", json=_with_lots(body, 600))
            allowed = await ac.post("/api/strategies/outcome", json=_with_lots(body, 500))
        assert top.status_code == HTTPStatus.OK, top.text
        assert over.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, over.text
        assert "at most 10000 lots" in over.text
        assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, refused.text
        assert "at most 500 lots; this leg has 600" in refused.text
        assert allowed.status_code == HTTPStatus.OK, allowed.text
    finally:
        await trans.rollback()
        await conn.close()
