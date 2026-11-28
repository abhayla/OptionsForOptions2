"""FD2 item 4: the worker's last stored reading of each rule's value, for the opportunity records (ADR-330 (58), (13)).

The worker (Lane FE's ``background.py``) calls ``publish`` once per check cycle with the value of every rule it
evaluated, in the same units as the record's ``value`` (rupees for a P&L rule, points for an index rule, per-unit
premium for a leg stop). The API reads it back with ``read``: ``now_value`` and ``now_as_of`` on each
``OpportunityOut``. Redis, the heartbeat's own store (no migration); written at most as often as the worker checks,
expiring after ``TTL_S`` so a dead worker's figures age out into "no reading" (null), never a stale number kept.

Answer states (``read``): nothing stored, unreadable JSON, a time with no zone, a value that is not a finite number ->
no reading for that entry (a bad entry is dropped alone); the whole snapshot unreadable -> ``{}``. Money is exact
Decimal, stored as text (ADR-008). Browsers never reach Redis (ADR-012): only this module and the route do.
"""
from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from redis.exceptions import RedisError

from ofo_app import feed_bus

log = logging.getLogger(__name__)

TTL_S: Final = 3600

Readings = dict[tuple[int, str], tuple[Decimal, datetime.datetime]]


def key() -> str:
    return f"{feed_bus.KEY_PREFIX}:background:rule_values"


async def publish(client: Any, values: Mapping[tuple[int, str], Decimal], at: datetime.datetime) -> None:
    """One snapshot: (strategy id, rule id) -> value, stamped with ``at`` (aware). A failure is the caller's to log."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("a rule reading time must carry a time zone")
    body = {"at": at.isoformat(), "values": {f"{sid}:{rule}": format(v, "f") for (sid, rule), v in values.items()}}
    await client.set(key(), json.dumps(body), ex=TTL_S)


def _decode(raw: Any) -> Readings:
    try:
        body = json.loads(raw)
        at = datetime.datetime.fromisoformat(body["at"])
        values = body["values"]
    except (TypeError, ValueError, KeyError):
        return {}
    if at.tzinfo is None or at.utcoffset() is None or not isinstance(values, dict):
        return {}
    out: Readings = {}
    for name, text in values.items():
        sid, _, rule = str(name).partition(":")
        try:
            value = Decimal(str(text))
            if not (sid.isascii() and sid.isdigit() and rule and value.is_finite()):
                continue
        except InvalidOperation:
            continue
        out[(int(sid), rule)] = (value, at)
    return out


async def read(client: Any, now: datetime.datetime) -> Readings:  # the time is kept for a freshness rule
    """Every stored reading, or ``{}`` when none is stored or the store cannot be read (the screens then show none)."""
    try:
        raw = await client.get(key())
    except (RedisError, OSError, TimeoutError) as exc:
        log.warning("rule readings could not be read: %s", type(exc).__name__)
        return {}
    return {} if raw is None else _decode(raw)
