"""W-060 round 3, second layer (B8: the ModelInputs type is the first): no product code reaches the engine's pricing
functions except through ofo.engine.model.

Outside backend/ofo/engine/, no module may import, alias, name or getattr any of the pricing functions, import a
pricing module object (``black_scholes``, ``estimate``), ``import *`` from the engine, or import an engine module by a
computed name. The scan reads the source with ``ast`` (docstrings and comments are not code) and fails closed on any
shape it cannot resolve.
"""
import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
ENGINE = BACKEND / "ofo" / "engine"
FORBIDDEN = {"bs_price", "implied_volatility", "bs_greeks", "bs_greeks_unrounded", "forward_price", "estimate_now",
             "estimate_now_grid", "_price", "_solve_iv", "_greek_floats"}
PRICING_MODULES = {"ofo.engine.black_scholes", "ofo.engine.estimate"}
DYNAMIC_IMPORTS = {"__import__", "import_module"}
# engine-private names (round 4): the gate token, the constructor and the module aliases that hold the pricing code
ENGINE_PRIVATE = {"_bs", "_estimate", "_TOKEN", "_make"}
# modules whose single-underscore names are the gate's or the pricing code's (other engine modules, e.g. metrics,
# keep private helper names that are not a way round the gate)
PRICING_PACKAGE = {"ofo.engine", "ofo.engine.model", "ofo.engine.black_scholes", "ofo.engine.estimate"}


FORGEABLE = {"ModelInputs", "ExpiryModel"}  # the gated types: an instance may only come from model_inputs()


def _is_private(name: str) -> bool:
    """A single-underscore name (not a dunder): private to the engine package."""
    return name.startswith("_") and not name.startswith("__")


def violations(source: str, where: str = "<src>") -> list[str]:
    """Every pricing access in one product module's source (empty = clean)."""
    found: list[str] = []
    tree = ast.parse(source)
    module_names: set[str] = set()  # local names bound to an ofo.engine module object
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in PRICING_MODULES or alias.name == "ofo.engine" or alias.name.startswith("ofo.engine."):
                    if alias.name in PRICING_MODULES:
                        found.append(f"{where}:{node.lineno} imports pricing module {alias.name}")
                    module_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or not mod.startswith("ofo"):
                if node.level:
                    found.append(f"{where}:{node.lineno} relative import (cannot resolve; fail closed)")
                continue
            for alias in node.names:
                full = f"{mod}.{alias.name}"
                if alias.name == "*" and mod.startswith("ofo.engine"):
                    found.append(f"{where}:{node.lineno} 'from {mod} import *' (fail closed)")
                elif mod in PRICING_PACKAGE and _is_private(alias.name):
                    found.append(f"{where}:{node.lineno} imports engine-private {alias.name} from {mod}")
                elif alias.name in FORBIDDEN:
                    found.append(f"{where}:{node.lineno} imports {alias.name} from {mod}")
                elif full in PRICING_MODULES:
                    found.append(f"{where}:{node.lineno} imports pricing module {full}")
                elif mod.startswith("ofo.engine") and full.startswith("ofo.engine.") and alias.name.islower() \
                        and (BACKEND / Path(*full.split("."))).with_suffix(".py").exists():
                    module_names.add(alias.asname or alias.name)  # e.g. "from ofo.engine import model"
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN:
            found.append(f"{where}:{node.lineno} names {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN:
            found.append(f"{where}:{node.lineno} accesses .{node.attr}")
        elif isinstance(node, ast.Attribute) and (node.attr in ENGINE_PRIVATE or (
                _is_private(node.attr) and isinstance(node.value, ast.Name) and node.value.id in module_names)):
            found.append(f"{where}:{node.lineno} accesses engine-private .{node.attr}")
        elif isinstance(node, ast.Attribute) and node.attr == "__dict__":
            found.append(f"{where}:{node.lineno} reads .__dict__ (fail closed)")
        elif isinstance(node, ast.Attribute) and node.attr == "modules" and isinstance(node.value, ast.Name) \
                and node.value.id == "sys":
            found.append(f"{where}:{node.lineno} reads sys.modules (fail closed)")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            args = node.args
            if name == "__new__" and isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) \
                    and fn.value.id == "object" \
                    and (not args or not isinstance(args[0], ast.Name) or args[0].id in FORGEABLE):
                found.append(f"{where}:{node.lineno} object.__new__ on a gated type or an unresolved class (fail closed)")
            if name == "vars":
                found.append(f"{where}:{node.lineno} vars(...) (fail closed)")
            if name == "getattr" and len(args) >= 2:
                target, attr = args[0], args[1]
                if isinstance(attr, ast.Constant) and attr.value in FORBIDDEN:
                    found.append(f"{where}:{node.lineno} getattr(..., {attr.value!r})")
                elif isinstance(target, ast.Name) and target.id in module_names and not isinstance(attr, ast.Constant):
                    found.append(f"{where}:{node.lineno} getattr on engine module {target.id} by a computed name")
            elif name in DYNAMIC_IMPORTS and args:
                if not isinstance(args[0], ast.Constant):
                    found.append(f"{where}:{node.lineno} {name} with a computed module name (fail closed)")
                elif str(args[0].value).startswith("ofo.engine"):
                    found.append(f"{where}:{node.lineno} {name}({args[0].value!r})")
    return found


