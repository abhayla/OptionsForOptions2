# ruff: noqa: PLC0414, PLC0415, RUF007
"""GC-SET batch 1 (REQ-167 AC-4): the outcome route reads the scenario columns and the payoff steps from the settings
in force at each request, with no restart.

Spec basis: REQ-167 AC-4 "Each wired calculation reads the value in force when it runs (no restart)"; ADR-222 (9).
Same pattern as ``test_settings_rate_wiring.py``: the app is built once and asked twice; a row effective now is
inserted in the SAME rolled-back transaction between the two asks, so nothing is committed.
"""

from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_settings_rate_wiring import _app, _body, _live
from test_settings_rate_wiring import replayed as replayed


async def _add(session, key: str, value: str, correlation_id: str) -> None:
    from ofo_app import settings_store

    await settings_store.add_setting(session, key, value, set_by="admin-test", correlation_id=correlation_id)


async def test_scenario_columns_and_payoff_steps_follow_the_stored_settings(app_engine: AsyncEngine, replayed,
                                                                             monkeypatch):
    """Ask 1 (no rows): NIFTY step 100 and a 20-point payoff table is refused (422). Rows added: NIFTY step 200 / anchor
    200 and payoff step 1 = 20. Ask 2 on the SAME app: the columns are 200 apart and the 20-point table is served."""
    _live(replayed, monkeypatch)
    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        app = _app(session)
        body = _body(replayed)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            first = await ac.post("/api/strategies/outcome", json=body)
            refused = await ac.post("/api/strategies/outcome", json={**body, "payoff_step": 20})
            assert first.status_code == HTTPStatus.OK, first.text
            assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, refused.text
            await _add(session, "scenarios.nifty_step_points", "200", "gcset-b1-1")
            await _add(session, "scenarios.nifty_anchor_points", "200", "gcset-b1-2")
            await _add(session, "scenarios.payoff_step_1", "20", "gcset-b1-3")
            second = await ac.post("/api/strategies/outcome", json=body)
            served = await ac.post("/api/strategies/outcome", json={**body, "payoff_step": 20})
        assert second.status_code == HTTPStatus.OK, second.text
        assert served.status_code == HTTPStatus.OK, served.text
        assert first.json()["scenario"]["step"] == "100" and second.json()["scenario"]["step"] == "200"
        assert first.json()["scenario"]["levels"] != second.json()["scenario"]["levels"]
        table = served.json()["payoff_table"]
        levels = [Decimal(r["level"]) for r in table["rows"]]
        assert table["step"] == "20" and {b - a for a, b in zip(levels, levels[1:], strict=False)} == {Decimal(20)}
    finally:
        await trans.rollback()
        await conn.close()
