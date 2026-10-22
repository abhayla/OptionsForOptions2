"""REQ-050 AC-2 (W-136): per-strategy work stays per strategy - no per-strategy module reads or writes the shared cache.

The shared cache (``ofo.marketdata.shared_compute``) holds market-wide figures only. A strategy's P&L, risk and rules
are computed per active strategy and must never go through it (a hit there would serve one strategy's number to
another). This is an ALLOW-LIST: only the files below may touch the module; every other backend file is scanned, and a
file that cannot be parsed fails the test (fail closed). A reference by import (absolute, relative, aliased, from the
package, ``__import__``/``importlib`` string) or by any identifier or string naming the module or its classes counts.

Threat model: in scope - a per-strategy module importing or naming the cache, however spelled; out of scope - code built
at run time from pieces of the name, and test files.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
MODULE = "ofo.marketdata.shared_compute"
NAMES = ("shared_compute", "SharedCompute", "SharedKey", "FeedScope")

#: The only files that may name the shared cache, each with the market-wide figure it serves.
ALLOWED = {
    "backend/ofo/marketdata/shared_compute.py": "the cache itself",
    "backend/ofo/outcome/snapshot.py": "each expiry's forward (market-wide)",
    "backend/ofo/outcome/service.py": "each leg's implied volatility (market-wide; strategy maths stays per strategy)",
    "backend/ofo_app/routes/outcome.py": "owns the one process cache and the feed owner it passes",
}

#: Per-strategy code: never allowed to touch the cache (this list documents intent; the allow-list is what enforces).
PER_STRATEGY_DIRS = ("backend/ofo/engine/", "backend/ofo/rules/", "backend/ofo/table/", "backend/ofo/scenario/",
                     "backend/ofo/charges/", "backend/ofo/tracking/")


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def package_of(path_rel: str) -> list[str]:
    parts = path_rel.removesuffix(".py").split("/")[1:]  # drop "backend"
    return parts[:-1]  # the directory of the file: its package, for a module and for an __init__ alike


def references(source: str, path_rel: str) -> list[str]:
    """Every way ``source`` names the shared cache; raises SyntaxError on code it cannot parse (fail closed)."""
    found: list[str] = []
    base = package_of(path_rel)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name == MODULE or a.name.startswith(MODULE + ".")]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(base) - (node.level - 1)
                target = ".".join([*base[:max(keep, 0)], *([node.module] if node.module else [])])
            else:
                target = node.module or ""
            if target == MODULE or target.startswith(MODULE + "."):
                found.append(target)
            elif target == "ofo.marketdata" and any(a.name in ("shared_compute", "*") for a in node.names):
                found.append(f"{target}:{[a.name for a in node.names]}")
        elif isinstance(node, ast.Name) and node.id in NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in NAMES:
            found.append(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and any(n in node.value for n in NAMES):
            found.append(node.value)
    return found


def backend_files() -> list[pathlib.Path]:
    files = sorted(p for p in BACKEND.rglob("*.py") if "__pycache__" not in p.parts)
    assert len(files) > 100, "the scan found almost no files: wrong root"  # discovery, never a fixed list
    return files


def test_only_the_allow_listed_files_name_the_shared_cache():
    offenders: dict[str, list[str]] = {}
    for path in backend_files():
        path_rel = rel(path)
        try:
            refs = references(path.read_text(encoding="utf-8"), path_rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:  # fail closed on a file it cannot read
            pytest.fail(f"{path_rel} cannot be parsed ({type(exc).__name__}); the class check fails closed")
        if refs and path_rel not in ALLOWED:
            offenders[path_rel] = refs
    assert not offenders, f"files outside the allow-list name the shared cache: {offenders}"


def test_every_allow_listed_file_exists_and_really_uses_the_cache():
    for path_rel in ALLOWED:
        path = ROOT / path_rel
        assert path.is_file(), f"{path_rel} is allow-listed but missing: remove it from ALLOWED"
        assert references(path.read_text(encoding="utf-8"), path_rel), f"{path_rel} no longer uses the cache"


def test_no_per_strategy_module_is_allow_listed():
    assert not [p for p in ALLOWED if p.startswith(PER_STRATEGY_DIRS)]
    for directory in PER_STRATEGY_DIRS:
        assert (ROOT / directory).is_dir(), f"{directory} moved: update the class table"


@pytest.mark.parametrize("source", [
    "from ofo.marketdata.shared_compute import SharedCompute",
    "import ofo.marketdata.shared_compute as sc",
    "from ofo.marketdata import shared_compute",
    "from ofo.marketdata import *",
    "from ofo.marketdata import shared_compute as sc",
    "from ..marketdata.shared_compute import SharedKey",
    "from ..marketdata import shared_compute",
    "import importlib\nm = importlib.import_module('ofo.marketdata.shared_compute')",
    "m = __import__('ofo.marketdata.shared_compute')",
    "from ofo.marketdata.shared_compute import SharedCompute as Cache",
    "x = SharedKey",
    "x = obj.SharedCompute",
])
def test_the_scanner_catches_every_spelling(source):
    assert references(source, "backend/ofo/engine/estimate.py"), source


def test_the_scanner_passes_unrelated_imports_and_fails_closed_on_unparsable_code():
    assert references("from ofo.marketdata.forward import parity_forward\nimport math", "backend/ofo/engine/x.py") == []
    with pytest.raises(SyntaxError):
        references("def broken(:\n", "backend/ofo/engine/x.py")
