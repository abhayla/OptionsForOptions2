"""ADR-293 (no database): delete is offered to a practice-only strategy; restore stays closed after any order."""
from ofo_app import strategy_store as store


def test_delete_rule_ignores_practice_orders_but_still_needs_no_plan_and_no_version() -> None:
    assert "paper_orders" not in store._DELETABLE_SQL
    assert "execution_plans" in store._DELETABLE_SQL and "strategy_versions" in store._DELETABLE_SQL


def test_restore_rule_still_counts_practice_orders() -> None:
    assert "paper_orders" in store._CAN_DELETE_SQL  # ADR-293 (5): history stays view-only after any order


def test_the_list_offers_delete_by_the_delete_rule() -> None:
    assert store._DELETABLE_SQL in str(store._LIST)


# ADR-293 behaviour without a PostgreSQL server: sqlite can attach a database named "public", so the ONE rule
# fragment runs as written against stand-in tables (only strategy_id matters to it).
import sqlite3  # noqa: E402

import pytest  # noqa: E402

_TABLES = ("execution_plans", "strategy_versions", "strategy_held_entries", "paper_orders")


def _deletable(placed: tuple[str, ...]) -> bool:
    db = sqlite3.connect(":memory:")
    db.execute("ATTACH DATABASE ':memory:' AS public")
    db.execute("CREATE TABLE public.strategies (id INTEGER)")
    db.execute("INSERT INTO public.strategies VALUES (1)")
    for t in _TABLES:
        db.execute(f"CREATE TABLE public.{t} (strategy_id INTEGER)")
        if t in placed:
            db.execute(f"INSERT INTO public.{t} VALUES (1)")
    return db.execute(f"SELECT {store._DELETABLE_SQL} FROM public.strategies AS s").fetchone()[0] == 1  # noqa: S608


@pytest.mark.parametrize(("placed", "expected"), [
    ((), True),                                    # nothing placed
    (("paper_orders",), True),                     # practice orders only
    (("paper_orders", "execution_plans"), False),  # practice orders AND a plan row
    (("paper_orders", "strategy_held_entries"), False),  # a condor held at the broker (ADR-292)
    (("paper_orders", "strategy_versions"), False),
    (("execution_plans",), False),
])
def test_the_delete_rule_by_what_was_placed(placed: tuple[str, ...], expected: bool) -> None:
    assert _deletable(placed) is expected


def test_the_worker_does_not_lapse_open_records_of_a_hidden_strategy() -> None:
    from ofo_app import playbook_store  # noqa: PLC0415
    assert "deleted_at IS NULL" in str(playbook_store._OPEN_STRATEGY_IDS)  # ADR-293 (3): Undo finds them open
