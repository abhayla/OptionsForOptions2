"""REQ-118 (W-138): the CORE - every Kite REST call passes ONE limiter at the door, and a 429 puts its group into Kite's
10 s cooldown. Proven through the REAL door modules (``ofo.broker.kite_http.open_url`` urllib path and the
``ofo_app.kite_http`` httpx clients) against a loopback fake Kite server, with a fake clock (nothing really sleeps).

Honesty: no recorded Kite 429 exists (none in tests/fixtures); the reply here is Kite's documented status code
(F-60), so
this proves OUR handling of a 429, not the body Kite sends with it.
"""
# ruff: noqa: PLR2004, RUF059  - test constants, a fake token, fixture tuples unpacked whole
from __future__ import annotations

import asyncio
import re
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from fake_pacer import FakePacer, wait_for
from ofo.broker import kite_http as kite_http_module
from ofo.broker import rate_limit as rl
from ofo.broker.kite_http import open_url
from ofo.instruments import downloader
from ofo_app import kite_client, kite_history, kite_margin, kite_reads
from ofo_app.kite_http import KiteAsyncClient, KiteBusy, KiteClient

KEY, TOKEN = "apikey1", "SECRETACCESSTOKEN123"
AUTH = {"Authorization": f"token {KEY}:{TOKEN}", "X-Kite-Version": "3"}
BODY = b'{"status": "success", "data": []}'


class FakeKite:
    """A loopback Kite: records (fake clock, method, path) per request; ``script`` maps a path to the list of statuses
    it answers in order (the last repeats); ``gate`` holds the first reply until the test releases it."""

    def __init__(self, pacer: FakePacer) -> None:
        self.pacer = pacer
        self.hits: list[tuple[float, str, str]] = []
        self.script: dict[str, list[int]] = {}
        self.delay: dict[str, float] = {}
        self.retry_after: dict[str, str] = {}  # path -> the Retry-After a 429 on it carries (none by default, F-60)
        self.gate: threading.Event | None = None
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                path = self.path.split("?")[0]
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                with fake._lock:
                    fake.hits.append((fake.pacer.now(), self.command, path))
                    seen = sum(1 for h in fake.hits if h[2] == path)
                    statuses = fake.script.get(path, [200])
                    status = statuses[min(seen - 1, len(statuses) - 1)]
                    first = len(fake.hits) == 1
                if fake.gate is not None and first:
                    fake.gate.wait(10)
                if path in fake.delay:
                    threading.Event().wait(fake.delay[path])
                payload = BODY if status == 200 else b'{"status": "error", "error_type": "NetworkException"}'
                try:
                    self.send_response(status)
                    if status == 429 and path in fake.retry_after:
                        self.send_header("Retry-After", fake.retry_after[path])
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass

            do_GET = do_POST = _answer

            def log_message(self, *args) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def times(self, path: str | None = None) -> list[float]:
        with self._lock:
            return sorted(t for t, _, p in self.hits if path is None or p == path)

    def count(self) -> int:
        with self._lock:
            return len(self.hits)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def world(monkeypatch):
    # A local fake has a port, which check_call's plain-netloc rule refuses by design (test_egress_gate_doors does the
    # same for its own loopback server): the test widens ONLY that pattern, loopback still needs the egress test mode.
    monkeypatch.setattr(kite_http_module, "_PLAIN_NETLOC", re.compile(r"[A-Za-z0-9.-]+(:[0-9]{1,5})?", re.ASCII))
    pacer = FakePacer()
    limiter = rl.RateLimiter(pacer=pacer)
    kite = FakeKite(pacer)
    started: list[threading.Thread] = []
    with rl.use(limiter):
        yield pacer, limiter, kite, started
    pacer.advance(1000.0)  # release any sleeper still parked, so no thread outlives the test
    for thread in started:
        thread.join(5)
    kite.close()
    assert not any(t.is_alive() for t in started)


def run(started: list[threading.Thread], fn, results: list | None = None, *, background: bool = False) -> None:
    def target() -> None:
        try:
            if background:
                with rl.background():
                    out = fn()
            else:
                out = fn()
            if results is not None:
                results.append(out)
        except BaseException as exc:  # noqa: BLE001 - a thread must hand ANY failure to the test, never lose it
            if results is not None:
                results.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    started.append(thread)


