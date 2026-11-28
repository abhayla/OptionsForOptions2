"""I-81 (test plan 28 Nov 2026): the adjustment-history read answered 200 on ANOTHER user's strategy; it must be 404,
with no figure of the strategy in the reply, and the read writes nothing (the raw rows are the same before and after).
Real case: ADJ-13 seeded for the owner (paper book with an adjustment batch); another user asks for it; a hidden
(deleted) own strategy; an unknown id. Beside `test_adjustment_history.py` (one 404 case there, no leak or raw check).
Spec basis: REQ-163 AC-1..AC-3, ADR-293 (a deleted strategy is hidden), ADR-051 (the owner's data is the owner's).
"""
from __future__ import annotations

from sqlalchemy import text
from test_adjustment_history import NOT_FOUND, OK, _history, _seeded, app_db_url  # noqa: F401 - the fixture is by name

STRANGER = "someone-else"
RAW = ("SELECT (SELECT count(*) FROM public.paper_orders), (SELECT count(*) FROM public.adjustment_suggestions), "
       "(SELECT count(*) FROM public.strategies), "
       "(SELECT coalesce(sum(revision), 0) FROM public.strategies)")
FIGURES = {"rows", "totals", "booked", "credit", "adjustments", "summary"}


async def _raw(engine) -> tuple:
    async with engine.connect() as conn:
        return tuple((await conn.execute(text(RAW))).one())


async def test_another_users_strategy_is_404_leaks_no_figure_and_writes_nothing(app_db_url, monkeypatch):  # noqa: F811
    from ofo_app.routes.broker import current_user_ref  # noqa: PLC0415
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-13")
    own_status, own = await _history(sid)
    assert own_status == OK and own["totals"], "control: the owner reads their own history"
    before = await _raw(app_db_url)
    status, out = await _history(sid, {current_user_ref: lambda: STRANGER})
    assert status == NOT_FOUND, out
    assert not FIGURES & set(out), out  # no row, no total of the owner's trade in the refusal
    assert str(sid) not in repr(out)
    _, unknown = await _history(sid + 100000)
    assert out == unknown  # another user's strategy answers exactly as a missing one: nothing says it exists
    assert await _raw(app_db_url) == before  # the read wrote nothing


async def test_a_hidden_own_strategy_is_404_like_a_missing_one(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-13")
    async with app_db_url.begin() as conn:
        await conn.execute(text("UPDATE public.strategies SET deleted_at = now() WHERE id = :i"), {"i": sid})
    status, out = await _history(sid)
    assert status == NOT_FOUND, out
