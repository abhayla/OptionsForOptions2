"""W-070 round 4 (issue #197, finding sealed-object-mutable-after-seal): no product code outside the door's own module
names the door's private state.

Python has no truly private state, so a hidden store only moves the write door. The guard is two things: the door
re-checks every header value of its minted record (tests_app/test_response_door.py), and this scan, which fails when
any file under backend/ other than backend/ofo_app/errors.py uses `_freeze`, `_frozen`, `_SEAL`, `_REDIRECT_MINT` or
`_verify` as a name, an attribute, an imported name, a keyword or a string (``getattr(r, "_frozen")``). It reads the
source with ``ast`` (docstrings and comments are not code; a string that is only a docstring is skipped), so a longer
name such as ``_deep_freeze`` or ``_verify_checker`` is not a match.

Round 5 adds: `Emitted` is made only by api_models.py (no `Emitted(`, no `__new__` beside its name, no `bytes.__new__`,
`object.__new__` only in the listed domain files); and the indirect routes to a door name are closed (star imports,
`getattr`/`vars`/`.__dict__` on a door module, a door name built from literal parts, a bare door name as a docstring).
"""
import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
DOOR_MODULE = BACKEND / "ofo_app" / "errors.py"
DOOR_NAMES = frozenset({"_freeze", "_frozen", "_SEAL", "_REDIRECT_MINT", "_verify"})


API_MODELS = BACKEND / "ofo_app" / "api_models.py"
#: Private names of api_models that make an `Emitted` body from any JSON tree (`_encode`): named nowhere else.
API_PRIVATE_NAMES = frozenset({"_encode"})
DOOR_MODULES = frozenset({"ofo_app.errors", "ofo_app.api_models"})
DOOR_MODULE_LEAVES = frozenset({"errors", "api_models"})

#: Backend files allowed to call `object.__new__`, each with its reason. They build their own frozen domain objects
#: (never an `Emitted`, never a door response); none names `Emitted` (the scan refuses that combination everywhere).
#: Every other `__new__` outside api_models.py is refused, except `super().__new__` inside a class's own `__new__`.
OBJECT_NEW_ALLOWED = {
    "ofo/engine/model.py": "ModelInputs/ExpiryModel._make builds a token-checked frozen value",
    "ofo/entitlements/ledger.py": "rebuilds a StoredHistory / EntitlementLedger without running __init__",
    "ofo/errors/model.py": "UserFacingError keeps no text on the instance; built here only",
    "ofo/orders/model.py": "Order.replace clones a frozen dataclass",
}
ALL_CHECKS = frozenset({"names", "apinames", "indirect", "forgery"})


def _fold(node: ast.AST) -> str | None:
    """The text a string expression builds when every part is a literal (constants, f-strings, `+`, `%`, join, format)."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = [_fold(v.value) if isinstance(v, ast.FormattedValue) and v.conversion == -1 and v.format_spec is None
                 else _fold(v) for v in node.values]
        return None if any(p is None for p in parts) else "".join(parts)  # type: ignore[arg-type]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _fold(node.left), _fold(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left = _fold(node.left)
        args = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
        folded = [_fold(a) for a in args]
        if left is None or any(a is None for a in folded):
            return None
        try:
            return left % tuple(folded)
        except (TypeError, ValueError):
            return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        base = _fold(node.func.value)
        if base is None:
            return None
        if node.func.attr == "join" and len(node.args) == 1 and isinstance(node.args[0], (ast.List, ast.Tuple)):
            items = [_fold(e) for e in node.args[0].elts]
            return None if any(i is None for i in items) else base.join(items)  # type: ignore[arg-type]
        if node.func.attr == "format" and not node.keywords:
            items = [_fold(a) for a in node.args]
            if any(i is None for i in items):
                return None
            try:
                return base.format(*items)
            except (IndexError, KeyError, ValueError):
                return None
    return None


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else ""
    return ""


def _door_module_aliases(tree: ast.AST) -> set[str]:
    """Names this file binds to a door module (`import ofo_app.errors as e`, `from ofo_app import errors`, `a = e`)."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases |= {a.asname for a in node.names if a.asname and a.name in DOOR_MODULES}
        elif isinstance(node, ast.ImportFrom) and (node.module in (None, "ofo_app") or node.level):
            if node.module in (None, "ofo_app", ""):
                aliases |= {a.asname or a.name for a in node.names if a.name in DOOR_MODULE_LEAVES}
    for _ in range(5):  # `a = e`, `b = a`: follow plain Name copies until nothing new
        before = len(aliases)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                aliases |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        if len(aliases) == before:
            break
    return aliases


