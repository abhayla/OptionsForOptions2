"""REQ-118 AC-3 + AC-4 at the REAL urllib door (``ofo.broker.kite_http.open_url``): a read that gets a 429 is retried
after the wait Kite states, at most twice, and the whole call stays within its context's wait limit (5 s for a user
action, 30 s for a background job). Chunk 1 Tier A review F2 attack 1 (``review-a2/attack4.py``): before the fix a user
read sent once and was refused busy whatever Kite stated, because the fixed 10 s cooldown was longer than the 5 s wait.

Kite's answer states on a read (standing item d), each with what the door does:
- 200 -> returned.
- 429 with ``Retry-After: <seconds>`` -> the group cools for that long; the read is sent again if the retry starts
  within the call's wait limit, else ``KiteBusy('wait')`` (the busy text; the caller's fail-closed rule applies).
- 429 with no stated wait -> Kite's documented 10 s cooldown (F-60, Kite staff: "a cooldown period of 10s that must be
  respected"); longer than the user's 5 s, so a user read is refused busy; a background read retries.
- 429 on the third send -> the 429 is the answer (AC-4 "at most twice").
- 5xx, timeout, 403 token refused -> never retried: the error is the answer.
"""
from __future__ import annotations

import contextlib
import io
import urllib.error

import pytest
from ofo.broker import kite_http as kh
from ofo.broker import rate_limit as rl

URL = "https://api.kite.trade/portfolio/positions"
HEADERS = {"Authorization": "token k:abc", "X-Kite-Version": "3"}
TIMEOUT = 0  # the script's marker for "the send timed out"


class Pacer:
    """Auto-advancing fake clock: a sleep jumps the clock, so ``t - start`` is the total time the call waited."""

    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    def sleep_until(self, at: float) -> None:
        self.t = max(self.t, at)

    async def asleep_until(self, at: float) -> None:
        self.sleep_until(at)


class _Reply(io.BytesIO):
    status = 200


class Opener:
    """Answers each send from a script: 200 returns a body, TIMEOUT raises, any other status raises HTTPError."""

    def __init__(self, script: list[tuple[int, dict[str, str]]], pacer: Pacer) -> None:
        self.script, self.pacer, self.sent_at = list(script), pacer, []

    def open(self, req, timeout=None):
        self.sent_at.append(self.pacer.t)
        status, headers = self.script.pop(0)
        if status == 200:  # noqa: PLR2004
            return _Reply(b'{"status":"success"}')
        if status == TIMEOUT:
            raise TimeoutError("timed out")
        raise urllib.error.HTTPError(req.full_url, status, "x", headers, io.BytesIO(b""))  # type: ignore[arg-type]


@contextlib.contextmanager
def door(script, *, background: bool = False):
    pacer = Pacer()
    opener = Opener(script, pacer)
    original = kh._OPENER
    kh._OPENER = opener  # type: ignore[misc]
    context = rl.background() if background else contextlib.nullcontext()
    try:
        with rl.use(rl.RateLimiter(pacer=pacer, app_key="k")), context:
            yield opener, pacer
    finally:
        kh._OPENER = original  # type: ignore[misc]


def test_ac4_user_read_429_with_stated_wait_then_200_is_retried_within_5_s() -> None:
    """AC-4 + AC-3 (review attack 1): 429 (Retry-After 1) then 200 in user context -> 2 sends, the 200 returned, the
    retry sent 1 s later (Kite's stated wait), total wait under the 5 s user limit."""
    with door([(429, {"Retry-After": "1"}), (200, {})]) as (opener, pacer):
        start = pacer.t
        with kh.open_url(URL, headers=dict(HEADERS)) as reply:
            assert reply.status == 200  # noqa: PLR2004
    assert len(opener.sent_at) == 2  # noqa: PLR2004
    assert opener.sent_at[1] - opener.sent_at[0] == pytest.approx(1.0)
    assert pacer.t - start < rl.USER_MAX_WAIT_SECONDS


def test_ac4_user_read_429_three_times_sends_three_then_the_429_is_the_answer() -> None:
    """AC-4 "at most twice": 429 x3 (each Retry-After 1) -> 3 sends, then the read fails with the 429; never a 4th."""
    with door([(429, {"Retry-After": "1"})] * 4) as (opener, pacer), pytest.raises(urllib.error.HTTPError) as err:
        start = pacer.t
        kh.open_url(URL, headers=dict(HEADERS))
    assert err.value.code == 429  # noqa: PLR2004
    assert len(opener.sent_at) == 3  # noqa: PLR2004
    assert pacer.t - start <= rl.USER_MAX_WAIT_SECONDS


def test_ac3_user_read_never_waits_past_5_s_in_total_across_retries() -> None:
    """AC-3: the 5 s is the whole call's limit, not each attempt's: 429 (wait 3) then 429 (wait 3) -> the second retry
    would start at 6 s, so it is refused busy after 2 sends; the clock never passes the start + 5 s."""
    with door([(429, {"Retry-After": "3"}), (429, {"Retry-After": "3"}), (200, {})]) as (opener, pacer):
        start = pacer.t
        with pytest.raises(rl.KiteBusy) as busy:
            kh.open_url(URL, headers=dict(HEADERS))
    assert busy.value.reason == "wait"
    assert len(opener.sent_at) == 2  # noqa: PLR2004
    assert pacer.t - start <= rl.USER_MAX_WAIT_SECONDS


