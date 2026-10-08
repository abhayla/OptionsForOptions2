"""W-024 round 8 (ADR-056 item 1): the runtime identity check of the wording checker.

Spec basis: ADR-056 decision (1): "no attribute assignment on any imported module in backend/ofo
plus a runtime identity check of the wording checker." ADR-003 Q235: deliberate runtime
replacement is out of scope beyond the CI flag and this check; the check fails closed.

Fix round 1 (review REVISE): the check lives in ofo.wording's own public entry points, so every
caller fails closed, not only the error builder; and ofo.wording is a read-only module object, so
`ofo.wording.x = f` raises. The only remaining route is a write into the module's namespace dict,
which the tests below use deliberately (monkeypatch.setitem on vars(), undone after each test);
backend/ofo cannot (tests/errors/test_write_allowlist.py refuses vars/__dict__ in CI).
"""
from __future__ import annotations

import ast
import dataclasses
import datetime
from pathlib import Path

import pytest

import ofo.wording
from ofo.errors import model, render

WORDING_FILE = Path(__file__).resolve().parents[2] / "backend" / "ofo" / "wording.py"
NAMESPACE = vars(ofo.wording)


def _render_ok():
    return render("user_input_lot_size", entered=0)


def _swap(monkeypatch: pytest.MonkeyPatch, name: str, value: object) -> None:
    monkeypatch.setitem(NAMESPACE, name, value)


def test_render_works_with_the_original_checker() -> None:
    assert _render_ok().what_happened


def test_the_wording_module_refuses_attribute_writes_and_deletes() -> None:
    """Structural guarantee: the accidental route (`ofo.wording.f = g`) raises at run time."""
    with pytest.raises(AttributeError, match="read-only"):
        ofo.wording.find_advice_wording = lambda text: []
    with pytest.raises(AttributeError, match="read-only"):
        del ofo.wording.check_platform_text
    assert ofo.wording.find_advice_wording("you should buy") == ["should"]


def test_rebinding_find_advice_wording_makes_the_next_build_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    _swap(monkeypatch, "find_advice_wording", lambda text: [])
    with pytest.raises(ofo.wording.CheckerChanged, match="find_advice_wording is not the function"):
        _render_ok()


def test_swapping_the_code_object_makes_the_next_build_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same function object, new body: only the `__code__` comparison sees it."""
    monkeypatch.setattr(ofo.wording.find_advice_wording, "__code__", (lambda text: []).__code__)
    with pytest.raises(ofo.wording.CheckerChanged, match=r"find_advice_wording\.__code__"):
        _render_ok()


@pytest.mark.parametrize("name", model._CHECKER_FUNCTIONS)
def test_rebinding_any_checker_function_raises(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    _swap(monkeypatch, name, lambda *a, **k: None)
    with pytest.raises(ofo.wording.CheckerChanged, match=name):
        _render_ok()


@pytest.mark.parametrize("name", model._CHECKER_FUNCTIONS)
def test_swapping_any_checker_code_raises(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    fn = getattr(ofo.wording, name)
    monkeypatch.setattr(fn, "__code__", fn.__code__.replace())  # an equal but distinct code object
    with pytest.raises(ofo.wording.CheckerChanged, match=rf"{name}\.__code__"):
        _render_ok()


@pytest.mark.parametrize("name", model._CHECKER_DATA)
def test_rebinding_any_checker_data_raises(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    _swap(monkeypatch, name, ())
    with pytest.raises(ofo.wording.CheckerChanged, match=name):
        _render_ok()


def test_deleting_a_checker_function_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(NAMESPACE, "find_q226_bare_words")
    with pytest.raises(ofo.wording.CheckerChanged):
        _render_ok()


def test_reading_an_issued_error_after_a_rebind_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every read re-checks too: a message built before the swap is not shown after it."""
    err = _render_ok()
    _swap(monkeypatch, "find_advice_wording", lambda text: [])
    with pytest.raises(ofo.wording.CheckerChanged):
        err.as_dict()


# --- Fix round 1, finding 1: every caller of the checker fails closed, not only errors.model ----

def _safety_flag() -> object:
    from ofo.execution.safety import Flag, FlagCode

    return Flag(FlagCode.MULTI_EXPIRY, "You should buy this, it is the best trade")


def _safety_check_failure() -> object:
    from ofo.execution.safety import CheckCode, CheckFailure

    return CheckFailure(CheckCode.SESSION_INVALID, "You should buy this, it is the best trade")


def _disconnect() -> object:
    from ofo.marketdata import disconnect

    return disconnect.disconnect_message(datetime.datetime(2026, 9, 29, 5, 12, 17, tzinfo=datetime.timezone.utc))


def _why() -> object:
    from ofo.timeline import why

    return why._own("Your rule was triggered: {}.", "x")


def _loader() -> object:
    from ofo.strategy.loader import check_wording, load_templates

    return check_wording(dataclasses.replace(load_templates()[0], description="A spread on NIFTY."))


CALLER_PATHS = {
    "execution.safety Flag": _safety_flag,
    "execution.safety CheckFailure": _safety_check_failure,
    "marketdata.disconnect": _disconnect,
    "timeline.why": _why,
    "strategy.loader": _loader,
}


@pytest.mark.parametrize("label", sorted(CALLER_PATHS))
@pytest.mark.parametrize("swapped", ["find_advice_wording", "check_platform_text", "_COMPILED_PATTERNS"])
def test_each_caller_message_path_raises_on_a_swapped_checker(
    monkeypatch: pytest.MonkeyPatch, label: str, swapped: str
) -> None:
    """The reviewer's repro (a Flag built with "You should buy this, it is the best trade" after
    the checker was replaced) and every other caller: each refuses once the checker was swapped."""
    _swap(monkeypatch, swapped, (lambda *a, **k: None) if swapped != "_COMPILED_PATTERNS" else ())
    with pytest.raises(ofo.wording.CheckerChanged):
        CALLER_PATHS[label]()


def test_caller_paths_work_with_the_original_checker() -> None:
    with pytest.raises(ValueError, match="banned wording"):
        _safety_flag()
    assert _disconnect().startswith("Live market data disconnected.")
    assert _why() == "Your rule was triggered: x."
    _loader()


def test_every_function_and_constant_of_the_wording_module_is_captured() -> None:
    """A new helper or table added to ofo/wording.py is captured too, or this goes red. Names are
    read from the file's AST (top-level defs and assignments), not from the running module."""
    tree = ast.parse(WORDING_FILE.read_text(encoding="utf-8"))
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    data: set[str] = set()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        data |= {t.id for t in targets if isinstance(t, ast.Name)}
    assert functions == set(model._CHECKER_FUNCTIONS)
    assert data == set(model._CHECKER_DATA)
    # ofo.wording's own self-check covers the same functions and tables (its verifier aside).
    assert set(ofo.wording._SELF_CHECKED_FUNCTIONS) == functions - {"_make_verifier", "_make_frozen_module_class"}
    assert set(ofo.wording._SELF_CHECKED_DATA) == data - {
        "_SELF_CHECKED_FUNCTIONS", "_SELF_CHECKED_DATA", "_verify_checker", "_FrozenModule"}
