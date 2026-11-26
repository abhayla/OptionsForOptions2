"""P10 (ADR-330 (13), (11)): GET /api/strategies/{id}/plan-watch, the live "Plan watch" lines: one per trigger with
fires at / now / distance / state, from the one engine's evaluation (the adjustment check) and the trigger store.
Answer states: plan -> lines; no plan -> the NO_PLAN_TEXT sentence, no plan lines, armed triggers still listed;
prices not live -> state paused, no ``now``; strategy not found -> 404; evaluation unreadable -> refusal, no lines.
"""
from __future__ import annotations

from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from ofo.errors.explanations import NO_PLAN_TEXT
from ofo_app import db as app_db
from ofo_app import paper_store, paper_trigger_store
from test_adjustment_check import (
    _reset_engine,
    _seeded,
    app_db_url,  # noqa: F401 - the fixture of the check tests
)

OK, NOT_FOUND = 200, 404
KEYS = {"key", "kind", "label", "unit", "fires_at", "now", "distance_rs", "distance_pct", "state", "reason"}
STATES = {"watching", "fired", "not_applicable", "not_computable", "paused"}


async def _arm(app_engine, sid: int) -> None:
    """One armed index exit (above) and a leg stop on each of two open short legs."""
    async with app_engine.begin() as conn:
        orders = await paper_store.load(conn, sid)
        shorts = sorted({o.order.contract_id for o in orders if o.order.side == "SELL"})[:2]
        await paper_trigger_store.add(conn, sid, paper_trigger_store.NewTrigger(
            "conditional_exit", "above", Decimal("23400"), underlying="NIFTY"))
        for cid in shorts:
            await paper_trigger_store.add(conn, sid, paper_trigger_store.NewTrigger(
                "leg_stop", "above", Decimal("90"), contract_id=cid))


async def _watch(strategy_id: int) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    _reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/api/strategies/{strategy_id}/plan-watch")
    await app_db.close_db()
    return r.status_code, r.json()


async def test_planned_condor_lines(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _arm(app_db_url, sid)
    status, out = await _watch(sid)
    assert status == OK, out
    assert out["plan_state"] == "planned" and out["no_plan_text"] is None
    lines = out["lines"]
    assert all(set(x) >= KEYS and x["state"] in STATES for x in lines), lines
    kinds = [x["kind"] for x in lines]
    assert kinds.count("leg_stop") == 2 and kinds.count("index_exit") == 1  # noqa: PLR2004
    by_key = {x["key"]: x for x in lines}
    assert {"T-07", "T-06", "stop.credit_x"} <= set(by_key), sorted(by_key)  # target, loss stop, 2x-credit stop
    assert by_key["T-07"]["kind"] == "target" and by_key["T-06"]["kind"] == "stop"
    index = next(x for x in lines if x["kind"] == "index_exit")
    assert (index["fires_at"], index["state"]) == ("23400.00", "watching")
    assert index["now"] == "23050.00" and index["distance_rs"] == "350.00"  # the scenario's spot, 23400 - 23050
    assert out["armed_heading"] is not None


async def test_no_plan_sentence_and_armed_triggers_still_listed(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-43", plan=False)
    await _arm(app_db_url, sid)
    status, out = await _watch(sid)
    assert status == OK, out
    assert out["plan_state"] == "no_plan" and out["no_plan_text"] == NO_PLAN_TEXT
    assert [x["kind"] for x in out["lines"] if x["kind"] in ("target", "stop", "credit_stop", "rule")] == []
    assert sorted(x["kind"] for x in out["lines"]) == ["index_exit", "leg_stop", "leg_stop"]


async def test_unknown_strategy_is_404(app_db_url, monkeypatch):  # noqa: F811
    await _seeded(app_db_url, monkeypatch, "ADJ-01")
    status, _out = await _watch(987654)
    assert status == NOT_FOUND


async def test_prices_not_live_every_line_is_paused_with_no_now(app_db_url, monkeypatch):  # noqa: F811
    from ofo_app import adjustment_check as check  # noqa: PLC0415

    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _arm(app_db_url, sid)
    monkeypatch.setattr(check, "prices_fresh", lambda _ctx: False)
    status, out = await _watch(sid)
    assert status == OK, out
    assert out["lines"] and all(x["state"] in ("paused", "not_computable", "not_applicable") for x in out["lines"])
    assert all(x["now"] is None and x["distance_rs"] is None for x in out["lines"])  # absent, never 0
    assert {x["state"] for x in out["lines"] if x["kind"] in ("index_exit", "leg_stop")} == {"paused"}
    target = next(x for x in out["lines"] if x["kind"] == "target")
    assert target["state"] in ("paused", "not_computable")  # the check itself reads a stale price as not checked


async def test_records_store_unreadable_is_a_refusal_with_no_lines(app_db_url, monkeypatch):  # noqa: F811
    from ofo_app import playbook_store  # noqa: PLC0415
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415

    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")

    async def broken(*_a, **_k):
        raise OperationalError("SELECT", {}, Exception("connection lost"))
    monkeypatch.setattr(playbook_store, "open_suggestions", broken)
    status, out = await _watch(sid)
    assert status == 503 and "lines" not in out, out  # noqa: PLR2004 - Failure.UPSTREAM_BUSY