def _is_door_module(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in aliases
    if _dotted(node) in DOOR_MODULES:
        return True
    if isinstance(node, ast.Subscript) and _dotted(node.value) == "sys.modules":
        return True
    return isinstance(node, ast.Call) and _dotted(node.func).split(".")[-1] in ("import_module", "__import__")


def _indirect(tree: ast.AST, where: str) -> list[str]:
    """Reaching a door module's names without writing them: star imports, `getattr`/`setattr`/`delattr`/`vars`/
    `.__dict__`/`getmembers` on the module, and a door name built from literal parts (f-string, `+`, `%`, join)."""
    found: list[str] = []
    aliases = _door_module_aliases(tree)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            leaf = (node.module or "").split(".")[-1]
            if node.module in DOOR_MODULES or (node.level and leaf in DOOR_MODULE_LEAVES):
                found.append(f"{where}:{line} star-imports a door module")
        elif isinstance(node, ast.Call):
            fn = _dotted(node.func)
            if fn in ("getattr", "setattr", "delattr", "vars", "inspect.getmembers", "getmembers") and node.args \
                    and _is_door_module(node.args[0], aliases):
                literal = len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and fn.endswith("attr")
                if not literal:  # a literal name is the name check's business
                    found.append(f"{where}:{line} reads a door module with a non-literal name ({fn})")
        elif isinstance(node, ast.Attribute) and node.attr in ("__dict__", "__getattribute__") \
                and _is_door_module(node.value, aliases):
            found.append(f"{where}:{line} reads the namespace of a door module")
        if isinstance(node, (ast.JoinedStr, ast.BinOp, ast.Call)):
            text = _fold(node)
            if text in DOOR_NAMES or text in API_PRIVATE_NAMES:
                found.append(f"{where}:{line} builds the name {text}")
    return found


def _forgery(tree: ast.AST, where: str, source_path: str) -> list[str]:
    """Nothing but api_models.py makes an `Emitted`: no call of it, no `__new__` next to its name, no `bytes.__new__`,
    `object.__new__` only in the listed domain files, and no `__new__` as a string (``getattr(bytes, "__new__")``)."""
    found: list[str] = []
    names_emitted = any((isinstance(n, ast.Name) and n.id == "Emitted") or (isinstance(n, ast.Attribute) and n.attr == "Emitted")
                        or (isinstance(n, ast.alias) and "Emitted" in (n.name, n.asname)) for n in ast.walk(tree))
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Call) and _dotted(node.func).split(".")[-1] == "Emitted":
            found.append(f"{where}:{line} constructs Emitted")
        elif isinstance(node, ast.Attribute) and node.attr == "__new__":
            inner = node.value
            via_super = isinstance(inner, ast.Call) and _dotted(inner.func) == "super"
            via_object = isinstance(inner, ast.Name) and inner.id == "object" and source_path in OBJECT_NEW_ALLOWED
            if not (via_super or via_object):
                found.append(f"{where}:{line} calls __new__ on {_dotted(inner) or 'an expression'}")
        elif isinstance(node, ast.Constant) and node.value == "__new__" and id(node) not in docs:
            found.append(f"{where}:{line} names __new__ as a string")
        if names_emitted and ((isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__new__")
                              or (isinstance(node, ast.Attribute) and node.attr == "__new__")):
            found.append(f"{where}:{line} names Emitted and __new__ in one file")
    return found


def door_name_uses(source: str, where: str = "<src>", *, checks: frozenset[str] = ALL_CHECKS) -> list[str]:
    """Every place `source` names a door-private name or forges/reaches a door object (empty = clean). `where` is the
    path relative to backend/ (it picks the `object.__new__` allowance)."""
    tree = ast.parse(source)
    found: list[str] = _indirect(tree, where) if "indirect" in checks else []
    if "forgery" in checks:
        found += _forgery(tree, where, where.replace("\\", "/"))
    if not checks & {"names", "apinames"}:
        return found
    private = (DOOR_NAMES if "names" in checks else frozenset()) | (API_PRIVATE_NAMES if "apinames" in checks else frozenset())
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
                  and not (isinstance(n.body[0].value.value, str) and n.body[0].value.value.strip() in private)}
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, ast.alias):
            names = [node.name.split(".")[-1], node.asname or ""]
        elif isinstance(node, ast.keyword):
            names = [node.arg or ""]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            names = [node.value]
        hit = next((n for n in names if n in private), None)
        if hit is not None:
            found.append(f"{where}:{getattr(node, 'lineno', 0)} names {hit}")
    return found


def _checks_for(path: Path) -> frozenset[str]:
    """errors.py owns the door names (so no name check there) but is scanned for forgery; api_models.py owns Emitted
    (no forgery check there) but is scanned for the door names and the indirect reads. Everything else gets all three."""
    if path == DOOR_MODULE:
        return frozenset({"forgery"})
    if path == API_MODELS:
        return frozenset({"names", "indirect"})
    return ALL_CHECKS


