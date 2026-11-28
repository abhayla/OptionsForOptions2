"""The unknown-outcome block: ONE durable guard every order door passes (Lane B2, weekend round 3; migration 0063).

Spec basis: ADR-016 to ADR-019 (submitted is not executed; no automatic retry; an unresolved outcome blocks the next
execution), ADR-330 (58) (paper and real alike: the same rule, the door tag only), ADR-017 (the request key).

The request key (``request_key``) only de-duplicates the SAME key and body. A retry with another body or key (a changed
``prices_not_live_confirmed``, an add whose key follows the live price) is a new request, so a second order could follow
an order whose outcome was never known. This module is the server's guarantee, whatever the key or the body:

* Every order request OPENS an attempt for its strategy before it does anything else (``public.order_attempts``,
  committed at once, in its own transaction). A partial unique index allows ONE open attempt per strategy, so two tabs
  or two requests cannot both pass: the second is refused while the first runs.
* An open attempt closes when its outcome is known: the request ended without an exception (``stored``); it ended with a
  clean refusal (a ``StrategyRefused``) and the database holds nothing from it (``not_stored``), or holds orders
  (``stored``). Any other end (a crash, a failed or late commit, a cancelled request, a failed read after the commit)
  leaves it OPEN: the outcome is unknown.
* A request that finds an open attempt looks at what the database holds: orders, plans or a finished key row written
  since the attempt began -> it was ``stored``; nothing, and the attempt is older than ``SETTLE_SECONDS`` (longer than
  any request or commit can run) -> ``not_stored``; otherwise the new request is REFUSED (``order_outcome_unknown``),
  nothing is stored, and the page reads the strategy's orders. Release is therefore automatic once the outcome is
  known; no request is ever retried by the server (ADR-017).
* A table that cannot be read or written refuses the request (``request_key_store_unavailable``): fail closed.

The guard is a dependency of every route in ``scenario_mode.ORDER_ROUTES`` except the Return door (it RECORDS an
outcome); ``scenario_mode.misguarded_order_routes`` fails the start-up when one lacks it.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends
from fastapi.exceptions import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ofo_app.db import get_db
from ofo_app.errors import Failure
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused

_LOG = logging.getLogger(__name__)

#: An open attempt older than this with nothing stored is known not stored: far beyond the 8 s request deadline and
#: any commit; the unknown-outcome window of the request key is 120 s too.
SETTLE_SECONDS = 120
UNKNOWN_TEMPLATE = "order_outcome_unknown"
STORE_TEMPLATE = "request_key_store_unavailable"

_OPEN = text(
    "INSERT INTO public.order_attempts (user_ref, strategy_id, door, state) VALUES (:u, :s, :d, 'open') "
    "ON CONFLICT (strategy_id) WHERE state = 'open' DO NOTHING RETURNING id")
_READ_OPEN = text(
    "SELECT a.id, a.started_at, a.started_at < clock_timestamp() - make_interval(secs => :settle) AS settled, "
    "(EXISTS (SELECT 1 FROM public.paper_orders o WHERE o.strategy_id = a.strategy_id "
    "          AND o.created_at >= a.started_at) "
    " OR EXISTS (SELECT 1 FROM public.execution_plans p WHERE p.strategy_id = a.strategy_id "
    "            AND p.created_at >= a.started_at) "
    " OR EXISTS (SELECT 1 FROM public.order_request_keys k WHERE k.strategy_id = a.strategy_id "
    "            AND k.created_at >= a.started_at)) AS stored "
    "FROM public.order_attempts a WHERE a.strategy_id = :s AND a.state = 'open'")
_STORED_SINCE = text(
    "SELECT (EXISTS (SELECT 1 FROM public.paper_orders o WHERE o.strategy_id = a.strategy_id "
    "                AND o.created_at >= a.started_at) "
    " OR EXISTS (SELECT 1 FROM public.execution_plans p WHERE p.strategy_id = a.strategy_id "
    "            AND p.created_at >= a.started_at) "
    " OR EXISTS (SELECT 1 FROM public.order_request_keys k WHERE k.strategy_id = a.strategy_id "
    "            AND k.created_at >= a.started_at)) FROM public.order_attempts a WHERE a.id = :id")
_CLOSE = text("UPDATE public.order_attempts SET state = :st, resolved_at = clock_timestamp() "
              "WHERE id = :id AND state = 'open'")


def _refused(template: str, failure: Failure = Failure.CONFLICT) -> StrategyRefused:
    return StrategyRefused(template, failure)


async def _end_transaction(db: Any, commit: bool) -> None:
    try:
        await (db.commit() if commit else db.rollback())
    except Exception:  # noqa: BLE001 - the answer is decided either way
        _LOG.warning("order outcome: could not end the guard's transaction", exc_info=True)


async def open_attempt(db: Any, user_ref: str, strategy_id: int, door: str) -> int:
    """Opens the strategy's one attempt and returns its id (committed). Refuses (nothing stored) while an earlier
    attempt's outcome is unknown, or when the table cannot be used."""
    try:
        for _ in range(3):
            row = (await db.execute(_OPEN, {"u": user_ref, "s": strategy_id, "d": door})).first()
            if row is not None:
                await db.commit()
                return int(row[0])
            earlier = (await db.execute(_READ_OPEN, {"s": strategy_id, "settle": SETTLE_SECONDS})).first()
            if earlier is None:  # it closed between the two statements: try the claim again
                continue
            if earlier.stored:
                await db.execute(_CLOSE, {"st": "stored", "id": earlier.id})
            elif earlier.settled:
                await db.execute(_CLOSE, {"st": "not_stored", "id": earlier.id})
            else:
                await _end_transaction(db, commit=False)
                raise _refused(UNKNOWN_TEMPLATE)
            await db.commit()
    except StrategyRefused:
        raise
    except (SQLAlchemyError, OSError, TimeoutError):
        await _end_transaction(db, commit=False)
        raise _refused(STORE_TEMPLATE, Failure.UPSTREAM_BUSY) from None
    await _end_transaction(db, commit=False)
    raise _refused(UNKNOWN_TEMPLATE)


