"""GC-ADJ2 step 5 (REQ-112 AC-1/AC-2/AC-4/AC-6, REQ-162 AC-1..AC-3, REQ-045 AC-8): the check opens one suggestion
record per flagged rule, the inbox lists them grouped with their label and outcome, Dismiss / acted on write one final
outcome each, a cleared rule or a closed strategy lapses its records, and a not-checked rule never does.
Strategies come from the scenario library (seed_scenario), the check from GET /api/strategies/{id}/adjustment-check."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import test_adjustment_check as check_test
from httpx import ASGITransport, AsyncClient
from ofo.adjustment import playbook_eval as pe
from ofo_app import db as app_db
from ofo_app import playbook_store
from ofo_app.adjustment_readers import TrackedExited
from test_adjustment_check import _reset_engine, _seeded, seed_mod

app_db_url = check_test.app_db_url  # the fresh-database fixture of the check test

OK, NOT_FOUND, CONFLICT, INVALID = 200, 404, 409, 422
ADJ02_FLAGS = 3  # T-01, T-03, T-09 (ADJ-02.json triggers_fired)
SYSTEM_LABEL = "Adjustment opportunity detected"
OWN_LABEL = "Your rule was triggered"


async def _call(method: str, url: str, body: Any = None, *, user: str | None = None,
                overrides: dict | None = None) -> tuple[int, Any]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    from ofo_app.routes.broker import current_user_ref  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    if user is not None:
        app.dependency_overrides[current_user_ref] = lambda: user
    app.dependency_overrides.update(overrides or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.request(method, url, json=body)
    await app_db.close_db()
    return r.status_code, r.json()


async def _check(sid: int) -> dict:
    status, body = await _call("GET", f"/api/strategies/{sid}/adjustment-check")
    assert status == OK, body
    return body


MARK: dict[int, int] = {}


async def _clean(engine, sid: int) -> int:
    """Lapse what earlier tests left open on the strategy; later reads see only records above the mark."""
    async with engine.begin() as conn:
        await playbook_store.lapse_all(conn, "owner", sid, playbook_store.LAPSE_STRATEGY_CLOSED)
        MARK[sid] = max((r.id for r in await playbook_store.suggestions(conn, "owner", sid)), default=0)
    return sid


async def _records(engine, sid: int) -> list[playbook_store.Suggestion]:
    async with engine.begin() as conn:
        return [r for r in await playbook_store.suggestions(conn, "owner", sid) if r.id > MARK.get(sid, 0)]


def _mine(inbox: dict, sid: int) -> list[dict]:
    """The inbox's groups of this strategy holding a record this test made, newest first."""
    return [g for g in inbox["groups"] if g["strategy_id"] == sid
            and any(r["id"] > MARK.get(sid, 0) for r in g["records"])]


async def _inbox(**kw) -> dict:
    status, body = await _call("GET", "/api/adjustment-opportunities", **kw)
    assert status == OK, body
    return body


