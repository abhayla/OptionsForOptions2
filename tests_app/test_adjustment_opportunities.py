"""GC-ADJ2 step 5 (REQ-112 AC-1/AC-2/AC-4/AC-6, REQ-162 AC-1..AC-3, REQ-045 AC-8): one suggestion record per flagged
rule, the inbox lists them grouped with their label and outcome, Dismiss / acted on write one final outcome each, a
lapsed record reads "Lapsed". ADR-237 (6): only the background worker opens and lapses records, so the records here are
opened through the worker's store path (``worker_records``: ``playbook_store.open_suggestion`` with the fields
``background.DbGateStore.apply`` writes; lapses through ``DbGateStore.apply`` itself), from the flags of a real screen
check; the screen's check (GET /api/strategies/{id}/adjustment-check) only names them and never writes one.
Strategies come from the scenario library (seed_scenario)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import test_adjustment_check as check_test
from httpx import ASGITransport, AsyncClient
from ofo_app import adjustment_check as chk
from ofo_app import db as app_db
from ofo_app import playbook_store
from ofo_app.adjustment_readers import TrackedExited
from test_adjustment_check import _reset_engine, _seeded, seed_mod
from worker_records import lapse_through_worker, open_flags

app_db_url = check_test.app_db_url  # the fresh-database fixture of the check test

OK, NOT_FOUND, CONFLICT, INVALID = 200, 404, 409, 422
#: T-01, T-03, T-09 (ADJ-02.json triggers_fired) + the situation rule sit.S-02 "Trending day" (ADJ-02.json
#: expected.situations == ["S-02"]; a rule since GC-IC1 6a, 9faf4a28, ADR-240 (3): |net delta per lot| >= 0.15).
#: Measured 2026-11-05 at 9e8e4eae (lead log lead-opps-9e8e.log): 4 records, the 4th ('sit.S-02', 'open',
#: label 'Trending day'). This test predated 6a and still said 3 (test_adjustment_check filters sit.* out instead).
ADJ02_FLAGS = 4
S02_THRESHOLD = Decimal("0.1500")  # other.situation_net_delta_per_lot, default 0.15 (REQ-167 AC-4)
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


async def _opened(engine, sid: int) -> dict:
    """A real screen check, then the worker opens a record for each of its flags (ADR-237 (6)); the check's reply."""
    reply = await _check(sid)
    async with engine.connect() as conn:
        body = (await chk.resolve(conn, "owner", sid, reply["strategy_type"])).body
    await open_flags(engine, sid, reply, body)
    return reply


MARK: dict[int, int] = {}


async def _clean(engine, sid: int) -> int:
    """Lapse what earlier tests left open on the strategy; later reads see only records above the mark."""
    async with engine.begin() as conn:
        await playbook_store.lapse_all(conn, "owner", sid, playbook_store.LAPSE_STRATEGY_CLOSED)
        for held in (await playbook_store.dismissed_holding(conn, "owner", sid)).values():  # ADR-217: forget dismissals
            await playbook_store.mark_cleared(conn, "owner", held.id)
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


