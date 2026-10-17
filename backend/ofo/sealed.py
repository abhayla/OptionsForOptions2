"""The ONE seal for proof objects an order gate trusts (W-098; findings caller-supplied-verdict-trusted and
sealed-object-mutable-after-seal).

A proof object (a basket the margin gate allowed, a margin verdict, Zerodha's eligibility) is believed by a gate only
because ordinary code cannot make one. ``SealedTuple`` gives every proof type the same closed shape:

- an immutable tuple with no attribute storage (``__slots__ = ()``): ``object.__setattr__`` and ``setattr`` have
  nothing to write (setting or deleting any attribute raises ``AttributeError``);
- calling the class raises (there is no token to borrow); the owning module's one maker builds it with the tuple
  base class's own constructor, which ``tests/test_door_names_private.py`` allows only in the owning files;
- ``copy`` / ``deepcopy`` / ``pickle`` (``__reduce__`` and ``__reduce_ex__``) raise;
- the class cannot be subclassed again (``__init_subclass__``), so no subclass can reopen it by overriding
  ``__setattr__``, ``__new__`` or a property.

A proof type is declared ``class X(SealedTuple, made_by="its maker", again="what to do instead of copying")``.
``tests/test_sealed_proof_objects.py`` discovers the gates' proof types from their signatures and fails for any
that is not sealed this way. Not proof against deliberate tricks (``copyreg``, a ``__class__`` swap, a lying source
object): those are out of scope (ADR-003 Q235).
"""
from __future__ import annotations

from typing import NoReturn


class SealedTuple(tuple):
    """Base of every proof type. Direct subclasses name their maker and how to get a fresh object."""

    __slots__ = ()
    _made_by: str
    _again: str

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError(f"a {cls.__name__} comes only from {cls._made_by}")

    def __init_subclass__(cls, *, made_by: str | None = None, again: str | None = None, **kwargs: object) -> None:
        if hasattr(super(cls, cls), "_made_by"):  # the next class in line is already a sealed proof type
            raise TypeError(f"{cls.__name__} would subclass a sealed type; sealed types cannot be subclassed")
        if not made_by or not again:
            raise TypeError(f"{cls.__name__} must say made_by and again")
        super().__init_subclass__(**kwargs)
        cls._made_by = made_by
        cls._again = again

    def __copy__(self) -> NoReturn:
        raise TypeError(f"a {type(self).__name__} cannot be copied; {self._again}")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError(f"a {type(self).__name__} cannot be copied; {self._again}")

    def __reduce_ex__(self, _protocol: object) -> NoReturn:
        raise TypeError(f"a {type(self).__name__} cannot be pickled; {self._again}")

    def __reduce__(self) -> NoReturn:
        raise TypeError(f"a {type(self).__name__} cannot be pickled; {self._again}")


__all__ = ["SealedTuple"]
