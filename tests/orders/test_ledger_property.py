"""Core: one fill ledger is the only source of truth. An order's filled quantity and each
position are computed from it, never stored.

Proof: after any random sequence of calls (fills, replays, reused trade ids across orders,
conflicts, add/transition misuse), each position equals the signed sum of the ledger and each
order's filled count equals the sum of its ledger rows for that order. Exceptions from invalid
calls are expected and swallowed (a rejected call must never corrupt state); the invariant is
re-checked after EVERY call, valid or not.
"""
from __future__ import annotations

import datetime
import random
from decimal import Decimal as D

import pytest

from book_helpers import bound_book

from ofo.engine.legs import Action
from ofo.orders.model import FillEvent, Order, OrderBook, OrderState

UTC = datetime.timezone.utc
READ_AT = datetime.datetime(2026, 9, 29, 10, 5, tzinfo=UTC)
STRATEGIES = ("STRAT-1", "STRAT-2")
CONTRACTS = ("NIFTY26OCT23000CE", "NIFTY26OCT23000PE")
BROKER_ORDER_IDS = ("BRK-1", "BRK-2", "BRK-3", "BRK-4")
TRADE_IDS = ("t1", "t2", "t3")  # deliberately few, so ids collide across orders (round-2 bug)


def _assert_invariants(book: OrderBook, registered: dict[str, Order]) -> None:
    """The Core property, checked against the RAW ledger rows (the one source of truth), never
    against a value another part of the code already computed the same way."""
    rows = book.raw_fills()

    # Each order's filled_quantity equals the sum of ITS OWN ledger rows.
    for broker_order_id in registered:
        expected = sum(f.quantity for f in rows if f.broker_order_id == broker_order_id)
        assert book.order_for(broker_order_id).filled_quantity == expected, (
            f"{broker_order_id}: filled_quantity diverged from its ledger rows"
        )

    # Each (strategy, contract) position equals the signed sum of the matching ledger rows.
    seen: set[tuple[str, str]] = set()
    for f in rows:
        order = registered[f.broker_order_id]
        seen.add((order.strategy_id, f.contract))
    for strategy_id, contract in seen:
        expected = sum(
            (f.quantity if f.side is Action.BUY else -f.quantity)
            for f in rows
            if registered[f.broker_order_id].strategy_id == strategy_id and f.contract == contract
        )
        assert book.position(strategy_id, contract) == expected, (
            f"({strategy_id}, {contract}): position diverged from the ledger's signed sum"
        )

    # No ledger row is ever duplicated at the same key with two different copies (append-only,
    # one copy per key) -- the FillConflictError guard's own invariant.
    keys = [(f.broker_order_id, f.trade_id) for f in rows]
    assert len(keys) == len(set(keys)), "a (broker_order_id, trade_id) key has more than one row"


def _new_order(rng: random.Random, broker_order_id: str, registered: dict[str, Order]) -> Order:
    return Order(
        strategy_id=rng.choice(STRATEGIES), leg_ref=f"leg-{broker_order_id}",
        contract=rng.choice(CONTRACTS), side=rng.choice([Action.BUY, Action.SELL]),
        quantity=rng.choice([10, 20, 30]), price=D("100.00"), broker_order_id=broker_order_id, version_id="v1",
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_ledger_is_the_only_source_of_truth_under_random_misuse(seed: int) -> None:
    rng = random.Random(seed)
    book = bound_book()
    registered: dict[str, Order] = {}

    for _ in range(400):
        action = rng.choice(["add", "transition", "fill", "reconcile"])
        try:
            if action == "add":
                broker_order_id = rng.choice(BROKER_ORDER_IDS)
                order = _new_order(rng, broker_order_id, registered)
                book.add(order)
                registered[broker_order_id] = order  # only reached if add() succeeded

            elif action == "transition" and registered:
                broker_order_id = rng.choice(list(registered))
                target = rng.choice(list(OrderState))
                book.transition(broker_order_id, target)

            elif action == "fill" and registered:
                broker_order_id = rng.choice(list(registered))
                order = registered[broker_order_id]
                # Sometimes match the order exactly, sometimes deliberately mismatch it, and
                # sometimes deliberately reuse a trade_id already used by ANOTHER order (the
                # round-2 defect class) to prove the composite key keeps them independent.
                contract = order.contract if rng.random() < 0.7 else rng.choice(CONTRACTS)
                side = order.side if rng.random() < 0.7 else rng.choice([Action.BUY, Action.SELL])
                fill = FillEvent(
                    trade_id=rng.choice(TRADE_IDS), broker_order_id=broker_order_id,
                    contract=contract, side=side, quantity=rng.choice([1, 5, 9, 15]),
                    price=D("100.00"), timestamp=datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
                )
                book.apply_fill(fill)

            elif action == "reconcile" and registered:
                broker_order_id = rng.choice(list(registered))
                book.reconcile_cumulative(broker_order_id, rng.choice([0, 1, 5, 100]), read_at=datetime.datetime.now(UTC))

        except ValueError:
            pass  # a refused call must change nothing; checked by the invariant below regardless

        _assert_invariants(book, registered)
