"""W-024 round 8 (ADR-056 item 1): the ALLOWLIST scan that replaces round 7's denylist of shapes.

Spec basis:
- ADR-056 decision (1): "the allowlist design - no attribute assignment on any imported module in
  backend/ofo plus a runtime identity check of the wording checker."
- ADR-003 Q235: the checks "stop accidental misuse by the platform's own code" and "are flagged in CI
  when code reaches into their internals".

Root cause of rounds 5-7 (issue 30): each round listed the code shapes that rebind the checker
(`ofo.wording.x = f`, `from ofo import wording; wording.x = f`, ...) and each verifier found a shape
not on the list (a relative import, a variable holding a module, `importlib.import_module(...)`).
This scan does not ask WHICH object is written. It allows exactly these, by AST shape:

1. A store or delete whose target is a plain name (`x = ...`, `del x`): rebinding a name in the
   current scope never changes another module.
2. A store or delete of an attribute (or item) whose chain is rooted at the name `self` or `cls`
   (`self.a = 1`, `self.a.b = 1`, `cls.x += 1`, `self.d[k] = v`).
3. A store or delete of an item of a plain name (`d[k] = v`, `del d[k]`): a local container.

Every other attribute or item write fails: `m.x = f`, `del m.x`, `m.x += 1`, `for m.x in ...`,
`with f() as m.x`, `[... for m.x in ...]`, `ofo.wording.X[0] = 1`, whatever import form bound `m`.
The scan finds writes by the AST node's `ctx` (Store / Del), so a new statement form that writes
an attribute is still seen. A write whose chain root is not a name (`f().x = 1`) cannot be
classified and fails ("fail closed").

Banned outright, as a call or as a bare reference, by name or by attribute (`builtins.setattr`):
`setattr`, `delattr`, `vars`, `globals`, `__import__`, `exec`, `eval`, `import_module`
(`importlib.import_module`); and any access to `.__dict__`, `.__setattr__` or `.__delattr__`, or
those names as string constants (`getattr(m, "__dict__")`). The ONLY exception shape, with no list:
`object.__setattr__(self, "<field>", value)` as a statement directly in the body of `__post_init__`
of a class decorated `@dataclass(frozen=True)` / `@dataclasses.dataclass(frozen=True)`.

Existing code that writes outside these shapes is listed in `ALLOWLIST` (file, line pattern,
reason); `test_allowlist_entries_are_printed_and_each_still_matches` prints every entry and fails
when one no longer matches anything (a stale exception is removed, not kept).

Not claimed: a name assembled at run time (`getattr(builtins, "set" + "attr")`), or code outside
backend/ofo. Q235 puts deliberate runtime replacement out of scope beyond this CI flag and the
ADR-056 runtime identity check in `ofo.errors.model`.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_OFO_DIR = REPO_ROOT / "backend" / "ofo"

#: Roots whose attributes a method may write: the instance or the class being defined.
ALLOWED_WRITE_ROOTS: frozenset[str] = frozenset({"self", "cls"})

#: Builtins / functions that write, read-for-write or execute by name. A call OR a bare reference
#: fails (`s = setattr; s(m, "x", f)`), as does importing one by name.
BANNED_NAMES: frozenset[str] = frozenset(
    {"setattr", "delattr", "vars", "globals", "__import__", "exec", "eval", "import_module"}
)

#: Attribute names that hand out or write an object's namespace.
BANNED_DUNDERS: frozenset[str] = frozenset({"__dict__", "__setattr__", "__delattr__"})


@dataclass(frozen=True)
class AllowlistEntry:
    """One reviewed exception: the file (relative to backend/ofo), a regex the offending source line
    must match, and why the write is safe."""

    file: str
    line_pattern: str
    reason: str


#: The ONLY exceptions to the scan. Each is printed by the test and must still match a hit.
#: Every entry writes a field of an object this module itself just built or owns (never a module),
#: through a local name the self/cls rule cannot see as the instance. Patterns are anchored to the
#: exact statement, so a new write in the same file is not excused by an old entry.
_DECIMAL_CONTEXT = "a decimal.localcontext() copy bound by `with ... as ctx`: thread-local arithmetic precision"
ALLOWLIST: tuple[AllowlistEntry, ...] = (
    AllowlistEntry("audit/log.py", r"^\s*log\._events = list\(events\)$",
                   "AuditLog.load: `log = cls()` two lines up; fills the new log, then verifies it"),
    AllowlistEntry("engine/metrics.py", r"^\s*ctx\.prec = 60$", _DECIMAL_CONTEXT),
    AllowlistEntry("table/model.py", r"^\s*ctx\.prec = 50$", _DECIMAL_CONTEXT),
    AllowlistEntry("entitlements/ledger.py", r'^\s*object\.__setattr__\(history, "(user_id|events)", ',
                   "_restore: `history = object.__new__(StoredHistory)` just above; fills a frozen record"),
    AllowlistEntry("entitlements/ledger.py", r"^\s*object\.__setattr__\(built, name, value\)$",
                   "EntitlementLedger._with: `built = object.__new__(EntitlementLedger)` just above"),
    AllowlistEntry("execution/partial.py", r"^\s*object\.__setattr__\(self, name, value\)$",
                   "Preparation.__init__ fills its own fields; its __setattr__ refuses every later change"),
    AllowlistEntry("execution/partial.py", r'^\s*object\.__setattr__\(preparation, "_consumed", True\)$',
                   "marks a Preparation (type-checked just above) as used, so it cannot be sent twice"),
    AllowlistEntry("execution/send_guard.py", r'^\s*object\.__setattr__\(self, "(resolve_all|submit)", ',
                   "the send sink's __init__ fills its own two closures; its __setattr__ refuses changes"),
    AllowlistEntry("instruments/catalogue.py", r"^\s*entry\.currently_listed = False$",
                   "an entry of the catalogue's own self._entries dict, iterated just above"),
    AllowlistEntry("marketdata/health.py", r'^\s*object\.__setattr__\(final, "validation_errors", ',
                   "`final = dataclasses.replace(...)` just above: a fresh frozen copy this function returns"),
    AllowlistEntry("orders/model.py", r"^\s*object\.__setattr__\(clone, (f\.name|\"_state\"), ",
                   "Order._copy_with: `clone = object.__new__(Order)` just above"),
    AllowlistEntry("orders/model.py", r'^\s*object\.__setattr__\(updated, "broker_order_id", boid\)$',
                   "OrderBook: `updated = order._copy_with(...)` just above, a copy the book owns"),
    AllowlistEntry("reconciliation/compare.py", r"^\s*by_(expiry|strike)\.setdefault\(.*\)\[other\] = None$",
                   "a local dict of dicts built in this function (setdefault returns the inner dict)"),
    AllowlistEntry("rules/conditions.py", r'^\s*object\.__setattr__\(node, "children", children\)$',
                   "_check_children, called from AllOf/AnyOf __post_init__ with that node: freezes its children"),
    AllowlistEntry("strategy/versions.py", r"^\s*object\.__setattr__\(self, name, value\)$",
                   "StrategyRecord._set: the record's own fields; its __setattr__ refuses outside writes"),
    AllowlistEntry("timeline/log.py", r'^\s*object\.__setattr__\(self, "_(strategy_id|clock|entries|follow_ups|recorded)", ',
                   "Timeline.__init__ (a __slots__ class) fills its own five slots"),
    AllowlistEntry("timeline/log.py", r"^\s*timeline\._(follow_ups|recorded)\[entry\.(seq|content)\] = ",
                   "Timeline.load: rebuilds the index dicts of the timeline it just built and verified"),
)


@dataclass(frozen=True)
class Hit:
    line: int
    message: str


def _write_root(node: ast.AST) -> ast.AST:
    """The node at the bottom of an Attribute/Subscript chain (`self` in `self.a[k].b`)."""
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


def _allowed_post_init_setattr_calls(tree: ast.AST) -> set[int]:
    """`id()` of every `object.__setattr__` Attribute node in the one allowed shape:
    `object.__setattr__(self, "<str>", value)` as an expression statement directly in the body of
    `__post_init__(self, ...)` of a frozen-dataclass class body."""
    allowed: set[int] = set()
    for cls_node in ast.walk(tree):
        if not isinstance(cls_node, ast.ClassDef):
            continue
        if not any(_is_dataclass_frozen(d) for d in cls_node.decorator_list):
            continue
        for fn in cls_node.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "__post_init__"):
                continue
            if not fn.args.args or fn.args.args[0].arg != "self":
                continue
            for call in _walk_own_scope(fn):
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
                ):
                    allowed.add(id(func))
    return allowed


def _walk_own_scope(fn: ast.FunctionDef) -> list[ast.AST]:
    """Every node inside `fn`'s body, NOT descending into a nested def, lambda or class (whose
    `self` is another object)."""
    found: list[ast.AST] = []
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        found.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return found


def scan_source(source: str, filename: str = "<sample>") -> list[Hit]:
    """Every write/reach in `source` outside the allowed shapes (module docstring)."""
    tree = ast.parse(source, filename=filename)
    allowed_setattr = _allowed_post_init_setattr_calls(tree)
    hits: list[Hit] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        # --- writes, found by context so every statement form is covered ---------------------
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            verb = "deletes" if isinstance(node.ctx, ast.Del) else "writes"
            root = _write_root(node)
            if not isinstance(root, ast.Name):
                hits.append(Hit(line, f"{verb} through a {type(root).__name__} root: cannot classify (fail closed)"))
            elif _is_item_chain(node):
                pass  # rule 3: an item (of an item ...) of a plain name: a container, not a module
            elif root.id not in ALLOWED_WRITE_ROOTS:
                kind = "an attribute" if isinstance(node, ast.Attribute) else "an item"
                hits.append(Hit(line, f"{verb} {kind} rooted at {root.id!r} (only self/cls roots are allowed)"))
        # --- banned names, as a call or as a reference -----------------------------------------
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            hits.append(Hit(line, f"uses {node.id}"))
        if isinstance(node, ast.Attribute) and node.attr in BANNED_NAMES:
            hits.append(Hit(line, f"uses .{node.attr}"))
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in BANNED_NAMES or alias.name == "*" and node.module in {"importlib", "builtins"}:
                    hits.append(Hit(line, f"imports {alias.name} from {node.module}"))
        # --- namespace dunders -----------------------------------------------------------------
        if isinstance(node, ast.Attribute) and node.attr in BANNED_DUNDERS and id(node) not in allowed_setattr:
            hits.append(Hit(line, f"reaches .{node.attr}"))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in BANNED_DUNDERS | BANNED_NAMES:
            hits.append(Hit(line, f"names {node.value!r} as a string"))
    return hits


def _source_files() -> list[Path]:
    return sorted(p for p in BACKEND_OFO_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    return path.relative_to(BACKEND_OFO_DIR).as_posix()


def _entry_for(path: Path, source_line: str) -> AllowlistEntry | None:
    for entry in ALLOWLIST:
        if entry.file == _rel(path) and re.search(entry.line_pattern, source_line):
            return entry
    return None


def scan_tree() -> tuple[list[str], dict[AllowlistEntry, int]]:
    """(offences not covered by an allowlist entry, hits per allowlist entry) over backend/ofo."""
    offences: list[str] = []
    used: dict[AllowlistEntry, int] = {e: 0 for e in ALLOWLIST}
    for path in _source_files():
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for hit in scan_source(source, str(path)):
            text = lines[hit.line - 1] if 0 < hit.line <= len(lines) else ""
            entry = _entry_for(path, text)
            if entry is None:
                offences.append(f"backend/ofo/{_rel(path)}:{hit.line}: {hit.message}: {text.strip()}")
            else:
                used[entry] += 1
    return offences, used


# --- The scan over backend/ofo -------------------------------------------------------------------

def test_backend_ofo_writes_only_through_self_or_cls_or_a_named_allowlist_entry() -> None:
    """ADR-056 (1): no code in backend/ofo writes an attribute of anything but `self`/`cls`, or uses
    setattr/delattr/vars/globals/import_module/__import__/exec/eval/__dict__/__setattr__, outside the
    named ALLOWLIST. Prints every allowlist entry, so the exceptions are visible in the test log."""
    for entry in ALLOWLIST:
        print(f"ALLOWLIST backend/ofo/{entry.file}  /{entry.line_pattern}/  - {entry.reason}")
    offences, _ = scan_tree()
    assert not offences, "\n".join(offences)


def test_every_allowlist_entry_still_matches_a_hit() -> None:
    """A stale exception (its code was changed or removed) is deleted, not kept."""
    _, used = scan_tree()
    stale = [f"{e.file} /{e.line_pattern}/" for e, n in used.items() if n == 0]
    assert not stale, "allowlist entries that match nothing: " + "; ".join(stale)


def test_allowlist_entry_does_not_excuse_another_line_in_its_file() -> None:
    """An entry excuses its exact statement only: a module write in the same file is still a hit."""
    entry = next(e for e in ALLOWLIST if e.file == "engine/metrics.py")
    assert re.search(entry.line_pattern, "        ctx.prec = 60")
    assert not re.search(entry.line_pattern, "        wording.find_advice_wording = f")


# --- Samples the scan must flag (each a shape a verifier used or named in issue 30) --------------

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
}


@pytest.mark.parametrize("label", sorted(FLAGGED))
def test_scan_flags_each_bypass_shape(label: str) -> None:
    assert scan_source(FLAGGED[label]) != [], label


CLEAN = {
    "self attribute": "class C:\n    def f(self):\n        self.x = 1",
    "self nested attribute": "class C:\n    def f(self):\n        self.a.b = 1",
    "self item": "class C:\n    def f(self, k):\n        self._d[k] = 1",
    "del self item": "class C:\n    def f(self, k):\n        del self._d[k]",
    "cls augmented": "class C:\n    @classmethod\n    def f(cls):\n        cls.n += 1",
    "plain name": "x = 1\nx += 1\ndel x",
    "local item": "d = {}\nd['k'] = 1\nd['a']['b'] = 2\ndel d['k']",
    "reading a module attribute": "from ofo import wording\nhits = wording.find_advice_wording('x')",
    "getattr on an object": "v = getattr(obj, 'name', None)",
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
