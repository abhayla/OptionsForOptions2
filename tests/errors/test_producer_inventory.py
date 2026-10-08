"""W-024 round 9, step 1 (REQ-065 AC-2, ADR-003 Q226): inventory of every user-facing text producer.

The rule is a SHAPE, not a list of names: a string literal (plain or f-string) in backend/ofo that reads as a
sentence a person is meant to read - it starts with a capital letter, a currency sign or a `{slot}`, and holds at
least three words - is user-facing text. The one place such text may live is the reviewed catalogue,
`backend/ofo/errors/templates.py`, whose text reaches a user only through `render()`.

Not user-facing, by position (each is a shape too): a docstring; an argument of a logging call (`logger.info`, ...);
a message of a raised BUILT-IN exception (ValueError, TypeError, ... : a programmer error, never shown); an assert
message; a pattern passed to `re.compile`/`re.search`/...; the forbidden-wording data of `ofo/wording.py` and
`ofo/strategy/wording.py` (the second layer: the phrases it refuses are not text it shows).

Fail closed: any sentence-shaped literal anywhere else fails this test, naming file, line and function. A producer
whose text could not be classified (a sentence-shaped literal in a position this scan does not recognise) is a
failure too - nothing is skipped by default.

`PENDING` lists the producers outside this round's scope that are NOT routed yet: per file, per function, the number
of sentence-shaped literals. It is a ratchet, not an allowlist: the test fails when a function gains a producer
(new function, or a higher count) AND when a listed count is higher than what is left, so the list can only shrink. Every entry is a known AC-2 gap, reported to the owner.
"""
from __future__ import annotations

import ast
import pathlib
import re
from collections import defaultdict

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "backend" / "ofo"
CATALOGUE_FILE = "errors/templates.py"
#: The door's own slot formatters: they print typed slot values that only render() places into catalogue text.
DOOR_FILES = frozenset({CATALOGUE_FILE, "errors/explanations.py", "errors/slots.py", "errors/gate_slots.py"})

#: Files whose literals are the forbidden-wording DATA (phrases refused, never shown).
WORDING_DATA_FILES = frozenset({"wording.py", "strategy/wording.py"})

#: Built-in exception types: their messages are programmer errors, never user-facing.
BUILTIN_EXCEPTIONS = frozenset({
    "ValueError", "TypeError", "RuntimeError", "KeyError", "LookupError", "IndexError", "NotImplementedError",
    "AssertionError", "AttributeError", "OverflowError", "ZeroDivisionError", "ArithmeticError", "Exception",
})
LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "log"})
REGEX_FUNCTIONS = frozenset({"compile", "search", "match", "fullmatch", "sub", "findall", "finditer", "split"})

_WORD = re.compile(r"[A-Za-z]")

#: Producers not routed through render() yet (out of round 9's five-module scope), file -> functions. Ratchet.
PENDING: dict[str, dict[str, int]] = {
    'admin/client_id.py': {'normalise_client_id': 1},
    'admin/qualifying.py': {'_classify_one': 4, 'preview_import': 1},
    'engine/display.py': {'describe_estimate': 1, 'estimate_line': 1},
    'engine/estimate.py': {'<module>': 1},
    'execution/alternatives.py': {'record_alternative_choice': 1},
    'execution/review.py': {'_notes': 1},
    'instruments/sources.py': {'<module>': 1},
    'rules/actions.py': {'respond': 1},
    'rules/model.py': {'describe': 1},
    'rules/plan.py': {'<module>': 2},
    'scenario/views.py': {'<module>': 1, 'scenario_values': 1},
    'strategy/builder_history.py': {'<module>': 9},
    'strategy/definition.py': {'changes_from': 1, 'describe': 1, 'describe_contract': 1},
    'table/model.py': {'<module>': 1, 'scenario_caption': 1},
}


def _text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{slot}" for v in node.values)
    return None


def is_sentence_shaped(text: str) -> bool:
    """A sentence a person reads: starts with a capital, a currency sign or a `{slot}`, at least three words."""
    stripped = text.strip()
    if not stripped or not (stripped[0].isupper() or stripped[0] in "{₹"):
        return False
    # words are whitespace-separated tokens holding a letter: an identifier such as VERSION_NOT_EXECUTABLE is one
    return sum(1 for token in stripped.split() if _WORD.search(token)) >= 3


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _excluded(chain: list[ast.AST]) -> bool:
    """True when the literal sits in a position that is never shown to a user (see module docstring)."""
    node, parent = chain[-1], chain[-2] if len(chain) > 1 else None
    if isinstance(parent, ast.Expr):
        return True  # docstring or bare expression statement
    for ancestor in reversed(chain[:-1]):
        if isinstance(ancestor, ast.Assert):
            return True
        if isinstance(ancestor, ast.keyword) and ancestor.arg == "detail":
            return True  # a labelled developer detail beside a render() message (e.g. TemplateError(detail=, message=))
        if isinstance(ancestor, ast.Raise):
            exc = ancestor.exc
            name = _call_name(exc) if isinstance(exc, ast.Call) else ""
            return name in BUILTIN_EXCEPTIONS
        if isinstance(ancestor, ast.Call):
            name = _call_name(ancestor)
            func = ancestor.func
            if isinstance(func, ast.Attribute) and name in LOG_METHODS:
                return True
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "re" \
                    and name in REGEX_FUNCTIONS:
                return True
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)) and ancestor.name == "__repr__":
            return True  # a developer's debugging view, never shown to a user
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return False
    del node
    return False


