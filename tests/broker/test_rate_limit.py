"""REQ-118 (W-138): the Kite rate limiter's own rules, with a fake clock (nothing here really sleeps).

The limits are Kite's published ones (F-60: quote 1 req/s, historical 3 req/s, all other endpoints 10 req/s; a 429
starts a 10 s cooldown). No recorded Kite 429 exists, so these tests prove OUR handling of the documented status code,
not the body Kite sends with it.
"""
# ruff: noqa: PLR2004, S105  - test constants, a fake token, fixture tuples unpacked whole
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fake_pacer import FakePacer
from ofo.broker import rate_limit as rl
from ofo.errors.templates import ZERODHA_BUSY_TEXT

TOKEN = "SECRETACCESSTOKEN123"
KEY = "apikey1"
QUOTE, OTHER, HIST = rl.GROUP_QUOTE, rl.GROUP_OTHER, rl.GROUP_HISTORICAL


class Recorder:
    def __init__(self, ok: bool = True, boom: bool = False) -> None:
        self.sent: list[dict[str, str]] = []
        self._ok, self._boom = ok, boom

    def send(self, payload):
        self.sent.append(dict(payload))
        if self._boom:
            raise RuntimeError("notifier down")
        return self._ok


def make(auto: bool = True, notifier=None) -> tuple[rl.RateLimiter, FakePacer]:
    pacer = FakePacer(auto=auto)
    return rl.RateLimiter(pacer=pacer, notifier=notifier), pacer


def test_the_limits_are_kites_published_ones() -> None:
    """AC-1: quote 1/s, historical 3/s, all other endpoints 10/s (F-60); the cooldown is 10 s; no other group."""
    assert dict(rl.GROUP_RATES) == {"quote": 1, "historical": 3, "other": 10}
    assert rl.COOLDOWN_SECONDS == 10.0


def test_slots_are_spaced_by_the_group_rate() -> None:
    """AC-1: n requests at once get slots 1/rate apart (hand: quote 0,1,2; historical 0,1/3,2/3; other 0,0.1)."""
    limiter, pacer = make()
    quote = [limiter._reserve(QUOTE, KEY, False, 5.0) for _ in range(3)]
    hist = [limiter._reserve(HIST, KEY, False, 5.0) for _ in range(3)]
    other = [limiter._reserve(OTHER, KEY, False, 5.0) for _ in range(3)]
    assert quote == [0.0, 1.0, 2.0]
    assert hist == pytest.approx([0.0, 1 / 3, 2 / 3])
    assert other == pytest.approx([0.0, 0.1, 0.2])
    assert pacer.now() == 0.0  # reserving books a slot; it does not move the clock


def test_groups_and_api_keys_have_their_own_buckets() -> None:
    """AC-1: a busy quote group does not slow 'other'; another api key has its own bucket (keyed by api key)."""
    limiter, _ = make()
    limiter._reserve(QUOTE, KEY, False, 5.0)
    assert limiter._reserve(QUOTE, KEY, False, 5.0) == 1.0
    assert limiter._reserve(OTHER, KEY, False, 5.0) == 0.0
    assert limiter._reserve(QUOTE, "otherkey", False, 5.0) == 0.0


def test_an_unknown_group_is_refused() -> None:
    """Allow-list: a group that is not in GROUP_RATES sends nothing."""
    limiter, _ = make()
    with pytest.raises(ValueError, match="unknown Kite endpoint group"):
        limiter.acquire("orders", KEY)


def test_a_user_action_that_would_wait_over_five_seconds_is_refused_at_once_with_the_busy_text() -> None:
    """AC-3: during a 10 s cooldown a user read is refused at once (clock unmoved) with the one busy text."""
    limiter, pacer = make()
    limiter.note_429(OTHER, KEY, "u1")
    with pytest.raises(rl.KiteBusy) as busy:
        limiter.acquire(OTHER, KEY)
    assert str(busy.value) == "Zerodha is busy - try again in a moment" == ZERODHA_BUSY_TEXT
    assert busy.value.reason == "wait" and pacer.now() == 0.0


