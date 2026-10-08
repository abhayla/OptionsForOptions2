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


def test_every_rule_label_comes_from_the_explanation_catalogue() -> None:
    """W-024 round 9: a Rule(...) label is a render_explanation(...) result or a variable holding one, never a literal."""
    tree = ast.parse(TEMPLATES_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Rule" and node.args:
            last = node.args[-1]
            assert not isinstance(last, (ast.Constant, ast.JoinedStr)), f"line {node.lineno}: literal rule label"


def test_rendered_rule_labels_keep_their_wording() -> None:
    """Expected texts from the former f-strings' meaning (hand-written, not produced by running the new code)."""
    import datetime
    from decimal import Decimal as D

    from ofo.engine import Action  # noqa: F401  (import check only: rules need no engine action here)
    from ofo.rules import templates as t
    from ofo.rules.inputs import InputName
    from ofo.rules.model import RuleAction

    act = RuleAction.ALERT_ONLY
    assert t.exit_max_loss("a", D("5000"), action=act).description == "Max loss 5000"
    assert t.exit_profit_target("a", D("3000"), action=act).description == "Profit target 3000"
    assert t.entry_immediate("a", action=act).description == "Enter now"
    assert t.entry_level_reached("a", D("24000"), t.Direction.AT_OR_ABOVE, action=act).description == (
        "Underlying at or above 24000")
    assert t.exit_underlying_level("a", D("23000"), t.Direction.AT_OR_BELOW, action=act).description == (
        "Underlying at or below 23000")
    assert t.entry_range("a", D("23000"), D("24000"), action=act).description == "Underlying between 23000 and 24000"
    assert t.entry_premium_target("a", D("3750"), receive=False, action=act).description == "Net debit at most Rs 3750"
    assert t.entry_time_window("a", datetime.time(9, 30), datetime.time(11, 0), action=act).description == (
        "Between 09:30 and 11:00 IST")
    assert t.exit_time("a", days_to_expiry=2, action=act).description == "2 days to expiry or fewer"
    assert t.exit_time("a", days_to_expiry=1, at_or_after=datetime.time(14, 0), action=act).description == (
        "1 days to expiry or fewer, from 14:00 IST")
    # A one-sided bound used to print the other side as "None"; it now has its own sentence.
    assert t.entry_volatility("a", InputName.IV, D("20"), None, action=act).description == (
        "implied volatility at or above 20")
    assert t.entry_volatility("a", InputName.IV_PERCENTILE, None, D("30"), action=act).description == (
        "IV percentile at or below 30")
