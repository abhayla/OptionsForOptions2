"""ADR-293 (no database): delete is offered to a practice-only strategy; restore stays closed after any order."""
from ofo_app import strategy_store as store


def test_delete_rule_ignores_practice_orders_but_still_needs_no_plan_and_no_version() -> None:
    assert "paper_orders" not in store._DELETABLE_SQL
    assert "execution_plans" in store._DELETABLE_SQL and "strategy_versions" in store._DELETABLE_SQL


def test_restore_rule_still_counts_practice_orders() -> None:
    assert "paper_orders" in store._CAN_DELETE_SQL  # ADR-293 (5): history stays view-only after any order


def test_the_list_offers_delete_by_the_delete_rule() -> None:
    assert store._DELETABLE_SQL in str(store._LIST)
