"""W-122 (REQ-109 AC-1, AC-2): paper tracking and the order path never import each other, in either direction.
No database needed."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_ac1_the_tracking_modules_import_nothing_from_the_order_path():
    """AC-1 (structural): the tracking route, store and domain import no execute/execution/basket module."""
    for path in (ROOT / "backend/ofo_app/routes/tracking.py", ROOT / "backend/ofo_app/tracking_store.py",
                 ROOT / "backend/ofo/tracking/paper.py"):
        imports = [line for line in path.read_text(encoding="utf-8").splitlines()
                   if line.startswith(("import ", "from "))]
        assert not [line for line in imports if "execut" in line or "basket" in line or "orders" in line], path


ORDER_PATH = ("backend/ofo/execution", "backend/ofo/orders", "backend/ofo_app/basket_post.py",
              "backend/ofo_app/checked_basket.py", "backend/ofo_app/execute_plan.py")


def test_ac1_no_order_path_module_imports_the_tracking_code():
    """REQ-109 AC-1/AC-2 (no account-wide switch, paper never mixed with real): the reverse direction - no module of
    the order path (execution, orders, the basket and execute-plan modules) imports ofo.tracking or
    ofo_app.tracking_store, so a paper entry cannot be read into an order. Every listed path must exist (a renamed
    module fails here, never passes silently)."""
    files = []
    for name in ORDER_PATH:
        path = ROOT / name
        assert path.exists(), path
        files += sorted(path.rglob("*.py")) if path.is_dir() else [path]
    offenders = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            names_tracking = "ofo.tracking" in stripped or "tracking_store" in stripped
            if stripped.startswith(("import ", "from ")) and names_tracking:
                offenders.append(f"{path.relative_to(ROOT)}: {stripped}")
    assert offenders == []
    assert len(files) > len(ORDER_PATH)  # the directories really held modules
