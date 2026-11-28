"""I-64 (test plan 28 Nov 2026): a just-saved draft must NOT say in Plan watch that the strategy is "not found" (or give
a plan it has not got). Beside ``test_plan_watch.py`` (one case there): here every answer state of the draft, on the
single route and on the batch route the Positions list uses.
Real case: a one-leg draft saved from the builder (a SELL of an ADJ-01 contract), opened in Plan watch at once.
States: draft (own, saved) -> 200 ``no_plan``, the catalogue's no-plan sentence, no lines, no pause, nothing refused;
batch row of the draft -> ``ok``; hidden (deleted) draft -> 404; another user's draft -> 404; unknown id -> 404.
Spec basis: ADR-330 (11) (no plan: say so), (13) (Plan watch lines), ADR-293 (a deleted one is hidden).
"""
from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from ofo.errors.explanations import render_explanation
from ofo.strategy import stored_form as sf
from ofo_app import db as app_db
from ofo_app import paper_store, strategy_store
from sqlalchemy import text
from test_adjustment_check import _reset_engine, _seeded, app_db_url  # noqa: F401 - the fixture is used by name

OK, NOT_FOUND = 200, 404
NO_PLAN = render_explanation("plan_sheet_no_plan")


async def _get(url: str, *, user: str | None = None) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    from ofo_app.routes.broker import current_user_ref  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    if user is not None:
        app.dependency_overrides[current_user_ref] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(url)
    await app_db.close_db()
    return r.status_code, r.json()


async def _draft(engine, monkeypatch, user: str = "owner") -> int:
    sid = await _seeded(engine, monkeypatch, "ADJ-01")
    async with engine.begin() as conn:
        order = next(o for o in await paper_store.load(conn, sid) if o.order.side == "SELL")
        saved = await strategy_store.build_definition(conn, "NIFTY", [sf.LegChoice(
            contract_id=order.order.contract_id, action=sf.Action.SELL, quantity=order.order.quantity)], rules_ref="t3")
        return (await strategy_store.save_draft(conn, user, saved)).id


async def test_a_just_saved_draft_is_no_plan_with_the_catalogue_sentence_and_nothing_refused(app_db_url, monkeypatch):  # noqa: F811
    sid = await _draft(app_db_url, monkeypatch)
    status, out = await _get(f"/api/strategies/{sid}/plan-watch")
    assert status == OK, out
    assert (out["strategy_id"], out["plan_state"], out["lines"], out["paused"]) == (sid, "no_plan", [], None)
    assert out["no_plan_text"] == NO_PLAN
    assert "not found" not in repr(out).lower()


async def test_the_batch_row_of_a_just_saved_draft_is_ok_not_refused(app_db_url, monkeypatch):  # noqa: F811
    sid = await _draft(app_db_url, monkeypatch)
    status, out = await _get(f"/api/plan-watch?strategy_ids={sid},{sid + 100000}")
    assert status == OK
    first, second = out["items"]
    assert (first["strategy_id"], first["state"], first["refusal"], first["status"]) == (sid, "ok", None, None)
    assert first["watch"]["plan_state"] == "no_plan" and first["watch"]["no_plan_text"] == NO_PLAN
    assert (second["state"], second["status"]) == ("refused", NOT_FOUND)  # an unknown id still says so


async def test_a_hidden_or_another_users_draft_stays_not_found(app_db_url, monkeypatch):  # noqa: F811
    sid = await _draft(app_db_url, monkeypatch)
    assert (await _get(f"/api/strategies/{sid}/plan-watch", user="someone-else"))[0] == NOT_FOUND
    async with app_db_url.begin() as conn:
        await conn.execute(text("UPDATE public.strategies SET deleted_at = now() WHERE id = :i"), {"i": sid})
    assert (await _get(f"/api/strategies/{sid}/plan-watch"))[0] == NOT_FOUND
