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
import uuid
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
NO_BUS: Final = "no_bus"  # RA: the API runs without the bus (FEED_MODE unset or inprocess): no worker is knowable
STATE_UNREADABLE: Final = "state_unreadable"
NOT_LISTED: Final = "not_listed"
CLOCK_SKEW_S: Final = feed_bus.HEARTBEAT_SKEW_S  # how far ahead of the reader's clock a stamp may still be current
SNAPSHOT_STALE_S: Final = feed_bus.HEARTBEAT_STALE_S  # the same two minutes as the heartbeat (AC-6)
INDEX_NOT_LIVE: Final = "index_not_live"  # the ``why`` of a trade whose index exit has no live index reading
EXITS_NOT_CHECKED_YET: Final = "exits_not_checked_yet"  # the ``why`` when no monitor has written any report
INDEX_EXITS_NOT_RUN: Final = "index_exits_not_run"  # the ``why`` when the monitor's own snapshot stopped
INDEX_STALE_REASON: Final = "stale"  # the existing code and sentence (``monitoring_why_stale``); no new on-screen text
INDEX_READING_TTL_S: Final = 120
LEG_NOT_LIVE: Final = "leg_not_live"  # the ``why`` of a trade whose leg-price exit has no live leg reading
LEG_READING_MAX_AGE_S: Final = 90  # current while the worker re-reads (its tick key turns over every IST minute)
EXIT_NOT_APPLICABLE: Final = "exit_not_applicable"  # the why of a real position's old armed paper stop (ADR-330 (64))
BOOK_NOT_READ: Final = "book_not_read"  # the why when the monitor could not read the book for longer than allowed (FE3)
EXIT_NOT_PRICED: Final = "exit_not_priced"  # the why of a crossed exit that could not run (no live leg price)
MAX_READING_VALUE: Final = Decimal(10) ** 9  # no index or option price is this large: such a value is no reading
WATCH_FRESH_S: Final = 30  # a monitor's claim "I judge this exit" counts this long (it renews every ``REFRESH_S``)
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


#: the ``why`` codes that name their own sentence (``monitoring_why_<code>``); any other ``why`` (the worker's own free
#: text, e.g. a REST detail) is a detail, never a sentence key
SENTENCE_WHYS: Final = frozenset({INDEX_NOT_LIVE, LEG_NOT_LIVE, EXIT_NOT_PRICED, INDEX_EXITS_NOT_RUN,
                                  EXITS_NOT_CHECKED_YET, BOOK_NOT_READ, EXIT_NOT_APPLICABLE})
#: every ``reason`` a pause can carry (the worker's ``PriceState`` pauses and the reader's own)
SENTENCE_REASONS: Final = frozenset({WORKERS_DOWN, NO_BUS, STATE_UNREADABLE, NOT_LISTED, "stale", "disconnected",
                                     "leg_missing", "check_failed", "market_closed", "expiry_kind_unknown",
                                     "user_paused"})


def sentence_code(entry: Entry) -> str:
    """The one place that picks which catalogue sentence (``monitoring_why_<code>``) a paused entry reads (review N2).
    The monitor's specific ``why`` wins over the generic reason it rides on (``stale`` + ``index_not_live``); else the
    worker's reason; anything else is ``unknown`` (a plain fallback, never blank, never another reason's)"""
    if entry.why in SENTENCE_WHYS:
        return entry.why
    return entry.reason if entry.reason in SENTENCE_REASONS else "unknown"


def _current(at: datetime.datetime, now: datetime.datetime) -> bool:
    """FE2 #879: a stamp is current when it is at most ``SNAPSHOT_STALE_S`` old and at most ``CLOCK_SKEW_S`` ahead of
    the reader's clock. One-sided: a writer whose clock runs 100 s ahead must not stretch the two-minute window to 220 s
    (a reading from the future is not a live one)."""
    return -CLOCK_SKEW_S <= (now - at).total_seconds() <= SNAPSHOT_STALE_S


