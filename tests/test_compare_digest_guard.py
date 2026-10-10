"""Guard (#174): no secret or identity comparison in backend/ may raise on non-ASCII text.

``compare_digest`` on two ``str`` raises ``TypeError`` for non-ASCII, a 500 on attacker-controlled input. The only
allowed caller is ``ofo.safe_compare`` (UTF-8 bytes); every other call in ``backend/`` must use ``equal_secret``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ofo.safe_compare import equal_secret

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ALLOWED = BACKEND / "ofo" / "safe_compare.py"


def _callers(source: str) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if name == "compare_digest":
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and any(a.name == "compare_digest" for a in node.names):
            lines.append(node.lineno)
    return lines


def test_only_the_helper_calls_compare_digest():
    offenders = [f"{p.relative_to(BACKEND)}:{n}" for p in sorted(BACKEND.rglob("*.py")) if p != ALLOWED
                 for n in _callers(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"use ofo.safe_compare.equal_secret, not compare_digest: {offenders}"


def test_the_scan_sees_a_plain_compare_digest():
    assert _callers("import secrets\nsecrets.compare_digest(a, b)\n") == [2]
    assert _callers("import hmac\nhmac.compare_digest(a, b)\n") == [2]
    assert _callers("from hmac import compare_digest\n") == [1]
    assert _callers("equal_secret(a, b)\n") == []


@pytest.mark.parametrize("a,b,expected", [("AB1234", "AB1234", True), ("AB1234", "AB1235", False),
                                           ("ÄB1234", "AB1234", False), ("AB1234", "ÄB1234", False),
                                           ("ÄB", "ÄB", True), ("", "", True), ("\ud800", "x", False)])
def test_equal_secret_never_raises_on_non_ascii(a, b, expected):
    assert equal_secret(a, b) is expected
