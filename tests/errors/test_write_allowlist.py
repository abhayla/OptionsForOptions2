"""W-024 round 8 (ADR-056 item 1): the ALLOWLIST scan that replaces round 7's denylist of shapes.

Spec basis:
- ADR-056 decision (1): "the allowlist design - no attribute assignment on any imported module in
  backend/ofo plus a runtime identity check of the wording checker."
- ADR-003 Q235: the checks "stop accidental misuse by the platform's own code" and "are flagged in CI
  when code reaches into their internals".

Root cause of rounds 5-7 (issue 30): each round listed the code shapes that rebind the checker and
each verifier found a shape not on the list. This scan does not ask WHICH object is written. Writes
are found by the AST node's `ctx` (Store / Del), so every statement form (`=`, `+=`, `del`, `for`,
`with ... as`, comprehension targets) is seen. Allowed, by AST shape only:

1. A store or delete of a plain name (`x = ...`, `del x`).
2. A store or delete of an item chain on a plain name (`d[k] = v`, `d[a][b] = v`, `del d[k]`).
3. An attribute (or item) write rooted at `self`/`cls` ONLY when that name is the first parameter of
   a function defined directly in a class body (not a staticmethod), and the name is never rebound
   in that function (assignment, for/with/walrus/comprehension target, except-as, import-as, del,
   global/nonlocal, match capture, a nested def/class of that name). Fix round 1: judged by binding,
   not by the name text (`self = wording; self.x = f` and `def patch(self, f): self.x = f` fail).

Everything else that writes an attribute fails, and a write whose chain root is not a name
(`f().x = 1`) cannot be classified and fails ("fail closed").

Banned outright, as a call, a bare reference, an attribute, an imported name or a string constant:
`setattr`, `delattr`, `vars`, `globals`, `__import__`, `exec`, `eval`, `import_module`, `reload`,
`setitem`, `delitem` (operator), `__builtins__`; the attributes `__dict__`, `__globals__`,
`__setattr__`, `__delattr__`, `__setitem__`, `__delitem__`; any `.modules` of a name bound to `sys`
(so no store/del/update/pop on sys.modules, direct or aliased); `.update/.pop/.popitem/.clear/
.setdefault` called on a name bound by an import (a module or another module's object) or on an
attribute chain rooted at one; and (fix round 1, finding 1) any `from <ofo.wording> import <name>`,
absolute or relative, so a caller holds the module and every rebind is a module-attribute write.

The ONLY exception shape, with no list: `object.__setattr__(self, ...)` inside `__post_init__(self)`
of a class decorated `@dataclass(frozen=True)` / `@dataclasses.dataclass(frozen=True)`, `self` bound
as in rule 3, not inside a nested def/lambda/class.

Existing code outside these shapes is listed in `ALLOWLIST` (file, statement pattern, reason). A
pattern must FULL-match the source of the one simple statement that holds the hit (fix round 1,
finding 4), so a second statement on the same line (`a; wording.f = g`) is judged on its own.

Fix round 2: a name an import in the file bound to ofo.wording (any alias, absolute or relative,
and the root `ofo` of `import ofo.wording`) is never stored, deleted, re-imported over, or declared
`global`/`nonlocal` anywhere in that file (`shared_wording = fake`,
`wording = types.SimpleNamespace(check_platform_text=print)`).

Not claimed (named limits):
- a name assembled at run time (`getattr(builtins, "set" + "attr")`);
- `C.m(<module>, f)`: a method called unbound with a module as `self` (its `self.x = f` is a
  legal method write to the scan);
- a caller that catches the checker's ValueError and shows the text anyway: the scan sees writes,
  not what a caller does with a refusal;
- code outside backend/ofo.
Q235 puts deliberate runtime replacement out of scope beyond this CI flag and the runtime checks in
`ofo.wording` (read-only module, identity check on every read) and `ofo.errors.model`. Because
ofo.wording is read-only, `importlib.reload(ofo.wording)` raises: tests must not reload or patch it
except through the monkeypatch-based namespace swaps in tests/errors/test_checker_identity.py.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
BACKEND_OFO_DIR = BACKEND_DIR / "ofo"

#: Roots whose attributes a method may write: the instance or the class being defined.
ALLOWED_WRITE_ROOTS: frozenset[str] = frozenset({"self", "cls"})

#: Names that write, read-for-write, execute or reload by name.
BANNED_NAMES: frozenset[str] = frozenset({
    "setattr", "delattr", "vars", "globals", "__import__", "exec", "eval", "import_module", "reload",
    "setitem", "delitem", "__builtins__",
})

#: Attribute names that hand out or write an object's namespace.
BANNED_DUNDERS: frozenset[str] = frozenset({
    "__dict__", "__globals__", "__builtins__", "__setattr__", "__delattr__", "__setitem__", "__delitem__",
})

#: Mapping-mutating methods refused on an imported name or a chain rooted at one.
MUTATING_METHODS: frozenset[str] = frozenset({"update", "pop", "popitem", "clear", "setdefault"})

#: The checker module: nothing may be imported FROM it by name.
CHECKER_MODULE = "ofo.wording"

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


@dataclass(frozen=True)
class AllowlistEntry:
    """One reviewed exception: the file (relative to backend/ofo), a regex that must FULL-match the
    source of the simple statement holding the hit, and why the write is safe."""

    file: str
    statement: str
    reason: str


_DECIMAL_CONTEXT = "a decimal.localcontext() copy bound by `with ... as ctx`: thread-local arithmetic precision"
ALLOWLIST: tuple[AllowlistEntry, ...] = (
    AllowlistEntry("audit/log.py", r"log\._events = list\(events\)",
                   "AuditLog.load: `log = cls()` two lines up; fills the new log, then verifies it"),
    AllowlistEntry("engine/metrics.py", r"ctx\.prec = 60", _DECIMAL_CONTEXT),
    AllowlistEntry("engine/model.py", r"object\.__setattr__\(obj, name, fields\[name\]\)",
                   "W-060 gated _make: `obj = object.__new__(cls)` just above, after the token check; fills a "
                   "frozen ModelInputs record whose __setattr__ refuses every later change"),
    AllowlistEntry("table/model.py", r"ctx\.prec = 50", _DECIMAL_CONTEXT),
    AllowlistEntry("entitlements/ledger.py", r'object\.__setattr__\(history, "user_id", user_id\)',
                   "_restore: `history = object.__new__(StoredHistory)` just above; fills a frozen record"),
    AllowlistEntry("entitlements/ledger.py", r'object\.__setattr__\(history, "events", tuple\(events\)\)',
                   "_restore: `history = object.__new__(StoredHistory)` just above; fills a frozen record"),
    AllowlistEntry("entitlements/ledger.py", r"object\.__setattr__\(built, name, value\)",
                   "EntitlementLedger._with: `built = object.__new__(EntitlementLedger)` just above"),
    AllowlistEntry("execution/partial.py", r"object\.__setattr__\(self, name, value\)",
                   "Preparation.__init__ fills its own fields; its __setattr__ refuses every later change"),
    AllowlistEntry("execution/partial.py", r'object\.__setattr__\(preparation, "_consumed", True\)',
                   "marks a Preparation (type-checked just above) as used, so it cannot be sent twice"),
    AllowlistEntry("execution/send_guard.py", r'object\.__setattr__\(self, "(resolve_all|submit)", (resolve_all|submit)\)',
                   "the send sink's __init__ fills its own two closures; its __setattr__ refuses changes"),
    AllowlistEntry("marketdata/fanout.py", r"sub\.lagging = (False|True)",
                   "W-059 fan-out: `sub = self._subs[handle]` just above; the fan-out's own private per-subscriber "
                   "record (no text, a queue-state flag)"),
    AllowlistEntry("marketdata/fanout.py", r"sub\.dropped \+= 1",
                   "W-059 fan-out: `sub = self._subs[handle]` just above; counts quotes dropped from its own queue"),
    AllowlistEntry("instruments/catalogue.py", r"entry\.currently_listed = False",
                   "an entry of the catalogue's own self._entries dict, iterated just above"),
    AllowlistEntry("marketdata/health.py",
                   r'object\.__setattr__\(final, "validation_errors", final\.validation_errors \+ \(result\.reason,\)\)',
                   "`final = dataclasses.replace(...)` just above: a fresh frozen copy this function returns"),
    AllowlistEntry("orders/model.py", r"object\.__setattr__\(clone, f\.name, getattr\(self, f\.name\)\)",
                   "Order._copy_with: `clone = object.__new__(Order)` just above"),
    AllowlistEntry("orders/model.py", r'object\.__setattr__\(clone, "_state", state\)',
                   "Order._copy_with: `clone = object.__new__(Order)` just above"),
    AllowlistEntry("orders/model.py", r'object\.__setattr__\(updated, "broker_order_id", boid\)',
                   "OrderBook: `updated = order._copy_with(...)` just above, a copy the book owns"),
    AllowlistEntry("reconciliation/compare.py",
                   r"by_(expiry|strike)\.setdefault\(\(other\[:2\], diff\[other\], other\[[23]\]\), \{\}\)\[other\] = None",
                   "a local dict of dicts built in this function (setdefault returns the inner dict)"),
    AllowlistEntry("rules/conditions.py", r'object\.__setattr__\(node, "children", children\)',
                   "_check_children, called from AllOf/AnyOf __post_init__ with that node: freezes its children"),
    AllowlistEntry("strategy/versions.py", r"object\.__setattr__\(self, name, value\)",
                   "StrategyRecord._set: the record's own fields; its __setattr__ refuses outside writes"),
    AllowlistEntry("timeline/log.py",
                   r'object\.__setattr__\(self, "_(strategy_id|clock|entries|follow_ups|recorded)", '
                   r'(_require_id\(strategy_id, "strategy_id"\)|clock|\[\]|\{\})\)',
                   "Timeline.__init__ (a __slots__ class) fills its own five slots"),
    AllowlistEntry("timeline/log.py", r"timeline\._(follow_ups\[entry\.seq\] = \{\}|recorded\[entry\.content\] = entry\.seq)",
                   "Timeline.load: rebuilds the index dicts of the timeline it just built and verified"),
    AllowlistEntry("wording.py", r"_this_module\.__class__ = _FrozenModule",
                   "ofo.wording makes ITSELF read-only (fix round 1, the structural guarantee); runs once at import"),
)


@dataclass(frozen=True)
class Hit:
    line: int
    message: str
    statement: str | None  # source of the innermost statement holding the hit


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _write_root(node: ast.AST) -> ast.AST:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node


def _is_item_chain(node: ast.AST) -> bool:
    """`d[k]`, `d[k][j]`: only Subscripts down to a plain name (no attribute anywhere in the chain)."""
    if not isinstance(node, ast.Subscript):
        return False
    while isinstance(node, ast.Subscript):
        node = node.value
    return isinstance(node, ast.Name)


def _own_scope(fn: ast.AST) -> list[ast.AST]:
    """Every node inside `fn`'s body, not descending into a nested def, lambda or class (their
    own nodes are listed, so a nested `def self` is seen as a binding)."""
    found: list[ast.AST] = []
    stack: list[ast.AST] = list(getattr(fn, "body", []))
    while stack:
        node = stack.pop()
        found.append(node)
        if isinstance(node, _SCOPE_NODES):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return found


def _binds(node: ast.AST, name: str) -> bool:
    """True if `node` (re)binds or unbinds `name` in the scope it sits in."""
    if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
        return True
    if isinstance(node, ast.ExceptHandler) and node.name == name:
        return True
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any((a.asname or a.name.split(".")[0]) == name for a in node.names)
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return name in node.names
    if isinstance(node, (*_FUNCTION_NODES, ast.ClassDef)) and node.name == name:
        return True
    if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == name:
        return True
    if isinstance(node, ast.MatchMapping) and node.rest == name:
        return True
    return False


def _is_bound_instance(root: ast.Name, parents: dict[int, ast.AST]) -> bool:
    """Rule 3: `root` (`self`/`cls`) is the first parameter of the innermost function around it,
    that function sits directly in a class body, is not a staticmethod, and never rebinds it."""
    if root.id not in ALLOWED_WRITE_ROOTS:
        return False
    node: ast.AST = root
    while id(node) in parents:
        node = parents[id(node)]
        if isinstance(node, (*_FUNCTION_NODES, ast.Lambda, ast.ClassDef)):
            break
    else:
        return False
    if not isinstance(node, _FUNCTION_NODES) or not isinstance(parents.get(id(node)), ast.ClassDef):
        return False
    if any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list):
        return False
    positional = [*node.args.posonlyargs, *node.args.args]
    if not positional or positional[0].arg != root.id:
        return False
    return not any(_binds(n, root.id) for n in _own_scope(node))


def _is_dataclass_frozen(decorator: ast.AST) -> bool:
    """`@dataclass(frozen=True)` or `@dataclasses.dataclass(frozen=True)`, exactly."""
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    named = (isinstance(func, ast.Name) and func.id == "dataclass") or (
        isinstance(func, ast.Attribute)
        and func.attr == "dataclass"
        and isinstance(func.value, ast.Name)
        and func.value.id == "dataclasses"
    )
    return named and any(
        kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in decorator.keywords
    )


def _allowed_post_init_setattr(tree: ast.AST, parents: dict[int, ast.AST]) -> set[int]:
    """`id()` of every `object.__setattr__` Attribute node in the one allowed shape."""
    allowed: set[int] = set()
    for cls_node in ast.walk(tree):
        if not isinstance(cls_node, ast.ClassDef):
            continue
        if not any(_is_dataclass_frozen(d) for d in cls_node.decorator_list):
            continue
        for fn in cls_node.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "__post_init__"):
                continue
            for call in _own_scope(fn):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "__setattr__"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "object"
                    and len(call.args) == 3
                    and not call.keywords
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                    and _is_bound_instance(call.args[0], parents)
                ):
                    allowed.add(id(func))
    return allowed


def _resolve_from(node: ast.ImportFrom, module: str, is_package: bool) -> str:
    """The absolute module an `ImportFrom` reads from (`from ..wording import x` in ofo.errors.slots
    -> ofo.wording)."""
    if node.level == 0:
        return node.module or ""
    package = module.split(".") if is_package else module.split(".")[:-1]
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
    return ".".join([*base, *([node.module] if node.module else [])])


def _import_bound_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(every name bound by an import statement, the names bound to the `sys` module)."""
    imported: set[str] = set()
    sys_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                imported.add(bound)
                if alias.name == "sys":
                    sys_names.add(bound)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
    return imported, sys_names


