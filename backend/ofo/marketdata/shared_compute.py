"""Market-wide figures computed once per feed snapshot and served to every reader of that feed (REQ-050 AC-1, AC-3).

ADR-053 (V1): live prices come through each user's OWN Zerodha feed and one user's feed never drives another user's
screen (F-23). So the feed owner is part of every key: two users' feeds never share an entry, even with identical data.
Sharing across users waits for a licensed vendor feed (REQ-052 AC-5), which is not built.

The key is an allow-list (:class:`SharedKey`): feed owner, underlying, expiry, snapshot instant, the figure's name, the
contract and the exact inputs the figure is computed from. The inputs are in the key so a stale or poisoned entry can
never answer a different input: an entry is only ever read back for the very inputs it was computed from.

Behaviour (each has a test):

- one computation per key; concurrent first requests for one key are coalesced (the others wait for the one result);
- a slow computation for one key does not block reads or computations of other keys (a lock per key, never a global one
  held while computing);
- a computation that raises is not cached, affects no other key, and the next request computes again;
- memory is bounded: a newer snapshot instant of a feed evicts that feed's older entries, and a hard cap evicts the
  oldest entries of all;
- per-strategy modules (P&L, risk, rules) never import this module (``tests/marketdata/test_scale_classes.py``).

Standard library only.
"""
from __future__ import annotations

import datetime
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Final, TypeVar

T = TypeVar("T")

DEFAULT_MAX_ENTRIES: Final = 20_000


@dataclass(frozen=True)
class SharedKey:
    """The only way to address a shared entry; every field is validated, so no key exists without its owner."""

    feed_owner: str
    underlying: str
    expiry: datetime.date | None
    instant: datetime.datetime
    figure: str
    instrument_id: str | None
    inputs: tuple[Hashable, ...]

    def __post_init__(self) -> None:
        for name in ("feed_owner", "underlying", "figure"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string, got {value!r}")
        if self.expiry is not None and not isinstance(self.expiry, datetime.date):
            raise ValueError(f"expiry must be a date or None, got {self.expiry!r}")
        if not isinstance(self.instant, datetime.datetime) or self.instant.tzinfo is None:
            raise ValueError(f"instant must be a timezone-aware datetime, got {self.instant!r}")
        if self.instrument_id is not None and not isinstance(self.instrument_id, str):
            raise ValueError(f"instrument_id must be a string or None, got {self.instrument_id!r}")
        if not isinstance(self.inputs, tuple):
            raise ValueError(f"inputs must be a tuple, got {self.inputs!r}")
        hash(self.inputs)  # an unhashable input fails here, not inside the cache

    @property
    def feed(self) -> tuple[str, str]:
        return (self.feed_owner, self.underlying)


@dataclass(frozen=True)
class FeedScope:
    """One user's feed: the shared cache plus the feed's owner. Every key made through it carries the owner (ADR-053),
    so a caller cannot reach the cache without saying whose feed it is."""

    cache: SharedCompute
    feed_owner: str

    def __post_init__(self) -> None:
        if not isinstance(self.cache, SharedCompute):
            raise ValueError(f"cache must be a SharedCompute, got {self.cache!r}")
        if not isinstance(self.feed_owner, str) or not self.feed_owner.strip():
            raise ValueError("a shared cache needs the feed owner: one user's feed never serves another's (ADR-053)")

    def compute(self, scope: tuple, inputs: tuple, compute: Callable[[], T]) -> T:
        """``scope`` is (underlying, expiry, instant, figure, instrument_id); the result is computed once per key."""
        underlying, expiry, instant, figure, instrument_id = scope
        key = SharedKey(self.feed_owner, underlying, expiry, instant, figure, instrument_id, inputs)
        return self.cache.get_or_compute(key, compute)


class _Slot:
    __slots__ = ("done", "lock", "value")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.done = False
        self.value: object = None


class SharedCompute:
    """A bounded cache of market-wide results with one computation per key."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if not isinstance(max_entries, int) or max_entries < 1:
            raise ValueError(f"max_entries must be a positive int, got {max_entries!r}")
        self._max = max_entries
        self._guard = threading.Lock()  # protects the maps only; never held while a computation runs
        self._slots: OrderedDict[SharedKey, _Slot] = OrderedDict()
        self._newest: dict[tuple[str, str], datetime.datetime] = {}
        self.computations = 0  # how many times a computation actually ran (the proof counter)

    def __len__(self) -> int:
        with self._guard:
            return len(self._slots)

    def get_or_compute(self, key: SharedKey, compute: Callable[[], T]) -> T:
        """The result for ``key``, computing it once; a deterministic "no answer" must be returned as a value, because
        an exception is never cached."""
        if not isinstance(key, SharedKey):
            raise ValueError(f"key must be a SharedKey, got {key!r}")
        with self._guard:
            newest = self._newest.get(key.feed)
            if newest is not None and key.instant < newest:
                slot = None  # an older snapshot than the feed's newest: compute, keep nothing
            else:
                slot = self._slots.get(key)
                if slot is None:
                    slot = self._slots[key] = _Slot()
                    self._advance(key)
        if slot is None:
            return self._run(compute)
        with slot.lock:
            if slot.done:
                return slot.value  # type: ignore[return-value]
            try:
                value = self._run(compute)
            except BaseException:
                with self._guard:
                    if self._slots.get(key) is slot:
                        del self._slots[key]
                raise
            slot.value, slot.done = value, True
            return value

    def _run(self, compute: Callable[[], T]) -> T:
        with self._guard:
            self.computations += 1
        return compute()

    def _advance(self, key: SharedKey) -> None:
        """Called under the guard after a new entry: evict this feed's older snapshots, then enforce the hard cap."""
        newest = self._newest.get(key.feed)
        if newest is None or key.instant > newest:
            self._newest[key.feed] = key.instant
            for old in [k for k in self._slots if k.feed == key.feed and k.instant < key.instant]:
                del self._slots[old]
        while len(self._slots) > self._max:
            self._slots.popitem(last=False)
