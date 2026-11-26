"""ADR-330 (11): only a strategy's own plan applies. ``adjustment_check.resolve`` on a migrated database.

A playbook is only a source to copy from when a plan is made; a strategy with no plan resolves "none" (no body), so the
worker watches nothing for it. Answer states: plan stated -> "plan"; absent (no plan, typed or untyped) -> "none";
another user's strategy -> its plan is not visible, "none"; plan body unreadable -> refused (raises), never "none".

Spec basis: ADR-330 (11), SPEC CHANGE to REQ-158 (order plan > chosen playbook > system default ends).
"""
from __future__ import annotations

import json

import pytest
from ofo_app import adjustment_check as check
from ofo_app import playbook_store
from sqlalchemy import text

LEG = {"contract_id": 1001, "action": "SELL", "instrument": "CE", "strike": "23000", "expiry": "2026-10-29",
       "quantity": 75}
DEFINITION = json.dumps({"schema_version": 1, "underlying": "NIFTY", "legs": [LEG], "rules_ref": None,
                         "risk_limits": {}, "preferences": {}})
INSERT = text("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
              "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1) RETURNING id")
USER = "test-own-plan-only"
OTHER = "test-own-plan-only-other"


@pytest.fixture
async def conn(app_engine):
    async with app_engine.connect() as c:
        trans = await c.begin()
        try:
            yield c
        finally:
            await trans.rollback()


async def _strategy(conn, user: str = USER) -> int:
    return (await conn.execute(INSERT, {"u": user, "d": DEFINITION})).scalar_one()


async def _plan(conn, sid: int) -> None:
    pb = await playbook_store.active_for(conn, USER, "ic")
    await playbook_store.accept_plan(conn, USER, sid, pb.id)


async def test_no_plan_active_playbook_resolves_none(conn):
    sid = await _strategy(conn)
    assert (await playbook_store.active_for(conn, USER, "ic")).body  # the type DOES have an active playbook
    got = await check.resolve(conn, USER, sid, "ic")
    assert (got.source, got.body, got.playbook_id) == ("none", None, None)


async def test_own_plan_resolves_plan(conn):
    sid = await _strategy(conn)
    await _plan(conn, sid)
    got = await check.resolve(conn, USER, sid, "ic")
    assert got.source == "plan" and got.body is not None


async def test_no_plan_no_type_resolves_none(conn):
    got = await check.resolve(conn, USER, await _strategy(conn), None)
    assert (got.source, got.body) == ("none", None)


async def test_another_users_strategy_plan_is_not_visible(conn):
    sid = await _strategy(conn)
    await _plan(conn, sid)
    got = await check.resolve(conn, OTHER, sid, "ic")
    assert (got.source, got.body) == ("none", None)


async def test_plan_with_unreadable_body_is_refused_not_none(conn):
    sid = await _strategy(conn)
    await _plan(conn, sid)
    await conn.execute(text("UPDATE public.strategy_adjustment_plans SET body = CAST(:b AS JSONB) "
                            "WHERE strategy_id = :id"), {"b": '{"guards": {"max_adjustments": 1.5}}', "id": sid})
    with pytest.raises(ValueError, match="float"):
        await check.resolve(conn, USER, sid, "ic")