def test_the_user_wait_limit_is_exactly_five_seconds() -> None:
    """AC-3: the 6th simultaneous quote read (slot 5.0 s) still fits; the 7th (6.0 s) is refused. Beyond the bound,
    the waiting list never grows past 5 whatever the number of attempts."""
    limiter, _ = make()
    starts = [limiter._reserve(QUOTE, KEY, False, 5.0) for _ in range(6)]
    assert starts == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    for _ in range(100):
        with pytest.raises(rl.KiteBusy):
            limiter._reserve(QUOTE, KEY, False, 5.0)
    assert len(limiter._buckets[(QUOTE, KEY)].booked) == 5


def test_a_background_burst_keeps_few_slots_so_a_user_read_still_gets_one() -> None:
    """Standing item (a): a background burst of 6 quote reads books at most 2 slots ahead (the 'queue' refusal); a user
    quote read still gets a slot inside its 5 s afterwards."""
    limiter, _ = make()
    bg = []
    for _ in range(6):
        try:
            bg.append(limiter._reserve(QUOTE, KEY, True, 30.0))
        except rl.KiteBusy as busy:
            assert busy.reason == "queue"
    assert bg == [0.0, 1.0, 2.0]  # one now, two booked ahead, three refused
    assert limiter._reserve(QUOTE, KEY, False, 5.0) == 3.0  # the user is behind at most 2 s of background


def test_a_background_job_waits_through_a_cooldown_and_a_user_action_does_not() -> None:
    """AC-3: a background job waits up to 30 s (the 10 s cooldown fits); a user action's 5 s cannot cover it."""
    limiter, pacer = make()
    limiter.note_429(OTHER, KEY, "u1")
    limiter.acquire(OTHER, KEY, background=True)
    assert pacer.now() == 10.0
    limiter.note_429(OTHER, KEY, "u1")
    with pytest.raises(rl.KiteBusy):
        limiter.acquire(OTHER, KEY)


def test_a_wait_over_thirty_seconds_is_refused_even_for_a_background_job() -> None:
    """AC-3: nothing waits without bound: a background slot past 30 s is refused."""
    limiter, _ = make()
    with pytest.raises(rl.KiteBusy) as busy:
        limiter._reserve(OTHER, KEY, True, 30.0 - 31.0)  # a deadline already behind the earliest slot
    assert busy.value.reason == "wait"


def test_a_429_starts_a_ten_second_cooldown_that_is_not_extended() -> None:
    """AC-4 / F-60: the first 429 at t=0 puts the group in cooldown until t=10; a second 429 during it does not push it
    to 10+ (Kite's window is sliding, so we send nothing into it and never extend it ourselves)."""
    limiter, pacer = make()
    limiter.note_429(OTHER, KEY, "u1")
    assert limiter.in_cooldown(OTHER, KEY) and not limiter.in_cooldown(QUOTE, KEY)
    pacer.advance(4.0)
    limiter.note_429(OTHER, KEY, "u1")  # a request that was already in flight also got 429
    assert limiter._reserve(OTHER, KEY, True, 30.0) == 10.0
    pacer.advance(6.0)
    assert not limiter.in_cooldown(OTHER, KEY)


def test_the_third_429_in_a_minute_raises_one_alert_and_the_fourth_none() -> None:
    """AC-6: three 429s inside a minute -> exactly one alert; a fourth in the same minute -> none; 60 s later a new
    burst alerts again. The alert body carries no token and uses the Notifier's field names."""
    notifier = Recorder()
    limiter, pacer = make(notifier=notifier)
    for _ in range(2):
        limiter.note_429(OTHER, KEY, "u1")
    assert notifier.sent == []
    limiter.note_429(QUOTE, KEY, "u2")
    assert len(notifier.sent) == 1
    limiter.note_429(OTHER, KEY, "u1")
    assert len(notifier.sent) == 1
    assert set(notifier.sent[0]) == {"project", "severity", "title", "body", "type", "dedupeKey"}
    assert TOKEN not in json.dumps(notifier.sent)
    pacer.advance(61.0)
    for _ in range(3):
        limiter.note_429(OTHER, KEY, "u1")
    assert len(notifier.sent) == 2


def test_two_429s_in_a_minute_raise_no_alert() -> None:
    """AC-6 negative: below the threshold nothing is sent, even for 429s spread over a minute."""
    notifier = Recorder()
    limiter, pacer = make(notifier=notifier)
    limiter.note_429(OTHER, KEY, "u1")
    pacer.advance(59.0)
    limiter.note_429(OTHER, KEY, "u1")
    pacer.advance(59.0)
    limiter.note_429(OTHER, KEY, "u1")  # the first fell out of the minute
    assert notifier.sent == []


