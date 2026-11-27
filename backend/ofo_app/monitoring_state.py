"""Which trades the worker is NOT watching, why, and since when (REQ-115 AC-4 / AC-6, REQ-049 AC badge, ADR-330 (44)).

Real case, 27 Nov: the worker could not price some trades and skipped them without a word; Live Strategies showed no
"Monitoring paused" and no "Health unknown" dot while every price was missing. The worker's pause state lived only in
its own memory. One capability, one module:

- WRITE (the worker's one path): ``Publisher.publish`` stores, per strategy, ``status`` (active | paused), ``reason``
  (the
  worker's own price state or pause cause, a code, never prose), ``why`` (the REST stand-in's reason, or "") and
  ``since`` (when this status and reason began, kept while they stay the same). Redis, the heartbeat's own store
  (no migration); written when something changed, and at least every ``REFRESH_S`` so a dead worker's snapshot ages out.
- READ (any process): ``read_states`` answers every asked strategy, never leaves one out and never guesses "active":
  the worker's heartbeat not fresh -> paused, reason ``workers_down`` (AC-6); the snapshot missing, unreadable, old or
  from a clock far ahead -> paused, ``state_unreadable``; a strategy the snapshot does not name -> paused,
  ``not_listed`` (the worker does not list it: no plan, or not traded yet). A fresh snapshot's own answer otherwise.
The words shown to the trader are the screens' (REQ-049 "Monitoring paused", the grey "Health unknown" dot); this
module carries codes only (no new on-screen sentence).
Spec basis: REQ-115 AC-4, AC-6; REQ-049 AC "Monitoring paused"; domain-model state machine (a lost feed leaves the
strategy Active, its monitoring status shows paused); ADR-330 (44), (58).
"""
from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from ofo_app import feed_bus

log = logging.getLogger(__name__)

ACTIVE: Final = "active"
PAUSED: Final = "paused"
#: reasons that are not a price state of the worker (the worker's own are ``PriceState`` names, lower case)
WORKERS_DOWN: Final = "workers_down"
STATE_UNREADABLE: Final = "state_unreadable"
NOT_LISTED: Final = "not_listed"
SNAPSHOT_STALE_S: Final = feed_bus.HEARTBEAT_STALE_S  # the same two minutes as the heartbeat (AC-6)
REFRESH_S: Final = 10  # an unchanged snapshot is rewritten this often (it must stay younger than SNAPSHOT_STALE_S)


def key() -> str:
    return f"{feed_bus.KEY_PREFIX}:background:monitoring"


@dataclass(frozen=True)
class Entry:
    """One strategy's monitoring answer. ``since`` None = not known (a worker that is down says nothing of when)."""
    strategy_id: int
    status: str
    reason: str
    why: str
    since: datetime.datetime | None


def _aware(at: datetime.datetime) -> datetime.datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("a monitoring time must carry a time zone")
    return at


def encode(entries: Iterable[Entry], at: datetime.datetime) -> str:
    return json.dumps({"at": _aware(at).isoformat(), "strategies": {
        str(e.strategy_id): {"status": e.status, "reason": e.reason, "why": e.why,
                             "since": None if e.since is None else _aware(e.since).isoformat()}
        for e in entries}}, sort_keys=True)


def _time(raw: Any) -> datetime.datetime | None:
    try:
        at = datetime.datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    return at if at is not None and at.utcoffset() is not None else None