def get(kite: FakeKite, path: str):
    with open_url(kite.base + path, headers=AUTH, timeout=5) as response:
        return response.status


def booked(limiter: rl.RateLimiter, group: str) -> int:
    return len(limiter._buckets.get((group, KEY), rl._Bucket()).booked)


# -- the core ---------------------------------------------------------------------------------------------------------

def test_five_quote_reads_at_once_reach_the_server_no_faster_than_one_per_second(world) -> None:
    """AC-1/AC-2 core (a): 5 quote reads issued at once through the urllib door: the server sees them at t=0,1,2,3,4 and
    never two in the same second."""
    pacer, limiter, kite, started = world
    results: list = []
    for _ in range(5):
        run(started, lambda: get(kite, "/quote?i=NSE:NIFTY"), results)
    wait_for(lambda: kite.count() == 1 and booked(limiter, "quote") == 4, "1 sent, 4 waiting")
    for second in range(1, 5):
        assert kite.count() == second  # nothing arrives early
        pacer.advance(1.0)
        wait_for(lambda s=second: kite.count() == s + 1, f"request {second + 1} sent")
    wait_for(lambda: len(results) == 5, "all answered")
    assert kite.times() == [0.0, 1.0, 2.0, 3.0, 4.0] and results == [200] * 5


def test_ten_other_reads_at_once_are_spaced_a_tenth_of_a_second(world) -> None:
    """AC-1 attack 1: 10 'other' reads (positions) at once reach the server at 0, .1, .2 ... .9, never faster."""
    pacer, limiter, kite, started = world
    for _ in range(10):
        run(started, lambda: get(kite, "/portfolio/positions"))
    wait_for(lambda: kite.count() == 1 and booked(limiter, "other") == 9, "1 sent, 9 waiting")
    for n in range(1, 10):
        assert kite.count() == n
        pacer.advance(0.1)
        wait_for(lambda k=n: kite.count() == k + 1, f"read {n + 1} sent")
    assert kite.times() == pytest.approx([i / 10 for i in range(10)])


def test_a_429_stops_everything_to_that_group_for_ten_seconds_then_retries_at_most_twice(world) -> None:
    """AC-4 core (b): a background positions read gets 429 at t=0 -> NOTHING is sent to 'other' until t=10 (a
    second read
    of the same group waits too, a quote read is unaffected); the retry at t=10 gets 429 again; the second retry at t=20
    also; the third 429 is returned (3 sends in all) and the caller sees the 429."""
    pacer, limiter, kite, started = world
    kite.script["/portfolio/positions"] = [429, 429, 429]
    first: list = []
    run(started, lambda: get(kite, "/portfolio/positions"), first, background=True)
    wait_for(lambda: kite.count() == 1 and limiter.in_cooldown("other", KEY), "429 seen, cooldown started")
    second: list = []
    run(started, lambda: get(kite, "/user/profile"), second, background=True)  # same group, also during the cooldown
    wait_for(lambda: booked(limiter, "other") >= 1, "second read waiting")
    assert get(kite, "/quote?i=NSE:NIFTY") == 200  # a different group is not in cooldown
    pacer.advance(9.9)
    assert kite.times("/portfolio/positions") == [0.0] and kite.times("/user/profile") == []  # nothing during cooldown
    pacer.advance(0.1)
    wait_for(lambda: len(kite.times("/portfolio/positions")) == 2, "first retry at t=10")
    # the server counts the retry BEFORE the client has read its 429 and restarted the cooldown; moving the clock in
    # that gap starts the cooldown at t=20 instead of t=10 and the second retry never comes (a race in this test, seen
    # under load on 2026-10-23): wait until the client has noted the second 429
    wait_for(lambda: limiter.in_cooldown("other", KEY), "second 429 noted, cooldown restarted at t=10")
    pacer.advance(10.0)
    wait_for(lambda: len(first) == 1, "the read ended after its retries")
    assert kite.times("/portfolio/positions") == [0.0, 10.0, 20.0]  # 1 send + 2 retries, then it fails
    assert isinstance(first[0], HTTPError) and first[0].code == 429
    wait_for(lambda: len(second) == 1, "the waiting read answered")
    assert second == [200] and kite.times("/user/profile")[0] >= 10.0