async def test_adj02_worker_opens_three_records_the_screen_check_names_them_and_opens_none(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _check(sid)
    assert await _records(app_db_url, sid) == []  # ADR-237 (6): the screen's check opens none
    await _opened(app_db_url, sid)
    first = await _check(sid)
    recs = await _records(app_db_url, sid)
    assert sorted((r.rule_id, r.outcome) for r in recs) == [("T-01", "open"), ("T-03", "open"), ("T-09", "open"), ("sit.S-02", "open")]
    assert len({r.group for r in recs}) == 1 and recs[0].group  # one check = one group (REQ-045 AC-8)
    assert {r.source for r in recs} == {"system"}
    assert sorted((r.value, r.threshold) for r in recs if r.rule_id == "T-01") == [
        (Decimal("0.3416"), Decimal("0.5000"))]
    s02 = next(r for r in recs if r.rule_id == "sit.S-02")
    assert (s02.threshold, s02.cmp, s02.value >= S02_THRESHOLD) == (S02_THRESHOLD, "ge", True)
    flag_ids = {x["rule_id"]: x["suggestion_id"] for x in first["results"] if x["kind"] == "flag"}
    assert flag_ids == {r.rule_id: r.id for r in recs}
    await _check(sid)  # attack 1: more checks -> still exactly 3 records, not 6
    again = await _records(app_db_url, sid)
    assert [r.id for r in again] == [r.id for r in recs] and len(again) == ADJ02_FLAGS
    inbox = await _inbox()
    assert len(_mine(inbox, sid)) == 1
    g = _mine(inbox, sid)[0]
    assert (g["strategy_id"], g["strategy_name"], g["label"], g["summary"], g["has_open"]) == (
        sid, f'"{seed_mod.strategy_name("ADJ-02")}"', SYSTEM_LABEL, "4 adjustment conditions triggered", True)
    assert sorted((r["rule_id"], r["outcome_text"], r["can_act"]) for r in g["records"]) == [
        ("T-01", "Open", True), ("T-03", "Open", True), ("T-09", "Open", True), ("sit.S-02", "Open", True)]
    assert g["records"][0]["condition"] == "Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)"
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
    await _opened(app_db_url, sid)
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
    await _opened(app_db_url, sid)
    t03 = next(r for r in await _records(app_db_url, sid) if r.rule_id == "T-03")
    status, out = await _call("POST", f"/api/adjustment-opportunities/{t03.id}/acted-on")
    assert (status, out["outcome"]) == (OK, "acted_on")
    rows = {r["id"]: r for r in _mine(await _inbox(), sid)[0]["records"]}
    assert rows[t03.id]["outcome_text"] == "Acted on - Paper - not sent to Zerodha"
    counts = {c["outcome"]: c["count"] for c in (await _inbox())["counts"]}
    assert counts["open"] == ADJ02_FLAGS - 1 and counts["acted_on"] >= 1
    answer = await _check(sid)  # T-03 still flagged, its record final: the screen opens no new one (ADR-237 (6))
    assert {x["rule_id"]: x["suggestion_id"] for x in answer["results"] if x["kind"] == "flag"}["T-03"] is None
    assert sorted((r.rule_id, r.outcome) for r in await _records(app_db_url, sid)) == [
        ("T-01", "open"), ("T-03", "acted_on"), ("T-09", "open"), ("sit.S-02", "open")]


async def test_another_users_record_is_not_found_and_nothing_is_written(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _opened(app_db_url, sid)
    t09 = next(r for r in await _records(app_db_url, sid) if r.rule_id == "T-09")
    for path, body in (("dismiss", {"reason": "other"}), ("acted-on", None)):  # attack 4
        status, out = await _call("POST", f"/api/adjustment-opportunities/{t09.id}/{path}", body, user="someone-else")
        assert status == NOT_FOUND and out["what_happened"] == "This adjustment opportunity was not found."
    status, _ = await _call("POST", "/api/adjustment-opportunities/987654321/acted-on")
    assert status == NOT_FOUND
    assert next(r for r in await _records(app_db_url, sid) if r.id == t09.id).outcome == "open"
    assert (await _inbox(user="someone-else"))["groups"] == []


async def test_a_worker_lapse_reads_lapsed_and_a_screen_check_never_lapses(app_db_url, monkeypatch):
    """REQ-112 AC-2 through the worker's store (DbGateStore.apply, the gate's Lapsed event); a screen check lapses
    nothing and opens nothing, even with the rule still true (ADR-237 (6))."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _opened(app_db_url, sid)
    await _check(sid)
    assert {r.outcome for r in await _records(app_db_url, sid)} == {"open"}
    await lapse_through_worker(sid, "T-01")
    recs = {r.rule_id: r for r in await _records(app_db_url, sid)}
    assert (recs["T-01"].outcome, recs["T-01"].lapse_reason) == ("lapsed", "condition_stopped")
    assert (recs["T-03"].outcome, recs["T-09"].outcome) == ("open", "open")
    row = next(r for g in _mine(await _inbox(), sid) for r in g["records"] if r["id"] == recs["T-01"].id)
    assert (row["outcome_text"], row["detail"]) == ("Lapsed", "The condition stopped holding")
    answer = await _check(sid)  # T-01 still true on screen: a flag, no record opened, none named
    t01 = next(x for x in answer["results"] if x["rule_id"] == "T-01")
    assert (t01["kind"], t01["suggestion_id"], t01["note"]) == ("flag", None, None)
    assert len(await _records(app_db_url, sid)) == ADJ02_FLAGS


async def test_a_dismissed_flag_shows_the_note_and_the_screen_check_writes_nothing(app_db_url, monkeypatch):
    """ADR-217 on the screen: a flagged rule whose latest record is dismissed (none open) carries "You dismissed this"
    and no suggestion id; the other flags name their open records; checks write nothing (ADR-237 (6))."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _opened(app_db_url, sid)
    t01 = next(r for r in await _records(app_db_url, sid) if r.rule_id == "T-01")
    status, _ = await _call("POST", f"/api/adjustment-opportunities/{t01.id}/dismiss", {"reason": "not_relevant"})
    assert status == OK
    for _ in range(2):  # attack 1: two checks while it keeps holding
        answer = await _check(sid)
        flag = next(x for x in answer["results"] if x["rule_id"] == "T-01")
        assert (flag["kind"], flag["suggestion_id"], flag["note"]) == ("flag", None, "You dismissed this")
        assert all(x["note"] is None and x["suggestion_id"] for x in answer["results"]
                   if x["kind"] == "flag" and x["rule_id"] != "T-01")
    recs = await _records(app_db_url, sid)
    assert sorted((r.rule_id, r.outcome) for r in recs) == [
        ("T-01", "dismissed"), ("T-03", "open"), ("T-09", "open"), ("sit.S-02", "open")]  # attack 4: the others unaffected
    async with app_db_url.begin() as conn:  # attack 5: the hold is per strategy (the seed makes one ADJ-02 strategy)
        assert list(await playbook_store.dismissed_holding(conn, "owner", sid)) == ["T-01"]
        assert await playbook_store.dismissed_holding(conn, "owner", sid + 1000) == {}
    async with app_db_url.connect() as conn:  # the worker opens a new T-01 record: the screen names it, no note
        body = (await chk.resolve(conn, "owner", sid, "ic")).body
    new = await open_flags(app_db_url, sid, await _check(sid), body, rules={"T-01"})
    answer = await _check(sid)
    flag = next(x for x in answer["results"] if x["rule_id"] == "T-01")
    assert (flag["suggestion_id"], flag["note"]) == (new["T-01"], None)
    inbox_rows = [r for g in _mine(await _inbox(), sid) for r in g["records"]
                  if r["rule_id"] == "T-01" and r["id"] > MARK[sid]]  # this test's records only
    assert sorted(r["outcome_text"] for r in inbox_rows) == ["Open", "You dismissed this"]  # the inbox keeps the row


async def test_an_exited_strategy_is_refused_and_the_screen_lapses_nothing(app_db_url, monkeypatch):
    """ADR-237 (6): the worker lapses an exited strategy's records (background: TrackedExited -> lapse_all); the
    screen refuses (409) and writes nothing."""
    from ofo_app.routes.adjustment import get_tracked_reader  # noqa: PLC0415

    async def exited(_strategy_id, _rates):
        raise TrackedExited("no open option leg")

    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _opened(app_db_url, sid)
    status, _ = await _call("GET", f"/api/strategies/{sid}/adjustment-check",
                            overrides={get_tracked_reader: lambda: exited})
    assert status == CONFLICT
    recs = await _records(app_db_url, sid)
    assert {(r.outcome, r.lapse_reason) for r in recs} == {("open", None)} and len(recs) == ADJ02_FLAGS


async def test_the_own_playbook_label(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
        own = await playbook_store.duplicate(conn, "owner", system.id, "Mine")
        await playbook_store.make_active(conn, "owner", own.id)
    await _opened(app_db_url, sid)
    assert [g["label"] for g in _mine(await _inbox(), sid)] == [OWN_LABEL]


@pytest.mark.parametrize("bad", [0, -1])
async def test_an_impossible_id_is_not_found(app_db_url, bad):
    status, _ = await _call("POST", f"/api/adjustment-opportunities/{bad}/acted-on")
    assert status == NOT_FOUND


async def _card(sid: int) -> dict:
    status, body = await _call("GET", "/strategies")
    assert status == OK, body
    return next(s for s in body["strategies"] if s["id"] == sid)


async def test_card_mark_counts_open_records_and_goes_when_the_last_is_dismissed(app_db_url, monkeypatch):
    """GC-MU A3 (ADR-230 (2)): the Live Strategies list carries the open count; dismissing clears the mark."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    assert (await _card(sid))["open_opportunities_text"] is None  # nothing recorded: no mark
    await _check(sid)
    assert (await _card(sid))["open_opportunities_text"] is None  # the screen's check records nothing
    await _opened(app_db_url, sid)
    card = await _card(sid)
    assert (card["open_opportunities"], card["open_opportunities_text"]) == (ADJ02_FLAGS, "4 adjustment opportunities")
    records = await _records(app_db_url, sid)
    for r in records[:-1]:
        status, _ = await _call("POST", f"/api/adjustment-opportunities/{r.id}/dismiss", {"reason": "other"})
        assert status == OK
    card = await _card(sid)
    assert (card["open_opportunities"], card["open_opportunities_text"]) == (1, "1 adjustment opportunity")
    status, _ = await _call("POST", f"/api/adjustment-opportunities/{records[-1].id}/dismiss", {"reason": "other"})
    assert status == OK
    card = await _card(sid)
    assert (card["open_opportunities"], card["open_opportunities_text"]) == (0, None)


async def test_card_mark_ignores_acted_on_and_a_read_failure_gives_no_mark_but_the_list(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    await _opened(app_db_url, sid)
    first = (await _records(app_db_url, sid))[0]
    status, _ = await _call("POST", f"/api/adjustment-opportunities/{first.id}/acted-on")
    assert status == OK
    assert (await _card(sid))["open_opportunities"] == ADJ02_FLAGS - 1  # acted on is not open

    async def broken(*_a, **_k):
        raise RuntimeError("inbox unreadable")
    monkeypatch.setattr(playbook_store, "inbox", broken)
    card = await _card(sid)  # the list still answers; unread is None, never 0
    assert (card["open_opportunities"], card["open_opportunities_text"]) == (None, None)


async def test_t19_list_line_names_the_same_approach_and_cost_as_the_check(app_db_url, monkeypatch):
    """ADR-221 (review MAJOR 1): the opportunities list draws a T-19 record with the approach, cost and unpriced count
    stored when it opened, so the list line equals the check's flag line (the Compare's figure in both). The charge
    rates are the scenario library's stated rates (Zerodha's published F&O rates): with none (the conftest default)
    no approach can be priced and T-19 is rightly not checked."""
    import math  # noqa: PLC0415

    import t19_support  # noqa: PLC0415 - sits next to this file
    from ofo_app.routes import outcome  # noqa: PLC0415
    monkeypatch.setattr(outcome, "_rates_cache", {"until": math.inf, "value": t19_support.RATES})
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-43"))
    from ofo_app.routes import adjustment_check as route  # noqa: PLC0415
    states: list = []
    real_state_of = chk.state_of

    def spy(*a, **k):  # the state the check built: its T-19 approach and cost are what the worker stores (ADR-221)
        states.append(real_state_of(*a, **k))
        return states[-1]
    monkeypatch.setattr(chk, "state_of", spy)
    first = await _check(sid)  # last day 15:00: the clock trigger T-10b fires too (was a 500 before its line fix)
    async with app_db_url.connect() as conn:
        body = (await chk.resolve(conn, "owner", sid, first["strategy_type"])).body
    await open_flags(app_db_url, sid, first, body, cheapest=route.cheapest(states[-1]))
    clock = next(x for x in first["results"] if x["kind"] == "flag" and x["trigger_id"] == "T-10b")
    assert clock["condition"] == "Clock time reached (checked in this stage): 15:00 (rule 14:30)"
    flag = next((x for x in first["results"] if x["kind"] == "flag" and x["trigger_id"] == "T-19"), None)
    assert flag is not None, [(x["kind"], str(x["reason"])[:400]) for x in first["results"] if x["trigger_id"] == "T-19"]
    # Measured 2026-11-05 (t19_support.cheapest on ADJ-43, the same cheapest_offered): A-26 "Close the untested side
    # for profit" (built since GC-IC1 s2, c899dccb) costs 26.86 < A-28's, 2 offered approaches unpriced; premium left
    # 19.50 / 26.86 = 0.7260, the flag's value. The #629 wording (9ab9aabf) reads "we could price".
    assert flag["condition"] == ("Premium still left to earn is below this many x the adjustment's cost: 0.7260 "
                                 "(rule 1.0000); cheapest adjustment we could price: Close the untested side for "
                                 "profit, cost ₹26.86. 2 could not be priced.")
    rec = next(r for r in await _records(app_db_url, sid) if r.rule_id == "T-19")
    assert (rec.approach, rec.approach_cost, rec.unpriced) == ("A-26", Decimal("26.86"), 2)
    assert f"₹{rec.approach_cost}" in flag["condition"]
    g = _mine(await _inbox(), sid)[0]
    listed = next(r for r in g["records"] if r["rule_id"] == "T-19")
    assert listed["condition"] == flag["condition"]
