"""Market-wide figures computed once per feed snapshot and served to every reader of that feed (REQ-050 AC-1, AC-3).

ADR-053 (V1): live prices come through each user's OWN Zerodha feed and one user's feed never drives another user's
screen (F-23). So the feed owner is part of every key: two users' feeds never share an entry, even with identical data.
Sharing across users waits for a licensed vendor feed (REQ-052 AC-5), which is not built.

The key is an allow-list (:class:`SharedKey`): feed owner, underlying, expiry, snapshot instant, the figure (the engine
function's identity, ``module.qualname``), the contract and the exact inputs the figure is computed from. The inputs are
in the key so a stale or poisoned entry can never answer a different input: an entry is only ever read back for the very
inputs it was computed from.

The inputs are never written by hand (#519): :meth:`FeedScope.call` takes the engine function and its arguments, builds
the key FROM those arguments (bound to the function's signature, defaults applied) through ONE normaliser
(:func:`key_part`), then calls the function with exactly those bound arguments itself. A call site cannot drop or change
an input of the computation without the key changing with it. The normaliser's answer per argument:

- ``None``, ``bool``, ``int``, ``str`` (and ``str`` subclasses), ``Decimal`` (exact: sign, digits and exponent, so
  ``1.0`` and ``1.00`` are two keys), ``float``, ``date``, ``datetime`` (with its offset, zone name and fold), ``time``,
  an ``Enum`` member: kept, tagged with its exact type (``True`` and ``1`` are two keys);
- a ``tuple`` (also the empty one): each item reduced;
- a dataclass: its type and EVERY field by name, reduced (``compare=False`` fields too);
- a slots-only value object (``__slots__``, no ``__dict__``, e.g. the engine's gated ``ExpiryModel``): every slot;
- anything else (a list, dict, set, an object hashed by identity, a function): raises ``TypeError`` (fail closed),
  never silently left out of the key.

The function must be a plain module-level function its module holds under its name: a lambda, a nested function, a
closure, a bound method, a ``functools.partial`` or a callable object is refused, because what it captures would not be
in the key.

Known bypasses (written down, not chased):

- :meth:`SharedCompute.get_or_compute` called with a hand-built :class:`SharedKey` outside :meth:`FeedScope.call` (only
  the cache's own tests do this);
- module-level constants and other globals an engine function reads (``DAYS_IN_YEAR``, ``EXPIRY_CLOSE``): they are not
  arguments, so not in the key; they change only with a code change, which restarts the process and empties the cache;
- an argument object mutated AFTER the call (the key is taken at call time; every argument type used is frozen).

Behaviour (each has a test):

- one computation per key; concurrent first requests for one key are coalesced (the others wait for the one result);
- a slow computation for one key does not block reads or computations of other keys (a lock per key, never a global one
  held while computing);
- a computation that raises is not cached, affects no other key, and the next request computes again;
- memory is bounded: a hard cap evicts the least recently used entries. A newer snapshot instant is simply another key
  (the instant is in the key), so an older instant's entry is never served for it;
- per-strategy modules (P&L, risk, rules) never import this module (``tests/marketdata/test_scale_classes.py``).

Standard library only.
"""
from __future__ import annotations

import dataclasses
import datetime
import enum
import inspect
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from decimal import Decimal
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
        for name, value in (("feed_owner", self.feed_owner), ("underlying", self.underlying),
                            ("figure", self.figure)):
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

    def call(self, scope: tuple, fn: Callable[..., T], /, *args: object, **kwargs: object) -> T:
        """``fn(*args, **kwargs)``, computed once per key. ``scope`` is (underlying, expiry, instant, instrument_id);
        the figure is ``fn``'s identity and the inputs are built from the very arguments ``fn`` is then called with."""
        underlying, expiry, instant, instrument_id = scope
        figure, inputs, bound = call_key(fn, args, kwargs)
        key = SharedKey(self.feed_owner, underlying, expiry, instant, figure, instrument_id, inputs)
        return self.cache.get_or_compute(key, lambda: fn(*bound.args, **bound.kwargs))


def call_shared[R](shared: FeedScope | None, scope: tuple, fn: Callable[..., R], /, *args: object,
                   **kwargs: object) -> R:
    """The one way a market-wide figure is computed: through ``shared`` when there is a feed scope, else the same call
    unshared. Both paths call ``fn`` with the same arguments, so a shared figure equals an unshared one."""
    if shared is None:
        return fn(*args, **kwargs)
    return shared.call(scope, fn, *args, **kwargs)