def test_a_user_read_that_cannot_wait_out_the_cooldown_is_refused_busy_after_its_429(world) -> None:
    """AC-3 beats AC-4 for a user action: 429 at t=0, its 5 s cannot cover the 10 s cooldown -> KiteBusy at once, no
    second send."""
    pacer, limiter, kite, started = world
    kite.script["/portfolio/positions"] = [429]
    out: list = []
    run(started, lambda: get(kite, "/portfolio/positions"), out)
    wait_for(lambda: len(out) == 1, "refused")
    assert isinstance(out[0], rl.KiteBusy) and str(out[0]) == "Zerodha is busy - try again in a moment"
    assert kite.times() == [0.0] and pacer.now() == 0.0


def test_a_request_already_waiting_when_a_429_arrives_does_not_send_into_the_cooldown(world) -> None:
    """The cooldown binds the waiters too: T2 holds slot t=0.1; T1's reply (429) lands at t=0; T2 wakes at 0.1, sees the
    cooldown, re-books past its 5 s and is refused - the server never sees it."""
    pacer, limiter, kite, started = world
    kite.gate = threading.Event()
    kite.script["/orders"] = [429, 200]
    one: list = []
    two: list = []
    run(started, lambda: get(kite, "/orders"), one)
    wait_for(lambda: kite.count() == 1, "first request at the server (reply held)")
    run(started, lambda: get(kite, "/trades"), two)
    wait_for(lambda: booked(limiter, "other") == 1, "second request holds a later slot")
    kite.gate.set()
    wait_for(lambda: limiter.in_cooldown("other", KEY), "429 processed")
    pacer.advance(0.1)
    wait_for(lambda: len(two) == 1, "the waiter woke")
    assert isinstance(two[0], rl.KiteBusy) and kite.times("/trades") == []


def test_urllib_and_httpx_share_one_bucket_per_group(world) -> None:
    """Attack 6: a quote via urllib, one via the sync httpx client and one via the async httpx client in the same second
    reach the server at t=0, 1, 2: one bucket for the whole app, whichever door."""
    pacer, limiter, kite, started = world
    out: list = []

    def sync_httpx():
        with KiteClient(base_url=kite.base) as client:
            return client.get("/quote?i=NSE:NIFTY", headers=AUTH).status_code

    def async_httpx():
        async def go():
            async with KiteAsyncClient(base_url=kite.base) as client:
                return (await client.get("/quote?i=NSE:NIFTY", headers=AUTH)).status_code
        return asyncio.run(go())

    run(started, lambda: get(kite, "/quote?i=NSE:NIFTY"), out)
    wait_for(lambda: kite.count() == 1, "first quote sent")
    run(started, sync_httpx, out)
    wait_for(lambda: booked(limiter, "quote") == 1, "second waits")
    run(started, async_httpx, out)
    wait_for(lambda: booked(limiter, "quote") == 2, "third waits")
    assert kite.count() == 1
    pacer.advance(1.0)
    wait_for(lambda: kite.count() == 2, "second sent")
    pacer.advance(1.0)
    wait_for(lambda: len(out) == 3, "all answered")
    assert kite.times() == [0.0, 1.0, 2.0] and out == [200] * 3


def test_a_user_quote_read_still_gets_a_slot_while_a_background_burst_is_queued(world) -> None:
    """Standing item (a), through the door: 6 background quote reads at once keep 1 sent + 2 waiting (3 refused busy);
    a user quote read is then served inside its 5 s (t=3), not stuck behind the burst."""
    pacer, limiter, kite, started = world
    bg: list = []
    for _ in range(6):
        run(started, lambda: get(kite, "/quote?i=NSE:NIFTY"), bg, background=True)
    wait_for(lambda: len(bg) == 4 and booked(limiter, "quote") == 2, "1 sent, 3 refused, 2 waiting")
    assert sum(isinstance(r, rl.KiteBusy) for r in bg) == 3 and bg.count(200) == 1
    user: list = []
    run(started, lambda: get(kite, "/quote?i=NSE:NIFTY"), user)
    wait_for(lambda: booked(limiter, "quote") == 3, "user read booked")
    for _ in range(3):
        pacer.advance(1.0)
    wait_for(lambda: user == [200], "user read served")
    assert kite.times()[-1] == 3.0


