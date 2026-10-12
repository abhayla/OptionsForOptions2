"""W-070 round 4 (issue #197, finding sealed-object-mutable-after-seal): no product code outside the door's own module
names the door's private state.

Python has no truly private state, so a hidden store only moves the write door. The guard is two things: the door
re-checks every header value of its minted record (tests_app/test_response_door.py), and this scan, which fails when
any file under backend/ other than backend/ofo_app/errors.py uses `_freeze`, `_frozen`, `_SEAL`, `_REDIRECT_MINT` or
`_verify` as a name, an attribute, an imported name, a keyword or a string (``getattr(r, "_frozen")``). It reads the
source with ``ast`` (docstrings and comments are not code; a string that is only a docstring is skipped), so a longer
name such as ``_deep_freeze`` or ``_verify_checker`` is not a match.
"""
import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
DOOR_MODULE = BACKEND / "ofo_app" / "errors.py"
DOOR_NAMES = frozenset({"_freeze", "_frozen", "_SEAL", "_REDIRECT_MINT", "_verify"})


def door_name_uses(source: str, where: str = "<src>") -> list[str]:
    """Every place `source` names a door-private name (empty = clean)."""
    tree = ast.parse(source)
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    found: list[str] = []
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
        hit = next((n for n in names if n in DOOR_NAMES), None)
        if hit is not None:
            found.append(f"{where}:{getattr(node, 'lineno', 0)} names {hit}")
    return found


def _product_files() -> list[Path]:
    return [p for p in BACKEND.rglob("*.py") if p != DOOR_MODULE and "__pycache__" not in p.parts]


def test_no_backend_file_but_the_door_names_its_private_state() -> None:
    files = _product_files()
    assert len(files) > 50 and DOOR_MODULE.exists()  # the scan really walks backend/ofo and backend/ofo_app
    bad = [v for p in files for v in door_name_uses(p.read_text(encoding="utf-8"), str(p.relative_to(BACKEND)))]
    assert bad == []


def test_the_door_module_does_name_them() -> None:
    """The scan is not vacuous: the one allowed file really uses every name, so the exemption is what keeps it quiet."""
    used = {v.rsplit(" ", 1)[1] for v in door_name_uses(DOOR_MODULE.read_text(encoding="utf-8"))}
    assert used == DOOR_NAMES


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

_ROUND5 = pytest.mark.xfail(strict=True, reason="round 5 step 1: the scan does not see this shape yet")

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


@_ROUND5
@pytest.mark.parametrize("source", FORGERY_SHAPES)
def test_scan_catches_every_way_to_forge_an_emitted_body(source: str) -> None:
    assert door_name_uses(source), source


@_ROUND5
@pytest.mark.parametrize("source", GAP_SHAPES)
def test_scan_catches_every_indirect_way_to_a_door_name(source: str) -> None:
    assert door_name_uses(source), source
