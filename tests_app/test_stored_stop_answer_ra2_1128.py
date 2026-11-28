"""Lane RA2, Opus review F-3 of Lane RA (a stop that WAS stored is never reported as failed): a read AFTER the commit
of a trigger route (the trigger list, the contracts, the book) that fails answered 500 for a stop that is stored and
armed. Now the answer is built once more on a clean transaction; if that also fails the route answers the success it
is (201 with an empty list; the page reloads the list), never an error. Nothing is stored twice: a repeat press is
answered ``already_set``.
Real case: the stop "above 23,100" on strategy 1 of the replay book: the list read after its commit fails once."""
from __future__ import annotations

from http import HTTPStatus

from ofo_app import paper_monitor, paper_trigger_store
from sqlalchemy.exc import OperationalError
from test_paper_triggers_routes import _client, _close_the_market, _open, _stored, _url, db, notified  # noqa: F401

BODY = {"kind": "conditional_exit", "above": "23100"}


def _fail_after_commit(monkeypatch, times: int):
    """``list_for`` raises ``times`` times once the route has committed (``paper_monitor.notify`` runs right after)."""
    state = {"committed": False, "left": times}
    real = paper_trigger_store.list_for

    async def list_for(db, strategy_id):  # noqa: F811
        if state["committed"] and state["left"] > 0:
            state["left"] -= 1
            raise OperationalError("SELECT", {}, Exception("the database dropped the connection"))
        return await real(db, strategy_id)

    monkeypatch.setattr(paper_trigger_store, "list_for", list_for)
    monkeypatch.setattr(paper_monitor, "notify", lambda: state.update(committed=True))


async def test_core_a_failed_read_after_the_commit_is_retried_and_the_stop_is_answered(db, notified, monkeypatch):  # noqa: F811
    app, stored, _ids = await _open(db)
    _close_the_market(app)
    _fail_after_commit(monkeypatch, times=1)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=BODY)
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert [(r["direction"], r["state"]) for r in reply.json()["triggers"]] == [("above", "armed")]
    assert len(await _stored(db, stored.id)) == 1


async def test_a_read_that_keeps_failing_still_answers_the_stop_as_stored_never_an_error(db, notified, monkeypatch):  # noqa: F811
    app, stored, _ids = await _open(db)
    _close_the_market(app)
    _fail_after_commit(monkeypatch, times=99)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=BODY)
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert reply.json()["triggers"] == [] and reply.json()["already_set"] is False
    assert len(await _stored(db, stored.id)) == 1, "the stop is stored and armed"