def _aware(at: datetime.datetime) -> datetime.datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("a monitoring time must carry a time zone")
    return at


def _row(e: Entry) -> dict[str, Any]:
    return {"status": e.status, "reason": e.reason, "why": e.why,
            "since": None if e.since is None else _aware(e.since).isoformat()}


def encode(entries: Iterable[Entry], at: datetime.datetime,
           readings: Mapping[str, tuple[IndexReading, datetime.datetime]] | None = None,
           kept: Iterable[Entry] = (), market_open: bool | None = None) -> str:
    """The snapshot. ``readings`` (Lane FE): slot ("index:NIFTY", "leg:<instrument id>") -> (the reading, when the
    worker last noted it): the prices a trade was called watched on travel in the SAME write as that call.
    ``kept`` (Lane FE3 item 4, issue 880): the pause starts of trades paused before a restart that the new worker has
    not answered for yet. They are NOT strategies of this snapshot (a reader never sees them: such a trade reads
    "not listed"); a second restart reads them back, so the "since" of a pause survives any number of restarts."""
    body = {"at": _aware(at).isoformat(), "strategies": {str(e.strategy_id): _row(e) for e in entries},
            "kept": {str(e.strategy_id): _row(e) for e in kept},
            "readings": {slot: _reading_body(r, noted) for slot, (r, noted) in sorted((readings or {}).items())}}
    if market_open is not None:  # Lane B1b item 6: the worker's market answer AT ``at`` (the one clock)
        body["market_open"] = market_open
    return json.dumps(body, sort_keys=True)


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
    if at is None or not _current(at, now):
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


RESTORE_MAX_AGE_S: Final = 86400  # a stored snapshot older than this says nothing a restart should keep