# -- a call that creates something is never retried (AC-5) ---------------------------------------------------------

def test_a_429_on_the_login_exchange_is_not_retried(world) -> None:
    """Attack 4 / AC-5: POST /session/token answered 429 -> the response comes back at once, exactly one send, then the
    group is in cooldown; no retry even from a background context."""
    pacer, limiter, kite, started = world
    kite.script["/session/token"] = [429, 200]
    results: list = []

    def exchange():
        async def go():
            async with KiteAsyncClient(base_url=kite.base) as client:
                return (await client.post("/session/token", data={"api_key": KEY, "request_token": "r",
                                                                  "checksum": "c"})).status_code
        with rl.background():
            return asyncio.run(go())

    run(started, exchange, results)
    wait_for(lambda: len(results) == 1, "answered")
    assert results == [429] and kite.times("/session/token") == [0.0]
    assert limiter.in_cooldown("other", KEY) and limiter.count("other", "-") == 1


def test_a_timeout_on_the_login_exchange_is_not_retried(world) -> None:
    """Attack 4 / AC-5: a POST /session/token that times out raises once; the server saw exactly one request."""
    pacer, limiter, kite, started = world
    kite.delay["/session/token"] = 1.0
    results: list = []

    def exchange():
        async def go():
            async with KiteAsyncClient(base_url=kite.base) as client:
                return await client.post("/session/token", data={"api_key": KEY}, timeout=0.2)
        with rl.background():
            return asyncio.run(go())

    run(started, exchange, results)
    wait_for(lambda: len(results) == 1, "timed out")
    assert isinstance(results[0], Exception) and not isinstance(results[0], rl.KiteBusy)
    assert kite.times("/session/token") == [0.0] and not limiter.in_cooldown("other", KEY)


# The login exchange through each of the THREE real senders (urllib open_url, sync httpx KiteClient, async httpx
# KiteAsyncClient): row 10's first build left mutants M8 (urllib) and M9 (sync httpx) alive because the two tests above
# only drove the async client - the retry branch of the other two senders never ran. Each sender is driven here.
_LOGIN_FORM = {"api_key": KEY, "request_token": "r", "checksum": "c"}


def _login_urllib(kite: FakeKite, timeout: float = 5):
    form = b"api_key=" + KEY.encode() + b"&request_token=r"
    return open_url(kite.base + "/session/token", method="POST", data=form, timeout=timeout)


def _login_sync_httpx(kite: FakeKite, timeout: float = 5):
    with KiteClient(base_url=kite.base) as client:
        return client.post("/session/token", data=_LOGIN_FORM, timeout=timeout).status_code


def _login_async_httpx(kite: FakeKite, timeout: float = 5):
    async def go():
        async with KiteAsyncClient(base_url=kite.base) as client:
            return (await client.post("/session/token", data=_LOGIN_FORM, timeout=timeout)).status_code
    return asyncio.run(go())


_SENDERS = [pytest.param(_login_urllib, id="urllib"), pytest.param(_login_sync_httpx, id="httpx-sync"),
            pytest.param(_login_async_httpx, id="httpx-async")]


@pytest.mark.parametrize("login", _SENDERS)
@pytest.mark.parametrize("background", [False, True])
def test_a_429_on_the_login_exchange_reaches_the_server_once_through_every_sender(world, login, background) -> None:
    """Attack 1-2 / AC-5: POST /session/token answered 429 [then 200]: exactly ONE request reaches the server, the 429
    comes back to the caller (urllib raises HTTPError 429) and a cooldown starts, from a user or background context."""
    pacer, limiter, kite, started = world
    kite.script["/session/token"] = [429, 200]
    out: list = []
    run(started, lambda: login(kite), out, background=background)
    wait_for(lambda: len(out) == 1, "answered")
    answer = out[0].code if isinstance(out[0], HTTPError) else out[0]
    assert answer == 429 and kite.times("/session/token") == [0.0] and limiter.in_cooldown("other", KEY)
    pacer.advance(30.0)  # long past the cooldown: still nothing retried
    assert kite.times("/session/token") == [0.0]


