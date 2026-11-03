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
- only the row IN FORCE per key is checked against the registry (#636 r5 finding 1; as
  ``settings_store.rows_in_force`` checks only the rows in force): the check runs once per row on load and is kept
  with it, so ``at`` does no registry work per check. A replaced row (older than the one in force) or a future row
  the registry refuses never fails a load (the table is insert-only: a replaced bad row can never be removed, so
  failing on it would stop every reload for good). A refused row IN FORCE -> that key falls back to its registry
  default, logged once per row with the key, the value and the reason (never the refused value);
- empty table -> every key at its registry default (a loaded, valid cache);
- a failed count or reload -> the last good cache is kept and the failure is logged ONCE until a refresh succeeds;
- nothing loaded yet -> ``at`` raises ``SettingsError``: the caller refuses to check (never a silent default).

Lag (#636 r5 finding 4): a change reaches a check within one poll period + the poll's wait for ``gate`` + one cycle;
``LAG_SECONDS`` states it with the gate wait at its budget, ``lag_seconds()`` with the longest wait measured.

Connections: every refresh holds ``gate`` (the worker's one database gate, shared with its rebuild and its writer), so
the role opens at most one connection at a time (ADR-048 role limit of 5: API 2 + background 1 + feed 1).
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import time
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
#: the longest the poll is expected to wait for the role's one database gate (held by the rebuild's list and gate
#: reads, by the writer, by itself); a longer wait is measured, logged and counted in ``lag_seconds`` (#636 r5)
GATE_WAIT_BUDGET_SECONDS: Final = 2
#: the longest a stored change waits before a check uses it: one poll period, plus the poll's wait for the shared
#: database gate (its budget), plus one worker cycle (WAKE_SECONDS = 1). #636 r5 finding 4: round 4's figure (poll +
#: cycle = 3 s) left the gate wait out. The figure measured per refresh is ``SettingsCache.lag_seconds``.
LAG_SECONDS: Final = POLL_SECONDS + GATE_WAIT_BUDGET_SECONDS + 1
WAKE_SECONDS: Final = 1

_COUNT = text("SELECT count(*) FROM public.app_settings")

Connect = Callable[[], AbstractAsyncContextManager[Any]]


@dataclass(frozen=True)
class Checked:
    """One stored row with its registry answer: ``refused`` is None for a valid value, else the reason."""

    row: StoredSetting
    refused: str | None


@dataclass(frozen=True)
class Loaded:
    """One good load: the row count it was read at, every stored row per registry key (newest first, each with its
    registry answer), the defaults."""

    count: int
    rows: Mapping[str, tuple[Checked, ...]]
    defaults: Mapping[str, Decimal]


def _refusal(spec: Any, value: Any) -> str | None:
    if not isinstance(value, Decimal):
        return "not an exact Decimal"
    try:
        registry_mod.check_value(spec, value)
    except SettingRefused as exc:
        return str(exc.reason)
    return None


def check_rows(rows: Mapping[str, list[StoredSetting]]) -> dict[str, tuple[Checked, ...]]:
    """Every stored row per key, newest first, with its registry answer. Never raises for a refused value: whether
    it matters is decided by ``resolve`` for the row in force only (#636 r5 finding 1)."""
    known = registry_mod.registry()
    out: dict[str, tuple[Checked, ...]] = {}
    for key, kept in rows.items():
        ordered = sorted(kept, key=lambda r: r.effective_from, reverse=True)
        out[key] = tuple(Checked(r, _refusal(known[key], r.value)) for r in ordered)
    return out


def resolve(loaded: Loaded, at: datetime.datetime,
            refused: Callable[[str, Checked], None] | None = None) -> dict[str, Decimal]:
    """key -> value in force at ``at`` for every registry key: the newest row not after ``at``, else the default.
    A row in force the registry refuses -> the key's registry default (``refused(key, row)`` is told); rows it
    replaced are never looked at."""
    if not isinstance(at, datetime.datetime) or at.utcoffset() is None:
        raise SettingsError("the time asked about must be a timezone-aware datetime")
    values = dict(loaded.defaults)
    for key, rows in loaded.rows.items():
        for c in rows:  # newest first
            if c.row.effective_from <= at:
                if c.refused is None:
                    values[key] = c.row.value
                elif refused is not None:
                    refused(key, c)
                break
    return values


class SettingsCache:
    """Every stored setting in memory, refreshed off the check path (module docstring)."""

    def __init__(self, connect: Connect, *, gate: asyncio.Lock | None = None,
                 poll_seconds: float = POLL_SECONDS,
                 sleep: Callable[[float], Any] = asyncio.sleep,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._connect, self.gate = connect, gate if gate is not None else asyncio.Lock()
        self.poll_seconds, self._sleep, self._monotonic = poll_seconds, sleep, monotonic
        self.gate_wait = 0.0  # the last refresh's wait for the shared gate, seconds (float-ok: a duration measure)
        self.gate_wait_max = 0.0  # the longest such wait this process
        self.loaded: Loaded | None = None
        self.failing = False  # a failure streak is logged once
        self.failures = 0
        self.loads = 0
        self._logged: set[tuple[str, datetime.datetime, Any]] = set()  # refused rows in force already logged

    async def refresh(self) -> bool:
        """One poll: True when the cache was (re)loaded. Never raises (a failure keeps the last good cache)."""
        try:
            asked = self._monotonic()
            async with self.gate:
                self._waited(self._monotonic() - asked)
                async with self._connect() as conn:
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

    def _waited(self, seconds: float) -> None:
        self.gate_wait = seconds
        self.gate_wait_max = max(self.gate_wait_max, seconds)
        if seconds > GATE_WAIT_BUDGET_SECONDS:
            log.warning("settings cache: the poll waited %.1f s for the database gate (budget %s s); a stored change "
                        "can take %.1f s to reach a check", seconds, GATE_WAIT_BUDGET_SECONDS,
                        self.poll_seconds + seconds + WAKE_SECONDS)

    def lag_seconds(self) -> float:
        """The measured bound on a change reaching a check: poll period + the longest gate wait seen + one cycle."""
        return self.poll_seconds + max(self.gate_wait_max, 0.0) + WAKE_SECONDS

    def at(self, now: datetime.datetime) -> dict[str, Decimal]:
        """The settings in force at ``now`` from memory only; SettingsError when nothing has been loaded yet."""
        if self.loaded is None:
            raise SettingsError("no settings have been loaded yet")
        return resolve(self.loaded, now, self._refused_in_force)

    def _refused_in_force(self, key: str, c: Checked) -> None:
        mark = (key, c.row.effective_from, c.row.value)
        if mark not in self._logged:
            self._logged.add(mark)
            log.error("settings cache: stored setting %s (from %s) is refused by the registry (%s); the registry "
                      "default %s is used", key, c.row.effective_from, c.refused, self.loaded.defaults.get(key)
                      if self.loaded is not None else None)

    async def poll_loop(self) -> None:
        """The refresh on its own task: every ``poll_seconds``, until cancelled."""
        while True:
            await self._sleep(self.poll_seconds)
            await self.refresh()
