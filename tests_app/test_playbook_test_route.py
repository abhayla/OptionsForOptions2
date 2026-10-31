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


# ---- bounded reads (GC-ADJ2 step 3: no stall) ----------------------------------------------------------------------
LIMIT_FOR_TEST = 8.0  # the route constant: three strategies read at once took ~2.7 s on this host, so 8 s cuts only the hang
MAX_SECONDS, THREE, TWO = 30, 3, 2
TIMED_OUT = "Prices for this strategy did not arrive in time."


async def _three_seeded(app_db_url, monkeypatch) -> list[int]:
    """The seeder is idempotent by name, so each seeded copy is renamed before the next seed makes a new strategy."""
    ids = [await _seeded(app_db_url, monkeypatch, "ADJ-02")]
    for n in (2, 3):
        async with app_db_url.begin() as conn:
            await conn.execute(text("UPDATE public.strategies SET name = name || :n WHERE id = :id"),
                               {"n": f" copy {n}", "id": ids[-1]})
        _reset_engine()
        ids.append(await check_test.seed_mod.seed("ADJ-02"))
    assert len(set(ids)) == THREE
    return ids


async def _post_with_market(market_wrapper, body: dict) -> tuple[Any, float]:
    """POST the test with the market reader replaced by ``market_wrapper(real_reader)``; -> (response, seconds)."""
    import time  # noqa: PLC0415

    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes import adjustment as adj  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    real = adj.get_market_reader()
    app.dependency_overrides[adj.get_market_reader] = lambda: market_wrapper(real)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        started = time.monotonic()
        r = await ac.post("/api/playbooks/test", json={"type": "ic", "body": body})
        took = time.monotonic() - started
    await app_db.close_db()
    return r, took


async def test_one_hanging_strategy_is_listed_not_checked_and_the_others_are_evaluated(app_db_url, monkeypatch):
    import asyncio  # noqa: PLC0415

    from ofo_app.routes import playbooks as route  # noqa: PLC0415
    monkeypatch.setattr(route, "TEST_READ_LIMIT_SECONDS", LIMIT_FOR_TEST)
    ids = await _three_seeded(app_db_url, monkeypatch)
    body = await _system_ic_body(app_db_url)
    calls = 0

    def wrapper(real):
        async def read(tracked, ctx):
            nonlocal calls
            calls += 1
            if calls == 1:  # the first strategy to reach the market read never gets its answer
                await asyncio.Event().wait()
            return await real(tracked, ctx)
        return read

    before = await _counts(app_db_url)
    r, took = await _post_with_market(wrapper, body)
    assert r.status_code == OK, r.text
    assert took < MAX_SECONDS  # a bounded answer (the hang alone would never return)
    by_id = {s["strategy_id"]: s for s in r.json()["strategies"] if s["strategy_id"] in ids}
    assert sorted(by_id) == sorted(ids), ids
    hung = [s for s in by_id.values() if s["stage"] == {"name": None, "index": None}]
    assert len(hung) == 1
    assert hung[0]["results"]
    assert all(x["kind"] == "not_checked" and x["reason"]["what_happened"] == TIMED_OUT and x["value"] is None
               for x in hung[0]["results"])
    others = [s for s in by_id.values() if s is not hung[0]]
    assert len(others) == TWO and all(_rows(s, "flag") for s in others)  # evaluated: ADJ-02 flags T-01, T-03, T-09
    assert await _counts(app_db_url) == before  # nothing written


async def test_raising_market_read_on_an_iron_condor_is_listed_not_checked_never_flagged(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    body = await _system_ic_body(app_db_url)

    def wrapper(real):
        async def read(tracked, ctx):
            raise RuntimeError("feed down")
        return read

    r, _ = await _post_with_market(wrapper, body)
    assert r.status_code == OK, r.text
    (mine,) = [s for s in r.json()["strategies"] if s["strategy_id"] == sid]
    assert len(mine["results"]) == len(body["rules"])
    assert all(x["kind"] == "not_checked" and x["reason"]["what_happened"] == TIMED_OUT for x in mine["results"]), mine
    assert _rows(mine, "flag") == []


async def test_only_strategies_with_open_paper_legs_are_read_at_all(app_db_url, monkeypatch):
    """The cheap skip: a strategy with no open paper leg never reaches the tracked reader."""
    from ofo_app import paper_store, strategy_store  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes import adjustment as adj  # noqa: PLC0415
    await _seeded(app_db_url, monkeypatch, "ADJ-02")
    body = await _system_ic_body(app_db_url)
    async with app_db_url.connect() as conn:
        rows = await strategy_store.list_strategies(conn, "owner")
        tracked = await paper_store.tracked_ids(conn, [x.id for x in rows])
    seen: list[int] = []
    real = adj.get_tracked_reader()

    async def spy(strategy_id, rates):
        seen.append(strategy_id)
        return await real(strategy_id, rates)

    _reset_engine()
    app = create_app()
    app.dependency_overrides[adj.get_tracked_reader] = lambda: spy
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/api/playbooks/test", json={"type": "ic", "body": body})
    await app_db.close_db()
    assert r.status_code == OK, r.text
    assert sorted(seen) == sorted(tracked)


def test_the_limit_is_one_named_constant():
    import pathlib  # noqa: PLC0415
    src = (pathlib.Path(__file__).resolve().parent.parent / "backend/ofo_app/routes/playbooks.py").read_text("utf-8")
    assert src.count("asyncio.wait_for(") == 1 and "seams, listed, read), TEST_READ_LIMIT_SECONDS)" in src
    assert src.count("TEST_READ_LIMIT_SECONDS = ") == 1  # defined once; no second literal limit
