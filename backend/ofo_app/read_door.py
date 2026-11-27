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
from collections.abc import Awaitable, Callable
from typing import Any

POLL_SECONDS = 0.05  # the poll while a token has no live quote yet (the live push's own)
READ_KEY = "read-door"

_lease: Any = None


def read_lease() -> Any:
    """The door's lease table (one per process). Imported late: ``routes.leg_picker`` imports the app layer."""
    global _lease  # noqa: PLW0603 - one process-wide table, like the picker's own
    if _lease is None:
        from ofo_app.routes.leg_picker import WindowLease  # noqa: PLC0415
        _lease = WindowLease()
    return _lease


async def read_quotes(feed: Any, ids: Any, read: Callable[[], Any], done: Callable[[Any], bool],  # noqa: PLR0913
                      connected: Callable[[], bool], wait_s: float, poll_s: float = POLL_SECONDS, *,
                      sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                      now: Callable[[], float] | None = None) -> Any:
    """``read()`` of the tokens ``ids`` on ``feed`` (a ``LiveFeed``). Answer states: every price live at once
    (``done``) -> that read, no wait; otherwise polled, all tokens in parallel, until ``done``, the provider
    disconnects or ``wait_s`` passes -> the last read; the fan-out has no token for ANY id -> None (nothing held, the
    caller keeps its own read); no feed -> the caller does not call the door. The hold is the standing lease: a token
    already held is not subscribed again and the lease is released by its own timer, never by this call."""
    wanted = sorted(dict.fromkeys(ids))
    key = (READ_KEY, tuple(wanted))
    lease = read_lease()
    lease.hold(feed, key, wanted)
    if wanted and not lease.ids_of(key):
        return None
    clock = now or asyncio.get_running_loop().time
    deadline = clock() + wait_s
    snap = read()
    while not (done(snap) or not connected() or clock() >= deadline):
        await sleep(poll_s)
        snap = read()
    return snap
