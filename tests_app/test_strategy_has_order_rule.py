"""Issue 16 round 2 (ADR-299, ADR-298): ``has_order`` is ONE field, computed in ONE place, true when the strategy has
any placed order, practice (paper_orders) OR real (an execution_plans row: a basket was sent). No database: the rule is
read from the one SQL fragment the list uses, and the reply models carry the field. The rows themselves are proven by
tests_app/test_strategy_delete_app.py (database, run one file at a time)."""
from __future__ import annotations

import dataclasses

from ofo_app import strategy_store as store
from ofo_app.routes.strategies import StrategyListOut


def test_one_fragment_names_both_kinds_of_order():
    sql = store._HAS_ORDER_SQL
    assert "paper_orders" in sql and "execution_plans" in sql  # practice and real alike (ADR-298)
    assert "s.id" in sql  # a per-strategy EXISTS, the list's own alias


def test_the_list_selects_that_fragment_as_has_order():
    assert f"{store._HAS_ORDER_SQL} AS has_order" in str(store._LIST)


def test_summary_and_reply_carry_the_field_additively():
    fields = {f.name: f for f in dataclasses.fields(store.StrategySummary)}
    assert fields["has_order"].default is False  # fail closed: never "ordered" by default
    item = StrategyListOut.model_fields["strategies"].annotation.__args__[0]
    assert "has_order" in item.model_fields and "has_paper_order" in item.model_fields  # the old field stays
