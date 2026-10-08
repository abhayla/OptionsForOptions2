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
    'engine/interfaces.py': {'__post_init__': 2},
    'errors/classes.py': {'<module>': 9},
    'execution/partial.py': {'assess': 3, 'submit_confirmed': 2},
    'execution/safety.py': {'__post_init__': 1},
    'execution/sequence.py': {'<module>': 1, '_lot_sizes': 1, '_quantities': 1, 'sequence_plan': 1, 'slice_quantity': 1},
    'marketdata/health.py': {'evaluate_health': 1},
    'marketdata/kite_provider.py': {'<module>': 2},
    'marketdata/quote.py': {'__post_init__': 3},
    'orders/model.py': {'<module>': 1},
    'range/pick_lists.py': {'<module>': 1, '__post_init__': 1},
    'reconciliation/compare.py': {'<module>': 9, '__post_init__': 7, '_check_breakdown': 1, '_check_contract_pairs': 1, 'compare': 3, 'describe': 2, 'require_id': 1, 'unexplained_changes': 3},
    'reconciliation/resolution.py': {'<module>': 7, 'record_report': 1},
    'reconciliation/triggers.py': {'<module>': 8},
    'rules/defaults.py': {'resolve_adjustment_rules': 3},
    'scenario/levels.py': {'build_level_set': 1},
    'strategy/builder_history.py': {'__init__': 1},
    'strategy/definition.py': {'_limit_value': 1},
    'strategy/guard.py': {'compare_risk': 3},
    'strategy/live_state.py': {'_pairs': 1},
    'strategy/loader.py': {'check_wording': 2, 'load_templates': 1},
    'strategy/matching.py': {'<module>': 1, '_fit': 2},
    'strategy/model.py': {'violation': 3, 'violations': 4},
    'strategy/versions.py': {'__post_init__': 2, 'apply_result': 1, 'check_contract': 1, 'check_observation': 2, 'propose_execution': 2, 'reconcile': 2, 'restore': 1},
    'table/columns.py': {'<module>': 6},
    'table/model.py': {'_greek_cell': 1, '_iv_cell': 2, '_leg_per_unit_greeks': 1, '_leg_row': 8, '_money': 1, '_net_premium_cell': 2, '_percent_cell': 1, '_points': 1, '_text': 1, '_total_pnl_percent_cell': 4, '_total_row': 10},
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
        if isinstance(ancestor, ast.keyword) and ancestor.arg == "detail":
            return True  # a labelled developer detail beside a render() message (e.g. TemplateError(detail=, message=))
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


def exception_text_flows(source: str, rel: str) -> list[tuple[str, int, str]]:
    """Every use of an `except ... as e` name inside `render(...)` or inside a non-detail argument of a `UserFacing`
    constructor: the one route by which a hidden exception's text could still reach a user."""
    tree = ast.parse(source)
    found: list[tuple[str, int, str]] = []

    def walk(node: ast.AST, chain: list[ast.AST], bound: frozenset[str]) -> None:
        for child in ast.iter_child_nodes(node):
            names = bound | {child.name} if isinstance(child, ast.ExceptHandler) and child.name else bound
            child_chain = chain + [child]
            if isinstance(child, ast.Name) and child.id in bound:
                for index in range(len(child_chain) - 2, -1, -1):
                    link = child_chain[index]
                    if not isinstance(link, ast.Call):
                        continue
                    if _call_name(link) == "render" or _exception_flow(link, child_chain, rel) is False:
                        found.append((rel, child.lineno, child.id))
                        break
            walk(child, child_chain, names)

    walk(tree, [tree], frozenset())
    return found


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
    assert [r[1] for r in exception_text_flows(src, "execution/send_guard.py")] == [5, 15]