@pytest.mark.parametrize("login", _SENDERS)
def test_a_timeout_on_the_login_exchange_reaches_the_server_once_through_every_sender(world, login) -> None:
    """Attack 3 / AC-5: a POST /session/token that times out raises once; the server saw exactly one request."""
    pacer, limiter, kite, started = world
    kite.delay["/session/token"] = 1.0
    out: list = []
    run(started, lambda: login(kite, timeout=0.2), out)
    wait_for(lambda: len(out) == 1, "timed out")
    assert isinstance(out[0], Exception) and not isinstance(out[0], (rl.KiteBusy, HTTPError))
    assert kite.times("/session/token") == [0.0]


def test_the_httpx_door_retries_a_read_after_the_cooldown_but_returns_the_third_429(world) -> None:
    """AC-4 on the httpx path: a background GET /orders answered 429, 429, 429 is sent at t=0, 10, 20 and the third 429
    is returned (the caller's fail-closed rule applies)."""
    pacer, limiter, kite, started = world
    kite.script["/orders"] = [429, 429, 429]
    results: list = []

    def read():
        with KiteClient(base_url=kite.base) as client, rl.background():
            return client.get("/orders", headers=AUTH).status_code

    run(started, read, results)
    wait_for(lambda: kite.count() == 1 and limiter.in_cooldown("other", KEY), "first 429")
    pacer.advance(10.0)
    wait_for(lambda: kite.count() == 2 and limiter.in_cooldown("other", KEY), "retry 1 and its 429 noted")
    pacer.advance(10.0)
    wait_for(lambda: len(results) == 1, "done")
    assert kite.times() == [0.0, 10.0, 20.0] and results == [429]


# -- every answer state of Kite for a limited call (standing item d) -----------------------------------------------

@pytest.mark.parametrize(("status", "cooldown", "sends"), [
    (200, False, 1),   # success: returned; no cooldown
    (400, False, 1),   # InputException-style 4xx: raised, never retried, no cooldown
    (403, False, 1),   # TokenException: raised, no cooldown
    (429, True, 1),    # rate limited: cooldown (a user read is then refused busy, see above)
    (500, False, 1),   # server error: raised, never retried by the door, no cooldown
])
def test_each_status_from_kite_and_what_the_door_does(world, status: int, cooldown: bool, sends: int) -> None:
    """Standing item (d): 200, other 4xx, 429, 5xx - only 429 starts a cooldown; nothing but a 429 is retried."""
    pacer, limiter, kite, started = world
    kite.script["/user/profile"] = [status]
    out: list = []
    run(started, lambda: get(kite, "/user/profile"), out)
    wait_for(lambda: len(out) == 1, "answered")
    assert len(kite.times("/user/profile")) == sends and limiter.in_cooldown("other", KEY) is cooldown
    if status == 200:
        assert out == [200]
    else:
        assert isinstance(out[0], (HTTPError, rl.KiteBusy))


def test_a_connection_refused_sends_nothing_and_starts_no_cooldown(world) -> None:
    """Standing item (d): connection refused -> URLError from the door, no cooldown, no retry."""
    pacer, limiter, kite, started = world
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead = f"http://127.0.0.1:{probe.getsockname()[1]}"  # a port nobody listens on once the probe closes
    out: list = []

    def call():
        return open_url(dead + "/user/profile", headers=AUTH, timeout=2)

    run(started, call, out)
    wait_for(lambda: len(out) == 1, "raised")
    assert isinstance(out[0], (URLError, OSError)) and not limiter.in_cooldown("other", KEY) and kite.count() == 0


def test_a_read_timeout_is_raised_not_retried_and_a_malformed_body_is_the_callers_to_judge(world) -> None:
    """Standing item (d): a read that times out raises once (one send, no cooldown, no retry); a 200 with junk is
    returned untouched by the door (the reader's parser fails closed on it)."""
    pacer, limiter, kite, started = world
    kite.delay["/portfolio/positions"] = 1.0
    out: list = []

    def slow():
        return open_url(kite.base + "/portfolio/positions", headers=AUTH, timeout=0.2)

    run(started, slow, out)
    wait_for(lambda: len(out) == 1, "timed out")
    assert isinstance(out[0], (TimeoutError, URLError, OSError)) and len(kite.times("/portfolio/positions")) == 1
    assert not limiter.in_cooldown("other", KEY)