def _checker_bindings(tree: ast.AST, module: str, is_package: bool) -> tuple[set[str], set[int]]:
    """(names an import in this file bound to ofo.wording or to its root package `ofo`, `id()` of
    those import nodes). `import ofo.wording` binds `ofo`; `import ofo.wording as w` binds `w`;
    `from ofo import wording [as w]` and `from .. import wording` bind `wording`/`w`."""
    names: set[str] = set()
    nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == CHECKER_MODULE or alias.name.startswith(CHECKER_MODULE + "."):
                    names.add(alias.asname or alias.name.split(".")[0])
                    nodes.add(id(node))
        elif isinstance(node, ast.ImportFrom):
            source_module = _resolve_from(node, module, is_package)
            for alias in node.names:
                if f"{source_module}.{alias.name}" == CHECKER_MODULE:
                    names.add(alias.asname or alias.name)
                    nodes.add(id(node))
    return names, nodes


def _enclosing_statement(node: ast.AST, parents: dict[int, ast.AST]) -> ast.stmt | None:
    while node is not None and not isinstance(node, ast.stmt):
        node = parents.get(id(node))
    return node


def scan_source(source: str, module: str = "ofo.sample", is_package: bool = False) -> list[Hit]:
    """Every write/reach in `source` outside the allowed shapes (module docstring). `module` is the
    dotted name of the file, used to resolve relative imports."""
    tree = ast.parse(source)
    parents = _parents(tree)
    allowed_setattr = _allowed_post_init_setattr(tree, parents)
    imported, sys_names = _import_bound_names(tree)
    hits: list[Hit] = []

    def hit(node: ast.AST, message: str) -> None:
        # The innermost statement: for a compound one (a `for`/`with` target) that is its whole
        # source, keywords included, which no entry pattern (a plain statement) can full-match.
        stmt = _enclosing_statement(node, parents)
        hits.append(Hit(getattr(node, "lineno", 0), message,
                        ast.get_source_segment(source, stmt) if stmt is not None else None))

    checker_names, checker_imports = _checker_bindings(tree, module, is_package)
    for node in ast.walk(tree):
        # --- fix round 2: a name an import bound to ofo.wording is never rebound ---------------
        if id(node) not in checker_imports:
            for name in checker_names:
                if _binds(node, name):
                    hit(node, f"rebinds {name!r}, which an import bound to {CHECKER_MODULE}")
        # --- writes, found by context ------------------------------------------------------------
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            verb = "deletes" if isinstance(node.ctx, ast.Del) else "writes"
            root = _write_root(node)
            if not isinstance(root, ast.Name):
                hit(node, f"{verb} through a {type(root).__name__} root: cannot classify (fail closed)")
            elif _is_item_chain(node):
                pass  # rule 2
            elif not _is_bound_instance(root, parents):
                kind = "an attribute" if isinstance(node, ast.Attribute) else "an item"
                hit(node, f"{verb} {kind} rooted at {root.id!r} (not the bound self/cls of a method)")
        # --- banned names ---------------------------------------------------------------------
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            hit(node, f"uses {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in BANNED_NAMES:
            hit(node, f"uses .{node.attr}")
        if isinstance(node, ast.ImportFrom):
            source_module = _resolve_from(node, module, is_package)
            for alias in node.names:
                if alias.name in BANNED_NAMES or (alias.name == "*" and source_module in {"importlib", "builtins", "operator", "sys"}):
                    hit(node, f"imports {alias.name} from {source_module}")
                if source_module == CHECKER_MODULE:
                    hit(node, f"imports {alias.name!r} from {CHECKER_MODULE} by name (use the module: wording.<fn>)")
                if source_module == "sys" and alias.name == "modules":
                    hit(node, "imports sys.modules")
        # --- namespace dunders ----------------------------------------------------------------
        if isinstance(node, ast.Attribute) and node.attr in BANNED_DUNDERS and id(node) not in allowed_setattr:
            hit(node, f"reaches .{node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in BANNED_DUNDERS | BANNED_NAMES:
            hit(node, f"names {node.value!r} as a string")
        # --- sys.modules, any form ------------------------------------------------------------
        if (isinstance(node, ast.Attribute) and node.attr == "modules"
                and isinstance(node.value, ast.Name) and node.value.id in sys_names):
            hit(node, f"reaches {node.value.id}.modules")
        # --- mapping mutation on an imported name ---------------------------------------------
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in MUTATING_METHODS):
            receiver_root = _write_root(node.func.value)
            if not isinstance(receiver_root, ast.Name):
                if isinstance(node.func.value, (ast.Attribute, ast.Subscript)):
                    hit(node, f".{node.func.attr}() on a {type(receiver_root).__name__} root: cannot classify (fail closed)")
            elif receiver_root.id in imported:
                hit(node, f".{node.func.attr}() on {receiver_root.id!r}, a name bound by an import")
    return hits


def _source_files() -> list[Path]:
    return sorted(p for p in BACKEND_OFO_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _module_of(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(BACKEND_DIR).with_suffix("").parts)
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


def offences_in(rel: str, source: str, module: str = "ofo.sample", is_package: bool = False) -> tuple[list[str], list[AllowlistEntry]]:
    """(offences, allowlist entries used) for `source` as if it were backend/ofo/<rel>."""
    offences: list[str] = []
    used: list[AllowlistEntry] = []
    for h in scan_source(source, module, is_package):
        entry = None
        if h.statement is not None:
            entry = next((e for e in ALLOWLIST if e.file == rel and re.fullmatch(e.statement, h.statement)), None)
        if entry is None:
            offences.append(f"backend/ofo/{rel}:{h.line}: {h.message}: {h.statement}")
        else:
            used.append(entry)
    return offences, used


def scan_tree() -> tuple[list[str], dict[AllowlistEntry, int]]:
    """(offences not covered by an allowlist entry, hits per allowlist entry) over backend/ofo."""
    offences: list[str] = []
    counts: dict[AllowlistEntry, int] = {e: 0 for e in ALLOWLIST}
    for path in _source_files():
        module, is_package = _module_of(path)
        found, used = offences_in(path.relative_to(BACKEND_OFO_DIR).as_posix(), path.read_text(encoding="utf-8"),
                                  module, is_package)
        offences += found
        for entry in used:
            counts[entry] += 1
    return offences, counts


# --- The scan over backend/ofo -------------------------------------------------------------------

def test_backend_ofo_writes_only_through_self_or_cls_or_a_named_allowlist_entry() -> None:
    """ADR-056 (1): the scan over backend/ofo is clean outside the named ALLOWLIST. Prints every
    allowlist entry, so the exceptions are visible in the test log."""
    for entry in ALLOWLIST:
        print(f"ALLOWLIST backend/ofo/{entry.file}  /{entry.statement}/  - {entry.reason}")
    offences, _ = scan_tree()
    assert not offences, "\n".join(offences)


def test_every_allowlist_entry_still_matches_a_hit() -> None:
    """A stale exception (its code was changed or removed) is deleted, not kept."""
    _, used = scan_tree()
    stale = [f"{e.file} /{e.statement}/" for e, n in used.items() if n == 0]
    assert not stale, "allowlist entries that match nothing: " + "; ".join(stale)


def test_allowlist_does_not_excuse_a_second_statement_on_the_same_line() -> None:
    """Fix round 1, finding 4: the reviewer's one-line repro is flagged."""
    line = 'object.__setattr__(final, "validation_errors", ()); wording.find_advice_wording = f\n'
    offences, _ = offences_in("marketdata/health.py", "from ofo import wording\n" + line)
    assert any("rooted at 'wording'" in o for o in offences), offences
    exact = 'object.__setattr__(final, "validation_errors", final.validation_errors + (result.reason,))\n'
    assert offences_in("marketdata/health.py", exact)[0] == []  # the entry itself still excuses its statement
    tail = exact.rstrip("\n") + "; setattr(wording, 'x', f)\n"
    assert offences_in("marketdata/health.py", tail)[0] != []


def test_allowlist_does_not_excuse_a_compound_statement() -> None:
    """A hit inside a compound statement header (a `for`/`with` target) has no single statement to
    match, so no entry can excuse it."""
    offences, _ = offences_in("engine/metrics.py", "for ctx.prec in [60]:\n    pass\n")
    assert offences


# --- Samples the scan must flag ------------------------------------------------------------------

FLAGGED = {
    # The two round-7 escapes ADR-056 names (issue 30, round-7 comment).
    "relative-import rebind": "from .. import wording\nwording.find_advice_wording = f",
    "importlib rebind": 'import importlib\nimportlib.import_module("ofo.wording").x = f',
    # The other round-7 residuals.
    "relative submodule rebind": "from ..errors import slots\nslots.X = 1",
    "variable holding a module": "import ofo.wording\nw = ofo.wording\nw.x = f",
    "vars item": 'import ofo.wording\nvars(ofo.wording)["find_advice_wording"] = f',
    "__dict__.update": "import ofo.wording\nofo.wording.__dict__.update(find_advice_wording=f)",
    "setattr on a variable": 'm = get()\nsetattr(m, "find_advice_wording", f)',
    # Every write form, found by AST context.
    "absolute rebind": "import ofo.wording\nofo.wording.find_advice_wording = f",
    "aliased rebind": "import ofo.wording as w\nw.check_platform_text = None",
    "augmented assign": "from ofo import wording\nwording.Q226_BARE_WORDS += ('x',)",
    "annotated assign": "from ofo import wording\nwording.X: int = 1",
    "delete attribute": "from ofo import wording\ndel wording.find_advice_wording",
    "tuple-unpack target": "from ofo import wording\na, wording.x = 1, 2",
    "starred target": "from ofo import wording\na, *wording.x = 1, 2, 3",
    "for target": "from ofo import wording\nfor wording.x in [f]:\n    pass",
    "with target": "from ofo import wording\nwith ctx() as wording.x:\n    pass",
    "comprehension target": "from ofo import wording\n[0 for wording.x in [f]]",
    "item of a module attribute": "from ofo import wording\nwording.PATTERNS[0] = ('', '')",
    "item of an attribute of a local": "obj.d[k] = v",
    "delete item of an attribute": "del obj.d[k]",
    "write through a call root (fail closed)": "get_module().x = f",
    "write through a subscript-call root (fail closed)": "mods()[0].x = f",
    # Banned names, called, referenced, imported or spelled as a string.
    "setattr": "setattr(m, 'x', f)",
    "delattr": "delattr(m, 'x')",
    "vars": "v = vars(m)",
    "globals": "globals()['x'] = f",
    "__import__": "m = __import__('ofo.wording')",
    "exec": "exec('x = 1')",
    "eval": "eval('1')",
    "import_module from-import": "from importlib import import_module",
    "import_module attribute": "import importlib\nm = importlib.import_module(name)",
    "builtins.setattr": "import builtins\nbuiltins.setattr(m, 'x', f)",
    "setattr held in a variable": "s = setattr\ns(m, 'x', f)",
    "star import from importlib": "from importlib import *",
    "getattr string __dict__": "d = getattr(m, '__dict__')",
    "getattr string setattr": "import builtins\ns = getattr(builtins, 'setattr')",
    "__dict__ read": "d = m.__dict__",
    "type.__setattr__": "type.__setattr__(C, 'x', f)",
    "__delattr__": "object.__delattr__(m, 'x')",
    "object.__setattr__ on a module": "import ofo.wording\nobject.__setattr__(ofo.wording, 'x', f)",
    "object.__setattr__ in a plain function": "def g(self):\n    object.__setattr__(self, 'x', 1)",
    "object.__setattr__ in a non-frozen dataclass": (
        "@dataclass\nclass C:\n    def __post_init__(self):\n        object.__setattr__(self, 'x', 1)"
    ),
    "object.__setattr__ in a dataclass(order=True)": (
        "@dataclass(order=True)\nclass C:\n    def __post_init__(self):\n        object.__setattr__(self, 'x', 1)"
    ),
    "object.__setattr__ in a dataclass(frozen=False)": (
        "@dataclass(frozen=False)\nclass C:\n    def __post_init__(self):\n        object.__setattr__(self, 'x', 1)"
    ),
    "object.__setattr__ under another decorator(frozen=True)": (
        "@attrs(frozen=True)\nclass C:\n    def __post_init__(self):\n        object.__setattr__(self, 'x', 1)"
    ),
    "object.__setattr__ in a frozen dataclass __init__": (
        "@dataclass(frozen=True)\nclass C:\n    def __init__(self):\n        object.__setattr__(self, 'x', 1)"
    ),
    "object.__setattr__ on another object in __post_init__": (
        "@dataclass(frozen=True)\nclass C:\n    def __post_init__(self):\n        object.__setattr__(m, 'x', 1)"
    ),
    "object.__setattr__ in a def nested in __post_init__": (
        "@dataclass(frozen=True)\nclass C:\n    def __post_init__(self):\n"
        "        def h(self):\n            object.__setattr__(self, 'x', 1)"
    ),
    "object.__setattr__ after self rebound in __post_init__": (
        "@dataclass(frozen=True)\nclass C:\n    def __post_init__(self):\n"
        "        self = wording\n        object.__setattr__(self, 'x', f)"
    ),
    # Fix round 1, finding 2: self/cls judged by binding, not by name.
    "module-level self = wording": "from ofo import wording\nself = wording\nself.x = f",
    "module-level for self": "from ofo import wording\nfor self in [wording]:\n    self.x = f",
    "plain function with a self parameter": "def patch(self, f):\n    self.x = f",
    "method rebinds self by assignment": "class C:\n    def m(self):\n        self = wording\n        self.x = f",
    "method rebinds self by for": "class C:\n    def m(self):\n        for self in [wording]:\n            self.x = f",
    "method rebinds self by with": "class C:\n    def m(self):\n        with cm() as self:\n            self.x = f",
    "method rebinds self by walrus": "class C:\n    def m(self):\n        (self := wording)\n        self.x = f",
    "method rebinds self by except-as": (
        "class C:\n    def m(self):\n        try:\n            pass\n        except E as self:\n            self.x = f"
    ),
    "method rebinds self by import-as": "class C:\n    def m(self):\n        import ofo.wording as self\n        self.x = f",
    "method rebinds self by del": "class C:\n    def m(self):\n        del self\n        self.x = f",
    "method declares global self": "class C:\n    def m(self):\n        global self\n        self.x = f",
    "method defines a nested def self": "class C:\n    def m(self):\n        def self():\n            pass\n        self.x = f",
    "method rebinds self by match capture": (
        "class C:\n    def m(self, v):\n        match v:\n            case self:\n                self.x = f"
    ),
    "method rebinds self in a comprehension": "class C:\n    def m(self):\n        [0 for self in [wording]]\n        self.x = f",
    "nested def with a self parameter": "class C:\n    def m(self):\n        def h(self):\n            self.x = f",
    "lambda with a self parameter": "class C:\n    def m(self):\n        g = lambda self: [0 for self.x in [f]]",
    "staticmethod with a self parameter": "class C:\n    @staticmethod\n    def m(self):\n        self.x = f",
    "self is not the first parameter": "class C:\n    def m(other, self):\n        self.x = f",
    "cls in a plain function": "def m(cls):\n    cls.x = f",
    # Fix round 1, finding 3.
    "__globals__": "g = fn.__globals__",
    "__globals__.update": "fn.__globals__.update(find_advice_wording=f)",
    "__builtins__ name": "__builtins__['setattr'](m, 'x', f)",
    "__builtins__ attribute": "b = fn.__builtins__",
    "__setitem__": "d.__setitem__(k, v)",
    "__delitem__": "d.__delitem__(k)",
    "sys.modules store": "import sys\nsys.modules['ofo.wording'] = fake",
    "sys.modules delete": "import sys\ndel sys.modules['ofo.wording']",
    "sys.modules aliased module": "import sys as s\ns.modules.pop('ofo.wording')",
    "sys.modules held in a variable": "import sys\nmods = sys.modules\nmods['ofo.wording'] = fake",
    "from sys import modules": "from sys import modules\nmodules['ofo.wording'] = fake",
    "sys.modules update": "import sys\nsys.modules.update({'ofo.wording': fake})",
    "operator.setitem": "import operator\noperator.setitem(d, k, v)",
    "operator.delitem": "import operator\noperator.delitem(d, k)",
    "from operator import setitem": "from operator import setitem",
    "importlib.reload": "import importlib\nimportlib.reload(m)",
    "from importlib import reload": "from importlib import reload",
    "update on an imported module": "from ofo import wording\nwording.update(x=f)",
    "pop on an imported object": "from ofo.timeline.why import INPUT_LABELS\nINPUT_LABELS.pop('x')",
    "clear on a chain from an import": "import ofo.timeline.why as why\nwhy.INPUT_LABELS.clear()",
    "setdefault on a chain from an import": "from ofo import wording\nwording.X.setdefault('k', f)",
    "update on a call root (fail closed)": "get().d.update(x=f)",
    # Fix round 2: a name bound to ofo.wording by an import is never rebound in that file.
    "rebind the module alias": "from ofo import wording as shared_wording\nshared_wording = fake",
    "rebind the module alias via global": (
        "from ofo import wording as shared_wording\ndef f():\n    global shared_wording\n    shared_wording = fake"
    ),
    "rebind wording to a SimpleNamespace": (
        "import types\nfrom ofo import wording\nwording = types.SimpleNamespace(check_platform_text=print)"
    ),
    "rebind import-as alias": "import ofo.wording as w\nw = fake",
    "rebind the ofo root": "import ofo.wording\nofo = fake",
    "rebind relative module import": "from . import wording\nwording += 1",  # in ofo.sample: ofo.wording
    "rebind by annotated assign": "from ofo import wording\nwording: object = fake",
    "rebind by for target": "from ofo import wording\nfor wording in [fake]:\n    pass",
    "rebind by with target": "from ofo import wording\nwith cm() as wording:\n    pass",
    "rebind by except-as": "from ofo import wording\ntry:\n    pass\nexcept E as wording:\n    pass",
    "rebind by walrus": "from ofo import wording\n(wording := fake)",
    "rebind by a second import-as": "from ofo import wording\nimport fake as wording",
    "delete the module name": "from ofo import wording\ndel wording",
    "nonlocal declaration": (
        "from ofo import wording\ndef f():\n    wording = 1\n    def g():\n        nonlocal wording"
    ),
    # Fix round 1, finding 1: nothing imported from ofo.wording by name.
    "from ofo.wording import name": "from ofo.wording import check_platform_text",
    "from ofo.wording import star": "from ofo.wording import *",
    "from ofo.wording import as": "from ofo.wording import find_advice_wording as fw",
}


@pytest.mark.parametrize("label", sorted(FLAGGED))
def test_scan_flags_each_bypass_shape(label: str) -> None:
    assert scan_source(FLAGGED[label]) != [], label


@pytest.mark.parametrize("module,source", [
    ("ofo.errors.slots", "from ..wording import is_blank_after_normalising"),
    ("ofo.timeline.why", "from ..wording import check_platform_text"),
    ("ofo.execution", "from ..wording import check_platform_text"),  # package __init__: is_package below
    ("ofo.marketdata.disconnect", "from .wording import x"),  # ofo.marketdata.wording: another module
])
def test_scan_flags_a_relative_from_import_of_a_checker_name(module: str, source: str) -> None:
    is_package = module == "ofo.execution"
    hits = scan_source(source, module, is_package)
    if module == "ofo.marketdata.disconnect":
        assert all("ofo.wording" not in h.message for h in hits)  # resolves elsewhere: not the checker
        return
    assert any("from ofo.wording by name" in h.message for h in hits), hits


CLEAN = {
    "self attribute": "class C:\n    def f(self):\n        self.x = 1",
    "self nested attribute": "class C:\n    def f(self):\n        self.a.b = 1",
    "self item": "class C:\n    def f(self, k):\n        self._d[k] = 1",
    "del self item": "class C:\n    def f(self, k):\n        del self._d[k]",
    "cls augmented": "class C:\n    @classmethod\n    def f(cls):\n        cls.n += 1",
    "async method": "class C:\n    async def f(self):\n        self.x = 1",
    "method with a nested def not named self": "class C:\n    def f(self):\n        def h(x):\n            return x\n        self.x = h",
    "plain name": "x = 1\nx += 1\ndel x",
    "local item": "d = {}\nd['k'] = 1\nd['a']['b'] = 2\ndel d['k']",
    "reading a module attribute": "from ofo import wording\nhits = wording.find_advice_wording('x')",
    "module import of the checker": "from ofo import wording as shared_wording\nimport ofo.wording",
    "getattr on an object": "v = getattr(obj, 'name', None)",
    "update on a local dict": "d = {}\nd.update(a=1)\nself_d = d.pop('a')",
    "update on own module-level dict": "LABELS = {}\nLABELS.update(a=1)",
    "frozen dataclass __post_init__": (
        "@dataclass(frozen=True)\nclass C:\n    def __post_init__(self):\n"
        "        if self.x:\n            object.__setattr__(self, 'x', tuple(self.x))"
    ),
    "dataclasses.dataclass(frozen=True) __post_init__": (
        "@dataclasses.dataclass(frozen=True)\nclass C:\n    def __post_init__(self):\n"
        "        for n in ('a',):\n            object.__setattr__(self, n, 1)"
    ),
    "defining __setattr__": "class C:\n    def __setattr__(self, n, v):\n        raise AttributeError(n)",
}


@pytest.mark.parametrize("label", sorted(CLEAN))
def test_scan_passes_each_allowed_shape(label: str) -> None:
    assert scan_source(CLEAN[label]) == [], (label, scan_source(CLEAN[label]))


def test_scan_reports_file_and_line_for_an_unclassifiable_write() -> None:
    """Fail closed with a location: the hit names the line of the write it could not classify."""
    hits = scan_source("x = 1\n\nget_module().x = f\n")
    assert [(h.line, "cannot classify" in h.message) for h in hits] == [(3, True)]
