"""RA N6: what a request's open transaction holds that a whole-session rollback would silently drop.

A request that claimed an order request key (``request_key.claim_in_transaction``) or locked its strategy row
(``strategy_store._locked``: the I-158 guarantee) keeps both until its commit. A failing optional read on the same
session (the stored catalogue read behind the expiry kind) must then fail inside its own savepoint, never roll the
session back. A session that holds neither takes no savepoint: a read-only request pays no extra statement (the
latency ceilings count them, ``tests_app/test_route_latency_budget.py``).

The mark lives in the session's (or connection's) ``info`` dict; it is never cleared (an extra savepoint after a
commit is harmless and correct). A session double with no ``info`` is simply unmarked."""
from __future__ import annotations

from typing import Any

_KEY = "ofo.txn_holds"


def mark(db: Any) -> None:
    """Say that ``db``'s transaction now holds a claim or a lock."""
    info = getattr(db, "info", None)
    if isinstance(info, dict):
        info[_KEY] = True


def held(db: Any) -> bool:
    info = getattr(db, "info", None)
    return isinstance(info, dict) and info.get(_KEY) is True
