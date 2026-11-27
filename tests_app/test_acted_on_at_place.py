"""Live test 27 Nov 2026, item 10 (REQ-112 AC-2): an adjustment opportunity is "Acted on" only when a paper order of
its basket is PLACED (accepted); staging the basket, a cancelled basket, or a refused placement leaves it "Open".

Through the real routes on a fresh migrated database (ADJ-02), as the screen takes the path: the record is open, the
builder places the basket naming it (POST /paper/strategies/{id}/orders with ``suggestion_ids``) and only that accepted
answer moves it to acted_on, in the order's own transaction.
"""
from __future__ import annotations

import asyncio

import test_adjustment_check as check_test
from ofo_app import actionable_alerts, playbook_store, strategy_store
from test_adjustment_check import _seeded
from test_adjustment_history_why import CREATED, OK, _book, _place, _records
from test_adjustment_opportunities import _call, _check, _clean, chk, open_flags

app_db_url = check_test.app_db_url


async def _seeded_on_the_system_plan(engine, monkeypatch) -> int:
    """ADJ-02 with the plan a copy of the SYSTEM iron condor playbook, whatever an earlier test left active for the
    user (test_adjustment_plan makes an edited "Core own" playbook the user's active one in the shared database, and
    ``_seeded`` copies the active one: its T-01 then no longer fires and this test found no T-01 record)."""
    sid = await _seeded(engine, monkeypatch, "ADJ-02")
    async with engine.begin() as conn:
        system = (await playbook_store.list_for_type(conn, "owner", "ic"))[0]  # the system playbook comes first
        assert system.is_system, system.name
        await playbook_store.accept_plan(conn, "owner", sid, system.id)
    return sid


async def _record(engine, sid: int, rule: str):
    """This strategy's record of the rule; a clear failure (not StopIteration) when the check never opened it."""
    records = await _records(engine, sid)
    found = next((r for r in records if r.rule_id == rule), None)
    assert found is not None, f"no {rule} record on strategy {sid}; it has {sorted(r.rule_id for r in records)}"
    return found


async def _open_all(engine, sid: int) -> None:
    """One record per rule the check names true (ADJ-02: T-01, T-03, T-09), as the worker's gate opens them. The
    check's own ``flag`` kind is used where it says so; a rule it calls ``already_true`` (the sandbox clock is past the
    scenario's time) is opened the same way, so the test starts from open records whatever the clock."""
    reply = await _check(sid)
    reply = {**reply, "results": [{**x, "kind": "flag"} if x["kind"] in ("flag", "already_true") else x
                                  for x in reply["results"]]}
    async with engine.connect() as conn:
        body = (await chk.resolve(conn, "owner", sid, reply["strategy_type"])).body
    await open_flags(engine, sid, reply, body)


async def _shown(sid: int, rec_id: int) -> tuple[str, str]:
    status, inbox = await _call("GET", "/api/adjustment-opportunities")
    assert status == OK
    r = next((r for g in inbox["groups"] if g["strategy_id"] == sid for r in g["records"] if r["id"] == rec_id), None)
    assert r is not None, f"record {rec_id} of strategy {sid} is not in the inbox"
    return r["outcome"], r["outcome_text"]


async def test_only_an_accepted_paper_order_stamps_acted_on(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded_on_the_system_plan(app_db_url, monkeypatch))
    await _open_all(app_db_url, sid)
    t01 = await _record(app_db_url, sid, "T-01")
    t03 = await _record(app_db_url, sid, "T-03")

    # staged / cancelled basket: nothing was sent to the server, the opportunity reads Open
    assert (await _shown(sid, t01.id))[0] == "open"

    # a basket naming an unknown id places (201): the id is skipped, never a refusal (a stale or hand-edited URL must
    # not block an exit); the known record is stamped and linked with the order
    status, out = await _place(app_db_url, sid, [t01.id, 987654321])
    assert status == CREATED, out
    new_id = (await _book(app_db_url, sid))[-1].id
    rec = await _record(app_db_url, sid, "T-01")
    assert (rec.outcome, rec.placed_order_ids) == ("acted_on", (new_id,))
    assert [e["outcome"] for e in rec.timeline if "outcome" in e] == ["open", "acted_on"]
    assert (await _shown(sid, t01.id))[0] == "acted_on"
    assert (await _shown(sid, t03.id))[0] == "open"  # a record the basket did not name is untouched

    # a second basket naming it again is accepted and leaves its first link: a record's state never refuses an order
    status, _ = await _place(app_db_url, sid, [t01.id])
    assert status == CREATED
    assert (await _record(app_db_url, sid, "T-01")).placed_order_ids == (new_id,)

    # a basket with one open and one lapsed record: placed, the open one acted on, the lapsed one unchanged
    t09 = await _record(app_db_url, sid, "T-09")
    async with app_db_url.begin() as conn:
        await actionable_alerts.close_by_system(conn, "owner", sid, playbook_store.LAPSE_STRATEGY_CLOSED, ids=[t03.id])
    status, out = await _place(app_db_url, sid, [t09.id, t03.id], reduce=True)
    assert status == CREATED, out
    last = (await _book(app_db_url, sid))[-1].id
    t09, t03 = await _record(app_db_url, sid, "T-09"), await _record(app_db_url, sid, "T-03")
    assert (t09.outcome, t09.placed_order_ids) == ("acted_on", (last,))
    assert (t03.outcome, t03.placed_order_ids) == ("lapsed", None)


async def _link(engine, sid: int, rec_id: int) -> None:
    async with engine.begin() as conn:
        await playbook_store.link_orders(conn, "owner", sid, rec_id, [1], None)


async def test_a_record_that_stops_being_open_or_does_not_exist_never_refuses(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded_on_the_system_plan(app_db_url, monkeypatch))
    await _open_all(app_db_url, sid)
    t01, t03 = await _record(app_db_url, sid, "T-01"), await _record(app_db_url, sid, "T-03")
    # unknown id, and another strategy's id: skipped, nothing raised, nothing written
    await _link(app_db_url, sid, 987654321)
    await _link(app_db_url, sid + 1000, t01.id)
    # belt and braces: act_on finds the record no longer open -> skipped, not raised
    async def not_open(conn, user_ref, suggestion_id):
        raise strategy_store.StrategyStoreError(playbook_store.SUGGESTION_NOT_OPEN, "x")
    monkeypatch.setattr(playbook_store, "act_on", not_open)
    await _link(app_db_url, sid, t01.id)
    monkeypatch.undo()
    assert (await _record(app_db_url, sid, "T-01")).outcome == "open"
    # the race: a Dismiss holds the row open (uncommitted) while the placement links; the placement waits on the lock,
    # then sees the committed state and skips - it neither raises nor stamps
    dismisser = await app_db_url.connect()
    tx = await dismisser.begin()
    await playbook_store.dismiss(dismisser, "owner", t03.id)
    placing = asyncio.create_task(_link(app_db_url, sid, t03.id))
    await asyncio.sleep(0.5)
    # waits on the dismisser's row lock (the lock, or act_on's own UPDATE, whichever comes first)
    assert not placing.done()
    await tx.commit()
    await dismisser.close()
    await asyncio.wait_for(placing, 10)
    t03 = await _record(app_db_url, sid, "T-03")
    assert (t03.outcome, t03.placed_order_ids) == ("dismissed", None)
