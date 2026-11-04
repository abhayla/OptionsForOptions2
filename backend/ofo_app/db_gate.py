"""The background role's ONE database gate with an order of service (#636 r6).

The role opens at most one connection at a time (ADR-048 role limit 5 = API 2 + background 1 + feed 1;
``config.py`` DB_POOL_SIZE=1 for the worker), so every database step of the role holds this gate. Waiters are served
by rank, then by arrival: the writer's alert-event and rule-memory writes first (``GATE_WRITER``: ADR-237 (3)
promises a confirmed crossing's record within 10 s of the close), then the settings poll (``GATE_POLL``: REQ-167 AC-4
lag), then the rebuild's per-strategy reads (``GATE_REBUILD``, also the rank of a plain ``async with gate``). A
holder is never interrupted, so a waiter's longest wait is one hold of whoever has the gate; the rebuild holds it for
one strategy's reads at a time (``background.owner_lister``, ``Worker._load_gates``), never for the whole list.

Answer states: free -> taken at once; held -> queued by (rank, arrival); a queued waiter cancelled -> removed, never
keeps the gate; a waiter handed the gate and cancelled before it ran -> the gate passes to the next waiter.
"""
from __future__ import annotations

import asyncio
import contextlib
import heapq
import itertools
from collections.abc import AsyncIterator
from typing import Any, Final

GATE_WRITER: Final = 0  # alert-event writes, then rule-memory writes (the ONE writer task)
GATE_POLL: Final = 1  # the settings cache's count(*) poll
GATE_REBUILD: Final = 2  # the strategy-list rebuild, one strategy's reads per hold


class DbGate:
    """A lock whose waiters are served by rank, then arrival (module docstring)."""

    def __init__(self) -> None:
        self._held = False
        self._waiters: list[tuple[int, int, asyncio.Future]] = []
        self._seq = itertools.count()

    def locked(self) -> bool:
        return self._held

    async def _acquire(self, rank: int) -> None:
        if not self._held and not self._waiters:
            self._held = True
            return
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiters, (rank, next(self._seq), fut))
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():  # handed the gate, cancelled before running: pass it on
                self._release()
            raise  # a still-queued cancelled future is skipped by ``_release``

    def _release(self) -> None:
        while self._waiters:
            _rank, _seq, fut = heapq.heappop(self._waiters)
            if not fut.done():
                fut.set_result(None)  # handed over: the gate stays held, by the next waiter
                return
        self._held = False

    @contextlib.asynccontextmanager
    async def hold(self, rank: int = GATE_REBUILD) -> AsyncIterator[None]:
        await self._acquire(rank)
        try:
            yield
        finally:
            self._release()

    async def __aenter__(self) -> None:
        await self._acquire(GATE_REBUILD)

    async def __aexit__(self, *_exc: object) -> bool:
        self._release()
        return False


def held(gate: Any, rank: int) -> contextlib.AbstractAsyncContextManager:
    """``gate`` held at ``rank``: a ``DbGate`` by rank, a plain lock as itself, none as no gate."""
    if gate is None:
        return contextlib.nullcontext()
    if isinstance(gate, DbGate):
        return gate.hold(rank)
    return gate
