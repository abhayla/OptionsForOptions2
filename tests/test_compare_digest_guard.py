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
        # Any Name/Attribute spelled compare_digest: a call, an alias (`_eq = hmac.compare_digest`), a reference.
        # Out of scope: the string form getattr(hmac, "compare_digest").
        if isinstance(node, ast.Attribute) and node.attr == "compare_digest":
            lines.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id == "compare_digest":
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


def test_the_scan_sees_a_reference_without_a_call():
    assert _callers("import hmac\n_eq = hmac.compare_digest\n") == [2]
    assert _callers("from hmac import compare_digest as cd\n_eq = cd\n") == [1]
    assert _callers("f(compare_digest)\n") == [1]


def test_nfc_and_nfd_forms_stay_unequal_no_normalisation():
    assert equal_secret("é", "é") is False
    assert equal_secret("é", "é") is True


def test_the_comparison_goes_through_hmac_compare_digest_on_bytes(monkeypatch):
    import ofo.safe_compare as sc
    calls = []
    real = sc.hmac.compare_digest

    def spy(x, y):
        calls.append((x, y))
        return real(x, y)

    monkeypatch.setattr(sc.hmac, "compare_digest", spy)
    assert equal_secret("Äb", "Äb") is True
    assert calls == [("Äb".encode(), "Äb".encode())]


@pytest.mark.parametrize("a,b", [(None, "x"), ("x", None), (b"x", "x"), ("x", b"x"), (1, "x"), ("x", 1)])
def test_a_non_str_argument_raises_a_deliberate_typeerror_without_echoing_the_value(a, b):
    with pytest.raises(TypeError, match="two str") as exc:
        equal_secret(a, b)
    assert "'x'" not in str(exc.value)


@pytest.mark.parametrize("a,b,expected", [("AB1234", "AB1234", True), ("AB1234", "AB1235", False),
                                           ("ÄB1234", "AB1234", False), ("AB1234", "ÄB1234", False),
                                           ("ÄB", "ÄB", True), ("", "", True), ("\ud800", "x", False)])
def test_equal_secret_never_raises_on_non_ascii(a, b, expected):
    assert equal_secret(a, b) is expected
