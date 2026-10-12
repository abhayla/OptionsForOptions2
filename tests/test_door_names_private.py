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
