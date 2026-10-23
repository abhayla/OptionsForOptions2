"""REQ-118 AC-7 period memo, review F2 items 2 and 3 (attack list items 2 and 3).

- Item 2: a refusal where nothing was sent (the limiter's own busy, whatever the caller wrapped it in) is never kept as
  the period's answer; a user's ask never waits on the per-key lock while a background read holds it.
- Item 3: a stored failure is re-raised as a NEW exception each time, so tracebacks never grow on one shared object.
"""
from __future__ import annotations

import datetime
import threading
import traceback

import pytest
from fake_pacer import FakePacer, wait_for
from ofo.broker import rate_limit as rl

T0 = datetime.datetime(2026, 10, 23, 9, 30, tzinfo=datetime.UTC)
KEY, USER, CALL = "apikey1", "user0001", "positions_and_orders"


class Wrapped(Exception):  # a caller's own code for the limiter's busy (as kite_reads' KiteReadError does)
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def stamp() -> datetime.datetime:
    return T0


def test_item2_a_refusal_with_nothing_sent_is_not_the_periods_answer() -> None:
    """Attack 2: the background read is refused by the limiter (its queue is full) and the caller wraps the busy; the
    user's next ask inside the period reads Zerodha (fresh), it is not served the background's busy."""
    pacer = FakePacer(auto=True)
    limiter = rl.RateLimiter(pacer=pacer, app_key=KEY)
    sent: list[str] = []

    def refused() -> object:
        try:
            limiter.acquire(rl.GROUP_OTHER, KEY, background=True, deadline=pacer.now() - 1.0)  # past: refused at once
        except rl.KiteBusy:
            raise Wrapped("kite_read_busy") from None
        sent.append("bg")
        return "never"

    def read() -> str:
        limiter.acquire(rl.GROUP_OTHER, KEY)
        sent.append("user")
        return "positions"

    with rl.use(limiter), rl.background(), pytest.raises(Wrapped):
        limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, refused, stamp)
    answer = limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, read, stamp)
    assert answer.value == "positions" and answer.fresh is True and sent == ["user"]


def test_item2_a_failure_after_a_send_is_the_periods_answer() -> None:
    """The other branch: a read that WAS sent and failed (5xx, a 429 answer) is remembered for the period: the next
    ask raises it again and sends nothing (AC-7 "a failed read gives the same failure again")."""
    pacer = FakePacer(auto=True)
    limiter = rl.RateLimiter(pacer=pacer, app_key=KEY)
    calls: list[int] = []

    def failing() -> object:
        limiter.acquire(rl.GROUP_OTHER, KEY)
        calls.append(1)
        raise Wrapped("kite_read_unavailable")

    for _ in range(2):
        with pytest.raises(Wrapped):
            limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, failing, stamp)
    assert calls == [1]


def test_item2_a_user_ask_never_waits_on_the_lock_a_background_read_holds() -> None:
    """Attack 2 (lock): a background read holds the key's lock while it waits (here: blocked inside its fetch); the
    user's ask does not wait for it - it reads for itself and is answered fresh. The background's older answer,
    finishing later, never replaces the user's newer one."""
    pacer = FakePacer(auto=True)
    limiter = rl.RateLimiter(pacer=pacer, app_key=KEY)
    entered, release = threading.Event(), threading.Event()
    out: list[object] = []

    def background_fetch() -> str:
        entered.set()
        release.wait(10)
        return "old"

    def background_job() -> None:
        with rl.background():
            out.append(limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, background_fetch, stamp))

    worker = threading.Thread(target=background_job, daemon=True)
    worker.start()
    wait_for(entered.is_set, "background read holds the lock")
    pacer.advance(1.0)
    answer = limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, lambda: "new", stamp)
    assert answer.value == "new" and answer.fresh is True
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, lambda: "x", stamp).value == "new"


def test_item2_a_second_user_ask_still_waits_for_the_first_users_read() -> None:
    """The other branch: a user holding the lock still makes a second user ask wait and share its answer (AC-7's
    'many tabs, one read')."""
    pacer = FakePacer(auto=True)
    limiter = rl.RateLimiter(pacer=pacer, app_key=KEY)
    entered, release = threading.Event(), threading.Event()
    reads: list[str] = []

    def slow() -> str:
        reads.append("first")
        entered.set()
        release.wait(10)
        return "first"

    out: list[object] = []
    first = threading.Thread(target=lambda: out.append(
        limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, slow, stamp)), daemon=True)
    first.start()
    wait_for(entered.is_set, "first user read holds the lock")
    second = threading.Thread(target=lambda: out.append(
        limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, lambda: reads.append("second") or "x", stamp)),
        daemon=True)
    second.start()
    second.join(0.2)
    assert second.is_alive(), "the second user ask waits for the first"
    release.set()
    first.join(5)
    second.join(5)
    assert reads == ["first"] and [a.value for a in out] == ["first", "first"]  # type: ignore[attr-defined]


def test_item3_a_stored_failure_is_raised_as_a_new_exception_each_time() -> None:
    """Attack 3: three asks inside the period after one failed read -> three distinct exception objects, each with the
    same code and the same traceback length (nothing piles up on a shared object)."""
    pacer = FakePacer(auto=True)
    limiter = rl.RateLimiter(pacer=pacer, app_key=KEY)

    def failing() -> object:
        limiter.acquire(rl.GROUP_OTHER, KEY)
        raise Wrapped("kite_read_unavailable")

    seen: list[BaseException] = []
    for _ in range(4):
        try:
            limiter.read_once_per_period(rl.READ_POSITIONS, CALL, USER, failing, stamp)
        except Wrapped as exc:
            seen.append(exc)
    stored = seen[1:]
    assert len({id(e) for e in seen}) == 4  # noqa: PLR2004
    assert [type(e) for e in stored] == [Wrapped] * 3 and [e.code for e in stored] == ["kite_read_unavailable"] * 3
    lengths = {len(traceback.extract_tb(e.__traceback__)) for e in stored}
    assert len(lengths) == 1
