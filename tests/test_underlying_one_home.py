"""REQ-001 AC-4 (W-129), second layer behind the structural `Underlying` type: no backend file retypes the underlying
set as a Literal, and the type is built from the home. Files are discovered from the tree; one that cannot be parsed
fails the test (fail closed)."""
from __future__ import annotations

import ast
import pathlib

import pytest

from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

pytestmark = pytest.mark.repo_scan
BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
HOME = {"underlying.py"}  # ofo_app/underlying.py builds the type from the home set; it names no string


def _strings(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_no_literal_retypes_the_underlying_set() -> None:
    names = set(SUPPORTED_UNDERLYINGS)
    offenders = []
    for path in sorted(BACKEND.rglob("*.py")):
        if "alembic" in path.parts or path.name in HOME:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))  # a SyntaxError fails the test
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and "Literal" in ast.dump(node.value) and _strings(node.slice) & names:
                offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    assert not offenders, f"an underlying name inside a Literal (use ofo_app.underlying.Underlying): {offenders}"
