"""I-39 (test plan 28 Nov 2026): the Completed Strategies header said 15 while the rows showed another number. The list
the page reads (GET /strategies) must carry exactly one row per completed strategy, so a count taken from it (the
header) equals the rows shown: no cap, no row dropped, none counted twice, a deleted one not counted.

Real case: 15 closed strategies of one user plus one draft and one hidden (soft-deleted) closed one: the page's
Completed filter (``status == 'closed'`` / word "Completed") must give 15 rows, the same 15 ids as the database.
Spec basis: ADR-299 (status word), ADR-259 (a closed trade is listed on Completed), ADR-293 (a deleted one is hidden).
"""
from __future__ import annotations

from sqlalchemy import text
from test_migration_0026_strategy_deleted_at import DEFINITION, INSERT
from test_strategy_closed_status import db  # noqa: F401 - the rolled-back connection fixture
from test_strategy_store import _client
from test_strategy_tracking import _setup

COMPLETED = 15
OK = 200


async def _closed(conn, user: str) -> int:
    sid = (await conn.execute(text(INSERT), {"u": user, "d": DEFINITION})).scalar_one()
    await conn.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :id"), {"id": sid})
    return sid


async def test_header_count_equals_the_completed_rows_the_list_returns(db):  # noqa: F811
    app, stored, *_ = await _setup(db)  # one draft of the user: not completed
    user = stored.user_ref
    ids = [await _closed(db, user) for _ in range(COMPLETED)]
    hidden = await _closed(db, user)
    await db.execute(text("UPDATE public.strategies SET deleted_at = now() WHERE id = :id"), {"id": hidden})
    async with _client(app) as c:
        reply = await c.get("/strategies")
    assert reply.status_code == OK, reply.text
    rows = reply.json()["strategies"]
    completed = [r for r in rows if r["status"] == "closed"]
    assert sorted(r["id"] for r in completed) == sorted(ids), "rows differ from the database's completed set"
    assert len(completed) == COMPLETED  # the header's number: a count of these rows, nothing else
    assert {r["status_word"] for r in completed} == {"Completed"}
    assert [r["id"] for r in rows if r["status_word"] == "Completed"] == [r["id"] for r in completed]
    assert hidden not in [r["id"] for r in rows] and stored.id in [r["id"] for r in rows]
    assert len({r["id"] for r in rows}) == len(rows)  # no row twice
