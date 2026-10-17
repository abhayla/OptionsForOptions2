"""AC-1: every proof object an order gate takes refuses forgery (W-098, finding caller-supplied-verdict-trusted).

The gates are found by name; their proof types are DISCOVERED from the gates' type hints (parameters, plus the sealed
types a gate or its minter hands back), never from a hand list of classes. A parameter type must be (a) a plain value
type, (b) on the explicit ALLOW list of plain inputs the gate re-checks itself, or (c) a proof type that passes every
refusal below. Anything else (for example a new open frozen dataclass) is reported as a violation, so a new proof
type added to a gate without the seal turns this file red.

``ofo_app.checked_basket`` may not be imported here (finding domain-test-imports-app-package); its signature is
checked in ``tests_app/test_checked_basket_proof_params.py`` with the same rules.
"""
from __future__ import annotations

import collections.abc
import copy
import dataclasses
import datetime
import inspect
import pickle
import typing
from decimal import Decimal
from enum import Enum

import pytest
from ofo.engine import Strategy
from ofo.execution import basket, margin_gate, safety
from ofo.execution.context import ExecutionContext
from ofo.execution.planned import ExecutionPlan
from ofo.instruments import eligibility
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import InstrumentId

#: The gates, and the functions that mint or consume what they trust. Found by name so a rename fails loudly.
GATES = (safety.check_pre_execution, basket.build_basket, margin_gate.check_margin,
         eligibility.registry_from_list, eligibility.apply_margin_refusals)

PLAIN_VALUE_TYPES = (str, int, bool, Decimal, datetime.date, datetime.datetime, type(None))

#: Plain inputs a gate RE-CHECKS itself (it never takes a verdict from them). One reason each; deleting one must turn
#: the discovery red (test_deleting_an_allow_entry_is_red).
RECHECKED_INPUTS: dict[type, str] = {
    Strategy: "the strategy under test: the gate only reads it and recomputes every check from its legs",
    ExecutionContext: "TRUSTED, not re-derived: margin_available, margin_required, session_valid, market_open and "
                      "reconciliation_blocked_strategy_ids are filled by callers from Zerodha reads; it is not a proof "
                      "object because the order send still needs a sealed KiteBasket built by checked_basket",
    Catalogue: "the instrument catalogue: contract facts are read from it, it holds no verdict",
    ExecutionPlan: "the plan: build_basket isinstance-checks it and resolves every leg against the catalogue itself",
    InstrumentId: "an exchange identity (segment, token) used only as a lookup key: it carries no verdict",
    basket.MarginSource: "a source of Zerodha's two figures: build_basket reads them and calls check_margin itself",
}

#: The exceptions the seal raises: TypeError (constructor, subclass, copy, pickle) and AttributeError (setattr).
REFUSED = (TypeError, AttributeError)


def _leaf_types(hint: object) -> list[object]:
    """Flatten Optional/Union/Iterable[...]/Annotated into the concrete types a parameter can hold."""
    origin = typing.get_origin(hint)
    if origin is None:
        return [hint]
    if origin is typing.Annotated:
        return _leaf_types(typing.get_args(hint)[0])
    if origin is typing.Literal:
        return [str]
    if origin is collections.abc.Callable:
        return [collections.abc.Callable]
    out: list[object] = []
    for arg in typing.get_args(hint):
        if arg is Ellipsis:
            continue
        out.extend(_leaf_types(arg))
    return out


def _hints(fn: typing.Callable[..., object]) -> typing.Mapping[str, object]:
    return typing.get_type_hints(fn)


def parameter_types(fn: typing.Callable[..., object]) -> set[type]:
    hints = _hints(fn)
    found: set[type] = set()
    for name in inspect.signature(fn).parameters:
        found.update(t for t in _leaf_types(hints[name]) if isinstance(t, type))
    return found


def returned_tuple_types(fn: typing.Callable[..., object]) -> set[type]:
    """The tuple-based types a gate or minter hands back: these are proof objects, whatever their name."""
    ret = _hints(fn).get("return")
    return {t for t in _leaf_types(ret) if isinstance(t, type) and issubclass(t, tuple) and t is not tuple}


def _is_plain(t: type) -> bool:
    return t in PLAIN_VALUE_TYPES or issubclass(t, Enum) or t is collections.abc.Callable


def violations(fn: typing.Callable[..., object], allow: typing.Mapping[type, str]) -> list[str]:
    """Parameter types of ``fn`` that are neither plain, allow-listed, nor a proof type that refuses forgery."""
    bad = []
    for t in sorted(parameter_types(fn), key=lambda x: x.__name__):
        if _is_plain(t) or t in allow:
            continue
        problems = forgery_problems(t)
        if problems:
            bad.append(f"{fn.__name__}: parameter type {t.__name__} is not plain, not allow-listed and not sealed: "
                       + "; ".join(problems))
    return bad


def proof_types(allow: typing.Mapping[type, str]) -> set[type]:
    """Every non-plain, non-allow-listed type in the gates' signatures, plus the tuple types they hand back."""
    found: set[type] = set()
    for fn in GATES:
        found.update(t for t in parameter_types(fn) if not _is_plain(t) and t not in allow)
        found.update(returned_tuple_types(fn))
    return found


def _instance(t: type) -> object:
    if not issubclass(t, tuple):
        raise TypeError(f"{t.__name__} is not a tuple-based type")
    return tuple.__new__(t, ())


def _raises(call: typing.Callable[[], object]) -> bool:
    try:
        call()
    except REFUSED:
        return True
    return False