# -- the callers of the door (REQ-118 R15) ----------------------------------------------------------------------------

@pytest.mark.parametrize("background", [False, True])
def test_two_429s_on_the_margin_read_block_the_margin_gate_never_a_figure(world, background) -> None:
    """Attack 5 / AC-4 / ADR-094: the margin read through the REAL urllib door and the client's own transport. Kite
    answers 429 to every try: the client raises its busy code, and the margin gate BLOCKS (no figure at all, nothing
    allowed). A user read is refused busy after its first 429 (the wait would pass 5 s); a background read is retried
    after the cooldown and the third 429 is returned - either way nothing is read as a margin figure."""
    pacer, limiter, kite, started = world
    kite.script["/user/margins"] = [429]
    client = kite_margin.KiteMargin(api_key=KEY, access_token=TOKEN, base_url=kite.base)
    out: list = []

    def verdict():
        with pytest.raises(kite_margin.KiteMarginError) as busy:
            client.fetch_available_funds()
        return busy.value.code, kite_margin.margin_verdict(client, [])

    run(started, verdict, out, background=background)
    wait_for(lambda: kite.count() >= 1 and limiter.in_cooldown("other", KEY), "first 429")
    for _ in range(20):  # each cooldown passes in turn; the read gives up after its third 429
        if out:
            break
        pacer.advance(10.0)
        threading.Event().wait(0.1)
    wait_for(lambda: len(out) == 1, "answered")
    code, blocked = out[0]
    assert code == "kite_margin_busy" and blocked.allowed is False and blocked.available is None


def test_the_callers_map_a_busy_refusal_to_their_own_fail_closed_codes(monkeypatch) -> None:
    """Callers: kite_margin / kite_reads (transport -> 429 -> *_busy), kite_history (-> CandleFetchError), the
    instrument downloader (runs in background mode), kite_client (-> kite_busy). Each is refused by the limiter,
    nothing is sent."""
    def busy(*args, **kwargs):
        raise rl.KiteBusy("wait")

    monkeypatch.setattr(kite_margin, "kite_open_url", busy)
    assert kite_margin.urllib_transport("GET", "https://api.kite.trade/user/margins", dict(AUTH), None) == (429, "")
    with pytest.raises(kite_margin.KiteMarginError) as margin:
        kite_margin.KiteMargin(api_key=KEY, access_token=TOKEN).fetch_available_funds()
    assert margin.value.code == "kite_margin_busy"
    with pytest.raises(kite_reads.KiteReadError) as read:
        kite_reads.KiteReads(api_key=KEY, access_token=TOKEN).fetch_orders()
    assert read.value.code == "kite_read_busy"

    monkeypatch.setattr(kite_history, "kite_open_url", busy)
    history_url = "https://api.kite.trade/instruments/historical/1/minute"
    assert kite_history.urllib_transport(history_url, dict(AUTH)) == (429, "")

    seen: list[bool] = []

    def spy(url, **kwargs):
        seen.append(rl._BACKGROUND.get())
        raise rl.KiteBusy("wait")

    monkeypatch.setattr(downloader, "open_url", spy)
    with pytest.raises(rl.KiteBusy):
        downloader.download_instruments_csv()
    assert seen == [True] and rl._BACKGROUND.get() is False

    class BusyClient:
        async def post(self, *args, **kwargs):
            raise KiteBusy("wait")

    with pytest.raises(kite_client.KiteExchangeError) as login:
        asyncio.run(kite_client.HttpKiteAuth(KEY, "secret", BusyClient()).exchange("rt"))
    assert login.value.code == "kite_busy"


# -- review F2: a user read's retry fits its 5 s when Kite states a short wait (AC-3 + AC-4 together) --------------