def _product_files() -> list[Path]:
    return [p for p in BACKEND.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_backend_file_but_the_door_names_its_private_state() -> None:
    files = _product_files()
    assert len(files) > 50 and DOOR_MODULE.exists() and API_MODELS.exists()  # walks backend/ofo and backend/ofo_app
    bad = [v for p in files for v in door_name_uses(p.read_text(encoding="utf-8"), p.relative_to(BACKEND).as_posix(),
                                                    checks=_checks_for(p))]
    assert bad == []


def test_the_door_module_does_name_them() -> None:
    """The scan is not vacuous: the one allowed file really uses every name, so the exemption is what keeps it quiet."""
    used = {v.rsplit(" ", 1)[1] for v in door_name_uses(DOOR_MODULE.read_text(encoding="utf-8"), checks=frozenset({"names"}))}
    assert used == DOOR_NAMES


def test_the_object_new_allowances_are_real_and_only_those_files_use_it() -> None:
    """Each allowance names a file that exists and really calls `object.__new__` (a stale allowance is a hole), and no
    other backend file calls it."""
    users = {p.relative_to(BACKEND).as_posix() for p in _product_files() if "object.__new__" in p.read_text(encoding="utf-8")}
    assert users == set(OBJECT_NEW_ALLOWED)


def test_api_models_is_the_only_file_that_builds_an_emitted() -> None:
    assert "Emitted(" in API_MODELS.read_text(encoding="utf-8")
    others = [p for p in _product_files() if p != API_MODELS and "Emitted(" in p.read_text(encoding="utf-8")]
    assert others == []


@pytest.mark.parametrize("source", [
    "r._frozen = (200, (), b'')",
    "from ofo_app.errors import _freeze",
    "from ofo_app import errors\nerrors._freeze(r)",
    "from ofo_app.errors import _verify as v",
    "x = getattr(r, '_frozen')",
    "scope['k'] = _SEAL",
    "import ofo_app.errors as e\ne._REDIRECT_MINT",
    "def _freeze(r):\n    pass",
    "f(_verify=1)",
])
def test_scan_catches_every_shape(source: str) -> None:
    assert door_name_uses(source), source


@pytest.mark.parametrize("source", [
    "x = _deep_freeze(y)",
    "_verify_checker()",
    "def frozen():\n    '''_frozen _verify in a docstring is not code'''",
    "# r._frozen in a comment\nx = 1",
    "frozen = 1",
])
def test_scan_passes_the_allowed_shapes(source: str) -> None:
    assert door_name_uses(source) == [], source


# --- round 5 (issue #197): the forgery shapes of the second review. Written red first (xfail strict); the mark comes off
# --- with the scan that closes them.


FORGERY_SHAPES = [
    "from ofo_app.api_models import Emitted\nx = bytes.__new__(Emitted, b'{}')",
    "import ofo_app.api_models as m\nx = bytes.__new__(m.Emitted, b'{}')",
    "from ofo_app.api_models import Emitted\nx = Emitted(b'{}', _token=1)",
    "from ofo_app.api_models import Emitted\nx = Emitted.__new__(Emitted, b'{}')",
    "x = bytes.__new__(type(emit(m)), b'{}')",
    "x = object.__new__(Thing)",
    "f = getattr(bytes, '__new__')",
]

GAP_SHAPES = [
    "from ofo_app import errors\ngetattr(errors, name)",
    "import ofo_app.errors as e\nsetattr(e, name, 1)",
    "import ofo_app.api_models as m\nvars(m)",
    "from ofo_app import errors\nerrors.__dict__['x']",
    "from ofo_app import errors as e\nalias = e\ngetattr(alias, name)",
    "import sys\ngetattr(sys.modules['ofo_app.errors'], name)",
    "from ofo_app.errors import *",
    "from ofo_app.api_models import *",
    "from .errors import *",
    "x = '_fro' + 'zen'",
    "x = f'_{\"fro\"}zen'",
    "x = ''.join(['_fro', 'zen'])",
    "x = '_%s' % 'frozen'",
    "def f():\n    '_frozen'",
]


@pytest.mark.parametrize("source", FORGERY_SHAPES)
def test_scan_catches_every_way_to_forge_an_emitted_body(source: str) -> None:
    assert door_name_uses(source), source


@pytest.mark.parametrize("source", GAP_SHAPES)
def test_scan_catches_every_indirect_way_to_a_door_name(source: str) -> None:
    assert door_name_uses(source), source


@pytest.mark.parametrize("source", [
    "x = getattr(self, name)",
    "from ofo_app import errors\nerrors.respond(m, 200)",
    "from ofo_app import errors\ngetattr(errors, 'respond')",
    "label = f'{a}-{b}'",
    "x = '_fro' + suffix",
    "class A:\n    def __new__(cls):\n        return super().__new__(cls)",
])
def test_scan_passes_ordinary_code_and_super_new(source: str) -> None:
    assert door_name_uses(source) == [], source


def test_object_new_is_allowed_only_in_the_listed_domain_files() -> None:
    plant = "clone = object.__new__(Order)"
    assert door_name_uses(plant, "ofo/orders/model.py") == []
    assert door_name_uses(plant, "ofo_app/routes/health.py")
    assert door_name_uses("from ofo_app.api_models import Emitted\nobject.__new__(Emitted)", "ofo/orders/model.py")


def test_a_planted_backend_file_is_caught_by_the_real_scan(tmp_path: Path) -> None:
    """End to end on a file: the same function the real scan calls refuses a planted forger (the plant is a tmp file)."""
    plant = tmp_path / "forger.py"
    plant.write_text("from ofo_app.api_models import Emitted\nBODY = bytes.__new__(Emitted, b'{\"x\":\"SENTENCE\"}')\n",
                     encoding="utf-8")
    assert door_name_uses(plant.read_text(encoding="utf-8"), "ofo_app/forger.py")


# --- round 6/7 (issue #197): the mechanisms that reach memory, deserialise, or lead to either -----------------------------
# The door mints its body from a model and re-emits it to check (tests_app/test_response_door.py), so a forged body cannot
# be passed in. No product code needs raw memory, object rebuilding without constructors, or the import machinery, so the
# rule is an allow-list over a small CLOSED set of mechanisms (a list of forbidden spellings is never complete):
#   (a) a module whose top-level name, leading underscores stripped, is in MECHANISM_MODULES (so `_ctypes`, `_pickle`);
#       also `import_module(...)` calls;
#   (b) the names `__builtins__`, `__import__`, `__loader__`, `__spec__` (as a name, an attribute or a string);
#   (c) `sys.modules`, `sys._getframe`, `sys.meta_path`, `sys.path_hooks`.
# Runtime resistance to code that rewrites the checker in-process is out of scope (ADR-003 Q235); this scan flags it.

MECHANISM_MODULES = frozenset({"ctypes", "pickle", "copyreg", "marshal", "shelve", "dill", "importlib", "pkgutil",
                               "builtins", "cffi", "gc"})
MECHANISM_NAMES = frozenset({"__builtins__", "__import__", "__loader__", "__spec__"})
SYS_MECHANISMS = frozenset({"modules", "_getframe", "meta_path", "path_hooks"})

#: Backend paths (prefix) allowed to use a mechanism, each with its reason and the tokens it may use. A token is a module
#: name (`importlib`) or `sys.<attr>`.
FORBIDDEN_MODULE_ALLOWED = {
    "ofo_app/alembic/versions/": ("migration scripts load the shared baseline helper by file path "
                                  "(importlib.util.spec_from_file_location); they never run in the API process",
                                  frozenset({"importlib"})),
    "ofo/errors/explanations.py": ("user_words() reads its caller's module name with sys._getframe(1) to refuse any "
                                   "caller outside REQUEST_LAYER; it is the door's own read-only guard, not a route",
                                   frozenset({"sys._getframe"})),
}


def forbidden_module_uses(source: str, where: str = "<source>") -> list[str]:
    """Every use in `source` of a mechanism in (a), (b) or (c) above, unless `where` is an allowed path for that token."""
    allowed = next((mods for prefix, (_, mods) in FORBIDDEN_MODULE_ALLOWED.items() if where.startswith(prefix)), frozenset())
    tree = ast.parse(source)
    sys_names = {"sys"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            sys_names |= {a.asname for a in node.names if a.name == "sys" and a.asname}
    found: list[str] = []

    def hit(node: ast.AST, token: str) -> None:
        if token not in allowed:
            found.append(f"{where}:{getattr(node, 'lineno', 0)} uses {token}")

    def module_hit(node: ast.AST, dotted: str) -> None:
        top = dotted.split(".")[0].lstrip("_")
        if top in MECHANISM_MODULES:
            hit(node, top)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                module_hit(node, a.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module_hit(node, node.module)
            if node.module == "sys":
                for a in node.names:
                    if a.name in SYS_MECHANISMS:
                        hit(node, f"sys.{a.name}")
        elif isinstance(node, ast.Name) and node.id in MECHANISM_NAMES:
            hit(node, node.id)
        elif isinstance(node, ast.Attribute):
            if node.attr in MECHANISM_NAMES:
                hit(node, node.attr)
            if node.attr in SYS_MECHANISMS and isinstance(node.value, ast.Name) and node.value.id in sys_names:
                hit(node, f"sys.{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in MECHANISM_NAMES:
            hit(node, node.value)
        elif isinstance(node, ast.Call) and _dotted(node.func).split(".")[-1] == "import_module":
            hit(node, "importlib")
    return found


def test_no_backend_file_imports_a_module_that_can_rewrite_or_forge_a_sealed_object() -> None:
    files = _product_files()
    assert len(files) > 50
    bad = [v for p in files for v in forbidden_module_uses(p.read_text(encoding="utf-8"), p.relative_to(BACKEND).as_posix())]
    assert bad == []


def test_the_forbidden_module_allowances_are_real() -> None:
    """Each allowance names files that exist and really import what it allows (a stale allowance is a hole)."""
    for prefix, (_, mods) in FORBIDDEN_MODULE_ALLOWED.items():
        files = [p for p in _product_files() if p.relative_to(BACKEND).as_posix().startswith(prefix)]
        assert files
        used = {m for p in files for m in mods if m in p.read_text(encoding="utf-8")}
        assert used == set(mods)


@pytest.mark.parametrize("module", sorted(MECHANISM_MODULES))
@pytest.mark.parametrize("template", ["import {m}", "import {m}.sub as s", "from {m} import thing", "from {m}.sub import thing"])
def test_the_scan_refuses_every_import_shape_of_every_forbidden_module(module: str, template: str) -> None:
    assert forbidden_module_uses(template.format(m=module), "ofo_app/routes/x.py"), (module, template)


def test_the_scan_refuses_a_dunder_import_and_passes_ordinary_imports() -> None:
    assert forbidden_module_uses("m = __import__('ctypes')", "ofo/x.py")
    assert forbidden_module_uses("import json\nfrom pathlib import Path\nfrom . import pickle_like\n", "ofo/x.py") == []


def test_a_planted_ctypes_file_is_caught_by_the_real_scan(tmp_path: Path) -> None:
    """End to end on a file: the same function the real scan calls refuses a planted ctypes import, also in a migration."""
    plant = tmp_path / "rewriter.py"
    plant.write_text("import ctypes\nctypes.memmove(0, b'x', 1)\n", encoding="utf-8")
    assert forbidden_module_uses(plant.read_text(encoding="utf-8"), "ofo_app/rewriter.py")
    assert forbidden_module_uses(plant.read_text(encoding="utf-8"), "ofo_app/alembic/versions/0011_x.py")


# --- round 7 (issue #197, ADR-003 Q235): the scan flags MECHANISMS, not module spellings ---------------------------------
# Runtime resistance to a same-process rewrite is out of scope (Q235); the CI source scan must flag every way product code
# reaches a raw-memory or deserialising module, or the import machinery that leads to one.

ROUND7_SHAPES = [
    "__builtins__['__import__']('ctypes')",
    "getattr(__builtins__, '__import__')",
    "import builtins\nbuiltins.__dict__['__imp' + 'ort__']('ctypes')",
    "import _ctypes",
    "import pkgutil\npkgutil.resolve_name('ctypes')",
    "import _pickle",
    "import gc\ngc.get_objects()",
    "import sys\nsys.modules['ctypes']",
    "import sys\nsys._getframe(0)",
    "import sys\nsys.meta_path.append(x)",
    "import sys\nsys.path_hooks.append(x)",
    "x = __loader__",
    "x = __spec__",
]


@pytest.mark.parametrize("source", ROUND7_SHAPES)
def test_round7_scan_refuses_every_mechanism(source: str) -> None:
    assert forbidden_module_uses(source, "ofo_app/routes/x.py"), source


# --- round 8 (issue #197, ADR-003 Q235): an allow-list over Python's reflection ENTRY POINTS ------------------------------
# Round 4-7 banned shapes: which object a name refers to, how a name is spelled. Neither can be complete in Python (the
# verifier's forger9 built `_verify` with chr() codes, reached the door through `[errors][0]` and used setattr). The ways to
# read, write or call an attribute or name CHOSEN AT RUNTIME are a small closed set, so every use of one in backend/ is
# either on a per-file allow-list below (with a reason) or fails.

FORGER9 = '''
from ofo_app import errors
from ofo_app.api_models import ApiModel, Identifier


class Ok(ApiModel):
    a: Identifier


def _word(codes):
    return "".join(chr(c) for c in codes)


def disarm():
    door = [errors][0]
    setattr(door, _word([95, 118, 101, 114, 105, 102, 121]), lambda response: None)


def forged_redirect():
    r = errors.respond(Ok(a="ok"), 200)
    record = (302, ((b"location", b"https://evil.example/steal"),), b"", None, False)
    setattr(r, _word([95, 102, 114, 111, 122, 101, 110]), record)
    return r
'''


#: Names whose every reference (a call, `functools.partial(setattr, ...)`, `map(getattr, ...)`) is a primitive.
REFLECTION_NAMES = frozenset({"setattr", "delattr", "eval", "exec", "compile", "globals", "locals", "vars"})
#: Attribute / string names that lead from an object to its class, code, frames or namespace (read or write).
REFLECTION_DUNDERS = frozenset({"__subclasses__", "__mro__", "__bases__", "__globals__", "__code__", "__closure__",
                                "__func__", "__self__", "__class__", "__dict__"})
#: `x.__setattr__(name, v)` / `object.__setattr__(x, name, v)`: a primitive unless the name argument is a string literal.
#: Value = how many trailing arguments follow the name (set: 1 value; del / getattribute: none).
DUNDER_ACCESSORS = {"__setattr__": 1, "__delattr__": 0, "__getattribute__": 0}
OPERATOR_PRIMITIVES = frozenset({"attrgetter", "methodcaller"})
PRIMITIVES = (REFLECTION_NAMES | REFLECTION_DUNDERS | OPERATOR_PRIMITIVES | frozenset(DUNDER_ACCESSORS)
              | {"getattr", "hasattr"})


def _is_str_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def reflection_uses(source: str, where: str = "<src>") -> list[tuple[int, str]]:
    """Every (line, primitive) in `source` that reads, writes or calls an attribute or name chosen at runtime. Complete over
    the closed set of Python reflection entry points, whatever the spelling or aliasing of the target (a primitive is flagged
    where it appears, not where its target is traced)."""
    tree = ast.parse(source)
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    found: list[tuple[int, str]] = []
    called: set[int] = set()  # id() of a Name/Attribute that is the func of a Call already judged by its arguments
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in ("getattr", "hasattr"):
            called.add(id(func))
            if len(node.args) < 2 or not _is_str_literal(node.args[1]) or node.keywords or any(
                    isinstance(a, ast.Starred) for a in node.args):
                found.append((node.lineno, func.id))
        elif isinstance(func, ast.Attribute) and func.attr in DUNDER_ACCESSORS:
            called.add(id(func))
            values = DUNDER_ACCESSORS[func.attr]
            index = len(node.args) - 1 - values  # bound: (name[, value]); unbound (`object.__setattr__(x, ...)`): one more
            ok = (not node.keywords and not any(isinstance(a, ast.Starred) for a in node.args)
                  and len(node.args) - values in (1, 2) and _is_str_literal(node.args[index]))
            if not ok:
                found.append((node.lineno, func.attr))
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Name):
            if node.id in REFLECTION_NAMES | OPERATOR_PRIMITIVES:
                found.append((line, node.id))
            elif node.id in ("getattr", "hasattr") and id(node) not in called:
                found.append((line, node.id))  # `map(getattr, ...)`, `partial(getattr, ...)`: the name argument is hidden
        elif isinstance(node, ast.Attribute):
            if node.attr in REFLECTION_DUNDERS | OPERATOR_PRIMITIVES:
                found.append((line, node.attr))
            elif node.attr in DUNDER_ACCESSORS and id(node) not in called:
                found.append((line, node.attr))
        elif isinstance(node, ast.alias) and node.name.split(".")[-1] in REFLECTION_NAMES | OPERATOR_PRIMITIVES:
            found.append((getattr(node, "lineno", 0), node.name.split(".")[-1]))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs                 and node.value in REFLECTION_DUNDERS:
            found.append((line, node.value))  # `getattr(x, "__globals__")`: a literal name reaching the same place
    return sorted(set(found))


#: Backend file -> (reflection primitives it may use, reason). Frozen from the real uses on 2026-10-12. Adding a use means
#: editing this dict in plain view; an entry whose primitive is no longer used fails (test below). `ofo_app/routes/` gets
#: no entry: route code never needs reflection.
REFLECTION_ALLOWED: dict[str, tuple[frozenset[str], str]] = {
    "ofo/engine/black_scholes.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/engine/model.py": (frozenset({'__setattr__', 'getattr'}),
        "token-checked frozen value: `object.__setattr__(obj, name, fields[name])` over `__slots__`; repr reads the same slots"),
    "ofo/entitlements/ledger.py": (frozenset({'__setattr__'}),
        "rebuilds/initialises its own frozen value with `object.__setattr__(self, name, ...)`, name from its own field list"),
    "ofo/errors/model.py": (frozenset({'__code__', 'getattr'}),
        "captures the wording checker's functions, `__code__` objects and data at import, then re-compares them (the checker-changed guard)"),
    "ofo/errors/templates.py": (frozenset({'getattr'}),
        "hashes each template part by a fixed tuple of part names"),
    "ofo/execution/context.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/execution/partial.py": (frozenset({'__setattr__'}),
        "Preparation sets its own fields once, `object.__setattr__(self, name, value)`"),
    "ofo/execution/planned.py": (frozenset({'getattr'}),
        "compares one fixed attribute across the legs of a plan"),
    "ofo/history/bars.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/instruments/models.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/marketdata/health.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/marketdata/quote.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/orders/model.py": (frozenset({'__setattr__', 'getattr'}),
        "Order.replace clones a frozen dataclass field by field"),
    "ofo/rules/conditions.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/rules/plan.py": (frozenset({'__setattr__', 'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value; stores the checked tuple back"),
    "ofo/strategy/definition.py": (frozenset({'getattr'}),
        "diffs two versions of a definition over a fixed tuple of field labels"),
    "ofo/strategy/guard.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/strategy/live_state.py": (frozenset({'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value"),
    "ofo/strategy/model.py": (frozenset({'__setattr__', 'getattr'}),
        "reads its own declared field names (`getattr(self, name)` over a fixed tuple) to validate a frozen value; stores the checked tuples back"),
    "ofo/strategy/versions.py": (frozenset({'__setattr__'}),
        "StrategyVersion.__setattr__ forwards an allowed write to object.__setattr__"),
    "ofo/table/model.py": (frozenset({'getattr'}),
        "sums a fixed tuple of position field names"),
    "ofo/wording.py": (frozenset({'__class__', '__code__', '__getattribute__'}),
        "the wording checker guards itself: captures `__code__` at import, reads through ModuleType.__getattribute__, swaps its module class to a frozen one"),
    "ofo_app/alembic/versions/0006_index_segments.py": (frozenset({'getattr', 'globals'}),
        "migration copies the public names of the shared baseline helper into its namespace; never runs in the API process"),
    "ofo_app/api_models.py": (frozenset({'__mro__', 'getattr'}),
        "the door itself: walks ApiModel's own MRO and reads declared fields off a model by name"),
    "ofo_app/catalogue_store.py": (frozenset({'getattr'}),
        "compares a stored and a new contract over the fixed REVISABLE_FIELDS tuples"),
    "ofo_app/closed_namespace.py": (frozenset({'__dict__'}),
        "the closed-namespace helper reads the class namespace it closes"),
    "ofo_app/history_store.py": (frozenset({'getattr'}),
        "maps a fixed tuple of bar field names to DB columns"),
    "ofo_app/redaction.py": (frozenset({'__dict__'}),
        "log-record redaction replaces a record's __dict__ with a redacting dict"),
}

NO_REFLECTION_PREFIXES = ("ofo_app/routes/",)


def reflection_violations(source: str, where: str, allowed: dict[str, tuple[frozenset[str], str]] | None = None) -> list[str]:
    """`file:line primitive` for each use of a reflection primitive that `where` is not allowed (empty = clean)."""
    table = REFLECTION_ALLOWED if allowed is None else allowed
    permitted = table.get(where, (frozenset(), ""))[0]
    return [f"{where}:{line} uses {prim}" for line, prim in reflection_uses(source, where) if prim not in permitted]


def _uses_by_file() -> dict[str, set[str]]:
    return {p.relative_to(BACKEND).as_posix(): {prim for _, prim in reflection_uses(p.read_text(encoding="utf-8"))}
            for p in _product_files()}


def test_every_reflection_use_in_backend_is_on_the_allow_list() -> None:
    files = _product_files()
    assert len(files) > 50
    bad = [v for p in files for v in reflection_violations(p.read_text(encoding="utf-8"), p.relative_to(BACKEND).as_posix())]
    assert bad == []


def test_every_allow_list_entry_is_still_used() -> None:
    """A stale entry is a hole (a later use would pass unseen), so the list must equal what the code really uses."""
    used = _uses_by_file()
    stale = [f"{f}: {sorted(prims - used.get(f, set()))}" for f, (prims, _) in REFLECTION_ALLOWED.items()
             if prims - used.get(f, set())]
    assert stale == []
    assert all(reason.strip() for _, reason in REFLECTION_ALLOWED.values())
    assert all(prims <= PRIMITIVES for prims, _ in REFLECTION_ALLOWED.values())


def test_route_code_gets_no_reflection_allowance() -> None:
    assert [f for f in REFLECTION_ALLOWED if f.startswith(NO_REFLECTION_PREFIXES)] == []
    routes = [p for p in _product_files() if p.relative_to(BACKEND).as_posix().startswith(NO_REFLECTION_PREFIXES)]
    assert routes  # the directory exists and was scanned


def test_the_domain_never_imports_the_application_package() -> None:
    """Layering: backend/ofo is standard library only, so domain reflection can never reach the door module."""
    bad = []
    for p in _product_files():
        rel = p.relative_to(BACKEND).as_posix()
        if not rel.startswith("ofo/"):
            continue
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "ofo_app" for a in node.names):
                bad.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "ofo_app":
                bad.append(f"{rel}:{node.lineno}")
    assert bad == []


def test_forger9_is_flagged_by_the_reflection_scan() -> None:
    assert door_name_uses(FORGER9, "ofo_app/routes/forger9.py") == []  # the round 4-7 scans are CLEAN on it (the gap)
    assert reflection_violations(FORGER9, "ofo_app/routes/forger9.py")


@pytest.mark.parametrize("source, primitive", [
    ("setattr(a, n, 1)", "setattr"),
    ("setattr(a, 'x', 1)", "setattr"),
    ("delattr(a, n)", "delattr"),
    ("x = getattr(a, n)", "getattr"),
    ("x = getattr(a, 'x' + n)", "getattr"),
    ("x = getattr(a)", "getattr"),
    ("x = hasattr(a, n)", "hasattr"),
    ("object.__setattr__(a, n, 1)", "__setattr__"),
    ("a.__setattr__(n, 1)", "__setattr__"),
    ("object.__delattr__(a, n)", "__delattr__"),
    ("a.__getattribute__(n)", "__getattribute__"),
    ("f = a.__setattr__", "__setattr__"),
    ("eval('1')", "eval"),
    ("exec('x = 1')", "exec"),
    ("compile('1', 'f', 'eval')", "compile"),
    ("globals()", "globals"),
    ("locals()", "locals"),
    ("vars(a)", "vars"),
    ("a.__subclasses__()", "__subclasses__"),
    ("a.__mro__", "__mro__"),
    ("a.__bases__", "__bases__"),
    ("f.__globals__", "__globals__"),
    ("f.__code__", "__code__"),
    ("f.__closure__", "__closure__"),
    ("m.__func__", "__func__"),
    ("m.__self__", "__self__"),
    ("a.__class__ = B", "__class__"),
    ("x = a.__class__", "__class__"),
    ("a.__dict__['k'] = 1", "__dict__"),
    ("import operator\nf = operator.attrgetter(n)", "attrgetter"),
    ("import operator\nf = operator.methodcaller(n)", "methodcaller"),
    ("from operator import attrgetter", "attrgetter"),
    ("import functools\nf = functools.partial(setattr, a)", "setattr"),
    ("f = functools.partial(getattr, a)", "getattr"),
    ("list(map(getattr, xs, names))", "getattr"),
    ("x = getattr(a, '__globals__')", "__globals__"),
])
def test_every_reflection_primitive_is_flagged_on_its_own(source: str, primitive: str) -> None:
    assert primitive in {p for _, p in reflection_uses(source)}, source
    assert reflection_violations(source, "ofo_app/routes/plant.py")


@pytest.mark.parametrize("source", [
    "x = getattr(self, 'name')",
    "x = getattr(self, 'name', None)",
    "x = hasattr(self, 'name')",
    "object.__setattr__(self, 'name', 1)",
    "self.__setattr__('name', 1)",
    "object.__delattr__(self, 'name')",
    "import re\nP = re.compile('x')",
    "class A:\n    def __setattr__(self, name, value):\n        raise TypeError(name)",
    "def f():\n    '''setattr, eval and __globals__ in a docstring are not code'''",
    "# setattr(a, n, 1) in a comment\nx = 1",
    "x = a.mro_like",
])
def test_the_reflection_scan_passes_literal_and_ordinary_code(source: str) -> None:
    assert reflection_uses(source) == [], source


def test_a_use_not_on_the_list_names_the_file_line_and_primitive() -> None:
    bad = reflection_violations("x = 1\nsetattr(a, n, 1)\n", "ofo/engine/model.py")
    assert bad == ["ofo/engine/model.py:2 uses setattr"]
    # an allowed primitive in an allowed file is quiet; the same primitive in another file is not
    assert reflection_violations("object.__setattr__(o, n, 1)", "ofo/engine/model.py") == []
    assert reflection_violations("object.__setattr__(o, n, 1)", "ofo/engine/inputs.py")


def test_a_planted_route_file_is_caught_by_the_real_scan(tmp_path: Path) -> None:
    """End to end on a file: the same function the real scan calls refuses forger9 planted as a route; routes have no
    allowance, so even a lone computed getattr there is refused."""
    plant = tmp_path / "forger9.py"
    plant.write_text(FORGER9, encoding="utf-8")
    assert reflection_violations(plant.read_text(encoding="utf-8"), "ofo_app/routes/forger9.py")
    assert reflection_violations("x = getattr(a, n)", "ofo_app/routes/anything.py")


# --- round 9 (issue #197, ADR-003 Q235): only the app-assembly files name the framework's app-assembly surface ------------
# Round 8 closed the reflection entry points, but plain attribute writes on the framework's app object reach the door's own
# internals (`request.app.user_middleware.clear()`, `request.app.middleware_stack.app.exempt = ...`). The surface for that is
# a small CLOSED set of framework names, so the rule is an allow-list by file. Written red first (xfail strict, step 1).

ROUND9_ATTACKS = {
    "A1_strip_boundary": '''
def x(request):
    request.app.user_middleware.clear()
    request.app.middleware_stack = None
''',
    "A2_reroute_stack_app": '''
def x(request):
    request.app.middleware_stack.app = request.app.middleware_stack.app.app
''',
    "A3_widen_exempt": '''
def x(request):
    request.app.middleware_stack.app.exempt = frozenset({("GET", "/raw")})
''',
    "A4_outer_rewriter": '''
from starlette.middleware import Middleware
class Rewriter:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)
def x(request):
    request.app.user_middleware.insert(0, Middleware(Rewriter))
    request.app.middleware_stack = None
''',
    "A5_raw_route": '''
from starlette.routing import Route
def x(request):
    request.app.router.routes.append(Route("/raw", None))
''',
    "A6_dependency_overrides": '''
def x(request):
    request.app.dependency_overrides[get_ctx] = lambda: None
''',
}
ROUND9_PLACES = ("ofo_app/routes/evil.py", "ofo_app/evil.py")


#: Attribute names of the framework's app-assembly surface: the middleware slot and stack, routes and routers, handlers,
#: lifecycle, schema and dependency overrides. Any access (read, write, call, `getattr` string) outside an allowed file fails.
APP_ASSEMBLY_ATTRS = frozenset({
    "user_middleware", "middleware_stack", "add_middleware", "middleware", "build_middleware_stack", "exempt", "router",
    "routes", "route_class", "add_route", "add_api_route", "add_websocket_route", "api_route", "mount", "host",
    "include_router", "dependency_overrides", "exception_handlers", "add_exception_handler", "exception_handler",
    "add_event_handler", "on_event", "lifespan_context", "openapi_schema",
    "app",  # `request.app`, `scope["app"]`, `self.app`: the way to OBTAIN the app object, so aliasing cannot hide the rest
})
#: Names (a name, an attribute or an imported name) that build or reach the app or its boundary.
APP_ASSEMBLY_NAMES = frozenset({"FastAPI", "Starlette", "_Boundary", "create_app"})
#: `state` is also an ordinary word (`work.state()`), so it counts only on a chain rooted in `app`.
APP_STATE_ATTR = "state"
APP_TOKENS = APP_ASSEMBLY_ATTRS | APP_ASSEMBLY_NAMES | {APP_STATE_ATTR, "ClosedRoute"}


def _rooted_in_app(node: ast.AST) -> bool:
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        if isinstance(node, ast.Attribute) and node.attr == "app":
            return True
        node = node.value if not isinstance(node, ast.Call) else node.func
    return isinstance(node, ast.Name) and node.id == "app"


def app_assembly_uses(source: str) -> list[tuple[int, str]]:
    """Every (line, token) in `source` that names the framework's app-assembly surface (see APP_ASSEMBLY_ATTRS). Complete
    over the closed set of names, whatever the object they are read off (a name is flagged where it is written). A string
    that spells one (also folded from literal parts) counts; docstrings and comments do not. `ClosedRoute` is only legal as
    the `route_class=` of an `APIRouter(...)` call (and in an import line)."""
    tree = ast.parse(source)
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    legal_route_class = {id(k.value) for n in ast.walk(tree) if isinstance(n, ast.Call)
                         and _dotted(n.func).split(".")[-1] == "APIRouter" for k in n.keywords if k.arg == "route_class"}
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Attribute):
            if node.attr in APP_ASSEMBLY_ATTRS | APP_ASSEMBLY_NAMES | {"ClosedRoute"}:
                found.append((line, node.attr))
            elif node.attr == APP_STATE_ATTR and _rooted_in_app(node.value):
                found.append((line, APP_STATE_ATTR))
        elif isinstance(node, ast.Name):
            if node.id in APP_ASSEMBLY_NAMES or (node.id == "ClosedRoute" and id(node) not in legal_route_class):
                found.append((line, node.id))
        elif isinstance(node, ast.alias):
            if node.name.split(".")[-1] in APP_ASSEMBLY_NAMES:
                found.append((line, node.name.split(".")[-1]))
        elif isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp, ast.Call)) and id(node) not in docs:
            text = _fold(node)
            if text in APP_ASSEMBLY_ATTRS | APP_ASSEMBLY_NAMES:
                found.append((line, text))
    return sorted(set(found))


#: Backend file -> (tokens it may use, reason). Frozen from the real uses on 2026-10-12. Only the app-assembly files are
#: listed. `ofo_app/routes/` gets nothing except `broker.py`'s mount helper and its `request.app.state.broker` read, and never
#: a middleware, routing-table or handler token (test below).
APP_ASSEMBLY_ALLOWED: dict[str, tuple[frozenset[str], str]] = {
    "ofo_app/main.py": (frozenset({"FastAPI", "router", "include_router", "dependency_overrides", "route_class",
                                   "ClosedRoute", "mount"}),
        "create_app: the one place that builds the FastAPI app, sets the route class, includes the routers and installs "
        "the test override of the market context"),
    "ofo_app/errors.py": (frozenset({"FastAPI", "app", "exempt", "add_middleware", "add_exception_handler", "_Boundary",
                                     "ClosedRoute"}),
        "the door itself: ClosedRoute and _Boundary are defined here; install(app) adds the boundary and the one handler"),
    "ofo_app/routes/broker.py": (frozenset({"FastAPI", "app", "state", "include_router", "add_api_route"}),
        "broker.mount(app, config) stores the runtime on app.state and adds the callback route; get-runtime reads "
        "request.app.state.broker"),
}
#: The most a route module may ever be allowed: the broker mount helper's tokens. Never a middleware or handler token.
ROUTES_TOKEN_CEILING = frozenset({"FastAPI", "app", "state", "include_router", "add_api_route"})


def app_assembly_violations(source: str, where: str, allowed: dict[str, tuple[frozenset[str], str]] | None = None) -> list[str]:
    table = APP_ASSEMBLY_ALLOWED if allowed is None else allowed
    permitted = table.get(where, (frozenset(), ""))[0]
    return [f"{where}:{line} uses {tok}" for line, tok in app_assembly_uses(source) if tok not in permitted]


def every_scan(source: str, where: str) -> list[str]:
    """What the whole backend scan reports for one file (each scan the real tests run, with the real allow-lists)."""
    return (door_name_uses(source, where) + forbidden_module_uses(source, where) + reflection_violations(source, where)
            + app_assembly_violations(source, where))


@pytest.mark.parametrize("where", ROUND9_PLACES)
@pytest.mark.parametrize("name", sorted(ROUND9_ATTACKS))
def test_round9_every_app_assembly_attack_is_flagged_in_routes_and_elsewhere(name: str, where: str) -> None:
    assert every_scan(ROUND9_ATTACKS[name], where), (name, where)


def test_every_app_assembly_use_in_backend_is_in_an_allowed_file() -> None:
    files = _product_files()
    assert len(files) > 50
    bad = [v for p in files for v in app_assembly_violations(p.read_text(encoding="utf-8"), p.relative_to(BACKEND).as_posix())]
    assert bad == []


def _assembly_uses_by_file() -> dict[str, set[str]]:
    return {p.relative_to(BACKEND).as_posix(): {t for _, t in app_assembly_uses(p.read_text(encoding="utf-8"))}
            for p in _product_files()}


def test_every_app_assembly_allowance_is_still_used() -> None:
    """A stale token is a hole (a later use would pass unseen), so each entry equals what its file really uses."""
    used = _assembly_uses_by_file()
    stale = [f"{f}: {sorted(toks ^ used.get(f, set()))}" for f, (toks, _) in APP_ASSEMBLY_ALLOWED.items()
             if toks != used.get(f, set())]
    assert stale == []
    assert all(reason.strip() for _, reason in APP_ASSEMBLY_ALLOWED.values())
    assert all(toks <= APP_TOKENS for toks, _ in APP_ASSEMBLY_ALLOWED.values())


def test_only_the_assembly_files_name_the_app_and_routes_get_no_middleware_token() -> None:
    assert set(APP_ASSEMBLY_ALLOWED) == {"ofo_app/main.py", "ofo_app/errors.py", "ofo_app/routes/broker.py"}
    routes = {f: toks for f, (toks, _) in APP_ASSEMBLY_ALLOWED.items() if f.startswith("ofo_app/routes/")}
    assert all(toks <= ROUTES_TOKEN_CEILING for toks in routes.values())
    assert not any(f.startswith("ofo/") for f in APP_ASSEMBLY_ALLOWED)  # the domain never names the app
    assert any(p.relative_to(BACKEND).as_posix().startswith("ofo_app/routes/") for p in _product_files())


REQUIRED_ASSEMBLY_ATTRS = ("user_middleware", "middleware_stack", "add_middleware", "middleware", "build_middleware_stack",
                           "exempt", "router", "routes", "add_route", "add_api_route", "add_websocket_route", "api_route",
                           "mount", "host", "include_router", "dependency_overrides", "exception_handlers",
                           "add_exception_handler", "exception_handler", "add_event_handler", "on_event", "lifespan_context",
                           "openapi_schema")


def test_the_assembly_set_holds_every_required_name() -> None:
    """The set is pinned by name, so dropping one cannot hide behind another name in the same attack."""
    assert set(REQUIRED_ASSEMBLY_ATTRS) <= APP_ASSEMBLY_ATTRS and {"_Boundary", "FastAPI", "Starlette"} <= APP_ASSEMBLY_NAMES


@pytest.mark.parametrize("token", sorted(APP_ASSEMBLY_ATTRS))
def test_each_assembly_attribute_is_flagged_on_its_own(token: str) -> None:
    assert [t for _, t in app_assembly_uses(f"x.{token}")] == [token]
    assert app_assembly_violations(f"x.{token} = 1", "ofo_app/evil.py")


def test_a_routes_file_cannot_be_allow_listed_for_the_middleware_slot() -> None:
    """Mutation guard: the ceiling is what keeps `routes/` from being granted app assembly."""
    assert not ROUTES_TOKEN_CEILING & {"user_middleware", "middleware_stack", "exempt", "router", "routes",
                                       "add_middleware", "dependency_overrides", "_Boundary"}
    for name, source in ROUND9_ATTACKS.items():
        assert app_assembly_violations(source, "ofo_app/routes/broker.py"), name  # even broker.py is refused for these


@pytest.mark.parametrize("source", [
    "request.app.router.routes.append(r)",
    "app.dependency_overrides[k] = v",
    "scope['app'].user_middleware.clear()",
    "x = getattr(a, 'middle' + 'ware_stack')",
    "a = request.app\na.middleware_stack = None",
    "app.state.x = 1",
    "from fastapi import FastAPI\nFastAPI()",
    "import starlette.applications as s\ns.Starlette()",
    "from ofo_app.main import create_app",
    "@app.middleware('http')\nasync def f(r, n): ...",
    "app.add_exception_handler(E, h)",
    "app.mount('/x', y)",
    "router.add_api_route('/x', f)",
    "router.routes.append(r)",
    "router.include_router(other)",
    "from ofo_app.errors import ClosedRoute\nclass R(ClosedRoute): ...",
    "from ofo_app.errors import _Boundary",
])
def test_app_assembly_scan_refuses_every_shape(source: str) -> None:
    assert app_assembly_violations(source, "ofo_app/routes/plant.py"), source


@pytest.mark.parametrize("source", [
    "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/x')\ndef f(): ...",
    "from ofo_app.errors import ClosedRoute\nrouter = APIRouter(route_class=ClosedRoute)\n@router.post('/x', status_code=201)\ndef f(): ...",
    "@router.put('/x')\n@router.delete('/y')\n@router.patch('/z')\ndef f(): ...",
    "x = work.state()\nrequest.state.user = 1",
    "def f():\n    '''request.app.middleware_stack in a docstring is not code'''",
    "# app.router in a comment\nx = 1",
    "label = 'application'",
])
def test_app_assembly_scan_passes_route_declaration_and_ordinary_code(source: str) -> None:
    assert app_assembly_violations(source, "ofo_app/routes/ok.py") == [], source


def test_a_planted_route_file_and_a_planted_module_are_caught_by_the_real_scan(tmp_path: Path) -> None:
    """End to end on files: the function the real scan calls refuses A1 planted as a route and as a plain module."""
    plant = tmp_path / "evil.py"
    plant.write_text(ROUND9_ATTACKS["A1_strip_boundary"], encoding="utf-8")
    for where in ROUND9_PLACES:
        assert app_assembly_violations(plant.read_text(encoding="utf-8"), where)
