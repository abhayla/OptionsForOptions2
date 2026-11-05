"""Scenario isolation guards (IC e2e paper contract, design decisions 3-5).

``guard_paper_order`` is the route dependency of every route in ``scenario_mode.PAPER_ORDER_ROUTES``. It is an
ALLOW-LIST: with scenario mode off it changes nothing (live behaviour unchanged, decision 17); with scenario mode on it
lets the request through ONLY when the strategy's stored ``scenario_id`` equals the scenario the process runs under.
Every other answer of the marker read refuses with 409 ``scenario_no_orders`` before the endpoint runs:

- marker equals the current scenario -> allowed;
- marker NULL (a live strategy) -> refused;
- marker of another scenario -> refused;
- no such strategy for this user -> refused (the endpoint never runs, so it cannot write);
- the read fails (database down, column missing) -> refused (fail closed).

``check_screen_isolation`` is the screen check's cross-case refusal (decision 4): a scenario strategy in live mode and
a live (or other-scenario) strategy in scenario mode -> 409 ``scenario_strategy_isolated``.

Real order routes (``REAL_ORDER_ROUTES``) keep ``scenario_mode.refuse_orders``: refused in scenario mode, always.
"""
from __future__ import annotations

import contextlib
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import text

from ofo_app import scenario_mode
from ofo_app.db import get_db
from ofo_app.errors import Failure
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused

ISOLATED_TEMPLATE = "scenario_strategy_isolated"
_MARKER = "SELECT scenario_id FROM public.strategies WHERE id = :id AND user_ref = :user_ref"

_ABSENT = object()


async def read_marker(db: Any, user_ref: str, strategy_id: int) -> object:
    """The stored ``scenario_id`` (a str, or None for a live strategy), or ``_ABSENT`` when no such strategy."""
    row = (await db.execute(text(_MARKER), {"id": strategy_id, "user_ref": user_ref})).first()
    return _ABSENT if row is None else row[0]


async def guard_paper_order(strategy_id: int, db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> None:
    current = scenario_mode.current_id()
    if current is None:
        return  # live mode: unchanged (decision 17)
    try:
        marker = await read_marker(db, user_ref, strategy_id)
    except Exception:  # noqa: BLE001 - an unreadable marker is never "the same scenario" (fail closed)
        await _rollback(db)
        marker = _ABSENT
    if marker is _ABSENT or marker != current:
        raise StrategyRefused(scenario_mode.TEMPLATE, Failure.CONFLICT)


async def _rollback(db: Any) -> None:
    with contextlib.suppress(Exception):  # the refusal is the answer either way
        await db.rollback()


def isolation_refusal(marker: object, current: str | None) -> bool:
    """True when the screen check must refuse: live mode on a scenario strategy, or scenario mode on a strategy whose
    marker is not the current scenario (NULL or another id). An absent strategy is left to the route's own 404."""
    if marker is _ABSENT:
        return False
    if current is None:
        return marker is not None
    return marker != current


async def check_screen_isolation(db: Any, user_ref: str, strategy_id: int) -> None:
    """Refuses (409 ``scenario_strategy_isolated``) a screen check across the live / scenario line."""
    if isolation_refusal(await read_marker(db, user_ref, strategy_id), scenario_mode.current_id()):
        raise StrategyRefused(ISOLATED_TEMPLATE, Failure.CONFLICT)
