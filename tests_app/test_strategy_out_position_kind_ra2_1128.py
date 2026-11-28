"""Lane RA2 item 4 (ADR-330 (64)): GET /strategies/{id} carries the list row's own ``position_kind`` and
``position_kind_text`` (``position_kind.kind_of`` / ``line_of``), so the page of one strategy tells a real trade by the
stored fact and not by the status word "Running" and the absence of a paper book.

Real case (Lane FJ's builder): a strategy held at the broker (ADR-292, a real position stored as practice orders) reads
status word "Running" like a paper trade; only ``position_kind`` tells them apart. Hand values: no order -> none
(no line), a paper order -> paper (no line), a held entry -> real with the one real-position sentence.
"""
from __future__ import annotations

import sys
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from ofo.errors.explanations import render_explanation
from ofo_app import held_entry_store, paper_store
from test_paper_monitor import OPEN_AT
from test_paper_routes import _client, _new, db  # noqa: F401 - db is the rollback fixture
from test_strategy_tracking import ENTRY_PRICES, _setup


async def _get(app, strategy_id: int) -> dict:
    async with _client(app) as c:
        reply = await c.get(f"/strategies/{strategy_id}")
    assert reply.status_code == HTTPStatus.OK, reply.text
    return reply.json()


async def _paper_book(db, stored) -> None:  # noqa: F811
    await paper_store.place(db, stored.user_ref, stored.id, [
        _new(cid, leg.action.value, leg.quantity, price)
        for cid, leg, price in zip(stored.saved.contract_ids, stored.saved.definition.legs, ENTRY_PRICES, strict=True)])


async def test_core_a_held_strategy_reads_real_a_paper_one_paper_a_draft_none(db):  # noqa: F811
    app, draft, *_ = await _setup(db)
    body = await _get(app, draft.id)
    assert (body["position_kind"], body["position_kind_text"]) == ("none", None)
    await _paper_book(db, draft)
    body = await _get(app, draft.id)
    assert (body["status_word"], body["position_kind"], body["position_kind_text"]) == ("Running", "paper", None)
    await held_entry_store.record(db, draft.id, OPEN_AT, None)
    body = await _get(app, draft.id)
    assert (body["status_word"], body["position_kind"]) == ("Running", "real")
    assert body["position_kind_text"] == render_explanation("position_kind_real")
    listed = next(s for s in (await _list(app))["strategies"] if s["id"] == draft.id)
    assert [listed[f] for f in ("position_kind", "position_kind_text")] == [
        body[f] for f in ("position_kind", "position_kind_text")]


async def _list(app) -> dict:
    async with _client(app) as c:
        return (await c.get("/strategies")).json()


async def test_an_unreadable_kind_reads_unknown_with_its_line_never_paper(db, monkeypatch):  # noqa: F811
    from ofo_app import strategy_store  # noqa: PLC0415
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

    app, draft, *_ = await _setup(db)

    async def unreadable(_conn, _ids):
        raise SQLAlchemyError("kinds unreadable")

    monkeypatch.setattr(strategy_store, "kinds_of", unreadable)
    body = await _get(app, draft.id)
    assert body["position_kind"] == "unknown"
    assert body["position_kind_text"] == render_explanation("position_kind_unknown")
