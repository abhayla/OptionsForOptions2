"""Per-request step timing (measurement only; no product behaviour). One mutable accumulator per HTTP request lives in a
ContextVar set by ``request_log.RequestLog``; outside a request (background worker, tests) every call is a no-op.

Steps: ``db`` (SQL statements, from SQLAlchemy cursor events: ms and query count), ``price`` (market and REST price
reads), ``margin`` (broker margin read). Spec basis: REQ-049 AC-4; cheap, always on: ``perf_counter`` only.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any, TypeVar

T = TypeVar("T")


class Steps:
    """ms and call count per step name, for ONE request. Mutated by the request's own tasks only."""

    __slots__ = ("count", "ms")

    def __init__(self) -> None:
        self.ms: dict[str, float] = {}
        self.count: dict[str, int] = {}


_current: ContextVar[Steps | None] = ContextVar("ofo_step_timing", default=None)


def start() -> Token:
    return _current.set(Steps())


def stop(token: Token) -> None:
    _current.reset(token)


def add(step: str, ms: float) -> None:
    steps = _current.get()
    if steps is None:
        return
    steps.ms[step] = steps.ms.get(step, 0.0) + ms
    steps.count[step] = steps.count.get(step, 0) + 1


def snapshot() -> dict[str, tuple[float, int]]:
    """step -> (total ms, calls); empty outside a request."""
    steps = _current.get()
    return {} if steps is None else {k: (v, steps.count[k]) for k, v in steps.ms.items()}


def timed(step: str, fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Same signature as ``fn``; adds the elapsed ms to ``step`` (also when ``fn`` raises)."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        t0 = time.perf_counter()
        try:
            return await fn(*args, **kwargs)
        finally:
            add(step, (time.perf_counter() - t0) * 1000.0)

    return wrapper


_t0: ContextVar[float | None] = ContextVar("ofo_step_timing_stmt", default=None)


def install_db_events(engine: Any) -> None:
    """Register the cursor-event timers once on a SQLAlchemy sync engine (idempotent)."""
    from sqlalchemy import event  # noqa: PLC0415 - keeps this module light for non-DB importers

    if getattr(engine, "_ofo_step_timing", False):
        return
    engine._ofo_step_timing = True

    def before(conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any) -> None:
        if _current.get() is not None:
            conn.info.setdefault("ofo_t0", []).append(time.perf_counter())

    def after(conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any) -> None:
        stack = conn.info.get("ofo_t0")
        if stack:
            add("db", (time.perf_counter() - stack.pop()) * 1000.0)

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)