async def test_adj02_first_check_opens_three_records_a_second_check_opens_none(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    first = await _check(sid)
    recs = await _records(app_db_url, sid)
    assert sorted((r.rule_id, r.outcome) for r in recs) == [("T-01", "open"), ("T-03", "open"), ("T-09", "open")]
    assert len({r.group for r in recs}) == 1 and recs[0].group  # one check = one group (REQ-045 AC-8)
    assert {r.source for r in recs} == {"system"}
    assert sorted((r.value, r.threshold) for r in recs if r.rule_id == "T-01") == [
        (Decimal("0.3416"), Decimal("0.5000"))]
    flag_ids = {x["rule_id"]: x["suggestion_id"] for x in first["results"] if x["kind"] == "flag"}
    assert flag_ids == {r.rule_id: r.id for r in recs}
    await _check(sid)  # attack 1: two checks in a row -> still exactly 3 records, not 6
    again = await _records(app_db_url, sid)
    assert [r.id for r in again] == [r.id for r in recs] and len(again) == ADJ02_FLAGS
    inbox = await _inbox()
    assert len(_mine(inbox, sid)) == 1
    g = _mine(inbox, sid)[0]
    assert (g["strategy_id"], g["strategy_name"], g["label"], g["summary"], g["has_open"]) == (
        sid, f'"{seed_mod.strategy_name("ADJ-02")}"', SYSTEM_LABEL, "3 adjustment conditions triggered", True)
    assert [(r["rule_id"], r["outcome_text"], r["can_act"]) for r in g["records"]] == [
        ("T-01", "Open", True), ("T-03", "Open", True), ("T-09", "Open", True)]
    assert g["records"][0]["condition"] == "T-01: 0.3416 at or below 0.5000"
    assert {c["outcome"]: c["count"] for c in inbox["counts"]}["open"] == ADJ02_FLAGS and inbox["empty_text"] is None
    assert all(r["outcome"] != "open" for x in inbox["groups"] if x is not g for r in x["records"])


async def test_adj01_opens_none_and_the_inbox_says_so(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-01"))
    await _check(sid)
    assert await _records(app_db_url, sid) == []
    assert _mine(await _inbox(), sid) == []
    inbox = await _inbox(user="a-user-with-no-strategy")
    assert (inbox["groups"], inbox["empty_text"]) == ([], "No adjustment opportunities")
    assert [r["text"] for r in inbox["dismiss_reasons"]] == [
        "Expected and within my plan", "I will act later", "Not relevant", "Other"]


async def test_dismiss_writes_one_timeline_entry_and_a_final_record_is_refused(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _check(sid)
    t01 = next(r for r in await _records(app_db_url, sid) if r.rule_id == "T-01")
    status, out = await _call("POST", f"/api/adjustment-opportunities/{t01.id}/dismiss", {"reason": "not_relevant"})
    assert (status, out["outcome"], out["outcome_text"]) == (OK, "dismissed", "You dismissed this")
    after = next(r for r in await _records(app_db_url, sid) if r.id == t01.id)
    assert [(e["outcome"], e.get("suggestion_id")) for e in after.timeline] == [("open", None), ("dismissed", t01.id)]
    assert after.dismiss_reason == "not_relevant"
    # attack 3: a final record -> the store's refusal text, nothing written
    status, out = await _call("POST", f"/api/adjustment-opportunities/{t01.id}/acted-on")
    assert status == CONFLICT and out["what_happened"] == "This adjustment opportunity already has its outcome."
    status, out = await _call("POST", f"/api/adjustment-opportunities/{t01.id}/dismiss", {"reason": "other"})
    assert status == CONFLICT
    final = next(r for r in await _records(app_db_url, sid) if r.id == t01.id)
    assert (final.outcome, len(final.timeline), final.dismiss_reason) == ("dismissed", 2, "not_relevant")
    status, _ = await _call("POST", f"/api/adjustment-opportunities/{t01.id + 1}/dismiss", {"reason": "nonsense"})
    assert status == INVALID  # off the closed list
    row = next(r for r in _mine(await _inbox(), sid)[0]["records"] if r["id"] == t01.id)
    assert (row["outcome_text"], row["detail"], row["can_act"]) == ("You dismissed this", "Not relevant", False)


async def test_acted_on_and_the_paper_wording(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _check(sid)
    t03 = next(r for r in await _records(app_db_url, sid) if r.rule_id == "T-03")
    status, out = await _call("POST", f"/api/adjustment-opportunities/{t03.id}/acted-on")
    assert (status, out["outcome"]) == (OK, "acted_on")
    rows = {r["id"]: r for r in _mine(await _inbox(), sid)[0]["records"]}
    assert rows[t03.id]["outcome_text"] == "Acted on - Paper - not sent to Zerodha"
    counts = {c["outcome"]: c["count"] for c in (await _inbox())["counts"]}
    assert counts["open"] == ADJ02_FLAGS - 1 and counts["acted_on"] >= 1
    await _check(sid)  # T-03 still flagged, its record is final: a new open record for the next occurrence
    assert sorted((r.rule_id, r.outcome) for r in await _records(app_db_url, sid)) == [
        ("T-01", "open"), ("T-03", "acted_on"), ("T-03", "open"), ("T-09", "open")]


async def test_another_users_record_is_not_found_and_nothing_is_written(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _check(sid)
    t09 = next(r for r in await _records(app_db_url, sid) if r.rule_id == "T-09")
    for path, body in (("dismiss", {"reason": "other"}), ("acted-on", None)):  # attack 4
        status, out = await _call("POST", f"/api/adjustment-opportunities/{t09.id}/{path}", body, user="someone-else")
        assert status == NOT_FOUND and out["what_happened"] == "This adjustment opportunity was not found."
    status, _ = await _call("POST", "/api/adjustment-opportunities/987654321/acted-on")
    assert status == NOT_FOUND
    assert next(r for r in await _records(app_db_url, sid) if r.id == t09.id).outcome == "open"
    assert (await _inbox(user="someone-else"))["groups"] == []


async def test_a_cleared_rule_lapses_and_a_not_checked_rule_never_does(app_db_url, monkeypatch):
    from ofo_app.routes.adjustment_check import _sync_records  # noqa: PLC0415 - the check route's own record step
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _check(sid)
    not_checked = pe.Evaluation(None, None, (pe.NotChecked("T-01", "T-01", "withheld_no_spot"),), {}, ())
    async with app_db_url.begin() as conn:  # attack 2: no spot -> neither flagged nor cleared
        assert await _sync_records(conn, "owner", sid, not_checked, "system") == {}
    assert {r.rule_id: r.outcome for r in await _records(app_db_url, sid)}["T-01"] == "open"
    cleared = pe.Evaluation(None, None, (), {}, ("T-01",))
    async with app_db_url.begin() as conn:
        await _sync_records(conn, "owner", sid, cleared, "system")
    recs = {r.rule_id: r for r in await _records(app_db_url, sid)}
    assert (recs["T-01"].outcome, recs["T-01"].lapse_reason) == ("lapsed", "condition_stopped")
    assert (recs["T-03"].outcome, recs["T-09"].outcome) == ("open", "open")
    row = next(r for g in _mine(await _inbox(), sid) for r in g["records"] if r["id"] == recs["T-01"].id)
    assert (row["outcome_text"], row["detail"]) == ("Lapsed", "The condition stopped holding")


async def test_an_exited_strategy_lapses_every_open_record(app_db_url, monkeypatch):
    from ofo_app.routes.adjustment import get_tracked_reader  # noqa: PLC0415

    async def exited(_strategy_id, _rates):
        raise TrackedExited("no open option leg")

    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _check(sid)
    status, _ = await _call("GET", f"/api/strategies/{sid}/adjustment-check",
                            overrides={get_tracked_reader: lambda: exited})
    assert status == CONFLICT
    recs = await _records(app_db_url, sid)
    assert {(r.outcome, r.lapse_reason) for r in recs} == {("lapsed", "strategy_closed")} and len(recs) == ADJ02_FLAGS


async def test_the_own_playbook_label(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
        own = await playbook_store.duplicate(conn, "owner", system.id, "Mine")
        await playbook_store.make_active(conn, "owner", own.id)
    await _check(sid)
    assert [g["label"] for g in _mine(await _inbox(), sid)] == [OWN_LABEL]


@pytest.mark.parametrize("bad", [0, -1])
async def test_an_impossible_id_is_not_found(app_db_url, bad):
    status, _ = await _call("POST", f"/api/adjustment-opportunities/{bad}/acted-on")
    assert status == NOT_FOUND
