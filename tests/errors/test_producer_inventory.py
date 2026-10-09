"""W-024 round 9, step 1 (REQ-065 AC-2, ADR-003 Q226): inventory of every user-facing text producer.

The rule is a SHAPE, not a list of names: a string literal (plain or f-string) in backend/ofo that holds at least
two words separated by a space, whatever its first letter or case ("leg expired before execution" counts as much as
"Leg expired"), is user-facing text unless its POSITION shows it is not (below). A position this scan cannot
classify is a producer too (fail closed). The one place such text may live is the reviewed catalogue,
`backend/ofo/errors/templates.py`, whose text reaches a user only through `render()`.

Not user-facing, by position (each is a shape too): a docstring; an argument of a logging call (`logger.info`, ...);
an assert message; a pattern passed to `re.compile`/`re.search`/...; the forbidden-wording data of `ofo/wording.py` and
`ofo/strategy/wording.py` (the second layer: the phrases it refuses are not text it shows).

Round 9 part 6 (structural, run-discipline B8): the guarantee sits at the API boundary (backend/ofo_app/errors.py):
a user sees an exception's text only when the exception is an `ofo.errors.UserFacing` (its render() message), and
the INTERNAL_SYSTEM template for anything else. So a literal passed to the constructor of a NON-UserFacing exception
class is developer detail by construction and is not counted; a literal passed to a `UserFacing` type counts unless it
binds (by the real `inspect.signature`) to its `detail` parameter. The callee is resolved by IMPORT SOURCE (the
scanned module's own global, i.e. its class or the object its `from x import y` bound), never by identifier text; an
attribute call, a name shadowed in an enclosing function, or a module that does not import is unresolved, and the
literal stays counted (fail closed). `test_exception_text_never_flows_into_a_user_facing_message` closes the other
route: an `except ... as e` name used inside `render(...)` or a `UserFacing` constructor.

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
    'audit/catalogue.py': {'<module>': 31},
    'engine/display.py': {'describe_estimate': 1},
    # merged from main (W-060 forward/ModelInputs, 2026-10-08): field names and data labels, not routed yet
    'engine/inputs.py': {'__post_init__': 1},
    'engine/model.py': {'expiry_model': 3, 'model_inputs': 2},
    'marketdata/forward.py': {'<module>': 1},
    'engine/interfaces.py': {'__post_init__': 2},
    'errors/classes.py': {'<module>': 9},
    'execution/partial.py': {'assess': 3, 'submit_confirmed': 2},
    'execution/safety.py': {'__post_init__': 1},
    'execution/sequence.py': {'<module>': 1, '_lot_sizes': 1, '_quantities': 1, 'sequence_plan': 1, 'slice_quantity': 1},
    'marketdata/health.py': {'evaluate_health': 1},
    'marketdata/quote.py': {'__post_init__': 3},
    'orders/model.py': {'<module>': 1},
    'range/pick_lists.py': {'<module>': 1, '__post_init__': 1},
    'reconciliation/compare.py': {'<module>': 9, '__post_init__': 7, '_check_breakdown': 1, '_check_contract_pairs': 1, 'compare': 3, 'describe': 2, 'require_id': 1, 'unexplained_changes': 3},
    'reconciliation/resolution.py': {'<module>': 7, 'record_report': 1},
    'reconciliation/triggers.py': {'<module>': 8},
    'rules/defaults.py': {'resolve_adjustment_rules': 3},
    'scenario/levels.py': {'build_level_set': 1},
    'strategy/builder_history.py': {'__init__': 1},
    'strategy/guard.py': {'compare_risk': 3},
    'strategy/live_state.py': {'_pairs': 1},
    'strategy/loader.py': {'check_wording': 2, 'load_templates': 1},
    'strategy/matching.py': {'<module>': 1, '_fit': 2},
    'strategy/model.py': {'violation': 3, 'violations': 4},
    'strategy/versions.py': {'__post_init__': 2, 'apply_result': 1, 'check_contract': 1, 'check_observation': 2, 'propose_execution': 2, 'reconcile': 2, 'restore': 1},
    'timeline/catalogue.py': {'<module>': 12},
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


_UNRESOLVED = object()


def _module_name(rel: str) -> str:
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(["ofo", *parts])


def _bound_in(function: ast.AST, name: str) -> bool:
    """True when `name` is bound inside `function` (argument, assignment, def, import, ...): a local that shadows
    the module's name, so the callee cannot be resolved by the module's import source (fail closed)."""
    args = getattr(function, "args", None)
    if args is not None:
        every = [*args.posonlyargs, *args.args, *args.kwonlyargs, *(a for a in (args.vararg, args.kwarg) if a)]
        if any(a.arg == name for a in every):
            return True
    for node in ast.walk(function):
        if node is function:
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id == name:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                (a.asname or a.name.split(".")[0]) == name for a in node.names):
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == name:
            return True
    return False


def resolve_callee(call: ast.Call, chain: list[ast.AST], rel: str) -> object:
    """The object a call's callee names, resolved by IMPORT SOURCE: the module-level global of the scanned module
    (its own class, or the object a `from x import y` bound there), via the imported module itself. Returns
    `_UNRESOLVED` for any shape it cannot resolve: an attribute call, a name bound locally in an enclosing function,
    a module that does not import, a name it does not hold."""
    if not isinstance(call.func, ast.Name):
        return _UNRESOLVED
    name = call.func.id
    if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and _bound_in(n, name) for n in chain):
        return _UNRESOLVED
    import builtins
    import importlib

    try:
        module = importlib.import_module(_module_name(rel))
    except Exception:  # an unknown module (a test sample) or one that cannot import: fail closed
        module = None
    if module is not None and name in vars(module):
        return vars(module)[name]
    if module is None and name in BUILTIN_EXCEPTIONS:
        return getattr(builtins, name)
    if module is not None and hasattr(builtins, name):
        return getattr(builtins, name)
    return _UNRESOLVED


#: The one parameter of a `UserFacing` type that holds developer text (`str(error)`), never shown: the boundary shows
#: only `user_message`. Matched against the parameter the literal BINDS to in the real signature, not the source text.
DETAIL_PARAMETER = "detail"


def _bound_parameter(call: ast.Call, chain: list[ast.AST], target: type) -> str | None:
    """The parameter of `target(...)` that the scanned literal's argument binds to, by `inspect.signature`; None when
    it cannot be told (a *args/**kwargs splat, a signature that cannot be read): fail closed."""
    import inspect

    index = next(i for i, node in enumerate(chain) if node is call)
    below = chain[index + 1]
    try:
        params = list(inspect.signature(target).parameters.values())
    except (TypeError, ValueError):
        return None
    if isinstance(below, ast.keyword):
        return below.arg if any(p.name == below.arg for p in params) else None
    if below in call.args and not any(isinstance(a, ast.Starred) for a in call.args):
        position = call.args.index(below)
        positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        return positional[position].name if position < len(positional) else None
    return None


def _exception_flow(call: ast.Call, chain: list[ast.AST], rel: str) -> bool | None:
    """True: the call builds a NON-user-facing exception (its text is developer detail; the API boundary shows the
    INTERNAL_SYSTEM template instead). False: it builds a `UserFacing` type (its text would be shown: a producer).
    None: not an exception class, or unresolvable (the caller keeps scanning, so the literal stays counted)."""
    from ofo.errors import UserFacing

    target = resolve_callee(call, chain, rel)
    if not isinstance(target, type):
        return None
    if issubclass(target, UserFacing):
        return _bound_parameter(call, chain, target) == DETAIL_PARAMETER  # detail: hidden; else shown
    if issubclass(target, BaseException):
        return True
    return None


def _excluded(chain: list[ast.AST], rel: str = "") -> bool:
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
        if isinstance(ancestor, ast.Raise):
            exc = ancestor.exc
            name = _call_name(exc) if isinstance(exc, ast.Call) else ""
            return name in BUILTIN_EXCEPTIONS
        if isinstance(ancestor, ast.Call):
            flow = _exception_flow(ancestor, chain, rel)
            if flow is not None:
                return flow  # True: developer detail of a non-UserFacing exception; False: text into a UserFacing
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
            if text is not None and is_sentence_shaped(text) and not _excluded(child_chain, rel):
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


def test_detail_is_resolved_by_the_real_signature_not_the_keyword_name() -> None:
    """Fix round (review MAJOR-1): `detail=` is developer text only when it binds to the `detail` parameter of the
    resolved callee; an unresolved callee is counted whatever the keyword (fail closed)."""
    src = (
        'def f(p):\n'
        '    raise TemplateError(detail=f"{p}: not valid YAML here", message=render("x"))\n'
        'def g(p):\n'
        '    raise TemplateError(f"{p}: not valid YAML here")\n'
    )
    assert scan_source(src, "strategy/model.py") == []  # TemplateError(detail, *, message): both bind to detail
    assert [r[2] for r in scan_source(src, "m.py")] == ["f", "g"]  # unresolved: counted


def test_catalogue_typed_helper_result_carries_no_taint() -> None:
    src = ('from ofo.errors import render, UserFacingError\n'
           'def msg(e) -> UserFacingError:\n    return render("partial_nothing_prepared")\n'
           'def f():\n    try:\n        pass\n    except ValueError as exc:\n'
           '        return render("x", m=msg(exc))\n')
    assert exception_text_flows(src, "execution/partial.py") == []


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


# --- round 9 part 6: narrowing by structure (the API boundary hides every non-UserFacing exception) ----------------

def test_non_user_facing_project_exception_text_is_developer_detail() -> None:
    """Resolved by import source: compare.py imports VersionError (not UserFacing); its own module defines it."""
    src = 'def f(x):\n    raise VersionError(f"version {x} cannot be edited now")\n'
    assert scan_source(src, "reconciliation/compare.py") == []
    assert scan_source(src, "strategy/versions.py") == []


def test_user_facing_type_text_counts_unless_it_binds_to_detail() -> None:
    src = (
        'def f(x):\n'
        '    raise ReconciliationError(f"strategy {x} has exited here")\n'  # binds to `detail`: hidden
        'def g(x):\n'
        '    raise ReconciliationError(detail="d", message="Leg 1 has already expired.")\n'  # message: shown
        'def h(x):\n'
        '    raise SendRefused("Leg 1 has already expired.")\n'  # SendRefused(message): shown
    )
    assert [r[2] for r in scan_source(src, "reconciliation/resolution.py")] == ["g", "h"]  # h: no SendRefused import
    assert [r[2] for r in scan_source(src, "execution/send_guard.py")[2:]] == ["h"]  # resolved: a UserFacing type
    assert [r[2] for r in scan_source(src, "execution/send_guard.py")] == ["f", "g", "h"]  # no such import: counted


def test_shadowed_or_attribute_callee_is_unresolved_and_counted() -> None:
    src = (
        'def f(VersionError):\n'
        '    raise VersionError("version cannot be edited now")\n'
        'def g(mod):\n'
        '    raise mod.VersionError("version cannot be edited now")\n'
    )
    assert [r[2] for r in scan_source(src, "reconciliation/compare.py")] == ["f", "g"]


def test_mutant_treating_user_facing_types_as_detail_lets_shown_text_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: drop the UserFacing branch (every exception counts as developer detail) -> the shown text escapes."""
    src = 'def h():\n    raise SendRefused("Leg 1 has already expired.")\n'
    assert len(scan_source(src, "execution/send_guard.py")) == 1
    original = _exception_flow

    def mutant(call: ast.Call, chain: list[ast.AST], rel: str) -> bool | None:
        result = original(call, chain, rel)
        return True if result is False else result

    monkeypatch.setattr(sys.modules[__name__], "_exception_flow", mutant)
    assert scan_source(src, "execution/send_guard.py") == []


RENDER_SINKS = frozenset({"render", "render_explanation"})


#: Return types only render()/render_explanation() can build: a call to a module function annotated with one of
#: these yields catalogue text whatever its arguments were, so it does not carry an exception's text onwards.
CATALOGUE_RETURN_TYPES = frozenset({"UserFacingError", "ExplanationText"})
_CATALOGUE_FUNCTIONS: set[str] = set()


def _names_in(node: ast.AST) -> set[str]:
    """Names an expression reads, skipping calls to functions typed to return catalogue text."""
    out: set[str] = set()
    stack = [node]
    while stack:
        sub = stack.pop()
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in _CATALOGUE_FUNCTIONS:
            continue
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        stack.extend(ast.iter_child_nodes(sub))
    return out


def _targets(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def _taint_closure(fn: ast.AST, seeds: set[str]) -> set[str]:
    """Flow-insensitive (fail closed): every name assigned from an expression holding a tainted name is tainted."""
    tainted = set(seeds) | {h.name for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler) and h.name}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(fn):
            pairs: list[tuple[ast.AST, ast.AST]] = []
            if isinstance(node, ast.Assign):
                pairs = [(t, node.value) for t in node.targets]
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and node.value is not None:
                pairs = [(node.target, node.value)]
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                pairs = [(node.target, node.iter)]
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                pairs = [(i.optional_vars, i.context_expr) for i in node.items if i.optional_vars is not None]
            for target, value in pairs:
                if _names_in(value) & tainted:
                    new = _targets(target) - tainted
                    if new:
                        tainted |= new
                        changed = True
    return tainted


def exception_text_flows(source: str, rel: str) -> list[tuple[str, int, str]]:
    """Every place a caught exception's text can reach a user message: an `except ... as e` name, any name assigned
    from it (aliases, `why = str(e)`), and any parameter of a module-level function it is passed to (helpers), used
    inside `render(...)` / `render_explanation(...)` or a non-detail argument of a `UserFacing` constructor (resolved
    by import source and the real signature). Flow-insensitive and fail closed."""
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    _CATALOGUE_FUNCTIONS.clear()
    _CATALOGUE_FUNCTIONS.update(name for name, fn in functions.items()
                                if fn.returns is not None and ast.unparse(fn.returns) in CATALOGUE_RETURN_TYPES)
    every_fn = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    seeds: dict[ast.AST, set[str]] = {fn: set() for fn in every_fn}
    found: set[tuple[str, int, str]] = set()
    work = list(every_fn)
    while work:
        fn = work.pop()
        tainted = _taint_closure(fn, seeds[fn])
        for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            args = [*call.args, *(k for k in call.keywords)]
            hot = [a for a in args if _names_in(a.value if isinstance(a, ast.keyword) else a) & tainted]
            if not hot:
                continue
            name = _call_name(call)
            if name in RENDER_SINKS:
                found.add((rel, call.lineno, name))
                continue
            target = resolve_callee(call, [tree, fn, call], rel)
            from ofo.errors import UserFacing

            if isinstance(target, type) and issubclass(target, UserFacing):
                for arg in hot:
                    if _bound_parameter(call, [call, arg], target) != DETAIL_PARAMETER:
                        found.add((rel, call.lineno, target.__name__))
                continue
            helper = functions.get(name) if isinstance(call.func, ast.Name) else None
            if helper is not None:
                params = [a.arg for a in (*helper.args.posonlyargs, *helper.args.args)]
                new = set()
                for arg in hot:
                    if isinstance(arg, ast.keyword):
                        new.add(arg.arg) if arg.arg else new.update(params)
                    elif isinstance(arg, ast.Starred):
                        new.update(params)
                    else:
                        index = call.args.index(arg)
                        if index < len(params):
                            new.add(params[index])
                        elif helper.args.vararg:
                            new.add(helper.args.vararg.arg)
                if not new <= seeds[helper]:
                    seeds[helper] |= new
                    work.append(helper)
    return sorted(found)


def test_exception_text_never_flows_into_a_user_facing_message() -> None:
    rows = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        rows.extend(exception_text_flows(path.read_text(encoding="utf-8"), rel))
    assert not rows, f"exception text flowing into a user-facing message: {rows}"


def test_exception_text_flow_detector_kills_its_samples() -> None:
    src = (
        'def f():\n'
        '    try:\n'
        '        pass\n'
        '    except ValueError as exc:\n'
        '        raise SendRefused(render("x", text=str(exc)))\n'
        'def g():\n'
        '    try:\n'
        '        pass\n'
        '    except ValueError as exc:\n'
        '        raise ReconciliationError(detail=f"bad: {exc}") from exc\n'
        'def h():\n'
        '    try:\n'
        '        pass\n'
        '    except ValueError as exc:\n'
        '        raise SendRefused(str(exc))\n'
    )
    assert sorted({r[1] for r in exception_text_flows(src, "execution/send_guard.py")}) == [5, 15]


# --- fix round (review MAJOR-1): the reviewer's three flow probes, each refused ------------------------------------

def test_probe_alias_of_exception_text_is_a_flow() -> None:
    src = ('from ofo.errors import render\n'
           'def f():\n    try:\n        pass\n    except ValueError as exc:\n        why = str(exc)\n'
           '        return render("x", text=why)\n')
    assert exception_text_flows(src, "execution/send_guard.py") == [("execution/send_guard.py", 7, "render")]


def test_probe_helper_receiving_the_exception_is_a_flow() -> None:
    src = ('from ofo.errors import render\n'
           'def g(e):\n    return render("x", text=str(e))\n'
           'def f():\n    try:\n        pass\n    except ValueError as exc:\n        return g(exc)\n')
    assert exception_text_flows(src, "execution/send_guard.py") == [("execution/send_guard.py", 3, "render")]


def test_probe_render_explanation_is_a_sink_and_detail_keyword_is_resolved_by_signature() -> None:
    ex = ('from ofo.errors.explanations import render_explanation\n'
          'def f(rule):\n    try:\n        pass\n    except ValueError as exc:\n'
          '        return render_explanation("rule_alert", rule="r", detail=str(exc))\n'
          'def g():\n    return render_explanation("rule_alert", rule="r", detail="Your stop loss was hit just now")\n')
    assert exception_text_flows(ex, "rules/actions.py") == [("rules/actions.py", 6, "render_explanation")]
    assert [r[2] for r in scan_source(ex, "rules/actions.py")] == ["g"]  # detail= of a non-exception call counts
    dc = ('from dataclasses import dataclass\n@dataclass\nclass Row:\n    detail: str\n'
          'def f():\n    return Row(detail="Your order was rejected by the exchange")\n')
    assert len(scan_source(dc, "table/model.py")) == 1


def test_mutant_flow_scan_without_alias_taint_misses_the_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: taint only the except name itself -> the alias probe escapes (so the closure is load-bearing)."""
    src = ('from ofo.errors import render\n'
           'def f():\n    try:\n        pass\n    except ValueError as exc:\n        why = str(exc)\n'
           '        return render("x", text=why)\n')
    monkeypatch.setattr(sys.modules[__name__], "_taint_closure",
                        lambda fn, seeds: set(seeds) | {h.name for h in ast.walk(fn)
                                                        if isinstance(h, ast.ExceptHandler) and h.name})
    assert exception_text_flows(src, "execution/send_guard.py") == []
