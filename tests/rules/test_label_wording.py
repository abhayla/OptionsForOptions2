"""W-024 item 6 (sweep): the rule label templates in backend/ofo/rules/templates.py (Rule(...)'s
final `label`/description argument, ~lines 45-128) pass the shared ADR-003 wording checker.

This does NOT redesign ofo.rules.templates: it statically extracts the label text each `Rule(...)`
call constructs (a plain string or an f-string's literal segments, skipping the `{...}` expression
parts, which are numbers/enum values, not authored wording) and scans it with `find_advice_wording`.
"""
from __future__ import annotations

import ast
from pathlib import Path

from ofo.wording import find_advice_wording

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_PATH = REPO_ROOT / "backend" / "ofo" / "rules" / "templates.py"


def _label_literal_text(node: ast.expr) -> str:
    """A `Rule(...)` label argument's authored (literal) text: the whole string for a plain
    Constant, or the joined Constant segments of an f-string (JoinedStr), skipping `{expr}` parts."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return ""


def _extract_rule_labels(path: Path) -> list[tuple[int, str]]:
    """Every `Rule(...)` call's last (label) argument, as (line number, literal text)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    labels: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Rule":
            if node.args:
                labels.append((node.lineno, _label_literal_text(node.args[-1])))
    return labels


def test_templates_py_has_rule_label_calls_to_scan() -> None:
    """Sanity: the extractor itself finds real Rule(...) label calls (not silently zero)."""
    labels = _extract_rule_labels(TEMPLATES_PATH)
    assert len(labels) >= 10, f"expected >=10 Rule(...) label calls, found {len(labels)}"


def test_every_rule_label_passes_the_wording_checker() -> None:
    """W-024 sweep: every rule label's literal text is free of ADR-003 advice wording."""
    for lineno, text in _extract_rule_labels(TEMPLATES_PATH):
        hits = find_advice_wording(text)
        assert not hits, f"{TEMPLATES_PATH.name}:{lineno}: banned wording {hits} in label {text!r}"
