"""The background role's settings in memory (#636 round 4): the check path reads NO database for a setting.

Spec basis: REQ-167 AC-1 ("the value in force at a time is the newest row not after that time, else the default"),
REQ-167 AC-4 / REQ-166 AC-1 (a changed setting takes effect with no restart: here within ``LAG_SECONDS``, the SPEC
CHANGE proposed in #636), ADR-023 (the database clock decides "now" for a WRITE; a read here resolves against the
worker's own clock, as each check already reads its own clock).

How it works:
- ``refresh`` (own task, never on a check): reads ``count(*)`` of the insert-only ``app_settings``; when that count
  differs from the loaded one (or nothing is loaded yet) it reloads EVERY stored row through the store's own reader
  (``settings_store.history``: registry keys only, newest ``effective_from`` first; any key the registry holds, so a
  key added to the registry is served with no change here). The count is read BEFORE the rows: a row inserted between
  the two reads makes the next poll's count differ again (reloaded once more), never a row missed for good.
- ``at(now)``: the values in force at ``now`` resolved in memory (the store's rule: the newest row not after ``now``,
  else the registry default), so a future-dated value takes effect when the worker clock passes it with no read.

Answer states (each has a test in ``tests_app/test_background_settings_cache.py``):
- a stored row in force -> its value; an absent key, or only future rows -> the registry default;
- a row for a key the registry no longer holds -> ignored (the store's reader drops it), as today;
- a stored value the registry refuses (checked on LOAD, every row, future-dated ones included) -> the load fails
  closed: ``SettingsError``, the last good cache is kept (a refused future row therefore blocks a reload from the
  moment it is stored, not from its effective time: stricter than the per-request read, named here);
- empty table -> every key at its registry default (a loaded, valid cache);
- a failed count or reload -> the last good cache is kept and the failure is logged ONCE until a refresh succeeds;
- nothing loaded yet -> ``at`` raises ``SettingsError``: the caller refuses to check (never a silent default).

Connections: every refresh holds ``gate`` (the worker's one database gate, shared with its rebuild and its writer), so
the role opens at most one connection at a time (ADR-048 role limit of 5: API 2 + background 1 + feed 1).
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo import settings as registry_mod
from ofo.settings import SettingRefused
from sqlalchemy import text

from ofo_app import settings_store
from ofo_app.settings_store import SettingsError, StoredSetting

log = logging.getLogger("ofo_app.settings_cache")

#: how often the background role polls ``count(*)`` of ``app_settings`` (#636 design: 2-5 s)
POLL_SECONDS: Final = 2
#: the longest a stored change waits before a check uses it: one poll period plus one worker cycle (WAKE_SECONDS = 1)
LAG_SECONDS: Final = POLL_SECONDS + 1

_COUNT = text("SELECT count(*) FROM public.app_settings")

Connect = Callable[[], AbstractAsyncContextManager[Any]]


@dataclass(frozen=True)
class Loaded:
    """One good load: the row count it was read at, every stored row per registry key (newest first), the defaults."""

    count: int
    rows: Mapping[str, tuple[StoredSetting, ...]]
    defaults: Mapping[str, Decimal]


def check_rows(rows: Mapping[str, list[StoredSetting]]) -> dict[str, tuple[StoredSetting, ...]]:
    """The registry check of every stored row (as ``settings_store.rows_in_force`` does for the rows in force)."""
    known = registry_mod.registry()
    out: dict[str, tuple[StoredSetting, ...]] = {}
    for key, kept in rows.items():
        for r in kept:
            if not isinstance(r.value, Decimal):
                raise SettingsError(f"setting {key} did not come back as an exact Decimal")
            try:
                registry_mod.check_value(known[key], r.value)
            except SettingRefused as exc:
                raise SettingsError(
                    f"stored setting {key} = {r.value} is refused by the registry: {exc.reason}") from None
        out[key] = tuple(sorted(kept, key=lambda r: r.effective_from, reverse=True))
    return out


def resolve(loaded: Loaded, at: datetime.datetime) -> dict[str, Decimal]:
    """key -> value in force at ``at`` for every registry key: the newest row not after ``at``, else the default."""
    if not isinstance(at, datetime.datetime) or at.utcoffset() is None:
        raise SettingsError("the time asked about must be a timezone-aware datetime")
    values = dict(loaded.defaults)
    for key, rows in loaded.rows.items():
        for r in rows:  # newest first
            if r.effective_from <= at:
                values[key] = r.value
                break
    return values


class SettingsCache:
    """Every stored setting in memory, refreshed off the check path (module docstring)."""

    def __init__(self, connect: Connect, *, gate: asyncio.Lock | None = None,
                 poll_seconds: float = POLL_SECONDS,
                 sleep: Callable[[float], Any] = asyncio.sleep) -> None:
        self._connect, self.gate = connect, gate if gate is not None else asyncio.Lock()
        self.poll_seconds, self._sleep = poll_seconds, sleep
        self.loaded: Loaded | None = None
        self.failing = False  # a failure streak is logged once
        self.failures = 0
        self.loads = 0

    async def refresh(self) -> bool:
        """One poll: True when the cache was (re)loaded. Never raises (a failure keeps the last good cache)."""
        try:
            async with self.gate, self._connect() as conn:
                count = (await conn.execute(_COUNT)).scalar_one()
                if self.loaded is not None and count == self.loaded.count:
                    self.failing = False
                    return False
                rows = check_rows(await settings_store.history(conn))
            self.loaded = Loaded(count, rows, registry_mod.defaults())
            self.loads += 1
            self.failing = False
            return True
        except Exception:  # contained: the last good cache stays (none yet -> the worker refuses to check)
            self.failures += 1
            if not self.failing:
                log.exception("settings cache: the refresh failed; keeping the last good settings")
            self.failing = True
            return False

    def at(self, now: datetime.datetime) -> dict[str, Decimal]:
        """The settings in force at ``now`` from memory only; SettingsError when nothing has been loaded yet."""
        if self.loaded is None:
            raise SettingsError("no settings have been loaded yet")
        return resolve(self.loaded, now)

    async def poll_loop(self) -> None:
        """The refresh on its own task: every ``poll_seconds``, until cancelled."""
        while True:
            await self._sleep(self.poll_seconds)
            await self.refresh()
