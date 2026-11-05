# ruff: noqa: E501, PLR2004 - long comments; basket sizes are literal test data
"""IC e2e paper contract, Stage C3 (design decision 11, REQ-112): every adjustment record ends in its outcome, read from
what was actually placed on paper: acted on (orders placed under its suggestion id), completed (every leg of the prepared
basket placed), partly completed (some), lapsed (the crossing cleared / the gate closed it).

The pure rules run without a database (first block); the DB block walks the real route on a throwaway database: Stage A seed
-> frame -> approaches route prepares A-05 -> record acted on -> basket posted with the suggestion id and the basket size ->
the inbox route is read back. Each test has its OWN strategy name (see _setup in the B3 file).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
import test_ic_approaches_paper_legs as b3
import test_ic_paper_loop_core as core
from httpx import ASGITransport, AsyncClient
from ofo_app import playbook_store, scenario_mode
from ofo_app.playbook_store import Suggestion

OK, CREATED = 200, 201
APPROACH, PATH, FRAME = "A-05", "PATH-01", 2
AT = datetime.datetime(2026, 11, 5, 9, 30, tzinfo=datetime.UTC)


def _s(outcome: str, *entries: dict) -> Suggestion:
    head = {"at": "x", "outcome": "open"}
    return Suggestion(1, 1, "T-01", "T-01", None, D("0.5"), D("0.5"), AT, outcome, None, [head, *entries])


def _placed(ids, legs="absent") -> dict:
    e = {"at": "x", "event": "orders_placed", "order_ids": ids}
    if legs != "absent":
        e["basket_legs"] = legs
    return e


# ---- pure rules: every answer state ---------------------------------------------------------------------------------
def test_open_dismissed_and_lapsed_are_shown_as_stored():
    assert [_s(o).shown_outcome for o in ("open", "dismissed", "lapsed")] == ["open", "dismissed", "lapsed"]


def test_acted_on_with_no_orders_is_acted_on_never_completed():  # attack 4
    assert _s("acted_on").shown_outcome == "acted_on"
    assert _s("acted_on", _placed([], 2)).shown_outcome == "acted_on"


def test_every_leg_placed_is_completed_and_one_missing_is_partly_completed():  # attack 1
    assert _s("acted_on", _placed([5, 6, 7, 8], 4)).shown_outcome == "completed"
    assert _s("acted_on", _placed([5, 6, 7], 4)).shown_outcome == "partly_completed"
    assert _s("acted_on", _placed([5], 4)).shown_outcome == "partly_completed"


def test_unsaid_unreadable_or_inconsistent_basket_sizes_stay_acted_on():
    for legs in (None, 0, -1, "4", 2.0, True):
        assert _s("acted_on", _placed([5, 6], legs)).shown_outcome == "acted_on", legs
    assert _s("acted_on", _placed([5, 6])).shown_outcome == "acted_on"  # an older record: size not said
    assert _s("acted_on", _placed([5, 6, 7], 2)).shown_outcome == "acted_on"  # more orders than legs
    assert _s("acted_on", _placed("junk", 2)).shown_outcome == "acted_on"  # unreadable order list
    assert _s("acted_on", _placed([5, 6.5], 2)).shown_outcome == "acted_on"


# ---- the DB walk -----------------------------------------------------------------------------------------------------
async def _prepare(ac: AsyncClient, sid: int, frame: int) -> dict:
    check = await ac.get(f"/api/strategies/{sid}/adjustment-check")
    assert check.status_code == OK, check.text
    assert scenario_mode.current().frame == frame
    prepared = await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})
    assert prepared.status_code == OK, prepared.text
    built = next(a for a in prepared.json()["approaches"] if a["id"] == APPROACH)
    assert built["refusal"] is None and len(built["trades"]) >= 2, built  # a basket of several legs
    return built


async def _orders(built: dict, sid: int, frame: int) -> list[dict]:
    net = await core._net(sid)
    out = []
    for t in built["trades"]:
        cid = await core._contract_id(t)
        closes = (net.get(cid, 0) < 0 and t["action"] == "BUY") or (net.get(cid, 0) > 0 and t["action"] == "SELL")
        out.append({"contract_id": cid, "side": t["action"], "quantity": t["quantity"], "price": t["price"],
                    "kind": "exit" if closes else "open"})
    return out


async def _record(sid: int, rule: str = "T-01") -> int:
    async with core._engine().begin() as conn:
        rec = await playbook_store.open_suggestion(conn, "owner", sid, rule, trigger_id=rule, stage=None,
                                                   value=D("0.5"), threshold=D("0.5"))
    return rec.id


async def _inbox(ac: AsyncClient) -> dict:
    r = await ac.get("/api/adjustment-opportunities")
    assert r.status_code == OK, r.text
    return r.json()


def _find(body: dict, rid: int) -> dict:
    return next(rec for g in body["groups"] for rec in g["records"] if rec["id"] == rid)


def _count(body: dict, outcome: str) -> int:
    return next(c["count"] for c in body["counts"] if c["outcome"] == outcome)


async def _walk(app_engine, monkeypatch, *, place: str, legs: str, second: bool = False):
    """place: none / first / all; legs: given / absent. Returns (inbox body, record id, other record id or None)."""
    sid = await b3._setup(app_engine, monkeypatch, PATH)
    await core._move(FRAME)
    rid = await _record(sid)
    other = await _record(sid, "T-02") if second else None
    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment of _setup
    scenario_mode._loaded.clear()
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as ac:
        built = await _prepare(ac, sid, FRAME)
        for r in (rid, other):
            if r is not None:
                acted = await ac.post(f"/api/adjustment-opportunities/{r}/acted-on", json={})
                assert acted.status_code == OK, acted.text
        orders = await _orders(built, sid, FRAME)
        sent = {"none": [], "first": orders[:1], "all": orders}[place]
        if sent:
            body = {"orders": sent, "suggestion_ids": [rid]}
            if legs == "given":
                body["basket_legs"] = len(built["trades"])
            placed = await ac.post(f"/paper/strategies/{sid}/orders", json=body)
            assert placed.status_code == CREATED, placed.text
        return await _inbox(ac), rid, other


@pytest.fixture
async def cleanup():
    yield
    await b3._cleanup()


async def test_acted_on_a_record_with_paper_orders_under_its_suggestion_id_shows_acted_on(app_engine, monkeypatch, cleanup):
    """Core proof: orders placed with the suggestion id (basket size not said) -> acted on, the link names them."""
    body, rid, _ = await _walk(app_engine, monkeypatch, place="all", legs="absent")
    assert _find(body, rid)["outcome"] == "acted_on"
    assert len(await b3._timeline_orders(rid)) == 1
    assert _count(body, "acted_on") == 1 and _count(body, "completed") == 0


async def test_completed_when_every_leg_of_the_prepared_basket_was_placed(app_engine, monkeypatch, cleanup):
    body, rid, _ = await _walk(app_engine, monkeypatch, place="all", legs="given")
    rec = _find(body, rid)
    assert rec["outcome"] == "completed" and rec["outcome_text"]["text"] == "Completed", rec
    assert _count(body, "completed") == 1 and _count(body, "acted_on") == 0


async def test_partly_completed_when_one_leg_is_missing(app_engine, monkeypatch, cleanup):  # attack 1
    body, rid, _ = await _walk(app_engine, monkeypatch, place="first", legs="given")
    rec = _find(body, rid)
    assert rec["outcome"] == "partly_completed" and rec["outcome_text"]["text"] == "Partly completed", rec
    assert _count(body, "partly_completed") == 1 and _count(body, "completed") == 0


async def test_acted_on_with_zero_orders_stays_acted_on(app_engine, monkeypatch, cleanup):  # attack 4
    body, rid, _ = await _walk(app_engine, monkeypatch, place="none", legs="given")
    assert _find(body, rid)["outcome"] == "acted_on"
    assert await b3._timeline_orders(rid) == []


async def test_two_records_on_one_strategy_each_count_their_own_orders_only(app_engine, monkeypatch, cleanup):  # attacks 2, 5
    body, rid, other = await _walk(app_engine, monkeypatch, place="all", legs="given", second=True)
    assert _find(body, rid)["outcome"] == "completed"
    assert _find(body, other)["outcome"] == "acted_on"  # the other record's basket placed nothing under ITS id
    assert await b3._timeline_orders(other) == []


async def test_lapsed_when_the_crossing_clears_and_it_is_no_longer_open(app_engine, monkeypatch, cleanup):  # attack 3
    sid = await b3._setup(app_engine, monkeypatch, PATH)
    await core._move(FRAME)
    rid = await _record(sid)
    async with core._engine().begin() as conn:
        await playbook_store.lapse(conn, "owner", rid, playbook_store.LAPSE_CONDITION_STOPPED)
    from ofo_app.main import create_app  # noqa: PLC0415
    scenario_mode._loaded.clear()
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as ac:
        body = await _inbox(ac)
    rec = _find(body, rid)
    assert rec["outcome"] == "lapsed" and rec["can_act"] is False, rec
    assert _count(body, "lapsed") == 1 and _count(body, "open") == 0
    assert not any(g["has_open"] for g in body["groups"] if g["strategy_id"] == sid)