def decode(raw: Any, now: datetime.datetime) -> dict[int, Entry] | None:  # noqa: PLR0911 - one answer per way to distrust
    """The stored snapshot, or None when it cannot be trusted: missing, not text, not our shape, no time zone, older
    than ``SNAPSHOT_STALE_S``, or that far ahead of ``now`` (a wrong or simulated clock is never read as live)."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        body = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
    if not isinstance(body, dict) or not isinstance(body.get("strategies"), dict):
        return None
    at = _time(body.get("at"))
    if at is None or abs((now - at).total_seconds()) > SNAPSHOT_STALE_S:
        return None
    out: dict[int, Entry] = {}
    for sid_text, row in body["strategies"].items():
        try:
            sid = int(sid_text)
        except ValueError:
            return None
        if not isinstance(row, dict) or row.get("status") not in (ACTIVE, PAUSED) \
                or not isinstance(row.get("reason"), str) or not isinstance(row.get("why"), str):
            return None  # one bad row: the whole snapshot is not trusted (fail closed)
        since = _time(row.get("since"))
        if row.get("since") is not None and since is None:
            return None
        out[sid] = Entry(sid, row["status"], row["reason"], row["why"], since)
    return out


def snapshot(status: Mapping[int, Any], reasons: Mapping[int, Any], whys: Mapping[int, str],
             previous: Mapping[int, Entry], now: datetime.datetime) -> list[Entry]:
    """The worker's entries from its own dicts. ``status`` values are ``MonitoringStatus`` (``.name`` PAUSED/ACTIVE),
    ``reasons`` values ``PriceState`` (``.name``). A paused strategy with no recorded reason says ``unknown``, never
    nothing. ``since`` is kept from ``previous`` while status and reason stay the same, else it is ``now``."""
    out: list[Entry] = []
    for sid in sorted(status):
        paused = getattr(status[sid], "name", str(status[sid])).upper() == "PAUSED"
        reason = "" if not paused else (getattr(reasons.get(sid), "name", None) or "unknown").lower()
        why = "" if not paused else whys.get(sid, "") or ""
        kept = previous.get(sid)
        same = kept is not None and kept.status == (PAUSED if paused else ACTIVE) and kept.reason == reason
        out.append(Entry(sid, PAUSED if paused else ACTIVE, reason, why, kept.since if same and kept else now))
    return out


class Publisher:
    """The worker's one write path. ``publish`` never raises (a store that cannot answer is logged; the cycle goes on,
    and readers see the snapshot age out as ``state_unreadable``)."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._previous: dict[int, Entry] = {}
        self._written: str | None = None
        self._written_at: datetime.datetime | None = None

    async def publish(self, status: Mapping[int, Any], reasons: Mapping[int, Any], whys: Mapping[int, str],
                      now: datetime.datetime) -> bool:
        """True when a snapshot was written."""
        if self._client is None:
            return False
        entries = snapshot(status, reasons, whys, self._previous, now)
        fingerprint = json.dumps([(e.strategy_id, e.status, e.reason, e.why) for e in entries])
        due = self._written_at is None or (now - self._written_at).total_seconds() >= REFRESH_S
        if fingerprint == self._written and not due:
            return False
        try:
            await self._client.set(key(), encode(entries, now))
        except Exception as exc:  # noqa: BLE001 - never stops a cycle; the reader then sees an old snapshot
            log.warning("background: writing the monitoring state failed: %s", type(exc).__name__)
            return False
        self._previous = {e.strategy_id: e for e in entries}
        self._written, self._written_at = fingerprint, now
        return True


async def read_states(client: Any, strategy_ids: Iterable[int], now: datetime.datetime, *,
                      heartbeat: Callable[..., Any] | None = None) -> dict[int, Entry]:
    """An answer for EVERY asked strategy (module docstring). Never raises; never answers "active" without a fresh
    heartbeat and a fresh snapshot that names the strategy."""
    ids = sorted(set(strategy_ids))

    def all_paused(reason: str) -> dict[int, Entry]:
        return {i: Entry(i, PAUSED, reason, "", None) for i in ids}
    check = heartbeat or feed_bus.read_heartbeat_state
    if await check(client, now) != feed_bus.FRESH:
        return all_paused(WORKERS_DOWN)
    try:
        raw = await client.get(key())
    except Exception as exc:  # noqa: BLE001 - a store that cannot answer is "cannot read", never "fine"
        log.warning("monitoring state could not be read: %s", type(exc).__name__)
        return all_paused(STATE_UNREADABLE)
    found = decode(raw, now)
    if found is None:
        return all_paused(STATE_UNREADABLE)
    return {i: found.get(i) or Entry(i, PAUSED, NOT_LISTED, "", None) for i in ids}