def function_identity(fn: object) -> str:
    """``module.qualname`` of a plain module-level function; refuses anything that may capture inputs outside its
    arguments (lambda, nested function, closure, bound method, partial, callable object)."""
    if not inspect.isfunction(fn):
        raise TypeError(f"a shared figure is computed by a plain module-level function, got {fn!r}")
    qualname, module = fn.__qualname__, fn.__module__
    if "<" in qualname or "." in qualname or fn.__closure__:
        raise TypeError(f"{module}.{qualname} is a lambda, nested function or closure: what it captures would not be "
                        "in the cache key; pass a module-level function")
    if getattr(inspect.getmodule(fn), qualname, None) is not fn:
        raise TypeError(f"{module}.{qualname} is not what its module holds under that name; refused")
    return f"{module}.{qualname}"


def call_key(fn: Callable[..., object], args: tuple, kwargs: dict) -> tuple[str, tuple[Hashable, ...],
                                                                             inspect.BoundArguments]:
    """(figure, inputs, bound arguments) of one engine call: the arguments bound to ``fn``'s signature with its
    defaults applied, each reduced by :func:`key_part`. ``fn`` is called with exactly the returned bound arguments."""
    figure = function_identity(fn)
    bound = inspect.signature(fn).bind(*args, **kwargs)
    bound.apply_defaults()
    params = bound.signature.parameters
    inputs = tuple((name, _keywords_part(value) if params[name].kind is inspect.Parameter.VAR_KEYWORD
                    else key_part(value)) for name, value in bound.arguments.items())
    return figure, inputs, bound


def _keywords_part(keywords: dict) -> Hashable:
    """A ``**kwargs`` parameter: every keyword, name and value, sorted by name."""
    return ("**", tuple((name, key_part(keywords[name])) for name in sorted(keywords)))


_SCALARS: Final = (type(None), bool, int, str, Decimal, float, datetime.date, datetime.time, enum.Enum)


def _type_tag(value: object) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"


def key_part(value: object) -> Hashable:
    """The ONE normaliser of an engine argument into an exact, hashable key part (answer states in the module
    docstring); anything it cannot reduce raises ``TypeError``, never drops out of the key."""
    tag = _type_tag(value)
    if isinstance(value, Decimal):
        return (tag, value.as_tuple())  # exact: sign, digits, exponent
    if isinstance(value, datetime.datetime):
        return (tag, value.isoformat(), value.tzname(), value.fold)
    if isinstance(value, _SCALARS):
        return (tag, value)
    if isinstance(value, tuple):
        return (tag, tuple(key_part(item) for item in value))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (tag, tuple((f.name, key_part(getattr(value, f.name))) for f in dataclasses.fields(value)))
    slots = _slot_names(value)
    if slots is not None:
        return (tag, tuple((name, key_part(getattr(value, name))) for name in slots))
    raise TypeError(f"{tag} cannot be reduced to a cache key part (fail closed); pass a value, a tuple or a dataclass")


def _slot_names(value: object) -> tuple[str, ...] | None:
    """Every slot of a slots-only value object (no ``__dict__``), across its classes; None for any other object."""
    if hasattr(value, "__dict__") or isinstance(value, type) or callable(value):
        return None
    names: list[str] = []
    for cls in type(value).__mro__:
        own = getattr(cls, "__slots__", ())
        for name in (own,) if isinstance(own, str) else own:
            if name not in names and name != "__weakref__":
                names.append(name)
    return tuple(names) if names else None


class _Slot:
    __slots__ = ("done", "lock", "value")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.done = False
        self.value: object = None

    def finish(self, value: object) -> None:
        self.value = value
        self.done = True


class SharedCompute:
    """A bounded cache of market-wide results with one computation per key."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if not isinstance(max_entries, int) or max_entries < 1:
            raise ValueError(f"max_entries must be a positive int, got {max_entries!r}")
        self._max = max_entries
        self._guard = threading.Lock()  # protects the maps only; never held while a computation runs
        self._slots: OrderedDict[SharedKey, _Slot] = OrderedDict()
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
            slot = self._slots.get(key)
            if slot is None:
                slot = self._slots[key] = _Slot()
                while len(self._slots) > self._max:
                    self._slots.popitem(last=False)
            else:
                self._slots.move_to_end(key)
        with slot.lock:
            if slot.done:
                return slot.value  # type: ignore[return-value]
            try:
                with self._guard:
                    self.computations += 1
                value = compute()
            except BaseException:
                with self._guard:
                    if self._slots.get(key) is slot:
                        del self._slots[key]
                raise
            slot.finish(value)
            return value
