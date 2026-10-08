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
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            args = node.args
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
])
def test_scan_catches_every_shape(source):
    assert violations(source), source


@pytest.mark.parametrize("source", [
    "from ofo.engine.black_scholes import GREEK_STEP, Greeks",
    "from ofo.engine.model import ModelInputs, leg_greeks_unrounded",
    "x = getattr(position, name)",
    '"""bs_greeks in a docstring is not code"""',
])
def test_scan_passes_the_allowed_shapes(source):
    assert violations(source) == [], source
