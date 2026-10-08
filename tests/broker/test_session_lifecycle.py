"""W-058 AC-7: a broker session is temporary (about one day) and its end never reaches identity, strategies or
entitlements (REQ-015 AC-7). Expected values are written from the spec and Kite's documented formats."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from ofo.broker import kite_auth, session
from ofo.broker.kite_auth import checksum, login_url
from ofo.broker.session import (
    IST,
    EndReason,
    SessionState,
    disconnect,
    expected_expiry,
    expire_on_clock,
    expire_on_token_exception,
    replace,
    start,
)

LOGIN = datetime(2026, 10, 7, 10, 15, tzinfo=IST)  # a Wednesday morning
LATER = LOGIN + timedelta(hours=2)


def test_start_is_connected_with_the_next_morning_expiry():
    s = start("u-1", LOGIN)
    assert s.state is SessionState.CONNECTED and s.active
    assert s.broker == "zerodha"
    assert s.expected_expiry == datetime(2026, 10, 8, 6, 0, tzinfo=IST)
    assert s.ended_at is None and s.end_reason is None


@pytest.mark.parametrize(
    "end, reason, state",
    [
        (expire_on_token_exception, EndReason.EXPIRED, SessionState.EXPIRED),
        (disconnect, EndReason.DISCONNECTED, SessionState.DISCONNECTED),
        (replace, EndReason.REPLACED, SessionState.REPLACED),
    ],
)
def test_each_end_transition(end, reason, state):
    s = end(start("u-1", LOGIN), LATER)
    assert (s.state, s.end_reason, s.ended_at, s.active) == (state, reason, LATER, False)


def test_token_exception_wins_before_the_expected_expiry():
    s = expire_on_token_exception(start("u-1", LOGIN), LATER)
    assert LATER < s.expected_expiry
    assert s.state is SessionState.EXPIRED


def test_clock_expiry_only_at_or_after_the_expected_expiry():
    s = start("u-1", LOGIN)
    before = datetime(2026, 10, 8, 5, 59, 59, tzinfo=IST)
    at = datetime(2026, 10, 8, 6, 0, tzinfo=IST)
    assert expire_on_clock(s, before) is s
    ended = expire_on_clock(s, at)
    assert (ended.state, ended.end_reason, ended.ended_at) == (SessionState.EXPIRED, EndReason.EXPIRED, at)


@pytest.mark.parametrize("first", [expire_on_token_exception, disconnect, replace])
@pytest.mark.parametrize("second", [expire_on_token_exception, disconnect, replace])
def test_end_states_are_terminal_and_the_first_reason_wins(first, second):
    ended = first(start("u-1", LOGIN), LATER)
    again = second(ended, LATER + timedelta(minutes=5))
    assert again == ended
    assert expire_on_clock(ended, LATER + timedelta(days=3)) == ended


def test_ending_does_not_change_the_session_identity():
    s = start("u-1", LOGIN)
    ended = disconnect(s, LATER)
    assert (ended.user_ref, ended.broker, ended.started_at, ended.expected_expiry) == (
        s.user_ref, s.broker, s.started_at, s.expected_expiry)


# ---- expected_expiry: the next 06:00 IST after login (an expectation until F-32 measures it) ----


@pytest.mark.parametrize(
    "login, expiry",
    [
        # evening login: across midnight to the next morning
        (datetime(2026, 10, 7, 23, 50, tzinfo=IST), datetime(2026, 10, 8, 6, 0, tzinfo=IST)),
        # just after midnight, before 06:00: the same calendar morning
        (datetime(2026, 10, 8, 0, 5, tzinfo=IST), datetime(2026, 10, 8, 6, 0, tzinfo=IST)),
        (datetime(2026, 10, 8, 5, 59, tzinfo=IST), datetime(2026, 10, 8, 6, 0, tzinfo=IST)),
        # exactly 06:00: the next day's 06:00
        (datetime(2026, 10, 8, 6, 0, tzinfo=IST), datetime(2026, 10, 9, 6, 0, tzinfo=IST)),
        # Saturday login: Sunday 06:00 (daily, weekends included)
        (datetime(2026, 10, 10, 14, 0, tzinfo=IST), datetime(2026, 10, 11, 6, 0, tzinfo=IST)),
        # Sunday night login: Monday 06:00
        (datetime(2026, 10, 11, 22, 0, tzinfo=IST), datetime(2026, 10, 12, 6, 0, tzinfo=IST)),
        # a UTC login time is read in IST: 2026-10-07 20:00 UTC = 2026-10-08 01:30 IST
        (datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc), datetime(2026, 10, 8, 6, 0, tzinfo=IST)),
        # 2026-10-08 00:30 UTC = 06:00 IST exactly
        (datetime(2026, 10, 8, 0, 30, tzinfo=timezone.utc), datetime(2026, 10, 9, 6, 0, tzinfo=IST)),
    ],
)
def test_expected_expiry(login, expiry):
    assert expected_expiry(login) == expiry


def test_naive_times_are_refused():
    with pytest.raises(ValueError):
        expected_expiry(datetime(2026, 10, 7, 10, 0))
    with pytest.raises(ValueError):
        disconnect(start("u-1", LOGIN), datetime(2026, 10, 7, 11, 0))


def test_only_zerodha_and_a_user_ref():
    with pytest.raises(ValueError):
        start("u-1", LOGIN, broker="upstox")
    with pytest.raises(ValueError):
        start("", LOGIN)


# ---- expiry never produces a call into any other store ----

FORBIDDEN = ("ofo.strategy", "ofo.entitlements", "ofo.admin", "ofo.audit", "ofo.orders", "ofo.execution",
             "ofo.reconciliation", "ofo.timeline", "ofo_app")
STANDARD = {"__future__", "dataclasses", "datetime", "enum", "hashlib", "typing", "urllib.parse"}


@pytest.mark.parametrize("module", [session, kite_auth])
def test_the_lifecycle_imports_nothing_but_the_standard_library(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= STANDARD, imported - STANDARD
    assert not any(name.startswith(FORBIDDEN) for name in imported)


@pytest.mark.parametrize("fn", [expire_on_token_exception, expire_on_clock, disconnect, replace])
def test_end_functions_take_only_the_session_and_a_time(fn):
    assert len(inspect.signature(fn).parameters) == 2


# ---- the login link and the checksum (Kite Connect v3 formats) ----


def test_login_url_is_zerodhas_page_with_the_state_in_redirect_params():
    url = login_url("kitekey", "st-123")
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == ("https", "kite.zerodha.com", "/connect/login")
    q = parse_qs(parts.query)
    assert q == {"v": ["3"], "api_key": ["kitekey"], "redirect_params": ["state=st-123"]}


def test_login_url_carries_no_secret_or_credential_field():
    q = parse_qs(urlsplit(login_url("kitekey", "st-123")).query)
    assert not {"api_secret", "password", "pin", "otp", "totp"} & {k.lower() for k in q}


def test_checksum_is_sha256_of_key_token_secret():
    # SHA-256("abc"), the FIPS 180-2 test vector
    assert checksum("a", "b", "c") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_checksum_refuses_an_empty_part():
    with pytest.raises(ValueError):
        checksum("a", "", "c")
