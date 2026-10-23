# ruff: noqa: PLR2004
"""REQ-015 AC-12 (RD-014) and REQ-118 AC-7 (RD-063): positions are read once at connect and then every 45 s, no ask
inside a user's period reaches Zerodha, and the periodic read never starves the order path.

Core proof: the REAL connect path (``LiveMarket._launch``) with an injected clock and a fake Kite (a counting transport
in place of ``urllib_transport``). No database (the stored token, catalogue and socket are fakes), no network, no
real Kite. Expected values come from the record: 45 s for positions, 30 s for numbers (RD-063 "positions every 45 s",
"numbers ... on a fixed 30 s timer").
"""
from __future__ import annotations

import asyncio
import datetime
import json
from types import SimpleNamespace

import pytest
from ofo.broker import rate_limit
from ofo.broker.rate_limit import (
    BACKGROUND_QUEUE_SECONDS,
    GROUP_OTHER,
    GROUP_RATES,
    READ_NUMBERS,
    READ_PERIOD_SECONDS,
    READ_POSITIONS,
    KiteBusy,
    RateLimiter,
)
from ofo_app import kite_period_reads, live_market
from ofo_app.kite_reads import KiteReadError, KiteReads

TOKEN_A, TOKEN_B = "ACtok_periodic_a", "ACtok_periodic_b"
T0 = datetime.datetime(2026, 10, 23, 9, 30, 0, tzinfo=datetime.UTC)


class Clock:
    """The limiter's pacer and the wall clock, moved only by the test."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def wall(self) -> datetime.datetime:
        return T0 + datetime.timedelta(seconds=self.t)

    def sleep_until(self, at: float) -> None:  # never really sleeps
        return None

    async def asleep_until(self, at: float) -> None:
        return None


class FakeKite:
    """Zerodha's side: counts every request by path; ``status`` per path (200 = success)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.status: dict[str, int] = {}

    def __call__(self, method, url, headers, body, *, timeout=None):
        path = url.split("kite.trade", 1)[-1].split("?")[0]
        self.calls.append((method, path))
        assert method == "GET", (method, url)  # a read, never an order call
        status = self.status.get(path, 200)
        if status != 200:
            kind = "TokenException" if status == 403 else "NetworkException"
            return status, json.dumps({"status": "error", "message": "x", "error_type": kind})
        data = {"net": [], "day": []} if path.endswith("/positions") else []
        return 200, json.dumps({"status": "success", "data": data})

    def count(self, path: str) -> int:
        return sum(1 for _, p in self.calls if p == path)


class _Socket:
    def __init__(self, *args, **kwargs) -> None:
        self._stop = asyncio.Event()

    async def run(self):
        await self._stop.wait()

    def stop(self) -> None:
        self._stop.set()


class _Catalogue:
    def all_entries(self):
        return []


class _Conn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Engine:
    def connect(self):
        return _Conn()


@pytest.fixture
def clock():
    c = Clock()
    with rate_limit.use(RateLimiter(pacer=c)):
        yield c


@pytest.fixture
def kite(monkeypatch, clock):
    from ofo_app import catalogue_store, db, feed_mode, kite_ws  # noqa: PLC0415

    wire = FakeKite()

    async def load(_conn):
        return _Catalogue()

    monkeypatch.setattr(live_market, "urllib_transport", wire)
    monkeypatch.setattr(kite_period_reads, "utc_now", clock.wall)
    monkeypatch.setattr(catalogue_store, "load_catalogue", load)
    monkeypatch.setattr(db, "get_engine", _Engine)
    monkeypatch.setattr(feed_mode, "feed_mode", lambda: feed_mode.INPROCESS)
    monkeypatch.setattr(kite_ws, "KiteSocket", _Socket)
    monkeypatch.setattr(live_market, "get_settings", lambda: SimpleNamespace(KITE_WS_URL="ws://127.0.0.1:9"))
    return wire


class Sleeps:
    """The periodic job's sleep: records the seconds, waits for the test, then moves the clock by them."""

    def __init__(self, clock: Clock) -> None:
        self.clock, self.asked, self.release = clock, [], asyncio.Queue()

    async def __call__(self, seconds: float) -> None:
        self.asked.append(seconds)
        await self.release.get()
        self.clock.t += seconds