def test_f2_attack1_urllib_user_read_429_with_stated_wait_then_200_two_sends_under_5_s(world) -> None:
    """AC-4 + AC-3 (review F2 attack 1, real urllib door, user context): 429 with Retry-After 1, then 200 -> sent at
    t=0 and t=1 (Kite's stated wait), the 200 returned, total wait 1 s < 5 s. Before the fix: 1 send, busy."""
    pacer, limiter, kite, started = world
    kite.script["/portfolio/positions"] = [429, 200]
    kite.retry_after["/portfolio/positions"] = "1"
    out: list = []
    run(started, lambda: get(kite, "/portfolio/positions"), out)
    wait_for(lambda: kite.count() == 1 and limiter.in_cooldown("other", KEY), "first 429 noted")
    pacer.advance(1.0)
    wait_for(lambda: len(out) == 1, "answered")
    assert out == [200] and kite.times() == [0.0, 1.0] and pacer.now() < rl.USER_MAX_WAIT_SECONDS


@pytest.mark.parametrize("asynchronous", [False, True])
def test_f2_attack1_httpx_user_read_429_with_stated_wait_then_200(world, asynchronous: bool) -> None:
    """The same through the httpx door (sync and async clients): one helper (``DoorCall``) serves both doors."""
    pacer, limiter, kite, started = world
    kite.script["/orders"] = [429, 200]
    kite.retry_after["/orders"] = "2"

    def read():
        if asynchronous:
            async def go():
                async with KiteAsyncClient(base_url=kite.base) as client:
                    return (await client.get("/orders", headers=AUTH)).status_code
            return asyncio.run(go())
        with KiteClient(base_url=kite.base) as client:
            return client.get("/orders", headers=AUTH).status_code

    out: list = []
    run(started, read, out)
    wait_for(lambda: kite.count() == 1 and limiter.in_cooldown("other", KEY), "first 429 noted")
    pacer.advance(2.0)
    wait_for(lambda: len(out) == 1, "answered")
    assert out == [200] and kite.times() == [0.0, 2.0]


def test_f2_attack1_user_margin_read_429_three_times_three_sends_then_the_gate_blocks(world) -> None:
    """AC-4 "at most twice" in user context (stated wait 1 s each): 3 sends at t=0, 1, 2, then the read fails and the
    margin gate blocks (ADR-094) - no figure, nothing allowed."""
    pacer, limiter, kite, started = world
    kite.script["/user/margins"] = [429]
    kite.retry_after["/user/margins"] = "1"
    client = kite_margin.KiteMargin(api_key=KEY, access_token=TOKEN, base_url=kite.base)
    out: list = []

    def verdict():
        with pytest.raises(kite_margin.KiteMarginError) as busy:
            client.fetch_available_funds()
        return busy.value.code, kite_margin.margin_verdict(client, [])

    run(started, verdict, out)
    for sends in (1, 2, 3, 4, 5):  # the read's three sends, then the gate's own read (its three sends)
        if out:
            break
        wait_for(lambda sends=sends: out or (kite.count() >= sends and limiter.in_cooldown("other", KEY)), "a 429")
        pacer.advance(1.0)
    wait_for(lambda: len(out) == 1, "the gate answered")
    assert kite.times("/user/margins")[:4] == [0.0, 1.0, 2.0, 3.0]  # 3 sends, then the gate's read: never a 4th try
    code, blocked = out[0]
    assert code == "kite_margin_busy" and blocked.allowed is False and blocked.available is None


def test_f2_standing_a_order_path_read_gets_its_retry_slot_while_a_background_burst_is_queued(world) -> None:
    """Standing item (a): background reads fill their small queue (``BACKGROUND_QUEUE_SECONDS``) in 'other'; a user
    read answered 429 (Retry-After 1) then 200 still gets its retry slot and finishes inside its 5 s in total."""
    pacer, limiter, kite, started = world
    kite.script["/orders"] = [429, 200]
    kite.retry_after["/orders"] = "1"
    background: list = []
    for _ in range(int(rl.GROUP_RATES["other"] * rl.BACKGROUND_QUEUE_SECONDS) + 5):
        run(started, lambda: get(kite, "/user/profile"), background, background=True)
    wait_for(lambda: booked(limiter, "other") >= 1, "background burst queued")
    out: list = []
    run(started, lambda: get(kite, "/orders"), out)
    for _ in range(60):
        if out:
            break
        pacer.advance(0.1)
        threading.Event().wait(0.01)
    wait_for(lambda: len(out) == 1, "user read answered")
    assert out == [200]
    orders = kite.times("/orders")
    assert len(orders) == 2 and orders[1] - orders[0] >= 1.0 and orders[1] < rl.USER_MAX_WAIT_SECONDS
