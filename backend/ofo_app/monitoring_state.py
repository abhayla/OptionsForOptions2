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

Lane FE (28 Nov, review F2; real case 23 Nov: the NIFTY tick stopped at 15:15:18, the REST stand-in kept the worker
"watching" while no index exit could fire). Two more records, one reader:
- INDEX READING (worker writes, the paper monitor reads): per underlying, the index value the worker's check used to
  call a trade watched, with the time of that quote and its source (feed tick or REST stand-in). The monitor evaluates
  its index exits from the newer of its own live feed index and this reading (``paper_monitor._index_exits_at``).
- INDEX EXITS (the paper monitor writes, ``read_states`` reads): the strategies whose armed index exit was NOT
  evaluated at the monitor's last pass (no reading within the age, the store unreadable) and a time. Such a strategy
  reads PAUSED (reason ``stale``: "The last price is too old, so no rule can fire.", why ``index_not_live``) whatever
  the worker says; a snapshot that has stopped being written reads every strategy it lists as PAUSED (``why``
  ``index_exits_not_run``: the monitor that checks the exits is not running). Never "watched" without the exit check.
Spec basis: REQ-115 AC-4, AC-6; REQ-049 AC "Monitoring paused"; domain-model state machine (a lost feed leaves the
strategy Active, its monitoring status shows paused); ADR-330 (44), (58).
"""
from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
INDEX_NOT_LIVE: Final = "index_not_live"  # the ``why`` of a trade whose index exit has no live index reading
INDEX_EXITS_NOT_RUN: Final = "index_exits_not_run"  # the ``why`` when the monitor's own snapshot stopped
INDEX_STALE_REASON: Final = "stale"  # the existing code and sentence (``monitoring_why_stale``); no new on-screen text
INDEX_READING_TTL_S: Final = 120
LEG_NOT_LIVE: Final = "leg_not_live"  # the ``why`` of a trade whose leg-price exit has no live leg reading
LEG_READING_MAX_AGE_S: Final = 90  # current while the worker re-reads (its tick key turns over every IST minute)
EXIT_NOT_PRICED: Final = "exit_not_priced"  # the why of a crossed exit that could not run (no live leg price)
MAX_READING_VALUE: Final = Decimal(10) ** 9  # no index or option price is this large: such a value is no reading
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
    answers = {i: found.get(i) or Entry(i, PAUSED, NOT_LISTED, "", None) for i in ids}
    return await _with_index_exits(client, answers, now)


async def _with_index_exits(client: Any, answers: dict[int, Entry], now: datetime.datetime) -> dict[int, Entry]:
    """The one place an index exit that is not being checked turns a trade from watched to paused. A strategy the
    worker calls ACTIVE is paused when the monitor's snapshot names it (not evaluated) or, with the snapshot too old,
    names it at all (the monitor is not running). A report that cannot be read pauses every trade the worker calls
    ACTIVE (``state_unreadable``); only "no report at all" (no monitor ever wrote one) keeps the worker's answer."""
    try:
        raw = await client.get(exits_key())
    except Exception as exc:  # noqa: BLE001 - a store that cannot answer cannot clear a trade with an exit
        log.warning("monitoring state: the index-exit report could not be read: %s", type(exc).__name__)
        return {i: _paused_unreadable(e) for i, e in answers.items()}
    if raw is None:
        return answers
    exits = decode_exits(raw, now)
    if exits is None:  # a report we cannot read clears nothing (fail closed, as the snapshot's own rule)
        return {i: _paused_unreadable(e) for i, e in answers.items()}
    out: dict[int, Entry] = {}
    for i, entry in answers.items():
        listed = exits.get(i)
        if entry.status != ACTIVE or listed is None:
            out[i] = entry
        else:
            out[i] = Entry(i, PAUSED, INDEX_STALE_REASON, listed, entry.since)
    return out


def _paused_unreadable(entry: Entry) -> Entry:
    return entry if entry.status != ACTIVE else Entry(entry.strategy_id, PAUSED, STATE_UNREADABLE, "", None)


# ---- the index reading (worker -> monitor) and the index-exit report (monitor -> read_states) -----------------------

def index_key(underlying: str) -> str:
    return f"{feed_bus.KEY_PREFIX}:background:index:{underlying}"


def leg_key(instrument_id: str) -> str:
    return f"{feed_bus.KEY_PREFIX}:background:leg:{instrument_id}"


def exits_key() -> str:
    return f"{feed_bus.KEY_PREFIX}:background:index_exits"


@dataclass(frozen=True)
class IndexReading:
    """One index value, the time of its quote, and its source: "feed" (a tick) or "rest" (the stand-in)."""
    underlying: str
    value: Decimal
    at: datetime.datetime
    source: str


def encode_reading(reading: IndexReading, published: datetime.datetime) -> str:
    return json.dumps({"underlying": reading.underlying, "value": str(reading.value),
                       "at": _aware(reading.at).isoformat(), "source": reading.source,
                       "published": _aware(published).isoformat()}, sort_keys=True)


