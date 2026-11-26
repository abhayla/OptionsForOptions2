"""P11 (S-15 server line, ADR-330 (10), owner answer Q11): the Paper totals say how many closed strategies they include.

Real case shape: tests/fixtures/paper/before-2026-10-29.json strategy 50 is fully exited (closed); 48 and 46 are open.
``totals.closed_count`` / ``closed_text`` come from the server (null text when none); the screen prints them.
"""
from __future__ import annotations

import datetime

from ofo_app import strategy_store as store
from sqlalchemy import text
from test_paper_routes import AT
from test_paper_totals import _fixture, _list, _seed_three, _strategy, db  # noqa: F401 - db is a fixture
from test_strategy_store import _ids, _saved_in

ONE = "Includes 1 closed strategy."
MANY = "Includes {n} closed strategies."
_DELETE = "UPDATE public.strategies SET deleted_at = clock_timestamp() WHERE id = :id"


async def _another_closed(db, sid: dict, hours: int):  # noqa: F811
    """A further fully exited strategy of the same user (fixture 50's leg), placed ``hours`` after AT."""
    owner = (await db.execute(text("SELECT user_ref FROM public.strategies WHERE id = :id"),
                              {"id": sid["50"]})).scalar_one()
    stored = await store.load(db, owner, sid["50"])
    return await _strategy(db, stored, [(0, _fixture(50)["legs"][0])], AT + datetime.timedelta(hours=hours))


async def test_one_closed_one_open(db):  # noqa: F811
    """50 is closed; 48 and 46 are open: one closed strategy."""
    app, *_ = await _seed_three(db)
    totals = (await _list(app))["totals"]
    assert (totals["closed_count"], totals["closed_text"]) == (1, ONE)


async def test_none_closed_is_zero_and_null(db):  # noqa: F811
    app, _p, _c, _l, sid = await _seed_three(db)
    await db.execute(text(_DELETE), {"id": sid["50"]})  # the only closed one is gone: 48 and 46 stay open
    totals = (await _list(app))["totals"]
    assert (totals["closed_count"], totals["closed_text"]) == (0, None)


async def test_a_closed_strategy_of_another_user_is_not_counted(db):  # noqa: F811
    app, _p, _c, _l, sid = await _seed_three(db)
    await db.execute(text(_DELETE), {"id": sid["50"]})  # the signed-in user's only closed one is gone ...
    other = await store.save_draft(db, "someone-else", await _saved_in(db, "someone-else", await _ids(db)))
    await _strategy(db, other, [(0, _fixture(50)["legs"][0])], AT, new=False)  # ... another user's closed one stays
    assert (await _list(app))["totals"]["closed_count"] == 0


async def test_a_deleted_closed_strategy_is_not_counted(db):  # noqa: F811
    """ADR-293 delete hides the strategy: it is neither listed nor counted."""
    app, _p, _c, _l, sid = await _seed_three(db)
    extra = await _another_closed(db, sid, 2)
    assert (await _list(app))["totals"]["closed_count"] == 2
    await db.execute(text(_DELETE), {"id": extra.id})
    assert (await _list(app))["totals"]["closed_count"] == 1


async def test_three_closed_is_plural(db):  # noqa: F811
    app, _p, _c, _l, sid = await _seed_three(db)
    for hours in (2, 3):
        await _another_closed(db, sid, hours)
    totals = (await _list(app))["totals"]
    assert (totals["closed_count"], totals["closed_text"]) == (3, MANY.format(n=3))


async def test_stored_closed_with_an_open_leg_is_not_counted(db):  # noqa: F811
    """The count uses the list's own predicate (no open leg): status "closed" on 48, with open legs, adds none."""
    app, _p, _c, _l, sid = await _seed_three(db)
    await db.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :id"), {"id": sid["48"]})
    totals = (await _list(app))["totals"]
    assert (totals["closed_count"], totals["closed_text"]) == (1, ONE)
