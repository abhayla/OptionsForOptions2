"""The ONE read door of a request that needs prices from the shared feed (hotfix 27 Nov, finding: market reads wait).

Spec basis: REQ-133 (live / stale), ADR-330 (39) (the per-quote age rule, ``FeedState.quote_health``: unchanged, the
caller's ``done`` predicate reads it), ADR-015, ADR-008; ``live_push.hold_and_read`` (retired by this door).

RCA: in bus mode the API process books a tick only for a token somebody in THIS process holds
(``KiteProvider.on_frame``). Every request read held what it read and RELEASED it at the end (a released token is
parked and reads "no quote"), so the next request found the book empty again and waited for a NEW frame per token, up
to its wait, one request after the other (plan-watch, adjustment check / plan, positions, paper strategy: 4-7 s each)
while fresh ticks sat in Redis.
Fix (class): a read takes its hold on a standing lease (``WindowLease``: the shared fan-out counts holders, a token a
lease already holds is never subscribed again, and the lease ends LEASE_SECONDS after its last read). A read first
looks at the book: when ``done`` (every price live by the caller's own rule) it returns at ONCE, zero waits; only
otherwise it polls, ALL tokens together under ONE deadline, never one token after another. No new age rule.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

POLL_SECONDS = 0.05  # the poll while a token has no live quote yet (the live push's own)
MAX_HELD_TOKENS = 500  # the cap on tokens the door's leases hold (REQ-113 AC-6's socket cap is higher)


class _NoToken:
    """The door's own answer "the fan-out has no token for any id": distinct from whatever the caller's read returns
    (a read may itself be None). Callers keep their own read on it."""

    def __repr__(self) -> str:
        return "NO_TOKEN"


NO_TOKEN: Any = _NoToken()


def _ignore(_quote: Any) -> None:
    """The fan-out listener: reads take the provider's current quotes (with their health at that moment)."""


@dataclass
class _Held:
    feed: Any
    handle: int
    expires: float


class ReadLease:
    """The door's standing holds: one handle per TOKEN (never per id set) with ONE shared expiry each, renewed by every
    read of that token; at most ``MAX_HELD_TOKENS`` (the oldest-renewed is let go first); ONE sweeper timer per door."""

    def __init__(self) -> None:
        self._held: OrderedDict[str, _Held] = OrderedDict()  # oldest-renewed first
        self._timer_loop: Any = None  # the loop the sweeper is armed on (None: no sweeper pending)

    @property
    def held_ids(self) -> frozenset[str]:
        return frozenset(self._held)

    def holds(self, feed: Any, instrument_id: str) -> bool:
        held = self._held.get(instrument_id)
        return held is not None and held.feed is feed

    def hold(self, feed: Any, ids: list[str], *, seconds: float, now: float) -> frozenset[str]:
        """Hold every id the provider knows (renewing one already held, never subscribing it again); returns the ids
        the provider has no token for: they are never leased, so the next read asks again."""
        unknown: set[str] = set()
        for i in ids:
            held = self._held.get(i)
            if held is not None and held.feed is feed:
                held.expires = now + seconds
                self._held.move_to_end(i)
                continue
            self._drop(i)
            try:
                handle = feed.fanout.subscribe(_ignore, [i], max_queue=1)
            except KeyError:
                unknown.add(i)
                continue
            self._held[i] = _Held(feed, handle, now + seconds)
        keep = set(ids)
        for i in [k for k in self._held if k not in keep]:  # over the cap: the oldest-renewed goes first
            if len(self._held) <= MAX_HELD_TOKENS:
                break
            self._drop(i)
        return frozenset(unknown)

    def _drop(self, instrument_id: str) -> None:
        held = self._held.pop(instrument_id, None)
        if held is not None:
            with contextlib.suppress(Exception):
                held.feed.fanout.unsubscribe(held.handle)

    def release(self, ids: Any = None) -> None:
        """End the hold of ``ids``, or every hold (the leases' end)."""
        for i in list(self._held) if ids is None else list(ids):
            self._drop(i)

    def arm(self, loop: Any) -> None:
        """ONE sweeper per door: armed when none is pending on this loop; it releases the expired tokens and re-arms
        for the earliest remaining expiry. (No timer is cancelled: a read is not an order route.)"""
        if self._timer_loop is loop or not self._held:
            return
        self._timer_loop = loop
        next_end = min(h.expires for h in self._held.values())
        loop.call_later(next_end - loop.time(), self._sweep, loop)  # a past end fires at once

    def _sweep(self, loop: Any) -> None:
        self._timer_loop = None
        now = loop.time()
        for i in [k for k, h in self._held.items() if h.expires <= now]:
            self._drop(i)
        self.arm(loop)


_lease: ReadLease | None = None


def read_lease() -> ReadLease:
    """The door's lease table (one per process)."""
    global _lease  # noqa: PLW0603 - one process-wide table, like the picker's own
    if _lease is None:
        _lease = ReadLease()
    return _lease


async def read_quotes(feed: Any, ids: Any, read: Callable[[], Any], done: Callable[[Any], bool],  # noqa: PLR0913
                      connected: Callable[[], bool], wait_s: float, poll_s: float = POLL_SECONDS, *,
                      sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                      now: Callable[[], float] | None = None,
                      done_known: Callable[[Any, frozenset[str]], bool] | None = None,
                      unknown_out: set[str] | None = None) -> Any:
    """``read()`` of the tokens ``ids`` on ``feed`` (a ``LiveFeed``). Answer states: every price live at once
    (``done``) -> that read, no wait; otherwise polled, all tokens in parallel, until ``done``, the provider
    disconnects or ``wait_s`` passes -> the last read; the fan-out has no token for ANY id -> ``NO_TOKEN`` (nothing
    held, distinct from a read that is itself None; the caller keeps its own read); no feed -> the caller does not call
    the door. An id with no token is never leased (the next read asks again), never waited for and is added to
    ``unknown_out``; with one, the wait ends when ``done_known(snap, known_ids)`` (the caller's rule for the known ids
    only) holds, and without it the door reads once and returns. The hold is the standing lease: a token already held
    is not subscribed again and the lease is released by its own sweeper, never by this call."""
    wanted = sorted(dict.fromkeys(ids))
    loop = asyncio.get_running_loop()
    from ofo_app.routes import leg_picker  # noqa: PLC0415 - imports the app layer; the lease length is the picker's
    lease = read_lease()
    unknown = lease.hold(feed, wanted, seconds=leg_picker.LEASE_SECONDS, now=loop.time())
    lease.arm(loop)
    if unknown_out is not None:
        unknown_out.update(unknown)
    if wanted and len(unknown) == len(wanted):
        return NO_TOKEN
    known = frozenset(wanted) - unknown
    clock = now or loop.time
    deadline = clock() + wait_s
    snap = read()
    if unknown and done_known is None:
        return snap  # an id nobody can quote is never waited for
    ready = done if not unknown else (lambda s: done_known(s, known))  # type: ignore[misc]
    while not (ready(snap) or not connected() or clock() >= deadline):
        await sleep(poll_s)
        snap = read()
    if not connected():
        lease.release(known)  # a disconnected provider quotes nothing: no standing hold is kept for it
    return snap
