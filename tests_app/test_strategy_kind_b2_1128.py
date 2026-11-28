# ruff: noqa: F811 - the imported fixture is used as a test argument
"""Lane B2 item 5 (ADR-330 (64)): GET /strategies/{id} (StrategyOut) names `position_kind` and `position_kind_text`
the way GET /strategies (SummaryOut) does, from the one rule (`kinds_of` / `position_kind.line_of`). Real case: Lane
FJ's builder told a real trade only by status_word "Running" and no paper book. Paper, held, real (a plan, no paper
order) and none."""
from __future__ import annotations

import datetime
from http import HTTPStatus

from ofo.marketdata.kite_provider import IST
from ofo_app import held_entry_store
from test_paper_adjustment_limit import _book
from test_paper_save_paths_fx2 import db  # noqa: F401 - fixture
from test_paper_triggers_routes import notified  # noqa: F401 - fixture
from test_strategy_store import _client

REAL_SENTENCE = "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only."


async def _both(app, sid):
    async with _client(app) as c:
        detail = await c.get(f"/strategies/{sid}")
        listed = await c.get("/strategies")
    assert detail.status_code == HTTPStatus.OK, detail.text[:300]
    assert listed.status_code == HTTPStatus.OK, listed.text[:300]
    (row,) = [r for r in listed.json()["strategies"] if r["id"] == sid]
    return detail.json(), row


async def test_a_paper_strategy_reads_paper_in_both_shapes_with_no_line(db, notified):
    app, stored, _ids = await _book(db, max_adjustments=2)
    detail, row = await _both(app, stored.id)
    assert detail["position_kind"] == row["position_kind"] == "paper"
    assert detail.get("position_kind_text") is None and row.get("position_kind_text") is None


async def test_a_held_strategy_reads_real_in_both_shapes_with_the_one_line(db, notified):
    app, stored, _ids = await _book(db, max_adjustments=2)
    await held_entry_store.record(db, stored.id, datetime.datetime(2026, 11, 27, 10, 0, tzinfo=IST), "Zerodha")
    detail, row = await _both(app, stored.id)
    assert detail["position_kind"] == row["position_kind"] == "real"
    assert detail["position_kind_text"] == row["position_kind_text"]
    assert REAL_SENTENCE in str(detail["position_kind_text"])


async def test_a_failed_kind_read_reads_unknown_never_paper(db, notified, monkeypatch):
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415
    app, stored, _ids = await _book(db, max_adjustments=2)

    async def broken(_db, _ids):
        raise OperationalError("SELECT", {}, Exception("kind read failed"))
    monkeypatch.setattr("ofo_app.strategy_store.kinds_of", broken)
    async with _client(app) as c:
        detail = await c.get(f"/strategies/{stored.id}")
    assert detail.status_code == HTTPStatus.OK, detail.text[:300]
    assert detail.json()["position_kind"] == "unknown" and detail.json()["position_kind_text"] is not None


async def test_a_plan_only_strategy_reads_real_and_a_draft_reads_none_in_both_shapes(
        app_engine, admin_engine, monkeypatch):
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_execution_return import _app_for, _Reads, _store_plan  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            draft = await _strategy_one(conn, user, app_engine.url.username)
            app = _app_for(conn, user, _Reads("122104"))
            detail, row = await _both(app, draft)
            assert detail["position_kind"] == row["position_kind"] == "none"
            await _store_plan(conn, user, draft, ("ENTRY", "BUY", "3.35"))
            detail, row = await _both(app, draft)
            assert detail["position_kind"] == row["position_kind"] == "real"
            assert detail["position_kind_text"] == row["position_kind_text"]
        finally:
            await trans.rollback()
