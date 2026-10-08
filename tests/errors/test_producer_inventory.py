"""W-024 round 9, step 1 (REQ-065 AC-2, ADR-003 Q226): inventory of every user-facing text producer.

The rule is a SHAPE, not a list of names: a string literal (plain or f-string) in backend/ofo that holds at least
two words separated by a space, whatever its first letter or case ("leg expired before execution" counts as much as
"Leg expired"), is user-facing text unless its POSITION shows it is not (below). A position this scan cannot
classify is a producer too (fail closed). The one place such text may live is the reviewed catalogue,
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
import sys
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
    'adjustment/registry.py': {'calculator': 1, 'get': 1, 'load_rows': 7, 'register_calculator': 3},
    'audit/catalogue.py': {'<module>': 31},
    'audit/log.py': {'from_events': 1},
    'audit/models.py': {'_reject_naive_datetime': 1, 'canonical_json': 1},
    'engine/black_scholes.py': {'_solve_iv': 2},
    'engine/display.py': {'describe_estimate': 1},
    'engine/interfaces.py': {'__post_init__': 2},
    'engine/metrics.py': {'strategy_metrics': 1},
    'errors/classes.py': {'<module>': 9},
    'errors/model.py': {'verify': 3},
    'execution/partial.py': {'assess': 3, 'submit_confirmed': 2},
    'execution/safety.py': {'__post_init__': 1},
    'execution/sequence.py': {'<module>': 1, '_lot_sizes': 1, '_quantities': 1, 'sequence_plan': 1, 'slice_quantity': 1},
    'instruments/models.py': {'check_broker_code': 1},
    'marketdata/health.py': {'evaluate_health': 1},
    'marketdata/quote.py': {'__post_init__': 3},
    'orders/model.py': {'<module>': 1, 'apply_fill': 1, 'clear_reconciliation_block': 1, 'reconcile_cumulative': 1},
    'range/pick_lists.py': {'<module>': 1, '__post_init__': 1},
    'reconciliation/blocking.py': {'blocked_strategy_ids': 3},
    'reconciliation/compare.py': {'<module>': 9, '__post_init__': 7, '_check_breakdown': 1, '_check_contract_pairs': 1, 'compare': 3, 'describe': 2, 'require_id': 1, 'unexplained_changes': 3},
    'reconciliation/resolution.py': {'<module>': 7, '_require_audit': 1, '_require_record': 1, '_start': 8, 'adopt_broker_position': 1, 'mark_exited_broker_flat': 2, 'prepare_closing_order': 2, 'record_report': 5},
    'reconciliation/triggers.py': {'<module>': 8, '_records': 3, 'plan_run': 2},
    'rules/defaults.py': {'resolve_adjustment_rules': 3},
    'scenario/levels.py': {'build_level_set': 1},
    'strategy/builder_history.py': {'__init__': 1, '_check_legs': 4, '_check_no_duplicate_with_others': 1, '_check_not_executed': 1, '_entry_by_seq': 1, '_leg_at': 1, 'add_leg': 1, 'change_expiry': 2, 'change_strike': 1, 'remove_leg': 1, 'rename': 1, 'reorder_legs': 1, 'restore': 1, 'toggle_display': 1, 'undo': 1},
    'strategy/definition.py': {'__post_init__': 11, '_limit_value': 1, '_preference_value': 1, 'changes_from': 1, 'from_engine': 1},
    'strategy/guard.py': {'compare_risk': 3},
    'strategy/linear.py': {'parse_expression': 4},
    'strategy/live_state.py': {'__post_init__': 8, '_pairs': 1},
    'strategy/loader.py': {'_build': 2, '_construct_unique_mapping': 2, 'check_catalogue': 2, 'check_wording': 4, 'load_templates': 2},
    'strategy/matching.py': {'<module>': 1, '_fit': 2, 'match': 1, 'match_shape': 1},
    'strategy/model.py': {'__post_init__': 18, '_check_constraints': 6, '_check_legs': 5, 'resolve_params': 2, 'resolve_template': 5, 'violation': 3, 'violations': 4},
    'strategy/modification.py': {'__post_init__': 8, '_engine_legs': 2, '_gate_legs': 1, '_guard_binding': 1, '_pending_binding': 1, 'apply_changes': 8, 'confirm_modification': 3, 'execute_confirmed_modification': 1, 'prepare_confirmed_modification': 6, 'propose_modification': 3},
    'strategy/versions.py': {'__init__': 1, '__post_init__': 10, '_add_version': 1, '_append_history': 1, '_check_time': 2, '_definition_from': 3, '_refuse_if_exited': 1, '_refuse_while_blocked': 2, 'apply_result': 7, 'check_contract': 6, 'check_observation': 5, 'confirm': 3, 'edit': 4, 'mark_exited': 4, 'propose_execution': 3, 'reconcile': 6, 'restore': 3, 'version': 1},
    'table/columns.py': {'<module>': 6},
    'table/model.py': {'_greek_cell': 1, '_iv_cell': 2, '_leg_per_unit_greeks': 1, '_leg_row': 8, '_money': 1, '_net_premium_cell': 2, '_percent_cell': 1, '_points': 1, '_text': 1, '_total_pnl_percent_cell': 4, '_total_row': 10},
    'timeline/catalogue.py': {'<module>': 12},
    'timeline/log.py': {'from_entries': 3},
    'timeline/records.py': {'__post_init__': 2, 'from_evaluation': 3},
}


def _text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{slot}" for v in node.values)
    return None


def is_sentence_shaped(text: str) -> bool:
    """Sentence-like: at least two words (tokens holding a letter) separated by a space, whatever the case."""
    # an identifier such as VERSION_NOT_EXECUTABLE or a path such as a/b.py is one token, not a sentence
    return sum(1 for token in text.split() if _WORD.search(token)) >= 2


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
    if isinstance(parent, ast.Dict) and any(node is key for key in parent.keys):
        return True  # a dict key is a lookup name, never shown
    for index, link in enumerate(chain[:-1]):
        below = chain[index + 1]
        if isinstance(link, ast.Subscript) and below is link.slice:
            return True  # a forward-reference type such as tuple[str, "Decimal | None"]
        if isinstance(link, ast.AnnAssign) and below is link.annotation:
            return True
        if isinstance(link, ast.arg) and below is link.annotation:
            return True
        if isinstance(link, (ast.FunctionDef, ast.AsyncFunctionDef)) and below is link.returns:
            return True
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


# --- round 9 part 5: the detector fails closed on lowercase shapes -------------------------------------------------

def _capital_only_shape(text: str) -> bool:
    """The old, fail-open shape (kept here as the mutant): capital/currency/slot start and three words."""
    stripped = text.strip()
    if not stripped or not (stripped[0].isupper() or stripped[0] in "{\u20b9"):
        return False
    return sum(1 for token in stripped.split() if _WORD.search(token)) >= 3


LOWERCASE_SAMPLES = (
    'def f():\n    raise TemplateError("leg expired before execution")\n',
    'def f(x):\n    return f"legs have expired: {x}"\n',
    'def f(x):\n    return f"leg {x} expired before execution"\n',
    'def f():\n    return "not available"\n',
    'LABEL = "rule triggered"\n',
)


@pytest.mark.parametrize("src", LOWERCASE_SAMPLES)
def test_lowercase_user_text_is_flagged(src: str) -> None:
    assert len(scan_source(src, "m.py")) == 1


@pytest.mark.parametrize("src", LOWERCASE_SAMPLES)
def test_mutant_capital_letter_condition_lets_lowercase_text_through(src: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: re-add the capital-letter condition -> the lowercase samples escape, so the test above would be red."""
    monkeypatch.setattr(sys.modules[__name__], "is_sentence_shaped", _capital_only_shape)
    assert scan_source(src, "m.py") == []


def test_single_words_identifiers_keys_and_annotations_are_not_sentences() -> None:
    src = (
        'import typing\n'
        'KEY = {"market data": 1}\n'
        'def f(a: "Decimal | None", b="sold") -> "list[int] | None":\n'
        '    x: "weakref.Ref[Foo, Bar]" = None\n'
        '    return typing.cast(tuple[str, "Decimal | None"], VERSION_NOT_EXECUTABLE)\n'
    )
    assert scan_source(src, "m.py") == []