def forgery_problems(t: type) -> list[str]:
    """Which forgery routes a type does NOT refuse (empty list = sealed)."""
    try:
        obj = _instance(t)
    except TypeError as exc:
        return [f"cannot be checked as a sealed tuple ({exc})"]
    routes: dict[str, typing.Callable[[], object]] = {
        "called with no arguments": t,
        "called with arguments": lambda: t(1, 2),
        "t.__new__ with arguments": lambda: t.__new__(t, 1),
        "object.__new__": lambda: object.__new__(t),
        "copy.copy": lambda: copy.copy(obj),
        "copy.deepcopy": lambda: copy.deepcopy(obj),
        "dataclasses.replace": lambda: dataclasses.replace(obj),
        "object.__setattr__": lambda: object.__setattr__(obj, "forged", True),
        "plain attribute assignment": lambda: setattr(obj, "forged", True),
        "subclass": lambda: type("Sub", (t,), {}),
        "subclass declaring its own maker": lambda: type("Sub3", (t,), {}, made_by="x", again="y"),
        "__reduce__ called directly": obj.__reduce__,
        "__reduce_ex__ called directly": lambda: obj.__reduce_ex__(2),
        "subclass overriding __setattr__": lambda: type("Sub2", (t,), {"__setattr__": object.__setattr__}),
    }
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        routes[f"pickle.dumps protocol {protocol}"] = lambda p=protocol: pickle.dumps(obj, protocol=p)
    if hasattr(copy, "replace"):
        routes["copy.replace"] = lambda: copy.replace(obj)
    return [name for name, call in routes.items() if not _raises(call)]


# -- discovery ----------------------------------------------------------------------------------------------------


def test_the_gates_proof_types_are_found_by_signature() -> None:
    """AC-1: discovery from the gates' hints finds exactly today's four proof types, not a hand-picked list."""
    names = {t.__name__ for t in proof_types(RECHECKED_INPUTS)}
    assert names == {"KiteBasket", "MarginVerdict", "ZerodhaEligibility", "ListState"}


@pytest.mark.parametrize("fn", GATES, ids=lambda f: f.__name__)
def test_every_gate_parameter_is_plain_allow_listed_or_sealed(fn: typing.Callable[..., object]) -> None:
    """AC-1: no gate takes an open proof-like type."""
    assert violations(fn, RECHECKED_INPUTS) == []


@pytest.mark.parametrize("t", sorted(proof_types(RECHECKED_INPUTS), key=lambda x: x.__name__),
                         ids=lambda t: t.__name__)
def test_each_discovered_proof_type_refuses_every_forgery_route(t: type) -> None:
    """AC-1: construction outside the mint, copy, deepcopy, pickle (every protocol), dataclasses.replace,
    object.__setattr__, subclassing and a subclass overriding __setattr__ are all refused."""
    assert forgery_problems(t) == []


@dataclasses.dataclass(frozen=True)
class OpenProof:
    allowed: bool


class OpenTuple(tuple):
    __slots__ = ()


class Mystery:
    pass


def planted_open_dataclass_gate(strategy: Strategy, proof: OpenProof) -> bool:
    return proof.allowed


def planted_open_tuple_gate(proof: OpenTuple) -> bool:
    return True


def planted_unknown_gate(x: Mystery) -> None: ...


# -- the killing tests: the guard itself is red when mutated ------------------------------------------------------


def test_a_planted_open_frozen_dataclass_proof_type_is_red() -> None:
    """AC-1: a gate that takes a new open frozen dataclass (replace and object.__setattr__ still work on it) fails."""

    bad = violations(planted_open_dataclass_gate, RECHECKED_INPUTS)
    assert len(bad) == 1 and "OpenProof" in bad[0]


def test_a_planted_open_tuple_subclass_is_red() -> None:
    """AC-1: a tuple subclass that merely looks sealed (no refusals) is reported route by route."""

    problems = forgery_problems(OpenTuple)
    for route in ("copy.copy", "copy.deepcopy", "subclass", "subclass overriding __setattr__"):
        assert route in problems
    assert violations(planted_open_tuple_gate, RECHECKED_INPUTS)


def test_deleting_an_allow_entry_is_red() -> None:
    """AC-1: with any one allow-list entry removed, some real gate reports a violation (none is stale)."""
    for entry in RECHECKED_INPUTS:
        smaller = {k: v for k, v in RECHECKED_INPUTS.items() if k is not entry}
        assert any(violations(fn, smaller) for fn in GATES), f"allow-list entry {entry.__name__} is unused"


def test_an_unknown_type_added_to_a_gate_is_red() -> None:
    """AC-1: a plain-looking custom class (not on the allow list) in a gate signature is reported."""

    assert violations(planted_unknown_gate, RECHECKED_INPUTS)


def test_every_allow_entry_states_a_reason() -> None:
    """AC-1: the allow list is explicit: one non-empty reason per entry."""
    assert all(isinstance(reason, str) and len(reason) > 20 for reason in RECHECKED_INPUTS.values())


class _SkipsTheSeal:
    """A mixin whose own __init_subclass__ does not call the seal's."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        pass


def test_a_mixin_first_subclass_is_a_documented_out_of_scope_gap() -> None:
    """AC-1: ``class Evil(Mixin, MarginVerdict)`` IS created (the mixin's __init_subclass__ shadows the seal's): a
    deliberate trick, out of scope (ADR-003 Q235). What still holds is asserted: calling it still refuses, so an
    instance needs the tuple base constructor, which tests/test_door_names_private.py flags outside the owning files."""
    evil = type("Evil", (_SkipsTheSeal, margin_gate.MarginVerdict), {})
    with pytest.raises(TypeError):
        evil()