@pytest.mark.parametrize("notifier", [Recorder(ok=False), Recorder(boom=True)])
def test_a_failing_alert_never_blocks_a_read(notifier, caplog) -> None:
    """AC-6: the Notifier returning False or raising is logged as not sent; the 429 handling carries on."""
    limiter, _ = make(notifier=notifier)
    with caplog.at_level(logging.WARNING, logger="ofo.broker.rate_limit"):
        for _ in range(3):
            limiter.note_429(OTHER, KEY, "u1")
    assert len(notifier.sent) == 1 and "NOT sent" in caplog.text
    assert limiter.in_cooldown(OTHER, KEY)


def test_with_no_notifier_url_the_alert_is_logged_as_not_sent(caplog) -> None:
    """AC-6: no NOTIFIER_URL (or no transport) -> LogNotifier; with a URL and a transport the call is POST
    {url}/notify with the shared gateway's fields and the key in a header."""
    assert isinstance(rl.notifier_from_env({}), rl.LogNotifier)
    assert isinstance(rl.notifier_from_env({"NOTIFIER_URL": "http://127.0.0.1:3300"}), rl.LogNotifier)  # no transport
    calls: list[tuple[str, dict[str, str], str]] = []
    notifier = rl.notifier_from_env({"NOTIFIER_URL": "http://127.0.0.1:3300/", "NOTIFIER_KEY": "k"},
                                    lambda url, headers, body: calls.append((url, headers, body)) or True)
    limiter, _ = make(notifier=notifier)
    for _ in range(3):
        limiter.note_429(OTHER, KEY, "u1")
    (url, headers, body), = calls
    assert url == "http://127.0.0.1:3300/notify" and headers["X-Notifier-Key"] == "k"
    assert json.loads(body)["dedupeKey"] == "kite-429-burst" and TOKEN not in body
    with caplog.at_level(logging.WARNING, logger="ofo.broker.rate_limit"):
        limiter2, _ = make()
        for _ in range(3):
            limiter2.note_429(OTHER, KEY, "u1")
    assert "alert NOT sent (no Notifier transport)" in caplog.text


def test_429s_are_counted_and_logged_per_group_and_user_without_a_token(caplog) -> None:
    """AC-6: counted per (group, user); the log line names group, user ref and count; the access token is nowhere."""
    limiter, _ = make()
    _, user = rl.identity(f"token {KEY}:{TOKEN}", None)
    with caplog.at_level(logging.INFO, logger="ofo.broker.rate_limit"):
        limiter.note_429(OTHER, KEY, user)
        limiter.note_429(OTHER, KEY, user)
        limiter.note_429(QUOTE, KEY, user)
    assert (limiter.count(OTHER, user), limiter.count(QUOTE, user), limiter.count(OTHER, "someone")) == (2, 1, 0)
    assert f"kite 429 group=other user={user} count=2" in caplog.text
    assert TOKEN not in caplog.text and TOKEN not in user and len(user) == 8


def test_identity_reads_the_api_key_and_hides_the_token() -> None:
    """The bucket key is the api key; the user ref is a hash prefix. The login exchange has only a form api_key."""
    key, user = rl.identity(f"token {KEY}:{TOKEN}", None)
    assert key == KEY and user != TOKEN and TOKEN not in user
    assert rl.identity(None, f"api_key={KEY}&request_token=x".encode()) == (KEY, "-")
    assert rl.identity(None, None) == ("-", "-") and rl.identity("Bearer abc", b"") == ("-", "-")


def test_background_context_is_off_by_default_and_scoped() -> None:
    """Standing item (a): background mode applies only inside the context manager."""
    assert rl._BACKGROUND.get() is False
    with rl.background():
        assert rl._BACKGROUND.get() is True
    assert rl._BACKGROUND.get() is False


def test_use_installs_one_process_wide_limiter_for_a_block() -> None:
    """Both doors call the module-level limiter: the block's limiter is the one they see, then it is restored."""
    limiter, _ = make()
    before = rl.current()
    with rl.use(limiter):
        assert rl.current() is limiter
        rl.acquire(OTHER, KEY)
    assert rl.current() is before
