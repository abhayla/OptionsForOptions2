"""GC-ADJ2 step 3: POST /api/playbooks/test on a fresh migrated database (REQ-160 AC-3, AC-4; REQ-159 AC-1). The
ADJ-02 scenario strategy is seeded the way the check route's test seeds it (catalogue writer + seed_scenario.seed);
the playbook body is the system iron condor's as the API reads it, edited the way the editor edits it (unsaved).
"""
from __future__ import annotations

import copy
from typing import Any

import test_adjustment_check as check_test
from httpx import ASGITransport, AsyncClient
from ofo_app import db as app_db
from ofo_app import playbook_store
from sqlalchemy import text

_reset_engine, _seeded = check_test._reset_engine, check_test._seeded
app_db_url = check_test.app_db_url  # the check test's fixture: the app's engine on the fresh database

OK, UNPROCESSABLE = 200, 422
PAST_NOTE = ("Testing against past expiries is not in this version: it needs licensed historical option data.")
_COUNTED = ("public.adjustment_rule_state", "public.adjustment_suggestions", "public.strategy_adjustment_plans",
            "public.paper_orders", "public.adjustment_playbooks")


async def _calls(*requests: tuple[str, str, dict | None]) -> list[Any]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env set by the fixture must be read first
    _reset_engine()
    app = create_app()
    out = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for method, url, body in requests:
            out.append(await ac.request(method, url, json=body))
    await app_db.close_db()
    return out


async def _system_ic_body(engine) -> dict:
    async with engine.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
    (read,) = await _calls(("GET", f"/api/playbooks/{system.id}", None))
    assert read.status_code == OK, read.text
    return read.json()["body"]


async def _counts(engine) -> dict[str, int]:
    async with engine.connect() as conn:
        return {t: (await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()  # noqa: S608 constant table
                for t in _COUNTED}


def _rows(strategy: dict, kind: str) -> list[tuple]:
    return sorted((x["trigger_id"], (x["value"] or "")[:6], x["threshold"], x["cmp"]) for x in strategy["results"]
                  if x["kind"] == kind)


def _stages(body: dict, weekly: list[tuple[str, int, int | None]]) -> dict:
    body = copy.deepcopy(body)
    body["stages"]["weekly"] = [{"name": n, "from": f, "to": t} for n, f, t in weekly]
    return body


async def test_unsaved_t01_middle_03_drops_t01_keeps_t03_t09_and_writes_nothing(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    body = await _system_ic_body(app_db_url)
    stored_before = copy.deepcopy(body)
    body["triggers"]["T-01"]["weekly"][1] = "0.3"  # Middle: 0.3416 > 0.3, so T-01 must not flag
    before = await _counts(app_db_url)
    (r,) = await _calls(("POST", "/api/playbooks/test", {"type": "ic", "body": body}))
    assert r.status_code == OK, r.text
    out = r.json()
    assert (out["type"], out["type_name"], out["none_text"], out["past_note"]) == ("ic", "Iron condor", None,
                                                                                   PAST_NOTE)
    (mine,) = [s for s in out["strategies"] if s["strategy_id"] == sid]
    assert mine["name"].startswith('"') and mine["stage"] == {"name": "Middle", "index": 1}
    assert _rows(mine, "flag") == [("T-03", "0.4103", "0.3500", "ge"), ("T-09", "2.7000", "3.0000", "le")]
    not_checked = [x for x in mine["results"] if x["kind"] == "not_checked"]
    assert not_checked and all(x["reason"] and x["value"] is None for x in not_checked)  # never listed as passed
    assert "T-01" not in {x["trigger_id"] for x in mine["results"]}
    assert await _counts(app_db_url) == before  # no rule state, suggestion, plan, order or playbook written
    assert await _system_ic_body(app_db_url) == stored_before  # the stored playbook is unchanged


async def test_unchanged_system_body_flags_t01_too(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    body = await _system_ic_body(app_db_url)
    (r,) = await _calls(("POST", "/api/playbooks/test", {"type": "ic", "body": body}))
    assert r.status_code == OK, r.text
    (mine,) = [s for s in r.json()["strategies"] if s["strategy_id"] == sid]
    assert _rows(mine, "flag") == [("T-01", "0.3416", "0.5000", "le"), ("T-03", "0.4103", "0.3500", "ge"),
                                   ("T-09", "2.7000", "3.0000", "le")]  # 4 dp half-up (step 5, the fixture's form)


async def test_no_strategy_of_the_type_says_so(app_db_url, monkeypatch):
    await _seeded(app_db_url, monkeypatch, "ADJ-02")  # an iron condor only: no short strangle is tracked
    async with app_db_url.begin() as conn:
        strangle = await playbook_store.active_for(conn, "owner", "strangle")
    (read,) = await _calls(("GET", f"/api/playbooks/{strangle.id}", None))
    (r,) = await _calls(("POST", "/api/playbooks/test", {"type": "strangle", "body": read.json()["body"]}))
    assert r.status_code == OK, r.text
    out = r.json()
    assert out["strategies"] == [] and out["none_text"] == "No current Short strangle strategy to test against"
    assert out["past_note"] == PAST_NOTE


async def test_invalid_body_and_unknown_type_are_refused_before_any_read(app_db_url, monkeypatch):
    await _seeded(app_db_url, monkeypatch, "ADJ-02")
    body = await _system_ic_body(app_db_url)
    floated = copy.deepcopy(body)
    floated["triggers"]["T-01"]["weekly"][1] = 0.3  # a float is never a playbook value
    (bad, unknown) = await _calls(("POST", "/api/playbooks/test", {"type": "ic", "body": floated}),
                                  ("POST", "/api/playbooks/test", {"type": "nope", "body": body}))
    assert bad.status_code == UNPROCESSABLE and bad.json()["what_happened"].startswith("The playbook value ")
    assert unknown.status_code == UNPROCESSABLE
    assert unknown.json()["what_happened"] == "The playbook value strategy_type is not valid."


async def test_gap_and_overlap_get_the_save_refusal_text(app_db_url, monkeypatch):
    await _seeded(app_db_url, monkeypatch, "ADJ-02")
    body = await _system_ic_body(app_db_url)
    overlap = _stages(body, [("Early", 5, None), ("Near", 2, 4), ("Last", 0, 4)])
    gap = _stages(body, [("Early", 7, None), ("Near", 2, 4), ("Last", 0, 1)])
    (o, g) = await _calls(("POST", "/api/playbooks/test", {"type": "ic", "body": overlap}),
                          ("POST", "/api/playbooks/test", {"type": "ic", "body": gap}))
    assert o.status_code == g.status_code == UNPROCESSABLE
    assert o.json()["what_happened"] == "Days 2 to 4 are in both Last and Near (weekly expiries)."
    assert g.json()["what_happened"] == "Days 5 to 6 are in no stage (weekly expiries)."