def decode_reading(raw: Any, now: datetime.datetime, max_age: datetime.timedelta | None,
                   published_max_s: float = INDEX_READING_TTL_S, *, expect: str | None = None) -> IndexReading | None:
    """The stored reading, or None: missing, not our shape, no time zone, a quote older than ``max_age`` (the one index
    age rule; None for an option leg, whose quote is current while the feed is, however long ago it last changed), a
    quote from the future, one published more than ``published_max_s`` ago (a worker that stopped writing), a value that
    is not a plausible price, or (``expect``) a reading of another instrument than the one asked for."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        body = json.loads(text) if isinstance(text, str) else None
        value = Decimal(body["value"]) if isinstance(body, dict) and isinstance(body.get("value"), str) else None
    except (ValueError, InvalidOperation, KeyError, TypeError):
        return None
    if body is None or value is None or not value.is_finite() or not 0 < value < MAX_READING_VALUE \
            or body.get("source") not in ("feed", "rest") or not isinstance(body.get("underlying"), str) \
            or (expect is not None and body["underlying"] != expect):
        return None
    at, published = _time(body.get("at")), _time(body.get("published"))
    if at is None or published is None:
        return None
    if (max_age is not None and now - at > max_age) or at - now > FUTURE_SKEW \
            or abs((now - published).total_seconds()) > published_max_s:
        return None
    return IndexReading(body["underlying"], value, at, body["source"])


FUTURE_SKEW: Final = datetime.timedelta(seconds=2)


async def publish_index(client: Any, reading: IndexReading, published: datetime.datetime, *,
                        leg: bool = False) -> bool:
    """The worker's write (an index reading by underlying; with ``leg``, an option leg's by instrument id, carried in
    ``reading.underlying``). Never raises; True when written."""
    if client is None:
        return False
    key = leg_key(reading.underlying) if leg else index_key(reading.underlying)
    try:
        await client.set(key, encode_reading(reading, published))
    except Exception as exc:  # noqa: BLE001 - the monitor then finds no reading and says so
        log.warning("background: writing the %s reading failed: %s", "leg" if leg else "index", type(exc).__name__)
        return False
    return True


async def read_index(client: Any, underlying: str, now: datetime.datetime,
                     max_age: datetime.timedelta) -> IndexReading | None:
    """The monitor's read. Never raises; None = no usable reading (the caller does not evaluate and says so)."""
    if client is None:
        return None
    try:
        raw = await client.get(index_key(underlying))
    except Exception as exc:  # noqa: BLE001 - a store that cannot answer gives no reading
        log.warning("paper monitor: the index reading could not be read: %s", type(exc).__name__)
        return None
    return None if raw is None else decode_reading(raw, now, max_age, expect=underlying)


async def read_leg(client: Any, instrument_id: str, now: datetime.datetime) -> IndexReading | None:
    """The monitor's read of the price the worker used for one option leg: current while the worker keeps writing it
    (``LEG_READING_MAX_AGE_S``). Never raises; None = no usable reading."""
    if client is None:
        return None
    try:
        raw = await client.get(leg_key(instrument_id))
    except Exception as exc:  # noqa: BLE001 - a store that cannot answer gives no reading
        log.warning("paper monitor: the leg reading could not be read: %s", type(exc).__name__)
        return None
    return None if raw is None else decode_reading(raw, now, None, LEG_READING_MAX_AGE_S, expect=instrument_id)


def encode_exits(not_run: Mapping[int, str], at: datetime.datetime) -> str:
    return json.dumps({"at": _aware(at).isoformat(), "not_run": {str(k): v for k, v in sorted(not_run.items())}},
                      sort_keys=True)


def decode_exits(raw: Any, now: datetime.datetime) -> dict[int, str] | None:
    """strategy -> why, from the monitor's report; a report older than ``SNAPSHOT_STALE_S`` (the monitor stopped) lists
    ``INDEX_EXITS_NOT_RUN`` for EVERY strategy it knew of (``not_run`` and ``watching``); None = not our shape (the
    caller fails closed: ``state_unreadable``)."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        body = json.loads(text) if isinstance(text, str) else None
        at = _time(body.get("at")) if isinstance(body, dict) else None
        listed = body.get("not_run") if isinstance(body, dict) else None
        watching = body.get("watching", []) if isinstance(body, dict) else None
        if at is None or not isinstance(listed, dict) or not isinstance(watching, list):
            return None
        stale = abs((now - at).total_seconds()) > SNAPSHOT_STALE_S
        known = {int(k) for k in listed} | {int(i) for i in watching}
        if stale:
            return dict.fromkeys(known, INDEX_EXITS_NOT_RUN)
        return {int(k): str(v) for k, v in listed.items()}
    except (ValueError, TypeError, AttributeError):
        return None


class ExitsPublisher:
    """The paper monitor's one write path of the index-exit report: which strategies have an armed index exit being
    evaluated (``watching``) and which do not (``not_run``, with the why). Never raises. Rewritten when it changes and
    at least every ``REFRESH_S`` so a stopped monitor ages out."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._written: str | None = None
        self._written_at: datetime.datetime | None = None

    async def publish(self, watching: Iterable[int], not_run: Mapping[int, str], now: datetime.datetime) -> bool:
        if self._client is None:
            return False
        body = json.loads(encode_exits(not_run, now))
        body["watching"] = sorted(set(watching) - set(not_run))
        fingerprint = json.dumps([body["not_run"], body["watching"]])
        due = self._written_at is None or (now - self._written_at).total_seconds() >= REFRESH_S
        if fingerprint == self._written and not due:
            return False
        try:
            await self._client.set(exits_key(), json.dumps(body, sort_keys=True))
        except Exception as exc:  # noqa: BLE001 - never stops the monitor; the report then ages out (= not run)
            log.warning("paper monitor: writing the index-exit report failed: %s", type(exc).__name__)
            return False
        self._written, self._written_at = fingerprint, now
        return True