def _entries_of(raw: Any, now: datetime.datetime) -> dict[int, Entry]:
    """The PAUSED entries of an old snapshot for their ``since`` only (no reader freshness rule; an active trade was
    not watched while the worker was down, so its ``since`` starts again): {} when it is missing, not our shape or
    older than ``RESTORE_MAX_AGE_S``."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        body = json.loads(text) if isinstance(text, str) else None
        at = _time(body.get("at")) if isinstance(body, dict) else None
        rows = body.get("strategies") if isinstance(body, dict) else None
        if at is None or not isinstance(rows, dict) or abs((now - at).total_seconds()) > RESTORE_MAX_AGE_S:
            return {}
        out: dict[int, Entry] = {}
        kept = body.get("kept")
        for group in (kept if isinstance(kept, dict) else {}, rows):  # the snapshot's own rows win over a kept one
            for sid_text, row in group.items():
                since = _time(row.get("since"))
                if row.get("status") == PAUSED and isinstance(row.get("reason"), str) and since is not None:
                    out[int(sid_text)] = Entry(int(sid_text), row["status"], row["reason"], str(row.get("why", "")),
                                               since)
        return out
    except (ValueError, TypeError, AttributeError):
        return {}


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
        self._kept: dict[int, Entry] = {}  # FE3 item 4: restored paused entries no check has answered for yet
        self._restored_at: datetime.datetime | None = None
        self.restore_pending = False  # FE3 item 3 (F6): the restart's empty snapshot was not written; tried again
        self._read_pending = False  # ... or the old snapshot could not be read
        self._written: str | None = None
        self._written_at: datetime.datetime | None = None

    async def restore(self, now: datetime.datetime) -> bool:
        """A worker's start (FE2 item 4, REQ-165 AC-6): the dead worker's answers must not stand as this one's. Keeps
        each strategy's ``since`` (while its status and reason stay the same the pause is the same pause) and writes a
        snapshot that names NO strategy, so every trade reads paused (``not_listed``) until its first check has run.
        A snapshot older than ``RESTORE_MAX_AGE_S``, of another shape, or a store that cannot answer restores nothing.
        Never raises. True when the empty snapshot was written."""
        if self._client is None:
            return False
        try:
            raw = await self._client.get(key())
        except Exception as exc:  # noqa: BLE001 - nothing known to keep yet; tried again (review F6)
            log.warning("background: reading the old monitoring state failed: %s", type(exc).__name__)
            self.restore_pending, self._read_pending = True, True
            return False
        self._read_pending = False
        self._previous = _entries_of(raw, now)
        self._kept, self._restored_at = dict(self._previous), now
        return await self._write_restart_snapshot(now)

    def forget_unlisted(self, listed: Iterable[int]) -> list[int]:
        """Lane RA2 item 3 (F8): after a SUCCESSFUL read of the strategy list, a kept pause start of a strategy that
        is not in it (the trade was deleted while the worker was down) is dropped, so an id listed later never shows
        the old "since". The caller never asks after a failed read (a failed read names nobody, so it would drop
        every kept start). Returns the ids dropped."""
        keep = set(listed)
        dropped = sorted(set(self._kept) - keep)
        for sid in dropped:
            self._kept.pop(sid, None)
            self._previous.pop(sid, None)
        return dropped

    async def retry_restore(self, now: datetime.datetime) -> bool:
        """FE3 item 3 (F6): a restart whose empty snapshot could not be written leaves the dead worker's answers
        standing; the worker calls this before every cycle until the write has landed (or a real snapshot has).
        Nothing is read again: the kept starts are the ones the restart read. Never raises."""
        if not self.restore_pending or self._client is None:
            return False
        if self._read_pending:  # the old snapshot could not be READ at the start: read it (and write) again
            return await self.restore(now)
        return await self._write_restart_snapshot(now)

    async def _write_restart_snapshot(self, now: datetime.datetime) -> bool:
        try:
            await self._client.set(key(), encode([], now, kept=self._kept.values()), ex=SNAPSHOT_STALE_S)
        except Exception as exc:  # noqa: BLE001 - the old snapshot then ages out by itself (``SNAPSHOT_STALE_S``)
            log.warning("background: writing the restart monitoring state failed: %s", type(exc).__name__)
            self.restore_pending = True
            return False
        self.restore_pending = False
        self._written, self._written_at = None, None  # the first real snapshot is written whatever it says
        return True

    async def publish(self, status: Mapping[int, Any], reasons: Mapping[int, Any], whys: Mapping[int, str],  # noqa: PLR0913
                      now: datetime.datetime,
                      readings: Mapping[str, tuple[IndexReading, datetime.datetime]] | None = None,
                      market_open: bool | None = None) -> bool:
        """True when a snapshot was written."""
        if self._client is None:
            return False
        entries = snapshot(status, reasons, whys, self._previous, now)
        answered = {e.strategy_id for e in entries}
        if self._restored_at is not None and (now - self._restored_at).total_seconds() > RESTORE_MAX_AGE_S:
            self._kept = {}  # a restored pause no check has answered for in a day is not carried any longer
        kept = {sid: e for sid, e in self._kept.items() if sid not in answered}  # FE3 item 4: not forgotten unseen
        seen = [(k, str(r.value), r.at.isoformat(), r.source) for k, (r, _n) in sorted((readings or {}).items())]
        fingerprint = json.dumps([[(e.strategy_id, e.status, e.reason, e.why) for e in entries], seen, market_open])
        due = self._written_at is None or (now - self._written_at).total_seconds() >= REFRESH_S
        if fingerprint == self._written and not due:
            return False
        try:
            await self._client.set(key(), encode(entries, now, readings, kept.values(), market_open),
                                    ex=SNAPSHOT_STALE_S)
        except Exception as exc:  # noqa: BLE001 - never stops a cycle; the reader then sees an old snapshot
            log.warning("background: writing the monitoring state failed: %s", type(exc).__name__)
            return False
        self._kept = kept
        self.restore_pending = False  # a real snapshot replaced the old one: nothing is left to retry
        self._previous = {**kept, **{e.strategy_id: e for e in entries}}
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
        raw = await read_exits_raw(client)
    except Exception as exc:  # noqa: BLE001 - a store that cannot answer cannot clear a trade with an exit
        log.warning("monitoring state: the index-exit report could not be read: %s", type(exc).__name__)
        return {i: _paused_unreadable(e) for i, e in answers.items()}
    if raw is None:  # no monitor has written a report: the exits have not been checked yet, never assumed good
        return {i: e if e.status != ACTIVE else Entry(i, PAUSED, INDEX_STALE_REASON, EXITS_NOT_CHECKED_YET, e.since)
                for i, e in answers.items()}
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


def _text(value: Any) -> Any:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


async def read_exits_raw(client: Any) -> str | None:
    """The stored index-exit report as one JSON text (``decode_exits`` reads it), or None when no monitor has written
    one. A client with hashes (every Redis client) reads the monitors' slots from ``exit_slots_key``; a bare get/set
    double (a test's) reads the one string key. Raises when the store cannot answer."""
    if not hasattr(client, "hgetall"):
        return _text(await client.get(exits_key()))
    fields = await client.hgetall(exit_slots_key())
    if not fields:
        return None
    owners: dict[str, Any] = {}
    for owner, raw in fields.items():
        try:
            owners[str(_text(owner))] = json.loads(_text(raw))
        except (ValueError, TypeError):
            owners[str(_text(owner))] = None  # one bad slot is skipped by ``_slots``
    return json.dumps({"owners": owners})


def _paused_unreadable(entry: Entry) -> Entry:
    return entry if entry.status != ACTIVE else Entry(entry.strategy_id, PAUSED, STATE_UNREADABLE, "", None)


# ---- the index reading (worker -> monitor) and the index-exit report (monitor -> read_states) -----------------------

def exits_key() -> str:
    return f"{feed_bus.KEY_PREFIX}:background:index_exits"


def exit_slots_key() -> str:
    """Lane FE3 item 3: the monitors' slots as ONE Redis hash, one field per monitor. A field is written by its own
    monitor alone and by one atomic command (``HSET``), so two monitors writing in the same instant can never drop each
    other's slot (the old key was one string, read-merged-written). A new name: the old key is a string, and
    ``HSET`` on it would answer WRONGTYPE until it expired."""
    return f"{feed_bus.KEY_PREFIX}:background:index_exit_slots"


@dataclass(frozen=True)
class IndexReading:
    """One index value, the time of its quote, and its source: "feed" (a tick) or "rest" (the stand-in)."""
    underlying: str
    value: Decimal
    at: datetime.datetime
    source: str


def _reading_body(reading: IndexReading, noted: datetime.datetime) -> dict[str, str]:
    return {"underlying": reading.underlying, "value": str(reading.value), "at": _aware(reading.at).isoformat(),
            "source": reading.source, "published": _aware(noted).isoformat()}


FUTURE_SKEW: Final = datetime.timedelta(seconds=2)


def reading_from(body: Any, now: datetime.datetime, max_age: datetime.timedelta | None,
                 noted_max_s: float, expect: str) -> IndexReading | None:
    """One stored reading, or None: not our shape, no time zone, a quote older than ``max_age`` (the one index age rule;
    None for an option leg, whose quote is current while the feed is, however long ago it last changed), a quote from
    the future, one the worker noted more than ``noted_max_s`` ago (it stopped re-reading), a value that is not a
    plausible price, or a reading of another instrument than ``expect``."""
    try:
        value = Decimal(body["value"]) if isinstance(body, dict) and isinstance(body.get("value"), str) else None
    except (InvalidOperation, ValueError):
        return None
    if value is None or not value.is_finite() or not 0 < value < MAX_READING_VALUE \
            or body.get("source") not in ("feed", "rest") or body.get("underlying") != expect:
        return None
    at, noted = _time(body.get("at")), _time(body.get("published"))
    if at is None or noted is None:
        return None
    if (max_age is not None and now - at > max_age) or at - now > FUTURE_SKEW \
            or abs((now - noted).total_seconds()) > noted_max_s:
        return None
    return IndexReading(expect, value, at, body["source"])


@dataclass(frozen=True)
class Readings:
    """The prices in the worker's last snapshot, one read per monitor pass (``read_readings``)."""
    items: Mapping[str, Any]

    def index(self, underlying: str, now: datetime.datetime, max_age: datetime.timedelta) -> IndexReading | None:
        """The index value the worker used for ``underlying``: the quote within ``max_age``, noted within 120 s."""
        return reading_from(self.items.get(f"index:{underlying}"), now, max_age, INDEX_READING_TTL_S, underlying)

    def leg(self, instrument_id: str, now: datetime.datetime) -> IndexReading | None:
        """The price the worker used for one option leg: current while the worker keeps re-reading it."""
        return reading_from(self.items.get(f"leg:{instrument_id}"), now, None, LEG_READING_MAX_AGE_S, instrument_id)


async def read_readings(client: Any, now: datetime.datetime) -> Readings | None:
    """The monitor's one read of the worker's prices: the snapshot's own ``readings``. Never raises; None = no usable
    snapshot (missing, unreadable, old: the caller judges nothing from the worker and says so)."""
    if client is None:
        return None
    try:
        raw = await client.get(key())
    except Exception as exc:  # noqa: BLE001 - a store that cannot answer gives no reading
        log.warning("paper monitor: the worker's readings could not be read: %s", type(exc).__name__)
        return None
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        body = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
    at = _time(body.get("at")) if isinstance(body, dict) else None
    items = body.get("readings") if isinstance(body, dict) else None
    if at is None or not _current(at, now) or not isinstance(items, dict):
        return None
    return Readings(items)


MARKET_CLOCK_MAX_AGE_S: Final = 120  # the worker's market answer is used by the monitor only while this young


async def read_market_open(client: Any, now: datetime.datetime) -> bool | None:
    """Lane B1b item 6 (FE4 F7, RA2's design): the worker's market-open answer from its snapshot, AT the snapshot's own
    instant, when the snapshot is under ``MARKET_CLOCK_MAX_AGE_S`` old; None (the reader uses its own clock) when the
    snapshot is missing, unreadable, not carrying the field, old or ahead of ``now``. Never raises."""
    if client is None:
        return None
    try:
        raw = await client.get(key())
    except Exception as exc:  # noqa: BLE001 - a store that cannot answer gives no clock
        log.warning("paper monitor: the worker's market answer could not be read: %s", type(exc).__name__)
        return None
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        body = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
    at = _time(body.get("at")) if isinstance(body, dict) else None
    answer = body.get("market_open") if isinstance(body, dict) else None
    if at is None or not isinstance(answer, bool) or not _current(at, now):
        return None
    return answer if 0 <= (now - at).total_seconds() <= MARKET_CLOCK_MAX_AGE_S else None


WRITE_TRIES: Final = 3  # a report write is verified and repeated this often at most (two writers can cross)
OWNER_KEEP_S: Final = 3600  # a monitor's slot that stopped reporting this long ago is dropped by the next writer
#: The report key's expiry, renewed by EVERY write (a monitor writes at least every ``REFRESH_S`` while it runs, so the
#: key lives while any monitor does, and a day of no write at all leaves nothing to read: "not checked yet").
EXITS_KEY_TTL_S: Final = 86400


def encode_exits(not_run: Mapping[int, str], at: datetime.datetime) -> str:
    """One monitor's slot of the report (``watching`` is added by ``ExitsPublisher``)."""
    return json.dumps({"at": _aware(at).isoformat(), "not_run": {str(k): v for k, v in sorted(not_run.items())}},
                      sort_keys=True)


def _slots(body: Any) -> dict[str, dict[str, Any]] | None:
    """The monitors' slots of a stored report (FE2 item 1: one slot per monitor, never one shared answer), or None
    when it is not our shape."""
    owners = body.get("owners") if isinstance(body, dict) else None
    if not isinstance(owners, dict):
        return None
    out: dict[str, dict[str, Any]] = {}
    for owner, slot in owners.items():
        at = _time(slot.get("at")) if isinstance(slot, dict) else None
        if at is None or not isinstance(slot.get("not_run"), dict) or not isinstance(slot.get("watching"), list):
            continue  # one bad slot is skipped (it claims nothing); a report with no good slot is unreadable below
        out[str(owner)] = {"at": at, "not_run": slot["not_run"], "watching": slot["watching"]}
    return out


def decode_exits(raw: Any, now: datetime.datetime) -> dict[int, str] | None:
    """strategy -> why, merged over every monitor's slot; None = not our shape (the caller fails closed:
    ``state_unreadable``). A strategy is judged (absent from the answer) when at least one FRESH monitor lists it as
    being evaluated; otherwise the why of a fresh monitor that lists it as not run; with no fresh monitor at all (every
    one stopped: older than ``SNAPSHOT_STALE_S``) every strategy any of them listed is ``INDEX_EXITS_NOT_RUN``. A
    stopped monitor's slot is ignored while a fresh monitor exists (a restart is a new monitor)."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        body = json.loads(text) if isinstance(text, str) else None
        slots = _slots(body)
        if not slots:  # not our shape, or no readable slot at all: a report that claims nothing clears nothing
            return None
        fresh = {o: sl for o, sl in slots.items() if _current(sl["at"], now)}
        if not fresh:
            return dict.fromkeys({int(k) for sl in slots.values() for k in (*sl["not_run"], *sl["watching"])},
                                 INDEX_EXITS_NOT_RUN)
        now_claims = {o: sl for o, sl in fresh.items() if (now - sl["at"]).total_seconds() <= WATCH_FRESH_S}
        covered = {int(i) for sl in now_claims.values() for i in sl["watching"]}
        out: dict[int, str] = {}
        for owner in sorted(fresh):  # review F1: a claim nobody renewed lately is not a claim (a restart, a crash)
            for k, why in fresh[owner]["not_run"].items():
                if int(k) not in covered:
                    out.setdefault(int(k), str(why))
            for k in fresh[owner]["watching"]:
                if int(k) not in covered:
                    out.setdefault(int(k), INDEX_EXITS_NOT_RUN)
        return out
    except (ValueError, TypeError, AttributeError):
        return None


#: Lane RA2 item 3 (F7): HDEL each (field, text) pair only when the field still holds that exact text (one atomic step)
_DELETE_IF_UNCHANGED = (
    "local n = 0 "
    "for i = 1, #ARGV, 2 do "
    "if redis.call('HGET', KEYS[1], ARGV[i]) == ARGV[i + 1] then n = n + redis.call('HDEL', KEYS[1], ARGV[i]) end "
    "end return n")


class ExitsPublisher:
    """The paper monitor's one write path of the index-exit report: which strategies have an armed index exit being
    evaluated (``watching``) and which do not (``not_run``, with the why). Every monitor (every API worker process)
    owns ONE slot of the report (one field of a Redis hash, written by one atomic ``HSET``: FE3 item 3, so two monitors
    writing in the same instant cannot drop each other's slot), and the key's expiry is renewed by every write. Never
    raises.
    Rewritten when it changes and at least every ``REFRESH_S`` so a stopped monitor ages out."""

    def __init__(self, client: Any, owner: str | None = None) -> None:
        self._client = client
        self.owner = owner or uuid.uuid4().hex
        self._written: str | None = None
        self._written_at: datetime.datetime | None = None

    async def publish(self, watching: Iterable[int], not_run: Mapping[int, str], now: datetime.datetime) -> bool:
        if self._client is None:
            return False
        slot = json.loads(encode_exits(not_run, now))
        slot["watching"] = sorted(set(watching) - set(not_run))
        fingerprint = json.dumps([slot["not_run"], slot["watching"]])
        due = self._written_at is None or (now - self._written_at).total_seconds() >= REFRESH_S
        if fingerprint == self._written and not due:
            return False
        try:
            kept = False
            for _ in range(WRITE_TRIES):  # the slot is verified, and written again when a store did not keep it
                if hasattr(self._client, "hset"):
                    kept = await self._write_field(slot, now)
                else:  # a bare get/set double: the one string key, read-merge-written (no second writer there)
                    owners = await self._others(now)
                    owners[self.owner] = slot
                    await self._client.set(exits_key(),
                                           json.dumps({"at": slot["at"], "owners": owners}, sort_keys=True),
                                           ex=EXITS_KEY_TTL_S)
                    kept = await self._has_slot(slot["at"])
                if kept:
                    break
        except Exception as exc:  # noqa: BLE001 - never stops the monitor; the report then ages out (= not run)
            log.warning("paper monitor: writing the index-exit report failed: %s", type(exc).__name__)
            return False
        if not kept:  # a store that never kept the slot: not recorded as written, so the next pass writes again
            log.warning("paper monitor: the index-exit report lost this monitor's slot %d times", WRITE_TRIES)
            return False
        self._written, self._written_at = fingerprint, now
        return True

    async def _write_field(self, slot: dict[str, Any], now: datetime.datetime) -> bool:
        """FE3 item 3: this monitor's field of the hash, by one atomic ``HSET`` (nobody else writes it, nobody's write
        can drop it); the key's expiry is renewed by the same write; the slots of monitors gone for ``OWNER_KEEP_S``
        are removed (a live monitor's slot is never that old, so this cannot remove a slot in use). True when the
        stored field is the slot just written."""
        text = json.dumps(slot, sort_keys=True)
        await self._client.hset(exit_slots_key(), self.owner, text)
        await self._client.expire(exit_slots_key(), EXITS_KEY_TTL_S)
        fields = await self._client.hgetall(exit_slots_key())
        gone = []
        mine = None
        for owner, raw in fields.items():
            name = str(_text(owner))
            if name == self.owner:
                mine = _text(raw)
                continue
            try:
                at = _time(json.loads(_text(raw)).get("at"))
            except (ValueError, TypeError, AttributeError):
                at = None
            if at is None or abs((now - at).total_seconds()) > OWNER_KEEP_S:
                gone.append(owner)
        if gone:
            await self._remove_dead(gone, fields)
        return mine == text

    async def _remove_dead(self, gone: list[Any], fields: Mapping[Any, Any]) -> None:
        """Lane RA2 item 3 (F7): one atomic step when the client runs scripts: a field is deleted only if it still holds
        the exact text that was judged long dead, so a monitor that wrote a fresh slot between our read and this delete
        keeps it. A client with no ``eval`` (the bare test doubles) keeps the two-step delete."""
        if not hasattr(self._client, "eval"):
            await self._client.hdel(exit_slots_key(), *gone)
            return
        args: list[Any] = []
        for owner in gone:
            args.extend((owner, fields[owner]))
        await self._client.eval(_DELETE_IF_UNCHANGED, 1, exit_slots_key(), *args)

    async def _has_slot(self, at_text: str) -> bool:
        """Whether the stored report holds this monitor's slot as just written."""
        raw = await self._client.get(exits_key())
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        try:
            found = (json.loads(text).get("owners") or {}).get(self.owner) if isinstance(text, str) else None
        except (ValueError, AttributeError):
            return False
        return isinstance(found, dict) and found.get("at") == at_text

    async def _others(self, now: datetime.datetime) -> dict[str, Any]:
        """The other monitors' slots as stored (those that stopped over ``OWNER_KEEP_S`` ago are dropped). A stored
        value that is not our shape is replaced; a store that cannot answer raises (nothing is written blind)."""
        raw = await self._client.get(exits_key())
        if raw is None:
            return {}
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        try:
            slots = _slots(json.loads(text) if isinstance(text, str) else None)
        except ValueError:
            slots = None
        return {o: {"at": sl["at"].isoformat(), "not_run": sl["not_run"], "watching": sl["watching"]}
                for o, sl in (slots or {}).items()
                if o != self.owner and abs((now - sl["at"]).total_seconds()) <= OWNER_KEEP_S}
