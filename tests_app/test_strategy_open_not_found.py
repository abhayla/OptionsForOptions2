"""NEW-T66 finish (ADR-330 (37)): opening one strategy by id that does not exist answers its own catalogue message
(404, `strategy_not_found`); every other caller of the same store refusal keeps the generic "not available" reply.
Domain test (no database): the route's refusal mapping is a pure function."""
from __future__ import annotations

from ofo_app import strategy_store as store
from ofo_app.errors import Failure
from ofo_app.routes.strategies import refused_answer


def _missing() -> store.StrategyStoreError:
    return store.StrategyStoreError(store.NOT_FOUND, "no such strategy")


def test_open_by_id_missing_strategy_has_its_own_message():
    out = refused_answer(_missing(), 409, open_by_id=True)
    assert out.failure is Failure.NOT_FOUND
    m = out.message
    assert m.what_happened == "This strategy was not found. It may have been deleted."
    assert m.code == "STRATEGY_VALIDATION_523"
    assert "My Strategies" in m.next_action


def test_other_callers_keep_the_generic_not_available_reply():
    out = refused_answer(_missing(), 409)
    assert out.failure is Failure.NOT_FOUND
    assert out.message.what_happened == "The page or action you asked for is not available here."


def test_open_by_id_leaves_other_refusals_alone():
    out = refused_answer(store.StrategyStoreError(store.HISTORY_NOT_FOUND, "x"), 409, open_by_id=True)
    assert out.message.what_happened == "The page or action you asked for is not available here."