def _product_files():
    return [p for p in BACKEND.rglob("*.py") if ENGINE not in p.parents and "__pycache__" not in p.parts]


def test_no_product_module_reaches_a_pricing_function():
    files = _product_files()
    assert len(files) > 50  # the scan really walks the product tree (backend/ofo and backend/ofo_app)
    bad = [v for p in files for v in violations(p.read_text(encoding="utf-8"), str(p.relative_to(BACKEND)))]
    assert bad == []


@pytest.mark.parametrize("source", [
    "from ofo.engine.black_scholes import bs_greeks",
    "from ofo.engine.black_scholes import bs_greeks_unrounded as g",
    "from ofo.engine.estimate import estimate_now",
    "from ofo.engine import black_scholes",
    "from ofo.engine import estimate as e",
    "import ofo.engine.black_scholes as bs",
    "from ofo.engine.black_scholes import *",
    "from ofo.engine import *",
    "import ofo.engine.model as m\nx = m.implied_volatility",
    "import ofo\nofo.engine.black_scholes.bs_price(1)",
    "getattr(obj, 'forward_price')",
    "from ofo.engine import model\nf = getattr(model, name)",
    "import importlib\nimportlib.import_module('ofo.engine.black_scholes')",
    "import importlib\nimportlib.import_module(name)",
    "__import__('ofo.engine.estimate')",
    "from .black_scholes import bs_price",
    # round 4: the reviewer's five shapes, plus the remaining private/forging shapes
    "from ofo.engine.model import _bs\nf = vars(_bs)['bs_price']",
    "from ofo.engine import model\nf = model._bs.__dict__['bs' + '_price']",
    "import sys\nbs = sys.modules['ofo.engine.black_scholes']",
    "from ofo.engine.model import _TOKEN, ModelInputs\nModelInputs._make(_TOKEN)",
    "from ofo.engine.model import _estimate as e\nx = e.__dict__",
    "from ofo.engine.model import ModelInputs\no = object.__new__(ModelInputs)",
    "from ofo.engine import model\nx = model._anything",
    "from ofo.engine.model import _helper",
    "x = vars(obj)",
])
def test_scan_catches_every_shape(source):
    assert violations(source), source


@pytest.mark.parametrize("source", [
    "from ofo.engine.black_scholes import GREEK_STEP, Greeks",
    "from ofo.engine.model import ModelInputs, leg_greeks_unrounded",
    "x = getattr(position, name)",
    "from ofo.engine.metrics import _Unlimited",
    "clone = object.__new__(Order)",
    '"""bs_greeks in a docstring is not code"""',
])
def test_scan_passes_the_allowed_shapes(source):
    assert violations(source) == [], source
