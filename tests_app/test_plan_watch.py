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
NA_CALL = "Not applicable: the call side is closed"
NA_PUT = "Not applicable: the put side is closed"


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


async def _exit_side(app_engine, sid: int, kind: str) -> None:
    """Exit every open leg of one side ("CE" / "PE") with a reducing order at a later time (as the book does it)."""
    import datetime  # noqa: PLC0415

    from ofo_app import tracked_contracts  # noqa: PLC0415
    from ofo_app.paper_book import NewOrder  # noqa: PLC0415
    from ofo_app.routes.paper import identity_of  # noqa: PLC0415

    async with app_engine.begin() as conn:
        orders = await paper_store.load(conn, sid)
        ids = sorted({o.order.contract_id for o in orders})
        found = {c.contract_id: c for c in await tracked_contracts.resolve(conn, ids)}
        net: dict[int, int] = {}
        for o in orders:
            net[o.order.contract_id] = net.get(o.order.contract_id, 0) + (
                o.order.quantity if o.order.side == "BUY" else -o.order.quantity)
        later = max(o.order.placed_at for o in orders) + datetime.timedelta(minutes=30)
        closing = [NewOrder(cid, "SELL" if q > 0 else "BUY", abs(q), Decimal("10"), "exit", later)
                   for cid, q in net.items() if q and identity_of(found[cid])[1].value == kind]
        assert len(closing) == 2, closing  # noqa: PLR2004 - a condor side has two legs
        await paper_store.place(conn, "owner", sid, closing)


async def _with_side_rule(app_engine, sid: int) -> None:
    """The system iron condor plan has no rule that needs a side (T-05, one side's value x the other's, is off and in
    no rule), so the strategy gets its own plan: the system rules plus a rule on T-05, switched on."""
    import copy  # noqa: PLC0415

    from ofo_app import playbook_store  # noqa: PLC0415

    async with app_engine.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
        mine = await playbook_store.duplicate(conn, "owner", system.id, f"Side rule {sid}")
        body = copy.deepcopy(mine.body)
        body["triggers"]["T-05"]["on"] = True
        body["rules"].append({"any_of": ["T-05"], "id": "T-05"})
        saved = await playbook_store.save_in_place(conn, "owner", mine.id, body, mine.version)
        await playbook_store.accept_plan(conn, "owner", sid, saved.id)


async def test_closed_call_side_rules_read_not_applicable_and_put_side_keeps_working(app_db_url, monkeypatch):  # noqa: F811
    """ADR-330 (2)(a), P10: the call side fully exited -> each rule that needs the call side reads "Not applicable: the
    call side is closed" (state not_applicable, the existing state / reason fields); the rules that still fit keep
    their own state."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _with_side_rule(app_db_url, sid)
    status, before = await _watch(sid)
    assert status == OK, before
    assert not [x for x in before["lines"] if x["reason"] == NA_CALL]  # nothing closed yet
    assert next(x for x in before["lines"] if x["key"] == "T-05")["state"] in ("watching", "fired")
    await _exit_side(app_db_url, sid, "CE")
    status, out = await _watch(sid)
    assert status == OK, out
    shown = {x["key"]: x for x in out["lines"] if x["section"] == "plan"}
    na = {k: x for k, x in shown.items() if x["state"] == "not_applicable"}
    assert set(na) == {"T-05"}, shown  # the one rule that needs both sides; every other rule still fits
    for x in na.values():
        assert x["reason"] == NA_CALL, x
        assert x["now"] is None and x["fires_at"] is None and x["distance_rs"] is None and x["distance_pct"] is None
    kept = [x for x in shown.values() if x["state"] != "not_applicable"]
    assert {"T-07", "T-06"} <= {x["key"] for x in kept}  # target and loss stop are not side rules
    assert {x["state"] for x in kept if x["key"] in ("T-07", "T-06")} <= {"watching", "fired"}  # they keep working
    assert {x["state"] for x in kept} <= {"watching", "fired", "not_computable"}, kept  # each its own state
    assert all(x["reason"] != NA_CALL for x in kept)


async def test_closed_put_side_reads_put_and_unreadable_entry_judges_no_side(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")  # its own strategy: the call test closed ADJ-01's call side
    await _with_side_rule(app_db_url, sid)
    await _exit_side(app_db_url, sid, "PE")
    status, out = await _watch(sid)
    assert status == OK, out
    reasons = {x["reason"] for x in out["lines"] if x["state"] == "not_applicable" and x["section"] == "plan"}
    assert reasons == {NA_PUT}, reasons
    from ofo_app.routes import plan_watch as pw  # noqa: PLC0415
    monkeypatch.setattr(pw, "_closed", lambda _run: frozenset())  # an unreadable entry: nothing judged closed
    status, out = await _watch(sid)
    assert status == OK and not [x for x in out["lines"] if x["reason"] == NA_PUT], out