def scan_source(source: str, rel: str) -> list[tuple[str, int, str, str]]:
    """Every user-facing text producer in one file: (file, line, function, text)."""
    if rel in DOOR_FILES or rel in WORDING_DATA_FILES:
        return []
    tree = ast.parse(source)
    found: list[tuple[str, int, str, str]] = []

    def walk(node: ast.AST, chain: list[ast.AST], function: str) -> None:
        for child in ast.iter_child_nodes(node):
            child_chain = chain + [child]
            child_function = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            text = _text(child)
            if text is not None and is_sentence_shaped(text) and not _excluded(child_chain):
                found.append((rel, child.lineno, function, text))
            if isinstance(child, ast.JoinedStr):
                continue  # its pieces are part of the f-string already reported (or not)
            walk(child, child_chain, child_function)

    walk(tree, [tree], "<module>")
    return found


def inventory() -> list[tuple[str, int, str, str]]:
    rows: list[tuple[str, int, str, str]] = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        rows.extend(scan_source(path.read_text(encoding="utf-8"), rel))
    return rows


def _counts(rows: list[tuple[str, int, str, str]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for rel, _, function, _ in rows:
        counts[(rel, function)] += 1
    return counts


def test_print_inventory(capsys: pytest.CaptureFixture[str]) -> None:
    """Prints the inventory (file, line, function, text example): `pytest -s` shows it."""
    rows = inventory()
    with capsys.disabled():
        print(f"\nuser-facing text producers outside the catalogue: {len(rows)}")
        for rel, line, function, text in rows:
            print(f"  {rel}:{line} {function}: {text[:70]!r}")
    assert all(len(row) == 4 for row in rows)


def test_every_producer_in_scope_is_routed_through_render() -> None:
    """AC-2 / Q226: no sentence-shaped user text outside the catalogue, except the PENDING ratchet."""
    rows = inventory()
    counts = _counts(rows)
    over = {key for key, n in counts.items() if n > PENDING.get(key[0], {}).get(key[1], 0)}
    unrouted = [f"{rel}:{line} in {function}: {text[:80]!r}" for rel, line, function, text in rows
                if (rel, function) in over]
    assert not unrouted, "user-facing text built outside render():\n" + "\n".join(unrouted)


def test_pending_ratchet_only_shrinks() -> None:
    """A PENDING entry that no longer produces text must be removed, so the gap list cannot go stale."""
    counts = _counts(inventory())
    stale = [f"{rel}:{fn} listed {n}, left {counts.get((rel, fn), 0)}" for rel, fns in PENDING.items()
             for fn, n in fns.items() if counts.get((rel, fn), 0) < n]
    assert not stale, f"routed producers still listed in PENDING (remove them): {stale}"


# --- the detector itself: killing samples (mutation tests first) ---------------------------------------------------

def test_detector_flags_a_plain_string_reason() -> None:
    """Mutation: route one producer back to a plain string -> the inventory flags it."""
    src = 'def f():\n    return CheckFailure(CheckCode.EXPIRY_PASSED, "Leg 1 has already expired.")\n'
    assert [(r[1], r[2]) for r in scan_source(src, "execution/safety.py")] == [(2, "f")]


def test_detector_flags_fstring_and_concatenation_pieces() -> None:
    src = (
        'def f(x):\n'
        '    a = f"{x} is not supported. Supported underlyings: NIFTY."\n'
        '    b = "Strikes you could consider instead: " + x\n'
        '    return a, b\n'
    )
    assert [r[1] for r in scan_source(src, "m.py")] == [2, 3]


def test_detector_flags_project_exception_text_and_passes_builtin_ones() -> None:
    src = (
        'def f():\n'
        '    raise TemplateError("The template could not be loaded today.")\n'
        'def g():\n'
        '    raise ValueError("Programmer error with many words here.")\n'
    )
    assert [r[2] for r in scan_source(src, "m.py")] == ["f"]


def test_detector_skips_docstrings_logs_asserts_and_regexes() -> None:
    src = (
        'import re\n'
        'def f():\n'
        '    """A docstring with several words."""\n'
        '    logger.warning("Blocked for this many reasons today.")\n'
        '    assert x, "An assert message with words."\n'
        '    re.compile("Some Regex with words")\n'
    )
    assert scan_source(src, "m.py") == []


def test_detector_fails_closed_on_unknown_positions() -> None:
    """A sentence in a position the scan does not recognise (a dict value, a default argument) still counts."""
    src = 'LABELS = {"a": "Your rule was triggered today."}\ndef f(x="Market data is unavailable now."):\n    pass\n'
    assert [(r[1], r[2]) for r in scan_source(src, "m.py")] == [(1, "<module>"), (2, "f")]


def test_detail_keyword_is_developer_text_but_a_positional_text_is_not() -> None:
    src = (
        'def f(p):\n'
        '    raise TemplateError(detail=f"{p}: not valid YAML here", message=render("x"))\n'
        'def g(p):\n'
        '    raise TemplateError(f"{p}: not valid YAML here")\n'
    )
    assert [r[2] for r in scan_source(src, "m.py")] == ["g"]


def test_catalogue_file_is_the_one_home() -> None:
    src = 'X = "Leg 1 has already expired today."\n'
    assert scan_source(src, CATALOGUE_FILE) == []
    assert scan_source(src, "errors/gate_slots.py") == []
    assert len(scan_source(src, "errors/other.py")) == 1
