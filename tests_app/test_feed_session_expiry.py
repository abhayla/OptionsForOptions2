"""REQ-113 AC-8 (row 9 part B): at the session's expiry (ADR-053, 06:00) the feed closes that user's socket, publishes
"session ended" for the user and does not reconnect it; another user's socket is unaffected.

The clock is injected (a fake that the test advances); nothing sleeps for the time to pass. The token store is the
in-memory stand-in whose session keeps being returned (the worst case: the store has not ended it yet), so the
no-reconnect comes from the feed. Store answer states at the expiry: session present and not past -> run | past at the
re-check of a running socket -> close, ended, no reconnect | past when first read -> no socket, ended | gone from
the store -> stopped | a NEW session (new login) after the end -> a new socket.
"""
from __future__ import annotations

import datetime

import pytest
from ofo_app import feed_bus
from test_feed_user_isolation import T0, FakeClock, Rig, new_ref, stream_entries, user_status


@pytest.fixture
async def rig(redis_url):
    made = Rig(redis_url, FakeClock())
    yield made
    await made.close()


async def _ended(rig, user):
    status = await user_status(rig.bus, user)
    return status if status and status["ended"] else None


async def test_the_session_expiry_closes_that_users_socket_publishes_ended_and_never_reconnects(rig):
    """AC-8 attack 5: A's session expires at T0+1h (the 06:00 analogue), B's a day later. Advancing the fake clock past
    A's expiry: A's Kite connection closes, A's stream gets exactly one ``ended`` event and its status says ended, and
    for 10 minutes of fake clock (each minute with at least two re-checks of A) there is no reconnect; B's socket is
    never touched. A new login for A (a new session) then starts a new socket."""
    user_a, user_b = new_ref("ua"), new_ref("ub")
    kite_a, kite_b = await rig.kite(user_a), await rig.kite(user_b)
    expiry_a = T0 + datetime.timedelta(hours=1)
    rig.store.set(user_a, "TOK-A-expiry", expiry_a)
    rig.store.set(user_b, "TOK-B-expiry", T0 + datetime.timedelta(hours=24))
    rig.start()

    async def both_live():
        return ((await rig.live(user_a)) and (await rig.live(user_b))) or None

    await rig.until(both_live, "both live before the expiry")
    assert kite_a.active == 1 and kite_b.active == 1
    rig.clock.advance(hours=1, seconds=1)  # past A's expiry

    async def a_closed_and_ended():
        status = await _ended(rig, user_a)
        return status if status and kite_a.active == 0 else None

    status = await rig.until(a_closed_and_ended, "A's socket closed and the status ended")
    assert status["connected"] is False
    events = [m.kind for _i, m in await stream_entries(rig.bus, user_a) if m.kind == feed_bus.KIND_ENDED]
    assert events == [feed_bus.KIND_ENDED], "exactly one session-ended event for A"
    accepted = kite_a.accepted
    for _minute in range(10):  # 10 minutes of fake clock, never a sleep
        rig.clock.advance(minutes=1)
        reads = rig.store.reads[user_a]
        await rig.until(lambda r=reads: _reads_since(rig, user_a, r, 2), "two re-checks of A in this fake minute")
    assert kite_a.accepted == accepted and kite_a.active == 0, "the ended session was reconnected"
    assert (await _ended(rig, user_a)) is not None, "the ended status must stay available to the API"
    assert kite_b.accepted == 1 and kite_b.active == 1 and (await rig.live(user_b)) is not None
    rig.store.set(user_a, "TOK-A-new-login", rig.clock.now + datetime.timedelta(hours=20))  # a new login

    async def a_live_again():
        return (await rig.live(user_a)) or None

    await rig.until(a_live_again, "a new session's socket")
    assert kite_a.accepted == accepted + 1 and kite_b.accepted == 1


async def _reads_since(rig, user, before, n):
    return rig.store.reads[user] >= before + n or None


async def test_a_session_already_past_its_expiry_when_first_read_opens_no_socket(rig):
    """AC-8: a stored session whose expiry has passed (a box restarted at 07:00) gets no socket at all: status ended,
    one ended event, and Kite sees no connection."""
    user = new_ref("ua")
    kite = await rig.kite(user)
    rig.store.set(user, "TOK-late-box", T0 - datetime.timedelta(minutes=1))
    rig.start()
    await rig.until(lambda: _ended(rig, user), "the ended status")
    reads = rig.store.reads[user]
    await rig.until(lambda: _reads_since(rig, user, reads, 3), "three re-checks")
    assert kite.accepted == 0
    assert [m.kind for _i, m in await stream_entries(rig.bus, user)] == [feed_bus.KIND_ENDED]


async def test_an_expiry_in_the_future_changes_nothing(rig):
    """AC-8 negative: before the expiry the socket stays, no ended event is published."""
    user = new_ref("ua")
    kite = await rig.kite(user)
    rig.store.set(user, "TOK-not-yet", T0 + datetime.timedelta(hours=1))
    rig.start()
    await rig.until(lambda: rig.live(user), "live")
    rig.clock.advance(minutes=59)
    reads = rig.store.reads[user]
    await rig.until(lambda: _reads_since(rig, user, reads, 3), "three re-checks")
    assert kite.accepted == 1 and kite.active == 1
    assert all(m.kind != feed_bus.KIND_ENDED for _i, m in await stream_entries(rig.bus, user))
