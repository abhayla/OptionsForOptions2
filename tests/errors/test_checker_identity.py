"""W-024 round 8 (ADR-056 item 1): the runtime identity check of the wording checker.

Spec basis: ADR-056 decision (1): "no attribute assignment on any imported module in backend/ofo
plus a runtime identity check of the wording checker." ADR-003 Q235: deliberate runtime
replacement is out of scope beyond the CI flag and this check; the check fails closed.

Rebinding happens HERE, in tests only, through monkeypatch (undone after each test). backend/ofo
may not do it: tests/errors/test_write_allowlist.py refuses any such write in CI.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import ofo.wording
from ofo.errors import model, render

WORDING_FILE = Path(__file__).resolve().parents[2] / "backend" / "ofo" / "wording.py"


def _render_ok():
    return render("user_input_lot_size", entered=0)


def test_render_works_with_the_original_checker() -> None:
    assert _render_ok().what_happened


def test_rebinding_find_advice_wording_makes_the_next_build_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """The brief's named case: a checker that finds nothing is swapped in; the next build refuses."""
    monkeypatch.setattr(ofo.wording, "find_advice_wording", lambda text: [])
    with pytest.raises(model.CheckerChanged, match="find_advice_wording is not the function"):
        _render_ok()


def test_swapping_the_code_object_makes_the_next_build_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same function object, new body (`__code__` replaced): only the `__code__` comparison sees it."""
    monkeypatch.setattr(ofo.wording.find_advice_wording, "__code__", (lambda text: []).__code__)
    with pytest.raises(model.CheckerChanged, match=r"find_advice_wording\.__code__"):
        _render_ok()


@pytest.mark.parametrize("name", model._CHECKER_FUNCTIONS)
def test_rebinding_any_checker_function_raises(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr(ofo.wording, name, lambda *a, **k: None)
    with pytest.raises(model.CheckerChanged, match=name):
        _render_ok()


@pytest.mark.parametrize("name", model._CHECKER_FUNCTIONS)
def test_swapping_any_checker_code_raises(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    fn = getattr(ofo.wording, name)
    monkeypatch.setattr(fn, "__code__", fn.__code__.replace())  # an equal but distinct code object
    with pytest.raises(model.CheckerChanged, match=rf"{name}\.__code__"):
        _render_ok()


@pytest.mark.parametrize("name", model._CHECKER_DATA)
def test_rebinding_any_checker_data_raises(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr(ofo.wording, name, ())
    with pytest.raises(model.CheckerChanged, match=name):
        _render_ok()


def test_deleting_a_checker_function_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(ofo.wording, "find_q226_bare_words")
    with pytest.raises(model.CheckerChanged):
        _render_ok()


def test_rebinding_the_builder_modules_own_checker_name_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model, "check_platform_text", lambda text, where: None)
    with pytest.raises(model.CheckerChanged, match="ofo.errors.model"):
        _render_ok()


def test_reading_an_issued_error_after_a_rebind_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every read re-checks too: a message built before the swap is not shown after it."""
    err = _render_ok()
    monkeypatch.setattr(ofo.wording, "find_advice_wording", lambda text: [])
    with pytest.raises(model.CheckerChanged):
        err.as_dict()


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
