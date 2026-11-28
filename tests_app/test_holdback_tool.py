"""The hold-back tools (tests_app/holdback.py) do what the screen tester needs: (a) withhold one contract, (b) silence
the index for 70 s, (c) delay one route. Pure: frames are bytes, times are passed in, the sleep is a recorder."""
from __future__ import annotations

import datetime
import json

from holdback import RouteDelay, RulesFile, filter_frame, parse_rules

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NIFTY, OPTION, OTHER = 256265, 11421186, 11421442
T0 = datetime.datetime(2026, 11, 27, 10, 0, 0, tzinfo=IST)
INDEX_MAX_AGE_S = 60  # detection.index_quote_max_age_seconds (ADR-330 (39)); the silence must outlast it
SILENCE_S = 70


def packet(token: int) -> bytes:
    body = token.to_bytes(4, "big") + bytes(40)
    return len(body).to_bytes(2, "big") + body


def frame(*tokens: int) -> bytes:
    return len(tokens).to_bytes(2, "big") + b"".join(packet(t) for t in tokens)


def tokens_of(data: bytes | None) -> list[int]:
    if data is None:
        return []
    out, off = [], 2
    for _ in range(int.from_bytes(data[:2], "big")):
        length = int.from_bytes(data[off:off + 2], "big")
        out.append(int.from_bytes(data[off + 2:off + 6], "big"))
        off += 2 + length
    return out


def test_no_rules_passes_every_frame_unchanged():
    rules = parse_rules("")
    assert filter_frame(rules, frame(NIFTY, OPTION), T0) == frame(NIFTY, OPTION)


def test_a_withheld_contract_is_removed_from_a_frame_and_the_others_stay():
    rules = parse_rules(json.dumps({"withhold_tokens": [OPTION]}))
    assert tokens_of(filter_frame(rules, frame(NIFTY, OPTION, OTHER), T0)) == [NIFTY, OTHER]
    assert filter_frame(rules, frame(OPTION), T0) is None  # a frame of only that contract is dropped


def test_the_index_is_silent_for_70_seconds_from_the_start_and_then_speaks_again():
    assert SILENCE_S > INDEX_MAX_AGE_S
    rules = parse_rules(json.dumps({"silence": {"tokens": [NIFTY], "from": T0.isoformat(), "seconds": SILENCE_S}}))
    s = datetime.timedelta
    assert tokens_of(filter_frame(rules, frame(NIFTY, OPTION), T0 - s(seconds=1))) == [NIFTY, OPTION]
    for at in (T0, T0 + s(seconds=35), T0 + s(seconds=69, milliseconds=999)):
        assert tokens_of(filter_frame(rules, frame(NIFTY, OPTION), at)) == [OPTION]  # option frames keep the feed alive
    assert tokens_of(filter_frame(rules, frame(NIFTY, OPTION), T0 + s(seconds=70))) == [NIFTY, OPTION]


def test_heartbeats_and_malformed_bytes_pass_unchanged():
    rules = parse_rules(json.dumps({"withhold_tokens": [OPTION]}))
    assert filter_frame(rules, b"\x00", T0) == b"\x00"
    broken = (2).to_bytes(2, "big") + packet(OPTION)[:10]
    assert filter_frame(rules, broken, T0) == broken


def test_a_time_without_an_offset_is_refused():
    try:
        parse_rules(json.dumps({"silence": {"tokens": [NIFTY], "from": "2026-11-27T10:00:00", "seconds": 70}}))
    except ValueError as exc:
        assert "offset" in str(exc)
    else:
        raise AssertionError("a naive time must be refused")


def test_the_rules_file_is_reread_when_it_changes_and_a_missing_file_is_no_rule(tmp_path):
    path = tmp_path / "holdback.json"
    book = RulesFile(path)
    assert book.current().withhold_tokens == frozenset()
    path.write_text(json.dumps({"withhold_tokens": [OPTION]}), encoding="utf-8")
    assert book.current().withhold_tokens == frozenset({OPTION})
    path.unlink()
    assert book.current().withhold_tokens == frozenset()


async def test_one_route_is_delayed_inside_its_window_and_no_other(tmp_path):
    path = tmp_path / "holdback.json"
    path.write_text(json.dumps({"delay_routes": [{"prefix": "/api/strategies/", "suffix": "/plan-watch", "seconds": 5,
                                                  "from": T0.isoformat(),
                                                  "until": (T0 + datetime.timedelta(minutes=10)).isoformat()}]}),
                    encoding="utf-8")
    slept, reached, now = [], [], [T0]

    async def inner(scope, _receive, _send):
        reached.append(scope["path"])

    async def sleep(seconds):
        slept.append(seconds)

    app = RouteDelay(inner, RulesFile(path), lambda: now[0], sleep)
    for p in ("/api/strategies/7/plan-watch", "/portfolio", "/health"):
        await app({"type": "http", "path": p}, None, None)
    now[0] = T0 + datetime.timedelta(minutes=11)  # the window is over
    await app({"type": "http", "path": "/api/strategies/7/plan-watch"}, None, None)
    assert slept == [5] and len(reached) == 4  # noqa: PLR2004 - four requests, one delayed