def _market(monkeypatch, clock: Clock, token: str | None = TOKEN_A) -> tuple[live_market.LiveMarket, Sleeps]:
    market = live_market.LiveMarket()
    market._config = SimpleNamespace(api_key="KEY-periodic", token_key=None)
    holder = {"token": token}

    async def stored(_config):
        return holder["token"]

    monkeypatch.setattr(market, "_stored_token", stored)
    market.holder = holder  # type: ignore[attr-defined]
    sleeps = Sleeps(clock)
    market._sleep = sleeps
    return market, sleeps


async def _until(check, seconds: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while not check():
        assert loop.time() < end, "timed out"
        await asyncio.sleep(0.005)


def _reads(wire: FakeKite, token: str = TOKEN_A) -> KiteReads:
    return KiteReads(api_key="KEY-periodic", access_token=token, transport=wire)


async def test_core_connect_reads_positions_once_then_every_45_s_and_asks_inside_the_period_are_served(
        monkeypatch, clock, kite):
    """AC-12 + AC-7 core: a connect reads positions with no Execute visit; +10 s an ask is served from that read (its
    read time, no Kite call); +45 s the job reads again."""
    market, sleeps = _market(monkeypatch, clock)
    await market._launch(market._config, TOKEN_A)
    try:
        await _until(lambda: sleeps.asked)  # the job read, then went to sleep
        assert kite.count("/portfolio/positions") == 1  # at connect, nobody opened Execute
        assert sleeps.asked == [45.0]

        clock.t = 10.0
        answer = kite_period_reads.screen_positions(_reads(kite))  # the Positions screen's call, same user
        assert answer.fresh is False and answer.read_at == T0  # the connect read's own time, never "now"
        assert kite.count("/portfolio/positions") == 1  # no new Kite call
        clock.t = 0.0

        sleeps.release.put_nowait(None)  # the clock moves to +45 s
        await _until(lambda: len(sleeps.asked) == 2)
        assert kite.count("/portfolio/positions") == 2
        again = kite_period_reads.screen_positions(_reads(kite))
        assert again.fresh is False and again.read_at == T0 + datetime.timedelta(seconds=45)
    finally:
        await market.stop()


async def test_ac7_one_second_before_the_period_ends_is_still_served_and_at_the_period_a_new_read_goes_out(clock, kite):
    """AC-7: the boundary - 44.999 s is inside the period, 45 s is not; 30 s for numbers."""
    reads = _reads(kite)
    kite_period_reads.screen_positions(reads)
    clock.t = 44.999
    assert kite_period_reads.screen_positions(reads).fresh is False
    clock.t = 45.0
    assert kite_period_reads.screen_positions(reads).fresh is True
    assert kite.count("/portfolio/positions") == 2
    assert READ_PERIOD_SECONDS == {READ_NUMBERS: 30.0, READ_POSITIONS: 45.0}


async def test_ac7_two_users_never_share_or_spend_each_others_period(clock, kite):
    """Attack 2: user B's read at +10 s is a real read even though A read at 0; A stays served from its own read."""
    kite_period_reads.screen_positions(_reads(kite, TOKEN_A))
    clock.t = 10.0
    b = kite_period_reads.screen_positions(_reads(kite, TOKEN_B))
    assert b.fresh is True and b.read_at == T0 + datetime.timedelta(seconds=10)
    a = kite_period_reads.screen_positions(_reads(kite, TOKEN_A))
    assert a.fresh is False and a.read_at == T0
    assert kite.count("/portfolio/positions") == 2


async def test_ac7_a_failed_read_is_answered_again_inside_the_period_and_never_as_an_old_success(clock, kite):
    """Standing item (d): a 5xx is remembered for the period (no storm), raised again, never served as fresh data."""
    kite.status["/portfolio/positions"] = 503
    reads = _reads(kite)
    for t in (0.0, 5.0, 44.0):
        clock.t = t
        with pytest.raises(KiteReadError) as err:
            kite_period_reads.screen_positions(reads)
        assert err.value.code == "kite_read_unavailable"
    assert kite.count("/portfolio/positions") == 1
    kite.status.clear()
    clock.t = 45.0
    assert kite_period_reads.screen_positions(reads).fresh is True


@pytest.mark.parametrize(("kind", "call", "user"), [("quotes", "x", "abc"), (READ_POSITIONS, "", "abc"),
                                                     (READ_POSITIONS, "x", ""), (READ_POSITIONS, "x", "-")])
def test_ac7_an_unknown_kind_or_an_unnamed_call_or_user_is_refused_before_any_read(clock, kind, call, user):
    """AC-7 fail closed: no unbounded kind, and never one shared answer for an unknown user."""
    calls = []
    with pytest.raises(ValueError):
        rate_limit.read_once_per_period(kind, call, user, lambda: calls.append(1), clock.wall)
    assert calls == []


async def test_attack3_disconnect_stops_the_job_and_a_reconnect_reads_once_at_connect(monkeypatch, clock, kite):
    """Attack 3: Disconnect stops the periodic read; a new login starts it again with one read at connect."""
    market, sleeps = _market(monkeypatch, clock)
    await market._launch(market._config, TOKEN_A)
    await _until(lambda: sleeps.asked)
    job = market._periodic
    await market.stop()  # what Disconnect (``stop_current``) and a new login's restart both call first
    await _until(job.done)
    assert market._periodic is None and kite.count("/portfolio/positions") == 1

    market.holder["token"] = TOKEN_B  # type: ignore[attr-defined]
    await market._launch(market._config, TOKEN_B)
    try:
        await _until(lambda: len(sleeps.asked) == 2)
        assert kite.count("/portfolio/positions") == 2  # the new session read at once (a new user ref)
    finally:
        await market.stop()


async def test_attack3_an_expired_token_ends_the_job_and_no_stored_session_reads_nothing(monkeypatch, clock, kite):
    """Attack 3: Zerodha refusing the token stops the job (no read every 45 s on a dead token); no session, no read."""
    kite.status["/portfolio/positions"] = 403
    market, sleeps = _market(monkeypatch, clock)
    market.start_periodic_positions()
    await _until(lambda: market._periodic is not None and market._periodic.done())
    assert sleeps.asked == [] and kite.count("/portfolio/positions") == 1

    empty, sleeps_empty = _market(monkeypatch, clock, token=None)
    empty.start_periodic_positions()
    await _until(empty._periodic.done)
    assert sleeps_empty.asked == [] and kite.count("/portfolio/positions") == 1


async def test_a_busy_or_failed_periodic_read_keeps_the_job_for_the_next_period(monkeypatch, clock, kite):
    """Standing item (d): a 429 is logged and the job sleeps to its next period; it never retries at once."""
    kite.status["/portfolio/positions"] = 429
    market, sleeps = _market(monkeypatch, clock)
    market.start_periodic_positions()
    try:
        await _until(lambda: sleeps.asked)
        assert kite.count("/portfolio/positions") == 1 and not market._periodic.done()
    finally:
        await market.stop()


def test_standing_a_background_reads_cannot_take_the_slots_the_order_path_needs(clock):
    """Standing item (a): background requests (the periodic job) book at most ``BACKGROUND_QUEUE_SECONDS`` ahead, so
    when they have filled their share a user read (Execute, return) still gets a slot inside its 5 s wait."""
    limiter = rate_limit.current()
    with rate_limit.background():
        booked = 0
        with pytest.raises(KiteBusy):
            while booked < 1000:
                rate_limit.acquire(GROUP_OTHER, "KEY-periodic")
                booked += 1
    assert booked == int(GROUP_RATES[GROUP_OTHER] * BACKGROUND_QUEUE_SECONDS) + 1  # the one sent now + the queue
    limiter.acquire(GROUP_OTHER, "KEY-periodic")  # the order path's read: not refused


def test_the_periodic_read_is_a_background_request():
    """Standing item (a): the job's read runs under ``rate_limit.background()``."""
    seen = []

    class _R:
        user_ref = "abc12345"

        def fetch_positions(self):
            seen.append(rate_limit._BACKGROUND.get())
            return {"net": [], "day": []}

        def fetch_orders(self):
            return []

    with rate_limit.use(RateLimiter(pacer=Clock())):
        kite_period_reads.background_screen_positions(_R())  # type: ignore[arg-type]
    assert seen == [True] and rate_limit._BACKGROUND.get() is False
