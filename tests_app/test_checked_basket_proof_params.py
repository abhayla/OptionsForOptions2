"""AC-1: the app-layer gate ``checked_basket`` takes no open proof-like parameter (W-098).

Same rules as ``tests/test_sealed_proof_objects.py`` (which may not import ``ofo_app``, finding
domain-test-imports-app-package): every parameter type of ``checked_basket`` is plain, on the explicit allow list, or
a sealed proof type; anything else is red.
"""
from __future__ import annotations

import collections.abc
import dataclasses
import typing
from decimal import Decimal

from ofo.execution.basket import KiteBasket
from ofo.execution.planned import ExecutionPlan
from ofo.instruments.catalogue import Catalogue
from ofo_app.checked_basket import checked_basket
from ofo_app.kite_margin import KiteMargin

#: Inputs checked_basket passes on to build_basket, which re-checks them itself (one reason each).
ALLOWED = {
    ExecutionPlan: "the plan: build_basket isinstance-checks it and resolves every leg itself",
    Catalogue: "the instrument catalogue: contract facts are read from it, it holds no verdict",
    KiteMargin: "the real Zerodha client: checked_basket requires exactly this class (no subclass, no duck)",
}
PLAIN = (str, int, bool, Decimal)


def _leaves(hint: object) -> list[object]:
    if typing.get_origin(hint) is collections.abc.Callable:
        return [collections.abc.Callable]
    args = typing.get_args(hint)
    return [hint] if not args else [leaf for arg in args for leaf in _leaves(arg)]


def _open_types(fn: typing.Callable[..., object]) -> list[str]:
    hints = typing.get_type_hints(fn)
    names = [n for n in hints if n != "return"]
    types = {t for n in names for t in _leaves(hints[n]) if isinstance(t, type)}
    return sorted(t.__name__ for t in types
                  if t not in PLAIN and t is not collections.abc.Callable and t not in ALLOWED)


def test_checked_basket_takes_no_proof_object() -> None:
    """AC-1: its parameters are plan, catalogue, version, the real client and a freeze callable: no proof type."""
    assert _open_types(checked_basket) == []
    assert typing.get_type_hints(checked_basket)["return"] is KiteBasket  # what it hands back is the sealed proof


def test_a_proof_like_parameter_added_to_checked_basket_is_red() -> None:
    """AC-1: the same check reports a new open frozen dataclass parameter."""

    @dataclasses.dataclass(frozen=True)
    class OpenVerdict:
        allowed: bool

    def planted(plan: ExecutionPlan, verdict: OpenVerdict) -> KiteBasket: ...

    planted.__annotations__ = {"plan": ExecutionPlan, "verdict": OpenVerdict, "return": KiteBasket}
    assert _open_types(planted) == ["OpenVerdict"]
