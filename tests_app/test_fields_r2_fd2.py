"""Lane FD2 item 4 (the fields the three screen lanes wait for): ``server_time`` on the exit-confirm replies and on
/api/market/exit-state; ``now_value`` / ``now_as_of`` on each adjustment opportunity; the monitoring-state entry whose
every exit rule is "not checked" because the expiry kind is unknown; the real-mode read of armed and fired exits.
Spec basis: ADR-330 (58), (60); ADR-008. Real PostgreSQL where a store is read; every test rolls back."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

import datetime
import json
from decimal import Decimal as D
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.marketdata.kite_provider import IST
from ofo_app.main import create_app
from ofo_app.routes.outcome import get_answer_clock, get_market_context
from test_paper_exit_risk import _ask, _condor, _exit_of, db  # noqa: F401 - fixtures
from test_paper_triggers_routes import notified  # noqa: F401 - fixture
from test_strategy_store import _client

SATURDAY = datetime.datetime(2026, 11, 28, 16, 2, tzinfo=IST)


# --- server_time ---------------------------------------------------------------------------------------------------

async def test_exit_state_carries_the_servers_own_aware_time():
    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: (lambda: SATURDAY)
    app.dependency_overrides[get_market_context] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = (await ac.get("/api/market/exit-state")).json()
    assert datetime.datetime.fromisoformat(body["server_time"]) == SATURDAY
    assert datetime.datetime.fromisoformat(body["server_time"]).utcoffset() is not None  # aware


async def test_the_exit_risk_reply_carries_the_servers_time(db):
    app, stored, ids, legs = await _condor(db)
    reply = await _ask(app, stored.id, _exit_of(ids, legs, [0]))
    assert reply.status_code == HTTPStatus.OK, reply.text
    stamp = datetime.datetime.fromisoformat(reply.json()["server_time"])
    assert stamp.utcoffset() is not None


async def test_the_armed_exits_reply_carries_the_servers_time(db):
    app, stored, ids, legs = await _condor(db)
    async with _client(app) as c:
        reply = await c.get(f"/paper/strategies/{stored.id}/armed-exits",
                            params={"orders": json.dumps(_exit_of(ids, legs, [0]))})
    assert reply.status_code == HTTPStatus.OK, reply.text
    assert datetime.datetime.fromisoformat(reply.json()["server_time"]).utcoffset() is not None


# --- now_value / now_as_of on each opportunity record ---------------------------------------------------------------

AT = datetime.datetime(2026, 11, 27, 11, 5, tzinfo=IST)


def _row(rule_id: str = "T-13", sid: int = 7):
    from ofo_app import playbook_store as ps  # noqa: PLC0415
    s = ps.Suggestion(id=1, strategy_id=sid, rule_id=rule_id, trigger_id=rule_id, stage=None, value=D("-4500.00"),
                      threshold=D("-4000.00"), shown_at=AT, outcome="open", dismiss_reason=None,
                      timeline=[{"group": "g1", "source": "own", "cmp": "le"}])
    return ps.InboxRow(s, "Condor", False)


def test_a_stored_reading_is_the_records_now_value_in_the_units_of_value():
    from ofo_app.routes.adjustment_opportunities import InboxOut, inbox_body  # noqa: PLC0415
    when = AT + datetime.timedelta(minutes=3)
    body = InboxOut.model_validate(inbox_body([_row()], readings={(7, "T-13"): (D("-4210.50"), when)}))
    (rec,) = body.groups[0].records
    assert (rec.value, rec.now_value, rec.now_as_of) == (D("-4500.00"), D("-4210.50"), when)


def test_no_stored_reading_for_that_rule_is_null_never_the_records_own_value():
    from ofo_app.routes.adjustment_opportunities import InboxOut, inbox_body  # noqa: PLC0415
    for readings in (None, {}, {(7, "T-99"): (D("1"), AT)}, {(8, "T-13"): (D("1"), AT)}):
        body = InboxOut.model_validate(inbox_body([_row()], readings=readings))
        (rec,) = body.groups[0].records
        assert (rec.now_value, rec.now_as_of) == (None, None)


async def test_the_workers_readings_round_trip_through_the_store_and_a_bad_snapshot_reads_as_none(redis_url):
    from ofo_app import feed_bus, rule_readings  # noqa: PLC0415
    client = feed_bus.new_client(redis_url)
    try:
        await client.flushdb()
        assert await rule_readings.read(client, AT) == {}  # nothing stored yet
        await rule_readings.publish(client, {(7, "T-13"): D("-4210.50")}, AT)
        assert await rule_readings.read(client, AT) == {(7, "T-13"): (D("-4210.50"), AT)}
        await client.set(rule_readings.key(), "not json")
        assert await rule_readings.read(client, AT) == {}
        await client.set(rule_readings.key(), json.dumps({"at": "2026-11-27T11:05:00", "values": {"7:T-13": "1"}}))
        assert await rule_readings.read(client, AT) == {}  # a time with no zone is not a reading
        both = {"at": AT.isoformat(), "values": {"7:T-13": "1.5e2", "x": "1"}}
        await client.set(rule_readings.key(), json.dumps(both))
        assert await rule_readings.read(client, AT) == {(7, "T-13"): (D("150"), AT)}  # the bad key is dropped alone
    finally:
        await client.aclose()


# --- the monitoring entry for "every exit rule is not checked: the expiry kind is unknown" -------------------------

async def test_expiry_kind_unknown_is_a_paused_entry_with_its_own_reason_and_the_badge():
    from ofo_app import monitoring_state as ms  # noqa: PLC0415
    from ofo_app.routes.monitoring_status import compose  # noqa: PLC0415
    found = {5: ms.Entry(5, ms.PAUSED, "expiry_kind_unknown", "", AT)}
    (out,) = compose(found, [5], AT)
    assert (out.watch_state, out.reason) == ("paused", "expiry_kind_unknown")
    assert str(out.badge_text) == "Monitoring paused"
    assert out.reason_text is not None and str(out.reason_text)  # the sentence below, or the generic one until it lands


def test_the_expiry_kind_sentence_is_the_owners_to_read_when_the_catalogue_holds_it():
    from ofo.errors.explanations import EXPLANATIONS  # noqa: PLC0415
    if "monitoring_why_expiry_kind_unknown" not in EXPLANATIONS:
        pytest.skip("explanations.py is Lane FC3's file: the exact entry is written in RESULTS-lane-fd2.md")
    from ofo_app import monitoring_state as ms  # noqa: PLC0415
    from ofo_app.routes.monitoring_status import compose  # noqa: PLC0415
    (out,) = compose({5: ms.Entry(5, ms.PAUSED, "expiry_kind_unknown", "", AT)}, [5], AT)
    assert str(out.reason_text) == ("Every exit rule is not checked because whether this trade expires weekly or "
                                    "monthly is not known.")


# --- #877: the paper route refuses an exit or a stop request for a real position ---------------------------------

# Lane R1 (ADR-330 (73)) rewrites the #877 tests below: a REAL position's exit and stop on the paper route are stored
# (records, nothing sent) and listed as armed; only a kind that could not be read is refused (503, fail closed).


async def _held(db):
    from ofo_app import held_entry_store  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)  # two practice orders: short 22800 CE, long 23000 CE
    await held_entry_store.record(db, stored.id, datetime.datetime(2026, 11, 27, 10, 0, tzinfo=IST), "Zerodha")
    return app, stored, ids


async def _orders(db, stored) -> int:
    from sqlalchemy import text  # noqa: PLC0415
    return (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": stored.id})).scalar_one()


async def test_877_an_exit_for_a_real_position_is_stored_as_a_record_and_no_paper_order(db, notified):
    from test_paper_armed_exits import _order as _body_of  # noqa: PLC0415
    from test_paper_routes import _new  # noqa: PLC0415
    app, stored, ids = await _held(db)
    before = await _orders(db, stored)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders",
                             json={"orders": [_body_of(_new(ids[0], "BUY", 65, "30", "exit"))]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert reply.json()["stored_not_sent"] is True and reply.json()["record"]["action"] == "exit"
    assert await _orders(db, stored) == before  # a record, never a paper order


async def test_877_a_stop_for_a_real_position_on_the_paper_route_is_stored_armed_and_recorded(db, notified):
    from ofo_app import paper_trigger_store  # noqa: PLC0415
    app, stored, ids = await _held(db)
    async with _client(app) as c:
        for body in ({"kind": "leg_stop", "contract_id": ids[0], "direction": "above", "level": "120.00"},
                     {"kind": "conditional_exit", "above": "23100"}):
            reply = await c.post(f"/paper/strategies/{stored.id}/triggers", json=body)
            assert reply.status_code == HTTPStatus.CREATED, reply.text
            assert reply.json()["stored_not_sent"] is True
    assert len(await paper_trigger_store.list_for(db, stored.id)) == 2  # noqa: PLR2004


async def test_877_a_paper_position_still_exits_and_stops_on_the_paper_route(db, notified):
    from test_paper_armed_exits import _order as _body_of  # noqa: PLC0415
    from test_paper_routes import _new  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)  # no held entry: a paper position
    async with _client(app) as c:
        stop = await c.post(f"/paper/strategies/{stored.id}/triggers",
                            json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above", "level": "120.00"})
        assert stop.status_code == HTTPStatus.CREATED, stop.text
        out = await c.post(f"/paper/strategies/{stored.id}/orders",
                           json={"orders": [_body_of(_new(ids[0], "BUY", 65, "30", "exit"))]})
        assert out.status_code == HTTPStatus.CREATED, out.text


# --- the real-mode read of armed and fired exits: the same shape as the paper read -----------------------------------

async def test_the_real_read_of_exits_has_the_papers_shape_and_an_empty_list_when_none_is_stored(db, notified):
    app, stored, _ids = await _held(db)  # a real position with no stop stored yet
    async with _client(app) as c:
        real = await c.get(f"/real/strategies/{stored.id}/triggers")
        paper = await c.get(f"/paper/strategies/{stored.id}/triggers")
        assert real.status_code == HTTPStatus.OK, real.text
        empty = {"triggers": [], "already_set": False, "already_armed": [], "position_kind": "real",
                 "position_kind_text": real.json()["position_kind_text"], "stored_not_sent": True, "record": None}
        assert real.json() == paper.json() == empty
        assert (await c.get("/real/strategies/999999999/triggers")).status_code == HTTPStatus.NOT_FOUND


async def test_the_real_read_names_an_armed_and_a_fired_exit_as_the_paper_read_does(db, notified):
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)
    armed = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D("120.00"), contract_id=ids[0]))
    fired = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "below", D("5.00"), contract_id=ids[1]))
    assert await triggers.claim_fire(db, fired)
    async with _client(app) as c:
        real = (await c.get(f"/real/strategies/{stored.id}/triggers")).json()
        paper = (await c.get(f"/paper/strategies/{stored.id}/triggers")).json()
    assert real == paper
    assert {t["id"]: t["state"] for t in real["triggers"]} == {armed: "armed", fired: "fired"}
    assert real["triggers"][0]["level"] in ("120.00", "5.00")  # exact decimal text


async def test_877_keeping_an_exit_of_a_real_position_answers_and_leaves_the_stored_stop_armed(db, notified):
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    app, stored, _ids = await _held(db)
    tid = await triggers.add(db, stored.id, triggers.NewTrigger("conditional_exit", "above", D("23100"),
                                                                underlying="NIFTY"))
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/triggers/{tid}/keep")
    assert reply.status_code == HTTPStatus.OK, reply.text[:200]  # nothing marked, nothing to keep: no churn
    assert [(r.trigger.id, r.cancelled_at is None) for r in await triggers.list_for(db, stored.id)] == [(tid, True)]


def test_lane_fes_four_why_codes_are_served_with_a_plain_sentence_never_blank():
    from ofo_app import monitoring_state as ms  # noqa: PLC0415
    from ofo_app.routes.monitoring_status import compose  # noqa: PLC0415
    for code in ("index_not_live", "leg_not_live", "exit_not_priced", "index_exits_not_run"):
        (out,) = compose({5: ms.Entry(5, ms.PAUSED, code, "", AT)}, [5], AT)
        assert out.reason == code and out.watch_state == "paused"
        assert str(out.badge_text) == "Monitoring paused"
        assert str(out.reason_text).strip()  # the catalogue's sentence, or the generic one


async def test_877_an_unknown_position_kind_is_refused_too_fail_closed(db, notified, monkeypatch):
    """Coordinator 28 Nov 07:30 (ADR-330 (64), ADR-016 to ADR-019): a kind that could not be read blocks the paper exit
    and the paper stop; it is never read as "paper"."""
    from test_paper_armed_exits import _order as _body_of  # noqa: PLC0415
    from test_paper_routes import _new  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)

    async def unknown(_db, sids):
        return dict.fromkeys(sids, "unknown")

    monkeypatch.setattr("ofo_app.routes.paper.store.kinds_of", unknown)
    before = await _orders(db, stored)
    async with _client(app) as c:
        out = await c.post(f"/paper/strategies/{stored.id}/orders",
                           json={"orders": [_body_of(_new(ids[0], "BUY", 65, "30", "exit"))]})
        stop = await c.post(f"/paper/strategies/{stored.id}/triggers",
                            json={"kind": "conditional_exit", "above": "23100"})
    assert out.status_code == HTTPStatus.SERVICE_UNAVAILABLE, out.text[:120]  # Lane R1: 503, nothing stored
    assert stop.status_code == HTTPStatus.SERVICE_UNAVAILABLE, stop.text[:120]
    assert await _orders(db, stored) == before
