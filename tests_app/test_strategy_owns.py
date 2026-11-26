"""Phase 7 R2 (modular-doors plan 5.7): ONE ownership read, ``strategy_store.owns``; the stores keep their own errors.

Spec basis: none: the spec says nothing about helper layout (searched: ownership SQL, owns). Behaviour pinned: another
user's, a soft-deleted and a missing strategy all answer exactly alike (REQ-070 AC-6; strategy_store docstring).
Real input: a saved strategy from the recorded instrument fixture (``test_strategy_store._with_draft``), each test in
a rolled-back transaction.
"""
from __future__ import annotations

import pytest
from ofo_app import strategy_level_watch_store as watch
from ofo_app import strategy_pause_store as pause
from ofo_app import strategy_store
from test_strategy_store import _user, _with_draft

MISSING_ID = 987654321


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _hidden(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    await strategy_store.delete_draft(db, user, stored.id, expected_revision=stored.revision)
    return user, stored.id


async def test_owns_true_for_the_owner(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    assert await strategy_store.owns(db, user, stored.id) is True


async def test_owns_false_for_another_user(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    assert await strategy_store.owns(db, _user(), stored.id) is False


async def test_owns_false_for_a_soft_deleted_strategy(db):
    user, sid = await _hidden(db)
    assert await strategy_store.owns(db, user, sid) is False


async def test_owns_false_for_a_missing_id(db):
    assert await strategy_store.owns(db, _user(), MISSING_ID) is False


async def test_pause_store_not_found_for_not_owned_and_soft_deleted(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    with pytest.raises(pause.PauseNotFound):
        await pause.pause_of(db, _user(), stored.id)
    hidden_user, hidden_id = await _hidden(db)
    with pytest.raises(pause.PauseNotFound):
        await pause.pause_of(db, hidden_user, hidden_id)


async def test_level_watch_store_not_found_for_not_owned_and_soft_deleted(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    with pytest.raises(watch.WatchNotFound):
        await watch.watches_of(db, _user(), stored.id)
    hidden_user, hidden_id = await _hidden(db)
    with pytest.raises(watch.WatchNotFound):
        await watch.watches_of(db, hidden_user, hidden_id)