def test_ac4_no_stated_wait_uses_kites_10_s_cooldown_user_refused_background_retries() -> None:
    """F-60: no Retry-After -> Kite's documented 10 s cooldown, never a shorter guess (a send inside it extends Kite's
    window). A user read cannot fit it in 5 s: 1 send, busy. A background read (30 s) retries at +10 s, gets the 200."""
    with door([(429, {}), (200, {})]) as (opener, _), pytest.raises(rl.KiteBusy):
        kh.open_url(URL, headers=dict(HEADERS))
    assert len(opener.sent_at) == 1
    with door([(429, {}), (200, {})], background=True) as (opener, _), kh.open_url(URL, headers=dict(HEADERS)) as r:
        assert r.status == 200  # noqa: PLR2004
    assert opener.sent_at[1] - opener.sent_at[0] == pytest.approx(rl.COOLDOWN_SECONDS)


def test_ac3_background_read_keeps_its_own_30_s_limit_across_retries() -> None:
    """A background read's retries fit its 30 s: 429 (wait 10) x2 then 200 -> 3 sends, 20 s; a stated 20 s twice would
    pass 30 s, so the second retry is refused busy."""
    with door([(429, {"Retry-After": "10"})] * 2 + [(200, {})], background=True) as (opener, pacer):
        start = pacer.t
        with kh.open_url(URL, headers=dict(HEADERS)):
            pass
    assert len(opener.sent_at) == 3  # noqa: PLR2004
    assert pacer.t - start == pytest.approx(20.0)
    with door([(429, {"Retry-After": "20"})] * 3, background=True) as (opener, _), pytest.raises(rl.KiteBusy):
        kh.open_url(URL, headers=dict(HEADERS))
    assert len(opener.sent_at) == 2  # noqa: PLR2004


@pytest.mark.parametrize("status", [500, 503, 403, TIMEOUT])
def test_ac4_5xx_timeout_and_token_refused_are_never_retried(status: int) -> None:
    """Only a 429 is retried: a 5xx, a timeout or a refused token (403) is the answer after 1 send."""
    with door([(status, {}), (200, {})]) as (opener, _), pytest.raises((urllib.error.HTTPError, TimeoutError)):
        kh.open_url(URL, headers=dict(HEADERS))
    assert len(opener.sent_at) == 1


def test_ac5_a_write_is_never_retried_even_with_a_stated_wait() -> None:
    """AC-5 / ADR-017: a 429 on a call that is not a retry-safe read (the login exchange, POST /session/token) is the
    answer after 1 send, whatever Kite states."""
    with door([(429, {"Retry-After": "1"}), (200, {})]) as (opener, _), pytest.raises(urllib.error.HTTPError):
        kh.open_url("https://api.kite.trade/session/token", method="POST", data=b"api_key=k&request_token=r",
                    headers={"X-Kite-Version": "3"})
    assert len(opener.sent_at) == 1


@pytest.mark.parametrize(("header", "seconds"), [("1", 1.0), ("0", 0.0), ("2", 2.0), ("7", 7.0), (" 2 ", 2.0),
                                                 ("60", 60.0), (None, 10.0), ("", 10.0), ("   ", 10.0)])
def test_ac4_stated_wait_honours_plain_seconds_up_to_60_else_no_header_is_kites_10_s(
        header: str | None, seconds: float, caplog: pytest.LogCaptureFixture) -> None:
    """AC-4 / ADR-179: Retry-After as plain ASCII delta-seconds up to 60 s is the wait, no log; no header (absent or
    blank) is Kite's documented 10 s cooldown (F-60), unchanged."""
    with caplog.at_level("WARNING", logger="ofo.broker.rate_limit"):
        assert rl.stated_wait(header) == seconds
    assert caplog.records == []


@pytest.mark.parametrize("header", ["61", "99999", "999999", "9" * 400, "abc", "-1", "1.5", "+5", "0x10",
                                    "Wed, 21 Oct 2026 07:28:00 GMT", "\N{FULLWIDTH DIGIT ONE}", "2 3", "10s"])
def test_ac4_a_larger_or_unreadable_retry_after_is_clamped_to_60_s_and_logged(
        header: str, caplog: pytest.LogCaptureFixture) -> None:
    """AC-4 / chunk 1 review round 2 (MINOR): one header must not block a group for hours (99999 s = 27 h). More than
    60 s or unreadable -> 60 s (never shorter than Kite may have asked), and one warning naming the header's value."""
    with caplog.at_level("WARNING", logger="ofo.broker.rate_limit"):
        assert rl.stated_wait(header) == rl.MAX_STATED_WAIT_SECONDS == 60.0  # noqa: PLR2004
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert repr(header.strip()[:40]) in caplog.records[0].getMessage()


def test_ac4_retry_after_99999_cools_the_group_60_s_not_27_hours() -> None:
    """AC-4 through the real door (background, 30 s limit): 429 with Retry-After 99999 -> the group cools 60 s, so the
    retry cannot fit and the read is refused busy after 1 send; the next read of that group goes out 60 s later."""
    with door([(429, {"Retry-After": "99999"}), (200, {})], background=True) as (opener, pacer):
        start = pacer.t
        with pytest.raises(rl.KiteBusy):
            kh.open_url(URL, headers=dict(HEADERS))
        pacer.t = start + rl.MAX_STATED_WAIT_SECONDS - 25  # still cooling: a new background read waits the rest out
        with kh.open_url(URL, headers=dict(HEADERS)) as reply:
            assert reply.status == 200  # noqa: PLR2004
    assert opener.sent_at[1] - opener.sent_at[0] == pytest.approx(rl.MAX_STATED_WAIT_SECONDS)
