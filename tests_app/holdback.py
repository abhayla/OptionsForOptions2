"""TEST-ONLY hold-back tools for the screen tester (Lane Q2 gap 7). Nothing in ``backend/`` imports this file.

They produce, on demand and without a change to the product, the three conditions the 27 Nov checks T1-23, AX-01 and
T2-08 needed a lucky market for:
 (a) withhold the ticks of ONE contract            -> a leg that is live in the feed but silent for the screen;
 (b) silence the INDEX for 70 s                    -> an index quote older than the 60 s index limit
     (``detection.index_quote_max_age_seconds``, ADR-330 (39)) while option frames keep the feed healthy;
 (c) delay ONE route by N seconds                  -> a slow answer for one page.

One rules file, JSON, named by the environment variable ``OFO_HOLDBACK_FILE`` (read ONLY by these test tools); it is
re-read when its modification time changes, so the tester edits it while the session runs. Absent file = no rule = every
frame and every route passes unchanged (fail open for the data, because this is a tester's tool, never a product path).
    {"withhold_tokens": [11421186],                              # (a) Kite instrument tokens
     "silence": {"tokens": [256265], "from": "2026-11-27T10:00:00+05:30", "seconds": 70},    # (b)
     "delay_routes": [{"prefix": "/api/strategies/", "suffix": "/plan-watch", "seconds": 5,
                       "from": "2026-11-27T10:00:00+05:30", "until": "2026-11-27T10:10:00+05:30"}]}  # (c)
Used with: a Kite WebSocket relay (design in RESULTS-lane-q2.md, "gap 7") that calls ``filter_frame`` on every binary
message between the real Kite socket and the feed process; and ``holdback_app:create_app`` (below), a wrapper that puts
``RouteDelay`` around the real app. Pure parts (rules, ``filter_frame``) take ``now`` from the caller.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

ENV = "OFO_HOLDBACK_FILE"
HEARTBEAT_LEN = 1


@dataclass(frozen=True)
class RouteRule:
    prefix: str
    suffix: str
    seconds: float
    start: datetime.datetime | None = None
    until: datetime.datetime | None = None

    def applies(self, path: str, now: datetime.datetime) -> bool:
        if not (path.startswith(self.prefix) and path.endswith(self.suffix)):
            return False
        return (self.start is None or now >= self.start) and (self.until is None or now < self.until)


@dataclass(frozen=True)
class Rules:
    withhold_tokens: frozenset[int] = frozenset()
    silence_tokens: frozenset[int] = frozenset()
    silence_from: datetime.datetime | None = None
    silence_seconds: float = 0
    routes: tuple[RouteRule, ...] = field(default_factory=tuple)

    def silenced(self, token: int, now: datetime.datetime) -> bool:
        if token in self.withhold_tokens:
            return True
        if token not in self.silence_tokens or self.silence_from is None:
            return False
        return self.silence_from <= now < self.silence_from + datetime.timedelta(seconds=self.silence_seconds)

    def delay_for(self, path: str, now: datetime.datetime) -> float:
        return max((r.seconds for r in self.routes if r.applies(path, now)), default=0.0)


def _when(raw: object) -> datetime.datetime | None:
    if raw is None:
        return None
    moment = datetime.datetime.fromisoformat(str(raw))
    if moment.tzinfo is None:
        raise ValueError(f"a hold-back time needs an offset (+05:30): {raw!r}")
    return moment


def parse_rules(text: str) -> Rules:
    data = json.loads(text) if text.strip() else {}
    silence = data.get("silence") or {}
    return Rules(
        withhold_tokens=frozenset(int(t) for t in data.get("withhold_tokens", ())),
        silence_tokens=frozenset(int(t) for t in silence.get("tokens", ())),
        silence_from=_when(silence.get("from")), silence_seconds=float(silence.get("seconds", 0)),
        routes=tuple(RouteRule(r.get("prefix", ""), r.get("suffix", ""), float(r["seconds"]),
                               _when(r.get("from")), _when(r.get("until"))) for r in data.get("delay_routes", ())))


class RulesFile:
    """The rules, re-read when the file's modification time changes. A missing file is no rule."""

    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self._path = Path(path) if path else (Path(os.environ[ENV]) if os.environ.get(ENV) else None)
        self._stamp: float | None = None
        self._rules = Rules()

    def current(self) -> Rules:
        if self._path is None or not self._path.exists():
            self._stamp, self._rules = None, Rules()
            return self._rules
        stamp = self._path.stat().st_mtime
        if stamp != self._stamp:
            self._rules, self._stamp = parse_rules(self._path.read_text(encoding="utf-8")), stamp
        return self._rules


def filter_frame(rules: Rules, frame: bytes, now: datetime.datetime) -> bytes | None:
    """One Kite binary message in, the message the feed should see out: packets of a silenced token are removed and the
    packet count rewritten; a message left with no packet is dropped (None); a heartbeat (1 byte) and a message that
    does not parse are passed unchanged (the tool never invents a failure of its own)."""
    if len(frame) <= HEARTBEAT_LEN or not (rules.withhold_tokens or rules.silence_tokens):
        return frame
    count, off, kept = int.from_bytes(frame[0:2], "big"), 2, []
    for _ in range(count):
        if off + 2 > len(frame):
            return frame
        length = int.from_bytes(frame[off:off + 2], "big")
        packet = frame[off + 2:off + 2 + length]
        if len(packet) != length or length < 4:  # noqa: PLR2004 - a token is 4 bytes
            return frame
        if not rules.silenced(int.from_bytes(packet[0:4], "big"), now):
            kept.append(frame[off:off + 2 + length])
        off += 2 + length
    if len(kept) == count:
        return frame
    return len(kept).to_bytes(2, "big") + b"".join(kept) if kept else None


Clock = Callable[[], datetime.datetime]
Sleep = Callable[[float], Awaitable[None]]


class RouteDelay:
    """ASGI middleware: waits ``Rules.delay_for(path)`` seconds before an HTTP request reaches the app."""

    def __init__(self, inner, rules: RulesFile, clock: Clock, sleep: Sleep = asyncio.sleep) -> None:
        self.inner, self.rules, self.clock, self.sleep = inner, rules, clock, sleep

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            seconds = self.rules.current().delay_for(scope["path"], self.clock())
            if seconds > 0:
                await self.sleep(seconds)
        await self.inner(scope, receive, send)


def create_app():
    """``uvicorn --factory holdback.create_app``: the REAL app wrapped by ``RouteDelay`` on the real clock."""
    from ofo.timeutil import IST  # noqa: PLC0415 - the tool's one import of the product, only when it is launched
    from ofo_app.main import create_app as real  # noqa: PLC0415
    return RouteDelay(real(), RulesFile(), lambda: datetime.datetime.now(IST))

