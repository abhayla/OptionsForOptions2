"""REQ-117 AC-5 (W-132): no safety-gate module imports the broker flag modules (a source scan).

Gate modules are named by path: the safety gate and its inputs, the margin and freeze checks, the send guard, the price
check, the plan, review and sequence, the kill switch, and EVERY module in ``backend/ofo/reconciliation`` (discovered
from the tree). Imports are found by import SOURCE with ``ast`` (an alias or a function-level import does not hide
one); a file that is missing or does not parse is a failure, never a skip. The behaviour half of AC-5 is
``tests/execution/test_flags_never_loosen_gates.py``.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parents[2]
GATE_FILES = ("backend/ofo/execution/safety.py", "backend/ofo/execution/context.py",
              "backend/ofo/execution/margin_gate.py", "backend/ofo/execution/freeze.py",
              "backend/ofo/execution/send_guard.py", "backend/ofo/execution/price_check.py",
              "backend/ofo/execution/planned.py", "backend/ofo/execution/review.py",
              "backend/ofo/execution/sequence.py", "backend/ofo_app/order_path_switch.py")
GATE_FOLDERS = ("backend/ofo/reconciliation",)
FLAG_MODULES = ("ofo.broker.flags", "ofo.broker.kite_flags", "flags", "kite_flags")
FLAG_LEAVES = ("flags", "kite_flags")


def _flag_imports(source: str) -> list[str]:
    """Flag modules a source imports, by import source: ``import x.y``, ``from x import y``, ``from . import y``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names if a.name in FLAG_MODULES)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FLAG_MODULES or any(a.name in FLAG_LEAVES for a in node.names):
                found.append(module or ".")
    return found


def _gate_sources() -> list[Path]:
    paths = [ROOT / rel for rel in GATE_FILES]
    for folder in GATE_FOLDERS:
        paths.extend(sorted((ROOT / folder).rglob("*.py")))
    return paths


def test_ac5_no_gate_module_imports_the_flag_modules() -> None:
    """AC-5: discovered gate sources import no flag module."""
    paths = _gate_sources()
    assert len(paths) >= len(GATE_FILES) + 5  # the reconciliation folder really contributed files
    for path in paths:
        assert path.is_file(), f"{path} is missing: a gate module cannot be cleared unread"
        assert _flag_imports(path.read_text(encoding="utf-8")) == [], path.name


@pytest.mark.parametrize("planted", [
    "import ofo.broker.flags\n", "from ofo.broker.flags import is_supported\n", "from ofo.broker import flags\n",
    "from ofo.broker import kite_flags\n", "from ofo.broker.kite_flags import load_zerodha_flags as f\n",
    "from . import flags\n", "import ofo.broker.kite_flags\n", "def f():\n    from ofo.broker import flags\n",
])
def test_ac5_the_import_scan_sees_every_import_shape(planted: str) -> None:
    """AC-5: each import shape a gate could use to reach a flag is found (the scan itself dies without its rules)."""
    assert _flag_imports(planted), planted
    assert _flag_imports("import os\nfrom ofo.errors import render\n") == []


def test_ac5_a_gate_file_that_does_not_parse_fails_the_scan() -> None:
    """AC-5 / standing item (c): unparsable source raises, it is never read as clean."""
    with pytest.raises(SyntaxError):
        _flag_imports("def f(:\n")