#: An exception that is a clean refusal made by the app before it stored anything it could not undo.
_CLEAN = (StrategyRefused, HTTPException)


async def close_attempt(db: Any, attempt_id: int, error: BaseException | None) -> None:
    """Closes the attempt when its outcome is known (module docstring); leaves it open otherwise. Never raises: a
    failure here leaves the attempt open, which blocks the strategy until the window passes (fail closed)."""
    try:
        if error is None:
            state = "stored"
        elif isinstance(error, _CLEAN):
            await db.rollback()  # the request's own transaction is over before the database is asked what it holds
            state = "stored" if (await db.execute(_STORED_SINCE, {"id": attempt_id})).scalar_one() else "not_stored"
        else:
            _LOG.warning("order outcome: attempt %s stays open, the request ended with %r", attempt_id, error)
            return
        await db.execute(_CLOSE, {"st": state, "id": attempt_id})
        await db.commit()
    except Exception:  # noqa: BLE001 - see the docstring
        _LOG.warning("order outcome: attempt %s could not be closed", attempt_id, exc_info=True)
        await _end_transaction(db, commit=False)


@contextlib.asynccontextmanager
async def attempt(door: str, strategy_id: int, db: Any, user_ref: str) -> AsyncIterator[None]:
    """Opens the strategy's attempt, runs the request, closes the attempt by how the request ended."""
    attempt_id = await open_attempt(db, user_ref, strategy_id, door)
    try:
        yield
    except BaseException as error:
        await close_attempt(db, attempt_id, error)
        raise
    await close_attempt(db, attempt_id, None)


async def guard_paper_outcome(strategy_id: int, db: Annotated[Any, Depends(get_db)],
                              user_ref: Annotated[str, Depends(current_user_ref)]) -> AsyncIterator[None]:
    """The dependency of every paper order route (``scenario_mode.PAPER_ORDER_ROUTES``)."""
    async with attempt("paper", strategy_id, db, user_ref):
        yield


async def guard_real_outcome(strategy_id: int, db: Annotated[Any, Depends(get_db)],
                             user_ref: Annotated[str, Depends(current_user_ref)]) -> AsyncIterator[None]:
    """The dependency of the real Execute door (the Return door records an outcome and is not guarded)."""
    async with attempt("real", strategy_id, db, user_ref):
        yield
